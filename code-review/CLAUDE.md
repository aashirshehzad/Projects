# CLAUDE.md - Hybrid Code Auditor

Project-specific guidance for Claude Code working in `code-review/`.

## What this is

A two-stage code auditor: a deterministic `ast` scanner (Stage 1-2, rules
SEC-001..SEC-010) feeds a single structured-output LLM call (Stage 3) that
triages findings and writes patches; results dispatch to console / GitHub PR /
SARIF / PDF (Stage 4). Original spec: `hybrid_code_auditor_implementation_plan.pdf`
in Downloads (covers SEC-001..005; 006-010 added later).

## Non-negotiables

- **The AST layer must stay deterministic and hallucination-free.** No network,
  no subprocess (except `git` in `diff_parser.py`), no heuristics that guess. If
  a pattern can't be proven from the AST, it isn't a rule. The only networked
  stage is `app/deps/` (OSV.dev, opt-in via `--deps`); keep network there.
- **Two engines, each with its own parser and rule set, sharing one `Violation`
  type.** Python (`app/static_scanner/`, `ast.parse`, rules SEC-*) and
  JavaScript/TypeScript (`app/js_scanner/`, `tree-sitter`, rules JS-*).
  `static_scanner/notebook.py` reassembles a notebook's code cells into a
  virtual Python source (markdown + magics stripped/blanked, line count
  preserved) so `scan_source` runs completely unmodified on it; the engine
  tags each finding with `(notebook cell N)`. Adding a **third** language is
  the same shape as JS: its own parser + rule module producing `Violation`s --
  never branches bolted onto an existing engine. C/C++/Java are not planned;
  raise it explicitly before starting one, it's a multi-day subsystem.
- **`app/static_scanner/engine.py` imports `app.js_scanner` lazily** (inside
  `_js()`, called only when a scan actually runs), not at module top level.
  Importing it eagerly reintroduces a real circular import: `app.js_scanner`
  needs `app.static_scanner.ast_rules`, which -- the first time anything
  touches the `static_scanner` package -- can re-enter `engine.py` before it
  has finished defining itself. If you add a third language engine, wire it
  in the same lazy way.
- **The LLM sees snippets, never whole files.** Keep `build_user_prompt` lean;
  every token added there multiplies over every violation on every PR.
- **One LLM call per run.** No agent loop, no tool-calling. A provider
  (`app/llm_remediation/providers.py`) makes exactly one structured-output
  request bound to `AuditRemediationReport`. Default backend is Gemini
  (`gemini-3.5-flash-lite`); `AUDITOR_LLM_PROVIDER=openai` switches to
  `chat.completions.parse`. Add backends as new `providers.py` classes, never as
  branches inside `remediator.py`.
- **Rule IDs are an API.** SEC-001..SEC-005 appear in SARIF, PR comments and
  tests. Renumbering is a breaking change; add SEC-006+ instead.

## Conventions

- Python 3.11+, standard library `ast`, `from __future__ import annotations`.
- Config only through `app.core.config.Settings` (pydantic-settings, `AUDITOR_`
  prefix; `GEMINI_API_KEY` / `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `GITHUB_*` are
  un-prefixed aliases). `require_llm_key()` picks the key for the active provider.
- Errors are `app.core.exceptions.AuditorError` subclasses; the CLI maps them to
  exit code 2. Findings are exit code 1. Clean is 0.
- Reporters (`app/reporter/`) consume a plain dict payload (`pdf.payload_from_scan`)
  or `ScanResult` + `AuditRemediationReport`; the web `/api/report.pdf` renders
  the same payload the browser already holds, so no re-scan.
- Every new rule needs: an entry in `RULES`, a `visit_*` branch (Python) or a
  `_check_*` handler in `_DISPATCH` (JS), a vulnerable and a clean fixture line,
  and a `test_individual_patterns` / `test_safe_patterns` case.
- Suppression is honoured in `scan_source`: `# nosec` (all rules) / `# nosec SEC-00X`
  / `# noqa: SEC-00X` (named only). Project config is `RuleConfig` from
  `[tool.code-auditor]` in pyproject (disabled_rules + severity overrides);
  `scan_source`/`scan_path` take a duck-typed `config=`. Baselines
  (`static_scanner/baseline.py`) fingerprint `rule_id + path + offending line`
  and are applied by the CLI after the scan, before remediation.
- `static_scanner/taint.py` is a deterministic, flow-insensitive, single-function
  taint pass (source list + assignment fixpoint, no cross-function/aliasing). It
  is *additive only*: every syntactic finding still fires; taint just adds
  `Violation.tainted` + a severity floor of HIGH, and enables the SEC-002
  "query built earlier" catch. Never let it suppress a finding.
- `app/deps/` (OSV) is the one networked stage, opt-in via `--deps`. Dependency
  hits are `DEP-001` `Violation`s; Stage 3 (`_code_violations` in main.py) skips
  `DEP-*`.

## Commands

```bash
pytest                         # must stay green and offline
python -m app.main audit . --no-llm
python -m app.main diff origin/main --ci-mode --fail-on HIGH
```

## Watch out

- `tests/` run with no API key and no network - keep it that way (inject a fake
  client via `Remediator(client=...)`).
- `diff` depends on `git merge-base <base>...HEAD`; shallow checkouts need
  `fetch-depth: 0`.
- GitHub Actions only runs workflows at the repo root; `pr_audit.yml` here is a
  template that must be moved up in the monorepo.
