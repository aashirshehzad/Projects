"""
Pydantic state schema for the stock-analysis LangGraph workflow.

The schema flows through four stages, the first three in parallel:
  1. Agent 1   (Quantitative) populates `historical_data`
  2. Agent 2   (Fundamental)  populates `fundamental_report` + `fundamental_highlights`
  2.5 Agent 2.5 (News)         populates `news_context`
  3. Agent 3   (Decision)      populates `final_decision` (a `DecisionReport`)
"""

from __future__ import annotations

from typing import Literal, Optional

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
    rsi_14: Optional[float] = Field(
        None,
        description=(
            "14-day Relative Strength Index (Wilder's smoothing) at the latest "
            "close. >70 is conventionally overbought, <30 oversold. None when "
            "there is too little history to compute it."
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


# ── per-ticker news context produced by Agent 2.5 ──────────────────────────

class NewsItem(BaseModel):
    """One search hit: a dated headline with a source link."""

    title: str = Field(..., description="Headline text.")
    url: str = Field(..., description="Source URL.")
    published_date: Optional[str] = Field(
        None, description="Publish date as returned by the search provider, if any."
    )
    snippet: Optional[str] = Field(
        None, description="Short extract of the article body."
    )


class TickerNews(BaseModel):
    """The recent-news bundle for one ticker (Agent 2.5)."""

    ticker: str = Field(..., description="Stock ticker symbol.")
    summary: Optional[str] = Field(
        None, description="Provider-synthesised summary of the recent news, if any."
    )
    items: list[NewsItem] = Field(
        default_factory=list, description="Individual dated headlines, newest first."
    )
    notes: Optional[str] = Field(
        None, description="Why the bundle is empty / partial (no key, provider error…)."
    )


# ── Agent 3 decision report ────────────────────────────────────────────────

class NewsCatalyst(BaseModel):
    """One dated news event correlated with a price/volume reaction."""

    date: str = Field(..., description='Event date, e.g. "2026-07-30" or "April 2026".')
    headline: str = Field(..., description="The catalyst, with its source named.")
    source: str = Field("", description="Publication or URL the catalyst comes from.")
    market_reaction: str = Field(
        ..., description="Stock % move / volume spike / trend shift that followed."
    )
    causal_impact: str = Field(
        ...,
        description="Why this news produced that reaction — the specific mechanism.",
    )


class Scenario(BaseModel):
    """One leg of the bull / base / bear matrix for a ticker."""

    case: Literal["bull", "base", "bear"] = Field(..., description="Which leg.")
    probability: Optional[float] = Field(
        None, description="Analytical probability estimate, 0..1."
    )
    drivers: str = Field(..., description="What has to happen for this case.")
    invalidation_trigger: str = Field(
        ..., description="The fundamental condition that would break this case."
    )


class TickerReport(BaseModel):
    """The full three-section analysis for a single ticker."""

    ticker: str = Field(..., description="Stock ticker symbol.")
    recommendation: Literal["Buy", "Sell", "Hold"] = Field(
        ..., description="Machine-readable verdict for this ticker."
    )
    executive_thesis: str = Field(
        ...,
        description=(
            "Section 1 — deep fundamental analysis: revenue drivers, moat, unit "
            "economics, balance sheet, macro/sector alignment. Plain prose, "
            "paragraphs separated by blank lines."
        ),
    )
    catalyst_timeline: list[NewsCatalyst] = Field(
        default_factory=list,
        description="Section 2 — dated catalysts with price impact, newest first.",
    )
    scenarios: list[Scenario] = Field(
        default_factory=list,
        description="Section 3 — bull / base / bear legs with invalidation triggers.",
    )
    downside_risks: list[str] = Field(
        default_factory=list, description="Ticker-specific downside risks."
    )


class DecisionReport(BaseModel):
    """Agent 3 output: one `TickerReport` per symbol plus shared context."""

    reports: list[TickerReport] = Field(
        default_factory=list, description="One entry per analysed ticker."
    )
    cross_cutting_risks: list[str] = Field(
        default_factory=list,
        description="Risks that hit the whole basket (rates, sector rotation…).",
    )
    model: Optional[str] = Field(None, description="LLM model id that produced this.")
    generated_at: Optional[str] = Field(
        None, description="UTC ISO-8601 timestamp of generation."
    )
    critic_notes: Optional[str] = Field(
        None,
        description="What the internal reflection pass flagged and corrected.",
    )
    raw_response: Optional[str] = Field(
        None, description="Verbatim final LLM JSON (for debugging)."
    )
    error: Optional[str] = Field(
        None, description="Set when the report is a degraded fallback."
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
    news_context: list[TickerNews] = Field(
        default_factory=list,
        description=(
            "Recent dated headlines per ticker from Agent 2.5, so Agent 3 can "
            "cite real catalysts instead of guessing."
        ),
    )
    final_decision: Optional[DecisionReport] = Field(
        None,
        description=(
            "Agent 3 output: a `DecisionReport` with one three-section "
            "`TickerReport` per symbol (executive thesis, dated catalyst "
            "timeline, bull/base/bear matrix) plus `cross_cutting_risks` and "
            "run metadata. `error` is set when it is a degraded fallback."
        ),
    )
