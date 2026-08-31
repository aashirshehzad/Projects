"""
FastAPI server for the Stock Analysis Agent.

Endpoints
─────────
GET  /health              →  liveness probe
POST /analyze             →  run the full LangGraph workflow
POST /analyze/quantitative →  run only Agent 1 (quantitative)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.agent_quantitative import quantitative_agent
from app.graph import graph
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
        "Agent 1 performs quantitative analysis using yfinance."
    ),
    version="0.1.0",
)


# ── request / response models ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    tickers: list[str] = Field(
        default=["AAPL", "NVDA", "SSNLF"],
        description="Stock ticker symbols to analyse.",
    )


class AnalyzeResponse(BaseModel):
    status: str = "success"
    state: StockAnalysisState


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest | None = None):
    """Run the **full** LangGraph workflow and return the final state."""
    tickers = request.tickers if request else ["AAPL", "NVDA", "SSNLF"]
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Starting full workflow for %s", tickers)
        result = graph.invoke(initial_state.model_dump())
        final_state = StockAnalysisState(**result)
        return AnalyzeResponse(state=final_state)
    except Exception as exc:
        logger.exception("Workflow failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/analyze/quantitative", response_model=AnalyzeResponse)
async def analyze_quantitative(request: AnalyzeRequest | None = None):
    """Run **only** Agent 1 (quantitative) outside the graph for quick testing."""
    tickers = request.tickers if request else ["AAPL", "NVDA", "SSNLF"]
    initial_state = StockAnalysisState(tickers=tickers)

    try:
        logger.info("Running quantitative agent for %s", tickers)
        result_state = quantitative_agent(initial_state)
        return AnalyzeResponse(state=result_state)
    except Exception as exc:
        logger.exception("Quantitative agent failed")
        raise HTTPException(status_code=500, detail=str(exc))
