# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI service wrapping a **LangGraph** multi-agent pipeline that analyses a list of
stock tickers. All three agents are implemented.

- **Agent 1 – quantitative** (`app/agent_quantitative.py`): price metrics via `yfinance`.
- **Agent 2 – fundamental** (`app/agent_fundamental.py`): 10-Q/10-K highlights via the
  free public **SEC EDGAR REST API** (`data.sec.gov`) over stdlib `urllib`. The paid
  `sec-api` package is deliberately not used.
- **Agent 3 – decision** (`app/graph.py`, alongside the graph wiring): feeds Agent 1's
  `historical_data` and Agent 2's `fundamental_report` into a single **Google Gemini**
  `generate_content` call (`google-genai` SDK, JSON mode + `response_schema`) and writes
  `StockAnalysisState.final_decision` — a dict with a strict `recommendation`
  (`"Buy"` / `"Sell"` / `"Hold"`), a bulleted `thesis`, plus
  `model` / `generated_at` / `raw_response`. Needs the `google-genai` package and
  `GEMINI_API_KEY` (or `GOOGLE_API_KEY`); without either it degrades to a conservative
  `"Hold"` carrying an `error` note rather than raising. `_parse_decision` stays as a
  defensive backstop around the model output.

## Environment & commands

Python runs in the conda env `stockproject`
(`C:\Users\Aashir\anaconda3\envs\stockproject\python.exe`).

```bash
pip install -r requirements.txt

# Config comes from a .env file at the repo root (auto-loaded in app/__init__.py
# via python-dotenv; real shell env vars still win). Bootstrap it with:
cp .env.example .env      # then fill in GEMINI_API_KEY

# Run the API. CWD must be this directory (imports are `from app.xxx`),
# or set PYTHONPATH to the repo root.
uvicorn app.main:app --reload
```

Environment variables (all settable via `.env`):

| Var | Agent | Required? | Notes |
|-----|-------|-----------|-------|
| `GEMINI_API_KEY` | 3 | **yes** (only real key) | Google Gemini auth (`GOOGLE_API_KEY` also accepted). Free key at aistudio.google.com/apikey. Without it Agent 3 returns a `"Hold"` carrying an `error`. |
| `DECISION_MODEL` | 3 | no | default `gemini-3.5-flash-lite` — set to whatever string Google AI Studio lists |
| `DECISION_MAX_TOKENS` | 3 | no | default `2048` |
| `SEC_EDGAR_USER_AGENT` | 2 | recommended | contact email string; EDGAR 403s without it. Not a key. |
| `SEC_EDGAR_TIMEOUT` | 2 | no | default `20` (seconds) |

No build step, and no linter/formatter/test runner is installed in the env. The only
static tooling is type checking via `pyrightconfig.json`, consumed by the editor
(Pylance); run it manually with `npx pyright` if needed.

There is **no test suite** (no pytest, no `tests/`). Verification so far has been ad hoc:
run `uvicorn` and `curl`, or import and invoke directly, e.g.

```bash
PYTHONPATH=. python -c "from app.graph import graph; from app.state import StockAnalysisState; \
print(graph.invoke(StockAnalysisState(tickers=['AAPL']).model_dump()))"
```

Endpoints: `GET /` (dashboard UI), `GET /health`, `POST /analyze` (full graph),
`POST /analyze/quantitative`, `POST /analyze/fundamental`. Request body:
`{"tickers": ["AAPL", "NVDA", "MSFT"]}` (optional; that list is the default). Non-US
symbols work in Agent 1 via their yfinance suffix (e.g. `005930.KS` for Samsung), but
Agent 2 is SEC-only and returns a `notes` explaining the miss for anything not on EDGAR.

**Dashboard.** `GET /` serves `app/static/index.html` verbatim (via `FileResponse`) — a
single, dependency-free page (inline CSS/JS; Chart.js from a CDN). It POSTs to `/analyze`
and renders the Buy/Sell/Hold card + thesis, a metrics table, a returns bar chart, and a
per-ticker price line chart (close + MA-50 + MA-200) built from `TickerSummary.price_history`.
No build step; edit the HTML and reload.

## Architecture

**Shared state.** `app/state.py` defines `StockAnalysisState` (Pydantic), the single
object threaded through the graph. Each agent reads only what it needs (usually just
`tickers`) and writes exactly one output field:
`historical_data` (Agent 1), `fundamental_report` + `fundamental_highlights` (Agent 2),
`final_decision` (Agent 3). `failed_tickers` collects Agent 1 per-ticker errors.

**Pydantic ↔ dict bridge.** `app/graph.py` builds `StateGraph(GraphState)` where
`GraphState` is a `TypedDict` mirroring `StockAnalysisState` — one channel per field, so
the two parallel agents can write concurrently (a bare `StateGraph(dict)` keeps the whole
mapping in one channel and rejects two writes per superstep). LangGraph runs on the dict;
the agents are typed on `StockAnalysisState`. Every node is a thin wrapper (`_quant_node`,
`_fundamental_node`, `_decision_node`) that does `StockAnalysisState(**state)` → call the
agent → `result.model_dump(include={...its own fields...})`. The `include=` is load-bearing
under parallelism: a full `model_dump()` from two concurrent nodes collides on `tickers`
and every other shared field. Keep this pattern when adding nodes; do not push Pydantic
models into the graph directly. Topology today (Agent 1 ∥ Agent 2, both joined into
Agent 3):
`START → {quantitative_agent, fundamental_agent} → decision_agent → END`.

`run_analysis(tickers)` in the same file is the one entry point `main.py` calls: it owns
the `StockAnalysisState` → `invoke` → `StockAnalysisState` round-trip.

**Agent contract.** An agent is a pure function `(StockAnalysisState) -> StockAnalysisState`
that returns `state.model_copy(update={...})` touching only its own field. Per-item
failures are caught and recorded in a state field (`failed_tickers`, or a `notes` string
on the per-ticker highlights model) — an agent never raises past its own loop, so one bad
ticker can't abort the run. `main.py` surfaces this as `status: "partial_success"`.

**Blocking I/O.** `graph.invoke`, `yfinance`, EDGAR, and the Gemini `generate_content`
call in Agent 3 are all synchronous network I/O. The heavy routes in `app/main.py` are
therefore declared `def`, not `async def`, so FastAPI runs them in a worker threadpool
instead of stalling the event loop. Keep new analysis routes sync.

**Agent 1 detail.** Fetches a 6-month analysis window *plus* ~300 extra calendar days of
look-back. Moving averages (50/200-day) are computed on the full series; return, period
dates, `data_points`, and the emitted `price_history` (per-day close + MA-50 + MA-200,
which powers the dashboard's price chart) all come from the trailing 6-month slice only.

**Agent 2 detail.** `extract_financial_highlights(text)` regex-scrapes revenue, net income,
and forward-guidance prose from stripped filing HTML (best-effort, scaled by an
"in millions/thousands" hint). Revenue and net income are then overridden with
authoritative XBRL `companyconcept` facts, anchored to the filing's `period_of_report`
and picking the shortest-duration (discrete quarter, not YTD) value; revenue takes the
largest value across candidate us-gaap tags. `fundamental_report` is a text block that is
**appended** to, not replaced. Tickers with no EDGAR registration (e.g. `SSNLF`) come back
with `notes` explaining why, not an error.

## Repo notes

- This directory is one project inside a larger multi-project git repo rooted at
  `D:\Projects`. `git log` / `git status` show sibling projects too; scope changes here.
- `app/__pycache__/*.pyc` is currently tracked and there is no `.gitignore`.
