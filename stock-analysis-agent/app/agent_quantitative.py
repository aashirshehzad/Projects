"""
Agent 1 – Quantitative Analysis Agent.

Responsibilities
────────────────
• Fetch 6 months of historical OHLCV data via **yfinance**.
• Compute 50-day & 200-day simple moving averages.
• Compute overall percentage return over the window.
• Package the results as `TickerSummary` objects and append them
  to `StockAnalysisState.historical_data`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from app.state import MovingAverages, StockAnalysisState, TickerSummary

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _fetch_history(ticker: str, period_months: int = 6) -> pd.DataFrame:
    """Download adjusted-close history for *ticker* over the last *period_months*."""
    end = datetime.today()
    start = end - timedelta(days=period_months * 30)  # approximate

    logger.info("Fetching %s  %s → %s", ticker, start.date(), end.date())
    stock = yf.Ticker(ticker)
    df: pd.DataFrame = stock.history(start=start.strftime("%Y-%m-%d"),
                                      end=end.strftime("%Y-%m-%d"))

    if df.empty:
        raise ValueError(f"No data returned for {ticker}. Check the symbol.")

    return df


def _build_summary(ticker: str, df: pd.DataFrame) -> TickerSummary:
    """Derive quantitative metrics from a price DataFrame."""
    close = df["Close"]

    first_close = float(close.iloc[0])
    last_close = float(close.iloc[-1])
    pct_return = (last_close - first_close) / first_close * 100

    ma_50 = float(close.rolling(window=50).mean().iloc[-1]) if len(close) >= 50 else None
    ma_200 = float(close.rolling(window=200).mean().iloc[-1]) if len(close) >= 200 else None

    return TickerSummary(
        ticker=ticker,
        period_start=str(df.index.min().date()),
        period_end=str(df.index.max().date()),
        latest_close=round(last_close, 4),
        moving_averages=MovingAverages(
            ma_50=round(ma_50, 4) if ma_50 is not None else None,
            ma_200=round(ma_200, 4) if ma_200 is not None else None,
        ),
        pct_return=round(pct_return, 4),
        data_points=len(df),
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
        A *new* state instance with ``historical_data`` filled in.
    """
    summaries: list[TickerSummary] = []

    for ticker in state.tickers:
        try:
            df = _fetch_history(ticker)
            summary = _build_summary(ticker, df)
            summaries.append(summary)
            logger.info("✓  %s — return %.2f%%", ticker, summary.pct_return)
        except Exception:
            logger.exception("✗  Failed to process %s", ticker)

    # Return a new state with historical_data populated
    return state.model_copy(update={"historical_data": summaries})
