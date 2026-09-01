"""
FastAPI server for the Stock Analysis Agent.

Endpoints
─────────
GET  /                     →  dashboard (static single-page UI)
GET  /health               →  liveness probe
POST /analyze              →  run the full LangGraph workflow
POST /analyze/quantitative →  run only Agent 1 (quantitative)
POST /analyze/fundamental  →  run only Agent 2 (fundamental)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent_fundamental import fundamental_agent
from app.agent_quantitative import quantitative_agent
from app.graph import run_analysis
from app.state import StockAnalysisState

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
        default=["AAPL", "NVDA", "MSFT"],
        description="Stock ticker symbols to analyse.",
    )


class AnalyzeResponse(BaseModel):
    status: str = "success"
    state: StockAnalysisState


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def dashboard():
    """Serve the single-page dashboard UI."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


def _response_status(state: StockAnalysisState) -> str:
    """`"success"` unless some tickers failed, in which case `"partial_success"`."""
    return "partial_success" if state.failed_tickers else "success"


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
    tickers = request.tickers if request else ["AAPL", "NVDA", "MSFT"]

    try:
        logger.info("Starting full workflow for %s", tickers)
        final_state = run_analysis(tickers)
        return AnalyzeResponse(status=_response_status(final_state), state=final_state)
    except Exception as exc:
        logger.exception("Workflow failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/quantitative", response_model=AnalyzeResponse)
def analyze_quantitative(request: AnalyzeRequest | None = None):
    """Run **only** Agent 1 (quantitative) outside the graph for quick testing."""
    tickers = request.tickers if request else ["AAPL", "NVDA", "MSFT"]
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Running quantitative agent for %s", tickers)
        result_state = quantitative_agent(initial_state)
        return AnalyzeResponse(status=_response_status(result_state), state=result_state)
    except Exception as exc:
        logger.exception("Quantitative agent failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/fundamental", response_model=AnalyzeResponse)
def analyze_fundamental(request: AnalyzeRequest | None = None):
    """Run **only** Agent 2 (fundamental) outside the graph for quick testing."""
    tickers = request.tickers if request else ["AAPL", "NVDA", "MSFT"]
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Running fundamental agent for %s", tickers)
        result_state = fundamental_agent(initial_state)
        return AnalyzeResponse(status=_response_status(result_state), state=result_state)
    except Exception as exc:
        logger.exception("Fundamental agent failed")
        raise HTTPException(status_code=500, detail=str(exc))
