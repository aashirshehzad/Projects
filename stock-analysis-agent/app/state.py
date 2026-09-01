"""
Pydantic state schema for the stock-analysis LangGraph workflow.

The schema flows through three stages:
  1. Agent 1 (Quantitative) populates `historical_data`
  2. Agent 2 (Fundamental)  populates `fundamental_report` + `fundamental_highlights`
  3. Agent 3 (Decision)     populates `final_decision`
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


class PricePoint(BaseModel):
    """One trading day inside the analysis window: close plus the two MAs."""

    date: str = Field(..., description="ISO trading date.")
    close: float = Field(..., description="Adjusted close price in USD.")
    ma_50: Optional[float] = Field(
        None, description="50-day SMA at this date (None until 50 sessions exist)."
    )
    ma_200: Optional[float] = Field(
        None, description="200-day SMA at this date (None until 200 sessions exist)."
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
        ..., description="Number of trading days in the analysis window."
    )
    price_history: list[PricePoint] = Field(
        default_factory=list,
        description=(
            "Per-day close + MA-50 + MA-200 over the analysis window, oldest "
            "first. Powers the price chart in the dashboard."
        ),
    )


class TickerError(BaseModel):
    """A ticker that an agent could not process, with the reason why."""

    ticker: str = Field(..., description="Stock ticker symbol that failed.")
    error: str = Field(
        ..., description="Human-readable reason the ticker could not be processed."
    )


# ── per-ticker highlights produced by Agent 2 ──────────────────────────────────

class FundamentalHighlights(BaseModel):
    """Key figures pulled from a company's most recent SEC 10-Q / 10-K filing."""

    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL.")
    cik: Optional[str] = Field(
        None, description="Zero-padded 10-digit SEC Central Index Key."
    )
    form_type: Optional[str] = Field(
        None, description='Filing form type — "10-Q" or "10-K".'
    )
    filing_date: Optional[str] = Field(
        None, description="ISO date the filing was submitted to EDGAR."
    )
    period_of_report: Optional[str] = Field(
        None, description="ISO end date of the fiscal period the filing covers."
    )
    filing_url: Optional[str] = Field(
        None, description="URL of the primary filing document on sec.gov."
    )
    revenue: Optional[float] = Field(
        None, description="Most recent reported total revenue / net sales, in USD."
    )
    net_income: Optional[float] = Field(
        None, description="Most recent reported net income (loss), in USD."
    )
    forward_guidance: Optional[str] = Field(
        None,
        description=(
            "Short narrative excerpt of forward-looking guidance / outlook "
            "found in the filing text, if any."
        ),
    )
    notes: Optional[str] = Field(
        None,
        description="Why a field is missing, or other caveats about the data.",
    )


# ── top-level workflow state ─────────────────────────────────────────────────

class StockAnalysisState(BaseModel):
    """
    Shared state object that travels through the LangGraph workflow.

    Each agent reads what it needs and writes to its designated field,
    keeping the pipeline loosely coupled.
    """

    tickers: list[str] = Field(
        default_factory=lambda: ["AAPL", "NVDA", "MSFT"],
        description="List of ticker symbols to analyse.",
    )
    historical_data: list[TickerSummary] = Field(
        default_factory=list,
        description=(
            "Quantitative summaries produced by Agent 1 (one entry per "
            "successfully processed ticker)."
        ),
    )
    failed_tickers: list[TickerError] = Field(
        default_factory=list,
        description=(
            "Tickers that could not be processed, with the reason for each. "
            "A non-empty list means the analysis is partial."
        ),
    )
    fundamental_report: Optional[str] = Field(
        None,
        description=(
            "Concise narrative fundamental-analysis report produced by Agent 2. "
            "Each run appends its text block to whatever is already here."
        ),
    )
    fundamental_highlights: list[FundamentalHighlights] = Field(
        default_factory=list,
        description=(
            "Structured per-ticker figures (revenue, net income, guidance) "
            "that back `fundamental_report`."
        ),
    )
    final_decision: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "Final investment decision produced by Agent 3: a dict with a strict "
            '`recommendation` ("Buy" / "Sell" / "Hold"), a bulleted `thesis` list, '
            "and `model` / `generated_at` / `raw_response` metadata (or an `error` "
            "key when the LLM call could not be made)."
        ),
    )
