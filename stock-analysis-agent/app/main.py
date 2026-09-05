"""
FastAPI server for the Stock Analysis Agent.

Endpoints
─────────
GET  /                     →  dashboard (static single-page UI)
GET  /health               →  liveness probe
GET  /api/quote            →  cheap last-price quotes for live polling
POST /analyze              →  run the full LangGraph workflow
POST /analyze/quantitative →  run only Agent 1 (quantitative)
POST /analyze/fundamental  →  run only Agent 2 (fundamental)
POST /analyze/news         →  run only Agent 2.5 (news / Tavily)
POST /api/analyze-indicator →  one-shot Gemini Buy/Sell/Hold read on a single
                               indicator value (dashboard Insight Card)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent_fundamental import fundamental_agent
from app.agent_news import news_agent
from app.agent_quantitative import quantitative_agent
from app.graph import run_analysis
from app.indicator_insight import analyze_indicator
from app.quotes import get_quotes, market_is_open
from app.state import (
    DEFAULT_TICKERS,
    DEFAULT_TIMEFRAME,
    StockAnalysisState,
    Timeframe,
)

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-7s │ %(message)s",
)
logger = logging.getLogger(__name__)

# ── app ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Stock Analysis Agent",
    description=(
        "Multi-agent stock analysis pipeline powered by LangGraph. "
        "Agent 1 performs quantitative analysis using yfinance; "
        "Agent 2 performs fundamental analysis using SEC EDGAR filings."
    ),
    version="0.1.0",
)

_STATIC_DIR = Path(__file__).parent / "static"


# ── request / response models ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TICKERS),
        description="Stock ticker symbols to analyse.",
    )
    timeframe: Timeframe = Field(
        DEFAULT_TIMEFRAME,
        description="Chart timeframe for Agent 1 price history: 1D/5D/1M/6M/1Y/ALL.",
    )


class AnalyzeResponse(BaseModel):
    status: str = "success"
    state: StockAnalysisState


class IndicatorInsightRequest(BaseModel):
    ticker: str = Field(..., description="Ticker the indicator belongs to, e.g. AAPL.")
    indicator_name: str = Field(
        ..., description='Human label, e.g. "14-day RSI", "MACD (12/26/9)".'
    )
    current_value: float | dict | str = Field(
        ...,
        description=(
            "Latest indicator reading — a number for scalar indicators, or a "
            "{macd_line, signal_line, macd_histogram} object for MACD."
        ),
    )
    current_price: float = Field(
        ...,
        description=(
            "Latest close price for the ticker, so the model can judge the "
            "indicator relative to price (above/below MA, crossover, etc.)."
        ),
    )


class IndicatorInsightResponse(BaseModel):
    ticker: str
    indicator_name: str
    insight: str = Field(
        ..., description="Two-sentence Buy/Sell/Hold read, or a degradation notice."
    )


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def dashboard():
    """Serve the single-page dashboard UI."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/quote")
def quote(tickers: str = ""):
    """
    Cheap last-price quotes for the dashboard's 10-second polling loop.

    ``?tickers=AAPL,NVDA`` (comma-separated); empty → the default basket.
    Returns ``{market_open, quotes: [{ticker, price, previous_close, change,
    change_pct} | {ticker, price: null, error}]}``. Sync ``def`` — yfinance is
    blocking — and never 500s.
    """
    syms = [s.strip().upper() for s in tickers.split(",") if s.strip()] or list(
        DEFAULT_TICKERS
    )
    return {"market_open": market_is_open(), "quotes": get_quotes(syms)}


def _response_status(state: StockAnalysisState) -> str:
    """`"success"` unless a ticker failed or Agent 3 degraded → `"partial_success"`."""
    decision_failed = bool(state.final_decision and state.final_decision.error)
    return "partial_success" if (state.failed_tickers or decision_failed) else "success"


# NOTE: these routes are declared ``def`` (not ``async def``) on purpose.
# ``graph.invoke`` and yfinance perform blocking network I/O; running them in a
# coroutine would stall the event loop for the whole process. As sync routes,
# FastAPI runs them in a worker threadpool instead.

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest | None = None):
    """
    Run the **full** LangGraph workflow (Agent 1 ∥ Agent 2 → Agent 3) and
    return the final state, including ``final_decision``.
    """
    tickers = request.tickers if request else list(DEFAULT_TICKERS)
    timeframe = request.timeframe if request else DEFAULT_TIMEFRAME

    try:
        logger.info("Starting full workflow for %s [%s]", tickers, timeframe)
        final_state = run_analysis(tickers, timeframe)
        return AnalyzeResponse(status=_response_status(final_state), state=final_state)
    except Exception as exc:
        logger.exception("Workflow failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/quantitative", response_model=AnalyzeResponse)
def analyze_quantitative(request: AnalyzeRequest | None = None):
    """
    Run **only** Agent 1 (quantitative). This is the endpoint the dashboard's
    timeframe bar hits — cheap, no LLM, honours ``timeframe``.
    """
    tickers = request.tickers if request else list(DEFAULT_TICKERS)
    timeframe = request.timeframe if request else DEFAULT_TIMEFRAME
    initial_state = StockAnalysisState(tickers=tickers, timeframe=timeframe)

    try:
        logger.info("Running quantitative agent for %s [%s]", tickers, timeframe)
        result_state = quantitative_agent(initial_state)
        return AnalyzeResponse(status=_response_status(result_state), state=result_state)
    except Exception as exc:
        logger.exception("Quantitative agent failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/fundamental", response_model=AnalyzeResponse)
def analyze_fundamental(request: AnalyzeRequest | None = None):
    """Run **only** Agent 2 (fundamental) outside the graph for quick testing."""
    tickers = request.tickers if request else list(DEFAULT_TICKERS)
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Running fundamental agent for %s", tickers)
        result_state = fundamental_agent(initial_state)
        return AnalyzeResponse(status=_response_status(result_state), state=result_state)
    except Exception as exc:
        logger.exception("Fundamental agent failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/analyze-indicator", response_model=IndicatorInsightResponse)
def analyze_indicator_endpoint(request: IndicatorInsightRequest):
    """
    Runtime, single-indicator AI insight for the dashboard's Insight Card.

    One Gemini call: given a ticker + an indicator's latest value, return a
    strict two-sentence Buy/Sell/Hold read. ``analyze_indicator`` never raises —
    a missing key or API error comes back as an ``"Insight unavailable: …"``
    string in ``insight`` with a 200 status, so the card always has something
    to show.
    """
    logger.info(
        "Indicator insight: %s / %s", request.ticker, request.indicator_name
    )
    insight = analyze_indicator(
        ticker=request.ticker,
        indicator_name=request.indicator_name,
        current_value=request.current_value,
        current_price=request.current_price,
    )
    return IndicatorInsightResponse(
        ticker=request.ticker,
        indicator_name=request.indicator_name,
        insight=insight,
    )


@app.post("/analyze/news", response_model=AnalyzeResponse)
def analyze_news(request: AnalyzeRequest | None = None):
    """Run **only** Agent 2.5 (news / Tavily) outside the graph for quick testing."""
    tickers = request.tickers if request else list(DEFAULT_TICKERS)
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Running news agent for %s", tickers)
        result_state = news_agent(initial_state)
        return AnalyzeResponse(status=_response_status(result_state), state=result_state)
    except Exception as exc:
        logger.exception("News agent failed")
        raise HTTPException(status_code=500, detail=str(exc))
