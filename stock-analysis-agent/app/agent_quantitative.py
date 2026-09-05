"""
Agent 1 – Quantitative Analysis Agent.

Responsibilities
────────────────
• Fetch a 6-month analysis window of historical OHLCV data via **yfinance**,
  plus extra look-back so the 200-day moving average is available on the
  first day of that window.
• Compute 50-day & 200-day simple moving averages and 9-day / 20-day EMAs.
• Compute the 14-day Relative Strength Index (Wilder's RSI) — both the latest
  value and the full per-day series over the analysis window.
• Compute the MACD (12/26/9) — line, signal and histogram series plus the
  latest snapshot.
• Compute Bollinger Bands (SMA-20 ± 2σ) — upper / middle / lower series plus
  the latest snapshot and normalised bandwidth.
• Compute overall percentage return over the analysis window.
• Emit a per-day OHLCV + MA-50 + MA-200 + EMA-9 + EMA-20 + RSI-14 + MACD +
  Bollinger series (`price_history`) for the dashboard's candlestick, volume,
  RSI and MACD charts.
• Package the results as `TickerSummary` objects and append them
  to `StockAnalysisState.historical_data`.
• Record any ticker that could not be processed in
  `StockAnalysisState.failed_tickers` instead of failing the whole run.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.state import (
    MACD,
    BollingerBands,
    MovingAverages,
    PricePoint,
    StockAnalysisState,
    TickerError,
    TickerSummary,
)

logger = logging.getLogger(__name__)

# ── timeframes ─────────────────────────────────────────────────────────────
# Each timeframe maps to a yfinance (period, interval) fetch plus how many of
# the fetched bars to *keep* for the chart. `period` is deliberately much
# longer than `display_bars` so the 200-bar MA / EMA / MACD / Bollinger series
# are already "warm" at the start of the kept window. Yahoo caps intraday
# history hard (1m ≤ 7d, 5m ≤ 60d, 1h ≤ 730d) — every period below stays
# inside that cap. Indicator look-backs (50, 200, 20, 14, 12/26/9) are counted
# in **bars**, so on an intraday timeframe "MA-50" means a 50-bar average.
_TIMEFRAMES: dict[str, dict] = {
    "1D":  {"period": "7d",  "interval": "1m", "display_bars": 390},
    "5D":  {"period": "1mo", "interval": "5m", "display_bars": 390},
    "1M":  {"period": "1y",  "interval": "1h", "display_bars": 154},
    "3M":  {"period": "2y",  "interval": "1d", "display_bars": 63},
    "6M":  {"period": "2y",  "interval": "1d", "display_bars": 126},
    # YTD isn't a fixed bar count — `_build_summary` slices from Jan 1 of the
    # current year instead of using `display_bars` (see the `ytd` flag there).
    "YTD": {"period": "2y",  "interval": "1d", "display_bars": None, "ytd": True},
    "1Y":  {"period": "5y",  "interval": "1d", "display_bars": 252},
    "ALL": {"period": "max", "interval": "1d", "display_bars": None},
}
_DEFAULT_TIMEFRAME = "6M"
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "1h", "90m"}

# Standard Wilder look-back for the Relative Strength Index.
_RSI_PERIOD = 14

# Spans for the Exponential Moving Average overlays (fast / short-term).
_EMA_FAST_SPAN = 9
_EMA_SPAN = 20

# Standard MACD parameters: 12/26 EMAs, 9-period signal EMA.
_MACD_FAST, _MACD_SLOW, _MACD_SIGNAL = 12, 26, 9

# Bollinger Bands: 20-period SMA middle band, ±2 rolling standard deviations.
_BB_WINDOW, _BB_STD = 20, 2.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _finite(value) -> Optional[float]:
    """
    Coerce *value* to a plain finite ``float``, or ``None``.

    Guards JSON serialisation: pandas yields ``NaN`` for undefined rolling
    windows and the first ~14 RSI rows, and a divide-by-zero RSI can produce
    ``inf``. Neither is valid JSON — Starlette's encoder runs with
    ``allow_nan=False`` and raises — so every number handed to a Pydantic model
    must pass through here first.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _round(value, digits: int = 4) -> Optional[float]:
    """``_finite`` then ``round``; ``None`` when the value is missing/non-finite."""
    v = _finite(value)
    return round(v, digits) if v is not None else None


def _int(value) -> Optional[int]:
    """Finite, non-negative integer (e.g. share volume), or ``None``."""
    v = _finite(value)
    return int(v) if v is not None and v >= 0 else None


def _ema_series(close: pd.Series, span: int = _EMA_SPAN) -> pd.Series:
    """
    Full *span*-day Exponential Moving Average of *close*
    (``ewm(span=span, adjust=False)`` — the standard "recursive" EMA that seeds
    on the first observation, so every row has a value).

    Gap-safe by construction: the recurrence is ``y[t] = α·x[t] + (1−α)·y[t−1]``
    with a *constant* ``α = 2/(span+1)`` — there is no division by any price, so
    a 20–30% single-day gap (MRNA, MARA) just steps the level; it cannot yield
    NaN or a divide-by-zero. MACD inherits this (it is only sums/differences of
    EMAs). ``_round`` still backstops every emitted value.
    """
    return close.ewm(span=span, adjust=False).mean()


def _macd_frame(close: pd.Series) -> pd.DataFrame:
    """
    Standard MACD (12/26/9) as a 3-column frame indexed like *close*:

    * ``macd_line``      = EMA-12(close) − EMA-26(close)
    * ``signal_line``    = EMA-9(macd_line)
    * ``macd_histogram`` = macd_line − signal_line

    All three seed on the first row (``adjust=False``), so there are no NaN
    rows to trim, and there is no price-division anywhere (see
    :func:`_ema_series`) so a severe gap cannot introduce ``inf``. The
    ``replace`` is belt-and-suspenders; ``_round`` also guards every emitted
    value.
    """
    macd_line = _ema_series(close, _MACD_FAST) - _ema_series(close, _MACD_SLOW)
    signal_line = macd_line.ewm(span=_MACD_SIGNAL, adjust=False).mean()
    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "macd_histogram": macd_line - signal_line,
        }
    ).replace([np.inf, -np.inf], np.nan)


def _bollinger_frame(close: pd.Series) -> pd.DataFrame:
    """
    Bollinger Bands (20-period SMA, ±2σ) as a 4-column frame indexed like
    *close*:

    * ``bb_middle``    = SMA-20(close)
    * ``bb_upper``     = bb_middle + 2 · rolling std(close, 20)
    * ``bb_lower``     = bb_middle − 2 · rolling std(close, 20)
    * ``bb_bandwidth`` = (bb_upper − bb_lower) / bb_middle  — normalised width,
      a volatility gauge (low = squeeze, high = expansion)

    The first ``_BB_WINDOW − 1`` rows are ``NaN`` (window not yet full). The
    only division is ``bandwidth = (upper − lower) / middle``; ``middle`` is a
    20-day mean of the OHLC-filtered (strictly positive) close, so it can't be
    zero. The trailing ``replace`` still scrubs any ``inf`` as a safeguard, and
    ``_round`` guards every emitted value.
    """
    middle = close.rolling(window=_BB_WINDOW).mean()
    std = close.rolling(window=_BB_WINDOW).std()
    upper = middle + std * _BB_STD
    lower = middle - std * _BB_STD
    return pd.DataFrame(
        {
            "bb_middle": middle,
            "bb_upper": upper,
            "bb_lower": lower,
            "bb_bandwidth": (upper - lower) / middle,
        }
    ).replace([np.inf, -np.inf], np.nan)


def _rsi_series(close: pd.Series, period: int = _RSI_PERIOD) -> pd.Series:
    """
    Full *period*-day RSI series for *close*, using Wilder's smoothing (an EWMA
    with ``alpha = 1 / period``). The first ``period`` entries are ``NaN`` until
    the average is seeded. A flat/rising stretch gives ``avg_loss == 0`` →
    ``rs == inf`` → ``rsi == 100``.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _compute_rsi(close: pd.Series, period: int = _RSI_PERIOD) -> Optional[float]:
    """
    Final value of the *period*-day RSI for *close* (see :func:`_rsi_series`).
    Returns ``None`` when there is not enough history to seed the average.
    """
    if len(close) <= period:
        return None

    return _round(_rsi_series(close, period).iloc[-1], 2)

def _fetch_history(
    ticker: str, timeframe: str = _DEFAULT_TIMEFRAME
) -> tuple[yf.Ticker, pd.DataFrame]:
    """
    Download price history for *ticker* at the resolution *timeframe* asks for
    (see ``_TIMEFRAMES``). Fetches well past the display window so the rolling
    indicators are warm; ``_build_summary`` trims to ``display_bars``.

    ``auto_adjust=True`` gives a single split/dividend-adjusted close series, so
    a corporate action (e.g. SMCI's 10-for-1 split) is not mistaken for a −90%
    crash and the EMA / MACD / Bollinger series stay continuous across it. The
    downstream maths is plain arithmetic that handles genuine high-beta spikes
    fine; the de-dup + drop-non-positive-OHLC filter in ``_build_summary`` is
    what protects it from bad prints (a zero / NaN row), so yfinance's own
    ``repair=`` pass — which pulls in a heavy SciPy dependency — is not used.

    Returns the ``yf.Ticker`` alongside the frame so the caller can reuse the
    same handle for :func:`_fetch_meta` instead of re-resolving the symbol.
    """
    cfg = _TIMEFRAMES.get(timeframe) or _TIMEFRAMES[_DEFAULT_TIMEFRAME]

    logger.info(
        "Fetching %s  [%s] period=%s interval=%s",
        ticker, timeframe, cfg["period"], cfg["interval"],
    )
    stock = yf.Ticker(ticker)
    df: pd.DataFrame = stock.history(
        period=cfg["period"],
        interval=cfg["interval"],
        auto_adjust=True,
        actions=False,
    )

    if df.empty:
        raise ValueError(
            f"No data returned for {ticker} at timeframe {timeframe}. "
            "Check the symbol / timeframe."
        )

    return stock, df


def _fetch_meta(stock: yf.Ticker) -> dict:
    """
    Best-effort company metadata: name, sector, industry, market cap, 52-week
    high/low. Never raises — a slow/blocked/partial fetch just leaves fields
    at their default ``None`` rather than failing the ticker.

    ``fast_info`` (cheap, one lightweight call — the same primitive
    ``app/quotes.py`` uses for live polling) covers the three numeric fields.
    Name/sector/industry have no fast equivalent in yfinance; ``get_info()``
    is a much heavier scrape, so it's wrapped separately and allowed to fail
    on its own without taking the numeric fields down with it.
    """
    meta: dict = {}
    try:
        fi = stock.fast_info
        meta["market_cap"] = _finite(getattr(fi, "market_cap", None))
        meta["week52_high"] = _finite(getattr(fi, "year_high", None))
        meta["week52_low"] = _finite(getattr(fi, "year_low", None))
    except Exception:  # noqa: BLE001 - metadata is decorative, never fatal
        logger.warning("fast_info metadata fetch failed for %s", stock.ticker, exc_info=True)
    try:
        info = stock.get_info() or {}
        meta["company_name"] = info.get("longName") or info.get("shortName")
        meta["sector"] = info.get("sector")
        meta["industry"] = info.get("industry")
    except Exception:  # noqa: BLE001 - the slow scrape; degrade, don't fail
        logger.warning("get_info() metadata fetch failed for %s", stock.ticker, exc_info=True)
    return meta


def _build_summary(
    ticker: str,
    df: pd.DataFrame,
    timeframe: str = _DEFAULT_TIMEFRAME,
    meta: Optional[dict] = None,
) -> TickerSummary:
    """
    Derive quantitative metrics from a price DataFrame.

    *df* carries look-back rows ahead of the display window: the moving
    averages / EMA / MACD / Bollinger are computed on the **full** series, then
    only the trailing ``display_bars`` (per ``_TIMEFRAMES[timeframe]``) are
    emitted.

    The emitted ``price_history`` is JSON-clean: OHLC rows with any missing or
    non-positive value are dropped, and every derived number is a finite
    ``float`` or ``None`` — never ``NaN`` / ``inf`` (see :func:`_finite`). Each
    point's ``date`` is a strict ``YYYY-MM-DD`` string for daily timeframes and
    a full ISO-8601 timestamp (with tz offset) for intraday ones, so the
    frontend can place intraday bars on the time axis.
    """
    cfg = _TIMEFRAMES.get(timeframe) or _TIMEFRAMES[_DEFAULT_TIMEFRAME]
    is_intraday = cfg["interval"] in _INTRADAY_INTERVALS
    display_bars = cfg["display_bars"]

    def _fmt_ts(idx) -> str:
        return idx.isoformat() if is_intraday else idx.strftime("%Y-%m-%d")
    # De-dupe and order the index so `.get(idx)` and the window slice are
    # well defined even if yfinance returns a stray duplicate row.
    df = df[~df.index.duplicated(keep="last")].sort_index()
    close = df["Close"]

    # Rolling means on the *full* series (look-back included) so they are
    # already "warm" on the first day of the analysis window.
    ma_50_series = close.rolling(window=50).mean()
    ma_200_series = close.rolling(window=200).mean()

    ma_50 = _finite(ma_50_series.iloc[-1]) if len(close) >= 50 else None
    ma_200 = _finite(ma_200_series.iloc[-1]) if len(close) >= 200 else None

    # 9-day / 20-day EMAs on the full series (seed on row 0, so always "warm").
    ema_9_series = _ema_series(close, _EMA_FAST_SPAN)
    ema_9 = _finite(ema_9_series.iloc[-1])
    ema_20_series = _ema_series(close)
    ema_20 = _finite(ema_20_series.iloc[-1])

    # 14-day RSI on the full series so it is "warm" for the first window day.
    rsi_series = _rsi_series(close)
    rsi_14 = _compute_rsi(close)

    # MACD (12/26/9) on the full series.
    macd_df = _macd_frame(close)
    macd_last = macd_df.iloc[-1]

    # Bollinger Bands (SMA-20 ± 2σ) on the full series.
    bb_df = _bollinger_frame(close)
    bb_last = bb_df.iloc[-1]

    # Restrict return / period metrics — and the emitted series — to the last
    # `display_bars` rows (all of them for "ALL"). YTD isn't a bar count: slice
    # from Jan 1 of the current year in the series' own index tz instead.
    if cfg.get("ytd"):
        year_start = pd.Timestamp(year=df.index.max().year, month=1, day=1, tz=df.index.tz)
        window = df.loc[df.index >= year_start]
        if window.empty:  # e.g. first trading day of the year, before the open
            window = df.iloc[-1:]
    else:
        window = df if display_bars is None else df.iloc[-display_bars:]

    # A candlestick needs all four OHLC values that are also *positive*; yfinance
    # yields NaN rows around holidays and, briefly, for the current bar, and a
    # bad print can leave a 0 / negative price. Drop anything not fully
    # finite-and-positive so neither the charts nor the ratio maths below ever
    # see a half-formed or zero bar.
    ohlc_cols = ["Open", "High", "Low", "Close"]
    ohlc = window[ohlc_cols].to_numpy()
    window = window[(np.isfinite(ohlc) & (ohlc > 0)).all(axis=1)]
    if window.empty:
        raise ValueError(
            f"No usable OHLC rows for {ticker} in the {timeframe} window."
        )

    window_close = window["Close"]
    first_close = float(window_close.iloc[0])
    last_close = float(window_close.iloc[-1])
    # first_close is guaranteed > 0 by the filter above, so this can't divide by
    # zero; _finite still backstops any freak non-finite result.
    pct_return = _finite((last_close - first_close) / first_close * 100) or 0.0

    price_history = [
        PricePoint(
            date=_fmt_ts(idx),
            open=round(float(row["Open"]), 4),
            high=round(float(row["High"]), 4),
            low=round(float(row["Low"]), 4),
            close=round(float(row["Close"]), 4),
            ma_50=_round(ma_50_series.get(idx)),
            ma_200=_round(ma_200_series.get(idx)),
            ema_9=_round(ema_9_series.get(idx)),
            ema_20=_round(ema_20_series.get(idx)),
            rsi_14=_round(rsi_series.get(idx), 2),
            macd_line=_round(macd_df["macd_line"].get(idx), 6),
            signal_line=_round(macd_df["signal_line"].get(idx), 6),
            macd_histogram=_round(macd_df["macd_histogram"].get(idx), 6),
            bb_upper=_round(bb_df["bb_upper"].get(idx)),
            bb_middle=_round(bb_df["bb_middle"].get(idx)),
            bb_lower=_round(bb_df["bb_lower"].get(idx)),
            volume=_int(row.get("Volume")),
        )
        for idx, row in window.iterrows()
    ]

    return TickerSummary(
        ticker=ticker,
        timeframe=timeframe,
        period_start=_fmt_ts(window.index.min()),
        period_end=_fmt_ts(window.index.max()),
        latest_close=round(last_close, 4),
        moving_averages=MovingAverages(
            ma_50=_round(ma_50),
            ma_200=_round(ma_200),
            ema_9=_round(ema_9),
            ema_20=_round(ema_20),
        ),
        pct_return=round(pct_return, 4),
        rsi_14=rsi_14,
        macd=MACD(
            macd_line=_round(macd_last["macd_line"], 6),
            signal_line=_round(macd_last["signal_line"], 6),
            macd_histogram=_round(macd_last["macd_histogram"], 6),
        ),
        bollinger=BollingerBands(
            bb_upper=_round(bb_last["bb_upper"]),
            bb_middle=_round(bb_last["bb_middle"]),
            bb_lower=_round(bb_last["bb_lower"]),
            bandwidth=_round(bb_last["bb_bandwidth"], 4),
        ),
        data_points=len(window),
        price_history=price_history,
        **(meta or {}),
    )


# ── public entry point (LangGraph node function) ────────────────────────────

def quantitative_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    LangGraph **node** that populates ``state.historical_data``.

    Parameters
    ----------
    state : StockAnalysisState
        Current graph state — ``tickers`` and ``timeframe`` are read.

    Returns
    -------
    StockAnalysisState
        A *new* state instance with ``historical_data`` filled in, and
        ``failed_tickers`` listing any symbol that could not be processed.
    """
    summaries: list[TickerSummary] = []
    failures: list[TickerError] = []
    timeframe = state.timeframe or _DEFAULT_TIMEFRAME

    for ticker in state.tickers:
        try:
            stock, df = _fetch_history(ticker, timeframe)
            meta = _fetch_meta(stock)
            summary = _build_summary(ticker, df, timeframe, meta)
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
