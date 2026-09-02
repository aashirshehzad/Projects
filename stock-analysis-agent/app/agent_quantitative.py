"""
Agent 1 – Quantitative Analysis Agent.

Responsibilities
────────────────
• Fetch a 6-month analysis window of historical OHLCV data via **yfinance**,
  plus extra look-back so the 200-day moving average is available on the
  first day of that window.
• Compute 50-day & 200-day simple moving averages.
• Compute the 14-day Relative Strength Index (Wilder's RSI).
• Compute overall percentage return over the analysis window.
• Package the results as `TickerSummary` objects and append them
  to `StockAnalysisState.historical_data`.
• Record any ticker that could not be processed in
  `StockAnalysisState.failed_tickers` instead of failing the whole run.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from app.state import (
    MovingAverages,
    PricePoint,
    StockAnalysisState,
    TickerError,
    TickerSummary,
)

logger = logging.getLogger(__name__)

# Extra calendar days fetched *before* the analysis window so that a full
# 200-session moving average can be computed for its first day (≈200 trading
# days ≈ 290 calendar days; 300 leaves head-room for holidays).
_MA_LOOKBACK_DAYS = 300

# Standard Wilder look-back for the Relative Strength Index.
_RSI_PERIOD = 14


# ── helpers ──────────────────────────────────────────────────────────────────

def _compute_rsi(close: pd.Series, period: int = _RSI_PERIOD) -> Optional[float]:
    """
    Final value of the *period*-day RSI for *close*, using Wilder's smoothing
    (an EWMA with ``alpha = 1 / period``). Returns ``None`` when there is not
    enough history to seed the average.
    """
    if len(close) <= period:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100.0 - 100.0 / (1.0 + rs)

    value = rsi.iloc[-1]
    if pd.isna(value):
        return None
    # A flat/rising series gives avg_loss == 0 → rs == inf → rsi == 100.
    return round(float(value), 2)

def _fetch_history(
    ticker: str,
    analysis_months: int = 6,
    ma_lookback_days: int = _MA_LOOKBACK_DAYS,
) -> pd.DataFrame:
    """
    Download price history for *ticker*.

    The fetched window is the last *analysis_months* **plus**
    ``ma_lookback_days`` of extra look-back, so the 200-day moving average is
    defined from the very start of the analysis window.
    """
    end = datetime.today()
    start = end - timedelta(days=analysis_months * 30 + ma_lookback_days)

    logger.info("Fetching %s  %s → %s", ticker, start.date(), end.date())
    stock = yf.Ticker(ticker)
    df: pd.DataFrame = stock.history(start=start.strftime("%Y-%m-%d"),
                                      end=end.strftime("%Y-%m-%d"))

    if df.empty:
        raise ValueError(f"No data returned for {ticker}. Check the symbol.")

    return df


def _build_summary(
    ticker: str, df: pd.DataFrame, analysis_months: int = 6
) -> TickerSummary:
    """
    Derive quantitative metrics from a price DataFrame.

    *df* carries look-back rows ahead of the analysis window: the moving
    averages are computed on the full series, while the return / period
    figures use only the trailing *analysis_months* slice.
    """
    close = df["Close"]

    # Rolling means on the *full* series (look-back included) so they are
    # already "warm" on the first day of the analysis window.
    ma_50_series = close.rolling(window=50).mean()
    ma_200_series = close.rolling(window=200).mean()

    ma_50 = float(ma_50_series.iloc[-1]) if len(close) >= 50 else None
    ma_200 = float(ma_200_series.iloc[-1]) if len(close) >= 200 else None

    # 14-day RSI on the full series so it is "warm" for the latest session.
    rsi_14 = _compute_rsi(close)

    # Restrict return / period metrics — and the emitted series — to the window.
    window_start = df.index.max() - pd.Timedelta(days=analysis_months * 30)
    window = df.loc[df.index >= window_start]
    window_close = window["Close"]

    first_close = float(window_close.iloc[0])
    last_close = float(window_close.iloc[-1])
    pct_return = (last_close - first_close) / first_close * 100

    def _clean(value: float) -> Optional[float]:
        return round(float(value), 4) if pd.notna(value) else None

    price_history = [
        PricePoint(
            date=str(idx.date()),
            close=round(float(price), 4),
            ma_50=_clean(ma_50_series.loc[idx]),
            ma_200=_clean(ma_200_series.loc[idx]),
        )
        for idx, price in window_close.items()
    ]

    return TickerSummary(
        ticker=ticker,
        period_start=str(window.index.min().date()),
        period_end=str(window.index.max().date()),
        latest_close=round(last_close, 4),
        moving_averages=MovingAverages(
            ma_50=round(ma_50, 4) if ma_50 is not None else None,
            ma_200=round(ma_200, 4) if ma_200 is not None else None,
        ),
        pct_return=round(pct_return, 4),
        rsi_14=rsi_14,
        data_points=len(window),
        price_history=price_history,
    )


# ── public entry point (LangGraph node function) ────────────────────────────

def quantitative_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    LangGraph **node** that populates ``state.historical_data``.

    Parameters
    ----------
    state : StockAnalysisState
        Current graph state — only ``tickers`` is read.

    Returns
    -------
    StockAnalysisState
        A *new* state instance with ``historical_data`` filled in, and
        ``failed_tickers`` listing any symbol that could not be processed.
    """
    summaries: list[TickerSummary] = []
    failures: list[TickerError] = []

    for ticker in state.tickers:
        try:
            df = _fetch_history(ticker)
            summary = _build_summary(ticker, df)
            summaries.append(summary)
            logger.info("✓  %s — return %.2f%%", ticker, summary.pct_return)
        except Exception as exc:  # noqa: BLE001 – isolate per-ticker failures
            logger.exception("✗  Failed to process %s", ticker)
            failures.append(
                TickerError(ticker=ticker, error=str(exc) or exc.__class__.__name__)
            )

    # Return a new state with the quantitative results populated.
    return state.model_copy(
        update={"historical_data": summaries, "failed_tickers": failures}
    )
