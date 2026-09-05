"""
Pydantic state schema for the stock-analysis LangGraph workflow.

The schema flows through four stages, the first three in parallel:
  1. Agent 1   (Quantitative) populates `historical_data`
  2. Agent 2   (Fundamental)  populates `fundamental_report` + `fundamental_highlights`
  2.5 Agent 2.5 (News)         populates `news_context`
  3. Agent 3   (Decision)      populates `final_decision` (a `DecisionReport`)
"""

from __future__ import annotations

import math
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Chart timeframes the pipeline understands (see `_TIMEFRAMES` in
# app/agent_quantitative.py for the yfinance period/interval each maps to).
Timeframe = Literal["1D", "5D", "1M", "6M", "1Y", "ALL"]
DEFAULT_TIMEFRAME: Timeframe = "6M"


# ── per-ticker summary produced by Agent 1 ──────────────────────────────────

class MovingAverages(BaseModel):
    """50-day / 200-day simple moving averages plus the 9-day & 20-day EMAs."""

    ma_50: Optional[float] = Field(
        None,
        description="50-day simple moving average of the adjusted close price.",
    )
    ma_200: Optional[float] = Field(
        None,
        description="200-day simple moving average of the adjusted close price.",
    )
    ema_9: Optional[float] = Field(
        None,
        description=(
            "9-day exponential moving average (ewm span=9, adjust=False) of the "
            "adjusted close, at the latest close. Fast short-term trend gauge; "
            "its cross with EMA-20 is a common momentum signal."
        ),
    )
    ema_20: Optional[float] = Field(
        None,
        description=(
            "20-day exponential moving average (ewm span=20, adjust=False) of "
            "the adjusted close, at the latest close. Short-term trend gauge."
        ),
    )


class MACD(BaseModel):
    """Standard MACD (12/26/9) snapshot at the latest close."""

    macd_line: Optional[float] = Field(
        None, description="EMA-12(close) − EMA-26(close) at the latest close."
    )
    signal_line: Optional[float] = Field(
        None, description="EMA-9 of the MACD line at the latest close."
    )
    macd_histogram: Optional[float] = Field(
        None,
        description=(
            "macd_line − signal_line at the latest close. Positive = bullish "
            "momentum, expanding bars = strengthening momentum."
        ),
    )

    @field_validator("*", mode="before")
    @classmethod
    def _nan_to_none(cls, v):
        if v is None:
            return None
        f = float(v)
        return f if math.isfinite(f) else None


class BollingerBands(BaseModel):
    """Bollinger Bands (SMA-20 ± 2σ) snapshot at the latest close."""

    bb_upper: Optional[float] = Field(
        None, description="Middle band + 2 × rolling std (20) at the latest close."
    )
    bb_middle: Optional[float] = Field(
        None, description="20-day SMA of close at the latest close."
    )
    bb_lower: Optional[float] = Field(
        None, description="Middle band − 2 × rolling std (20) at the latest close."
    )
    bandwidth: Optional[float] = Field(
        None,
        description=(
            "(bb_upper − bb_lower) / bb_middle — normalised band width. Low = "
            "volatility squeeze, high = expansion."
        ),
    )

    @field_validator("*", mode="before")
    @classmethod
    def _nan_to_none(cls, v):
        if v is None:
            return None
        f = float(v)
        return f if math.isfinite(f) else None


class PricePoint(BaseModel):
    """
    One trading day inside the analysis window: the full OHLC bar, share
    volume, the moving averages (MA-50 / MA-200 / EMA-9 / EMA-20), the 14-day
    RSI, the MACD (12/26/9) line / signal / histogram and the Bollinger Bands
    (SMA-20 ± 2σ) at that date. Powers the dashboard's candlestick + volume
    chart and its synchronised RSI & MACD sub-charts.
    """

    date: str = Field(..., description="ISO trading date.")
    open: float = Field(..., description="Opening price in USD.")
    high: float = Field(..., description="Intraday high in USD.")
    low: float = Field(..., description="Intraday low in USD.")
    close: float = Field(..., description="Adjusted close price in USD.")
    ma_50: Optional[float] = Field(
        None, description="50-day SMA at this date (None until 50 sessions exist)."
    )
    ma_200: Optional[float] = Field(
        None, description="200-day SMA at this date (None until 200 sessions exist)."
    )
    ema_9: Optional[float] = Field(
        None,
        description=(
            "9-day EMA (ewm span=9, adjust=False) at this date. Seeds on the "
            "first row of the underlying series, so rarely None."
        ),
    )
    ema_20: Optional[float] = Field(
        None,
        description=(
            "20-day EMA (ewm span=20, adjust=False) at this date. Seeds on the "
            "first row of the underlying series, so rarely None."
        ),
    )
    rsi_14: Optional[float] = Field(
        None,
        description=(
            "14-day Wilder RSI at this date (None for the first ~14 sessions of "
            "the underlying series). >70 overbought, <30 oversold."
        ),
    )
    macd_line: Optional[float] = Field(
        None, description="MACD line (EMA-12 − EMA-26 of close) at this date."
    )
    signal_line: Optional[float] = Field(
        None, description="Signal line (EMA-9 of the MACD line) at this date."
    )
    macd_histogram: Optional[float] = Field(
        None, description="MACD histogram (macd_line − signal_line) at this date."
    )
    bb_upper: Optional[float] = Field(
        None, description="Bollinger upper band (SMA-20 + 2σ) at this date."
    )
    bb_middle: Optional[float] = Field(
        None, description="Bollinger middle band (SMA-20 of close) at this date."
    )
    bb_lower: Optional[float] = Field(
        None, description="Bollinger lower band (SMA-20 − 2σ) at this date."
    )
    volume: Optional[int] = Field(
        None, description="Share volume for the bar (None if missing / non-finite)."
    )

    @field_validator("volume", mode="before")
    @classmethod
    def _volume_nonneg_int(cls, v):
        """Keep the field; a NaN / negative / non-finite volume becomes null."""
        if v is None:
            return None
        f = float(v)
        return int(f) if math.isfinite(f) and f >= 0 else None

    @field_validator("open", "high", "low", "close", mode="before")
    @classmethod
    def _ohlc_must_be_finite(cls, v, info):
        """A candlestick bar is only meaningful with real OHLC numbers."""
        f = float(v)
        if not math.isfinite(f):
            raise ValueError(f"{info.field_name} must be finite, got {v!r}")
        return f

    @field_validator(
        "ma_50", "ma_200", "ema_9", "ema_20", "rsi_14",
        "macd_line", "signal_line", "macd_histogram",
        "bb_upper", "bb_middle", "bb_lower",
        mode="before",
    )
    @classmethod
    def _overlay_nan_to_none(cls, v):
        """Keep the field, but collapse NaN / inf to ``null`` for clean JSON."""
        if v is None:
            return None
        f = float(v)
        return f if math.isfinite(f) else None


class TickerSummary(BaseModel):
    """Quantitative summary for a single ticker."""

    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL.")
    timeframe: Timeframe = Field(
        DEFAULT_TIMEFRAME,
        description="Chart timeframe this summary was computed at.",
    )
    period_start: str = Field(
        ...,
        description=(
            "Start of the window — a YYYY-MM-DD date for daily timeframes, a "
            "full ISO-8601 timestamp for intraday ones."
        ),
    )
    period_end: str = Field(
        ..., description="End of the window (same format as period_start)."
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
    macd: Optional[MACD] = Field(
        None,
        description="MACD (12/26/9) line / signal / histogram at the latest close.",
    )
    bollinger: Optional[BollingerBands] = Field(
        None,
        description="Bollinger Bands (SMA-20 ± 2σ) + bandwidth at the latest close.",
    )
    data_points: int = Field(
        ..., description="Number of trading days in the analysis window."
    )
    price_history: list[PricePoint] = Field(
        default_factory=list,
        description=(
            "Per-day OHLCV + MA-50 + MA-200 + EMA-9 + EMA-20 + RSI-14 + MACD "
            "(line/signal/histogram) + Bollinger (upper/middle/lower) over the "
            "analysis window, oldest first. Powers the candlestick + volume, "
            "RSI and MACD charts."
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

    @field_validator(
        "date", "headline", "source", "market_reaction", "causal_impact",
        mode="before",
    )
    @classmethod
    def _str_or_blank(cls, v):
        """Tolerate a null / non-string where the model should have sent prose."""
        return "" if v is None else str(v)


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

    @field_validator("case", mode="before")
    @classmethod
    def _case_lower(cls, v):
        return str(v).strip().lower() if v is not None else v

    @field_validator("probability", mode="before")
    @classmethod
    def _prob_clamp(cls, v):
        if v is None or v == "":
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(f):
            return None
        return min(1.0, max(0.0, f))

    @field_validator("drivers", "invalidation_trigger", mode="before")
    @classmethod
    def _str_or_blank(cls, v):
        return "" if v is None else str(v)


class TickerReport(BaseModel):
    """The full three-section analysis for a single ticker."""

    ticker: str = Field(..., description="Stock ticker symbol.")
    recommendation: Literal["Buy", "Sell", "Hold"] = Field(
        ..., description="Machine-readable verdict for this ticker."
    )

    @field_validator("recommendation", mode="before")
    @classmethod
    def _rec_normalise(cls, v):
        """Case-fold 'BUY'/'buy'/'Hold ' → the canonical literal; else 'Hold'."""
        s = str(v).strip().lower()
        return {"buy": "Buy", "sell": "Sell", "hold": "Hold"}.get(s, "Hold")
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

# Canonical default basket, shared by the graph entry point and every FastAPI
# route so there is one place to change it. A deliberately high-beta set —
# biotech (MRNA), crypto miners (MARA), semis (AMD, WOLF), space (ASTS) and
# retail turnaround (CVNA) alongside TSLA / SMCI — so the volatility and
# gap-handling paths stay exercised on every default run.
DEFAULT_TICKERS: list[str] = [
    "AAPL", "NVDA", "MSFT", "TSLA", "SMCI",
    "AMD", "MRNA", "WOLF", "ASTS", "MARA", "CVNA",
]


class StockAnalysisState(BaseModel):
    """
    Shared state object that travels through the LangGraph workflow.

    Each agent reads what it needs and writes to its designated field,
    keeping the pipeline loosely coupled.
    """

    tickers: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TICKERS),
        description="List of ticker symbols to analyse.",
    )
    timeframe: Timeframe = Field(
        DEFAULT_TIMEFRAME,
        description="Chart timeframe for Agent 1's price history (1D…ALL).",
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
