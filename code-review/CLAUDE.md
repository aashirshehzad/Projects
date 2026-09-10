# CLAUDE.md - Hybrid Code Auditor

Project-specific guidance for Claude Code working in `code-review/`.

## What this is

A two-stage code auditor: a deterministic `ast` scanner (Stage 1-2) feeds a
single structured-output LLM call (Stage 3) that triages findings and writes
patches; results dispatch to console / GitHub PR / SARIF (Stage 4). Full spec:
`hybrid_code_auditor_implementation_plan.pdf` in Downloads.

## Non-negotiables

- **The AST layer must stay deterministic and hallucination-free.** No network,
  no subprocess (except `git` in `diff_parser.py`), no heuristics that guess. If
  a pattern can't be proven from the AST, it isn't a rule.
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
- Every new rule needs: an entry in `RULES`, a `visit_*` branch, a vulnerable and
  a clean fixture line, and a `test_individual_patterns` / `test_safe_patterns`
  case.

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
