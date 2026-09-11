# Hybrid Code Auditor & Remediation Engine

Deterministic AST scanning + a single structured-JSON LLM call. Built to run on
every pull request over a 100k-line codebase in a couple of seconds for a
fraction of a cent, with **zero** false positives from the detection layer.

## Why hybrid

Streaming a whole repo into an LLM agent is expensive ($10-25/scan), slow
(45-120s), and unreliable ("lost in the middle" on big files). This tool splits
the job:

| Layer | What it does | Cost | Latency |
|-------|--------------|------|---------|
| **1-2. AST engine** | `ast.NodeVisitor` rules SEC-001..SEC-005, local CPU | $0.00 | < 2s / 100k LOC |
| **3. LLM remediation** | one structured-JSON call: triage + patch + test | ~$0.0003 | ~2.5s |
| **4. Dispatch** | Rich console, GitHub PR comments, SARIF 2.1.0 | - | - |

The LLM only ever sees the +/-5 line snippet around a violation, never the file.

## Supported input

**Two engines, each deterministic, each its own rule set:**

- **Python** (`.py`, `.ipynb`) -- `app/static_scanner/`, built on the `ast`
  module. A notebook's code cells are reassembled into a virtual Python source
  before the same rules run on it (markdown + magics skipped); findings are
  tagged with the cell they came from.
- **JavaScript / TypeScript** (`.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.mts`,
  `.cts`, `.tsx`) -- `app/js_scanner/`, built on `tree-sitter`. Rules JS-001..006
  (below). JSX/TSX is parsed natively, so `dangerouslySetInnerHTML` is checked too.

Adding either language reused every reporter (console/SARIF/PDF/web) unchanged
-- both engines emit the same `Violation` type. C/C++/Java and plain-text
formats (`.md`, config files) are not scanned for vulnerabilities -- see
`app/deps/` for the one exception (dependency-manifest parsing).

## Rules

| ID | Sev | Pattern |
|----|-----|---------|
| SEC-001 | CRITICAL | `eval` / `exec` / `__import__` |
| SEC-002 | HIGH | `cursor.execute()` with f-string / `%` / `.format()` |
| SEC-003 | HIGH | `key`/`secret`/`token`/`password = "<literal>"` |
| SEC-004 | CRITICAL | `pickle.loads` / `yaml.load` without `SafeLoader` |
| SEC-005 | MEDIUM | `shell=True` / `os.system()` with dynamic arguments |
| SEC-006 | HIGH | `verify=False` / `ssl._create_unverified_context()` |
| SEC-007 | MEDIUM | `md5`/`sha1`, AES/DES **ECB** mode, `random` seeding a secret |
| SEC-008 | MEDIUM | `debug=True`, `DEBUG = True`, `ALLOWED_HOSTS = ["*"]`, `host="0.0.0.0"` |
| SEC-009 | HIGH | `allow_origins=["*"]` (HIGH with credentials), `CORS_ORIGIN_ALLOW_ALL` |
| SEC-010 | CRITICAL | `yaml.unsafe_load`, `marshal`, `torch.load`, `read_pickle`, `allow_pickle=True` |
| JS-001 | CRITICAL | `eval()`, `new Function(...)`, `setTimeout`/`setInterval` given a string |
| JS-002 | HIGH | `.innerHTML`/`.outerHTML` = dynamic value, `document.write`, `insertAdjacentHTML`, `dangerouslySetInnerHTML` |
| JS-003 | HIGH | `key`/`secret`/`token`/`password = "<literal>"` (`const`, object property, or plain assignment) |
| JS-004 | HIGH | `child_process.exec`/`execSync` with a runtime-built command |
| JS-005 | MEDIUM | `Math.random()` seeding a token/secret/session/csrf value |
| JS-006 | HIGH | `rejectUnauthorized: false`, `NODE_TLS_REJECT_UNAUTHORIZED = "0"` |

A lightweight **intra-function taint pass** (deterministic, single-file, Python
only for now) backs SEC-001/002/005: it lets SEC-002 catch a query string
assembled a few lines before `execute()`, and tags any finding whose argument
reaches request data / `sys.argv` / `os.environ` / `input()` with
`[user input]` (and bumps it to at least HIGH).

**Suppress a finding** inline with `# nosec` (Python) / `// nosec` (JS/TS) --
bare silences every rule on that line, `# nosec SEC-002` / `// nosec JS-002`
silences a named rule, `# noqa: SEC-002` / `// noqa: JS-002` requires the name.

**Per-project config** in `pyproject.toml`:

```toml
[tool.code-auditor]
disabled_rules = ["SEC-007"]

[tool.code-auditor.severity]
SEC-005 = "HIGH"
```

**Baseline** an existing codebase so CI only fails on *new* findings:

```bash
python -m app.main audit . --no-llm --baseline .auditignore --update-baseline  # once
python -m app.main audit . --baseline .auditignore                             # thereafter
```

## Install

```bash
cd code-review
pip install -e ".[dev]"          # into your Python 3.11 env (here: conda env `code-review`)
cp .env.example .env             # add GEMINI_API_KEY for Stage 3
```

Python 3.11+ required.

### Stage 3 provider

Default backend is **Google Gemini** (`gemini-3.5-flash-lite`); set `GEMINI_API_KEY`
in `.env`. To use OpenAI instead, set `AUDITOR_LLM_PROVIDER=openai`,
`AUDITOR_LLM_MODEL=gpt-4o-mini`, `OPENAI_API_KEY=...` (or pass `--provider openai`).
Both paths return the identical `AuditRemediationReport` schema.

## Usage

```bash
# Full recursive audit (static only)
python -m app.main audit path/to/project --no-llm

# Full audit with LLM triage + suggested patches + SARIF for the security tab
python -m app.main audit path/to/project --sarif audit.sarif --json report.json

# Only the lines changed vs a base branch (what CI uses)
python -m app.main diff origin/main --ci-mode --fail-on HIGH

# Triage and write patches into the working tree (prompts per hunk)
python -m app.main fix path/to/file.py --auto-apply
```

Exit codes: `0` clean, `1` findings at/above `--fail-on`, `2` operational error.

### Key flags

- `--no-llm` - Stage 1-2 only; findings are unverified and unpatched.
- `--provider {gemini,openai}` / `--model <id>` - override the Stage 3 backend.
- `--fail-on {CRITICAL,HIGH,MEDIUM,LOW}` - severity gate (default `MEDIUM`).
- `--ci-mode` - terse output; a violation the LLM marks as a false positive no
  longer fails the build.
- `--github-pr-comments` - post one inline comment per exploitable finding plus a
  summary comment (needs `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_PR_NUMBER`,
  `GITHUB_SHA`).
- `--sarif PATH` / `--json PATH` - machine-readable output.
- `--pdf PATH` - plain-language PDF report for non-technical readers (exec
  summary, severity guide, per-finding explanation + suggested fix).
- `--config PATH` - `pyproject.toml` with `[tool.code-auditor]` (default `./pyproject.toml`).
- `--baseline PATH` / `--update-baseline` - suppress pre-existing findings / (re)write the baseline.
- `--deps` - also check pinned dependencies against **OSV.dev** (needs network;
  reads `requirements*.txt`, `poetry.lock`, `Pipfile.lock`, `uv.lock`, `pyproject.toml`).
  Reported as `DEP-001` findings; a scan failure only warns, it never fails the run.

## Local web UI

`web/` is a drag-drop frontend (React + Vite) over a FastAPI wrapper: upload a
`.zip` of a Python project, get the findings, snippets, and optional Gemini
patches in the browser. Local only. See [web/README.md](web/README.md).

```bash
python -m uvicorn web.backend.main:app --port 8000    # + `npm run dev` in web/frontend
```

## CI

`.github/workflows/pr_audit.yml` runs `diff` on every PR. GitHub only executes
workflows at the repo root, so in this monorepo layout move that file to
`<repo-root>/.github/workflows/` (it already sets `working-directory: code-review`).

## Tests

```bash
pytest                     # unit + CLI, no network
pytest --cov=app           # coverage
```

`tests/fixtures/vulnerable_sample.py` carries one deliberate bug per rule;
`clean_sample.py` is the safe counterpart and must stay silent.

## Layout

```
app/
  core/            config (pydantic-settings) + domain exceptions
  static_scanner/  Python engine: ast_rules.py, diff_parser.py, engine.py,
                   notebook.py, taint.py, ruleconfig.py, baseline.py
  js_scanner/      JS/TS engine (tree-sitter): grammar.py, rules.py
  deps/            OSV.dev dependency scan: manifests.py, osv.py, scanner.py
  llm_remediation/ schemas.py, prompts.py, providers.py (gemini/openai), remediator.py
  reporter/        console.py, github_pr.py, sarif.py
  main.py          Click CLI: audit / diff / fix
```
