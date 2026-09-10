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
| **3. LLM remediation** | one `chat.completions.parse` call: triage + patch + test | ~$0.0003 | ~2.5s |
| **4. Dispatch** | Rich console, GitHub PR comments, SARIF 2.1.0 | - | - |

The LLM only ever sees the +/-5 line snippet around a violation, never the file.

## Rules

| ID | Sev | Pattern |
|----|-----|---------|
| SEC-001 | CRITICAL | `eval` / `exec` / `__import__` |
| SEC-002 | HIGH | `cursor.execute()` with f-string / `%` / `.format()` |
| SEC-003 | HIGH | `key`/`secret`/`token`/`password = "<literal>"` |
| SEC-004 | CRITICAL | `pickle.loads` / `yaml.load` without `SafeLoader` |
| SEC-005 | MEDIUM | `shell=True` / `os.system()` with dynamic arguments |

## Install

```bash
cd code-review
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env   # add OPENAI_API_KEY for Stage 3
```

Python 3.11+ required.

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
- `--fail-on {CRITICAL,HIGH,MEDIUM,LOW}` - severity gate (default `MEDIUM`).
- `--ci-mode` - terse output; a violation the LLM marks as a false positive no
  longer fails the build.
- `--github-pr-comments` - post one inline comment per exploitable finding plus a
  summary comment (needs `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_PR_NUMBER`,
  `GITHUB_SHA`).
- `--sarif PATH` / `--json PATH` - machine-readable output.

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
  static_scanner/  ast_rules.py, diff_parser.py, engine.py
  llm_remediation/ schemas.py, prompts.py, remediator.py
  reporter/        console.py, github_pr.py, sarif.py
  main.py          Click CLI: audit / diff / fix
```
