"""
Pydantic state schema for the stock-analysis LangGraph workflow.

The schema flows through three stages:
  1. Agent 1 (Quantitative) populates `historical_data`
  2. Agent 2 (Fundamental)  populates `fundamental_report`  ← future
  3. Agent 3 (Decision)     populates `final_decision`      ← future
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── per-ticker summary produced by Agent 1 ──────────────────────────────────

class MovingAverages(BaseModel):
    """50-day and 200-day simple moving averages."""

    ma_50: Optional[float] = Field(
        None,
        description="50-day simple moving average of the adjusted close price.",
    )
    ma_200: Optional[float] = Field(
        None,
        description="200-day simple moving average of the adjusted close price.",
    )


class TickerSummary(BaseModel):
    """Quantitative summary for a single ticker."""

    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL.")
    period_start: str = Field(
        ..., description="ISO-formatted start date of the analysis window."
    )
    period_end: str = Field(
        ..., description="ISO-formatted end date of the analysis window."
    )
    latest_close: float = Field(
        ..., description="Most recent adjusted close price in USD."
    )
    moving_averages: MovingAverages = Field(
        default_factory=MovingAverages,
        description="50-day and 200-day simple moving averages.",
    )
    pct_return: float = Field(
        ...,
        description=(
            "Overall percentage return over the analysis window, "
            "calculated as (last_close - first_close) / first_close * 100."
        ),
    )
    data_points: int = Field(
        ..., description="Number of trading days in the fetched data."
    )


# ── top-level workflow state ─────────────────────────────────────────────────

class StockAnalysisState(BaseModel):
    """
    Shared state object that travels through the LangGraph workflow.

    Each agent reads what it needs and writes to its designated field,
    keeping the pipeline loosely coupled.
    """

    tickers: list[str] = Field(
        default_factory=lambda: ["AAPL", "NVDA", "SSNLF"],
        description="List of ticker symbols to analyse.",
    )
    historical_data: list[TickerSummary] = Field(
        default_factory=list,
        description=(
            "Quantitative summaries produced by Agent 1 (one entry per ticker)."
        ),
    )
    fundamental_report: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Fundamental analysis report produced by Agent 2. "
            "Populated in a later stage of the workflow."
        ),
    )
    final_decision: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Final investment decision produced by Agent 3. "
            "Populated in a later stage of the workflow."
        ),
    )
