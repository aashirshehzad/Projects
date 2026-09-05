# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI service wrapping a **LangGraph** multi-agent pipeline that analyses a list of
stock tickers. Four agents; the first three run in parallel.

- **Agent 1 – quantitative** (`app/agent_quantitative.py`): price metrics via `yfinance`.
- **Agent 2 – fundamental** (`app/agent_fundamental.py`): 10-Q/10-K highlights via the
  free public **SEC EDGAR REST API** (`data.sec.gov`) over stdlib `urllib`. The paid
  `sec-api` package is deliberately not used.
- **Agent 2.5 – news** (`app/agent_news.py`): recent dated headlines per ticker via the
  **Tavily** search API (`topic="news"`, ~180-day window), written to
  `StockAnalysisState.news_context` so Agent 3 can cite real catalysts. Needs
  `TAVILY_API_KEY`; without it (or without `tavily-python`) the node no-ops and every
  ticker comes back with a `notes` string.
- **Agent 3 – decision** (`app/graph.py`, alongside the graph wiring): feeds Agent 1's
  `historical_data`, Agent 2's `fundamental_report` and Agent 2.5's `news_context` into a
  **Google Gemini** `generate_content` call (`google-genai` SDK, JSON mode +
  `response_schema=_LlmDecision`) plus an internal reflection/critic step, and writes
  `StockAnalysisState.final_decision` — a `DecisionReport` (typed model in `state.py`)
  holding one `TickerReport` per symbol: `recommendation` (`Buy`/`Sell`/`Hold`),
  `executive_thesis` prose, a dated `catalyst_timeline` (`NewsCatalyst[]`), a
  bull/base/bear `scenarios` matrix (`Scenario[]` with `invalidation_trigger`),
  `downside_risks`, plus basket-level `cross_cutting_risks`, `critic_notes` and
  `model`/`generated_at`/`raw_response`. Needs the `google-genai` package and
  `GEMINI_API_KEY` (or `GOOGLE_API_KEY`); without either — or on an API/parse error — it
  degrades to one `Hold` `TickerReport` per ticker with an `error` note, never raising.
  `DECISION_CRITIC_PASSES` (0–2) adds explicit "audit your draft" round-trips.

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
| `GEMINI_API_KEY` | 3 | **yes** | Google Gemini auth (`GOOGLE_API_KEY` also accepted). Free key at aistudio.google.com/apikey. Without it Agent 3 degrades. |
| `TAVILY_API_KEY` | 2.5 | recommended | Tavily search auth. Free key at tavily.com. Without it Agent 2.5 no-ops and Agent 3 has no catalysts to cite. |
| `DECISION_MODEL` | 3 | no | default `gemini-3.5-flash-lite` — set to whatever string Google AI Studio lists |
| `DECISION_MAX_TOKENS` | 3 | no | default `10000` (per-ticker reports are large) |
| `DECISION_CRITIC_PASSES` | 3 | no | default `0`; `1`–`2` extra critic/revise round-trips |
| `NEWS_MAX_RESULTS` / `NEWS_LOOKBACK_DAYS` | 2.5 | no | default `8` / `180` |
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

The analysis routes take a request body of `{"tickers": [...]}` (optional; the
default basket is `DEFAULT_TICKERS` in `app/state.py` — a deliberately high-beta
set: AAPL, NVDA, MSFT, TSLA, SMCI, AMD, MRNA, WOLF, ASTS, MARA, CVNA, so the
gap-handling paths stay exercised — a full default run is therefore long). Non-US
symbols work in Agent 1 via their yfinance suffix (e.g. `005930.KS` for Samsung), but
Agent 2 is SEC-only and returns a `notes` explaining the miss for anything not on EDGAR.
A full run is ~40–90s (EDGAR is the slow leg; Gemini is one call).

Dashboard guidance lives in `app/static/CLAUDE.md` (loads when working under that dir).

## Architecture

**Shared state.** `app/state.py` defines `StockAnalysisState` (Pydantic), the single
object threaded through the graph. Each agent reads only what it needs (usually just
`tickers`) and writes exactly one output field: `historical_data` (Agent 1),
`fundamental_report` + `fundamental_highlights` (Agent 2), `news_context` (Agent 2.5),
`final_decision` — a `DecisionReport` (Agent 3). `failed_tickers` collects Agent 1
per-ticker errors.

**Pydantic ↔ dict bridge.** `app/graph.py` builds `StateGraph(GraphState)` where
`GraphState` is a `TypedDict` mirroring `StockAnalysisState` — one channel per field, so
the parallel agents can write concurrently (a bare `StateGraph(dict)` keeps the whole
mapping in one channel and rejects two writes per superstep). LangGraph runs on the dict;
the agents are typed on `StockAnalysisState`. Every node is a thin wrapper (`_quant_node`,
`_fundamental_node`, `_news_node`, `_decision_node`) that does `StockAnalysisState(**state)`
→ call the agent → `result.model_dump(include={...its own fields...})`. The `include=` is
load-bearing under parallelism: a full `model_dump()` from concurrent nodes collides on
`tickers` and every other shared field. Keep this pattern when adding nodes; do not push
Pydantic models into the graph directly. Topology today (Agents 1, 2 and 2.5 in parallel,
all joined into Agent 3):
`START → {quantitative_agent, fundamental_agent, news_agent} → decision_agent → END`.

`run_analysis(tickers)` in the same file is the one entry point `main.py` calls: it owns
the `StockAnalysisState` → `invoke` → `StockAnalysisState` round-trip.

**Agent contract.** An agent is a pure function `(StockAnalysisState) -> StockAnalysisState`
that returns `state.model_copy(update={...})` touching only its own field. Per-item
failures are caught and recorded in a state field (`failed_tickers`, a `notes` string on
the per-ticker highlights/news model, or `final_decision.error`) — an agent never raises
past its own loop, so one bad ticker or flaky call can't abort the run. `main.py`
surfaces `failed_tickers` **or** a `final_decision.error` as `status: "partial_success"`.

**Blocking I/O.** `graph.invoke`, `yfinance`, EDGAR, Tavily, and the Gemini
`generate_content` call are all synchronous network I/O. The heavy routes in `app/main.py`
are therefore declared `def`, not `async def`, so FastAPI runs them in a worker threadpool
instead of stalling the event loop. Keep new analysis routes sync.

**Agent 1 detail.** Fetches a 6-month analysis window *plus* ~300 extra calendar days of
look-back. Moving averages (50/200-day) and the 14-day Wilder RSI are computed on the full
series; return, period dates, `data_points`, and the emitted `price_history` (per-day
OHLC + MA-50 + MA-200 + RSI-14, which powers the dashboard's candlestick and RSI charts)
all come from the trailing 6-month slice only. `_rsi_series()` returns the whole RSI
series; `_compute_rsi()` is the thin scalar wrapper for `TickerSummary.rsi_14`.

**Agent 2 detail.** `extract_financial_highlights(text)` regex-scrapes revenue, net income,
and forward-guidance prose from stripped filing HTML (best-effort, scaled by an
"in millions/thousands" hint). Revenue and net income are then overridden with
authoritative XBRL `companyconcept` facts, anchored to the filing's `period_of_report`
and picking the shortest-duration (discrete quarter, not YTD) value; revenue takes the
largest value across candidate us-gaap tags. `fundamental_report` is a text block that is
**appended** to, not replaced. Tickers with no EDGAR registration (e.g. `SSNLF`) come back
with `notes` explaining why, not an error.

**Agent 2.5 detail.** One Tavily `topic="news"` query per ticker (`days=NEWS_LOOKBACK_DAYS`,
`max_results=NEWS_MAX_RESULTS`, `include_answer="basic"`). Keyword news search is noisy —
some hits come back tangential; Agent 3's prompt tells it to only build the timeline from
these headlines and to say so when a ticker has none, rather than inventing catalysts.
Tightening the query or `include_domains` is the obvious next improvement.

**Agent 3 detail.** `_SYSTEM_PROMPT` encodes the analyst persona, the three-section method
(first-principles thesis / dated catalyst attribution / bull-base-bear with invalidation
triggers) and an internal draft→critic→revise reflection step, with `critic_notes`
recording what changed. `response_schema=_LlmDecision` (a lean Pydantic model reusing
`TickerReport`) is passed straight to `google-genai`; `_parse_report` validates the reply
and falls back to a per-ticker `Hold` report on any failure. `DECISION_CRITIC_PASSES>0`
adds explicit extra revise round-trips.

## Repo notes

- This directory is one project inside a larger multi-project git repo rooted at
  `D:\Projects`. `git log` / `git status` show sibling projects too; scope changes here.
- `app/__pycache__/*.pyc` is currently tracked and there is no `.gitignore`.
