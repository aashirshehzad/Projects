"""
Lightweight last-price quotes for the dashboard's live-polling loop.

`get_quotes` uses yfinance's ``fast_info`` (a single cheap metadata call, no
history download) so the frontend can poll it every ~10s during market hours
and nudge the current candle with ``series.update()``. It never raises: a bad
symbol or a throttled call comes back as ``{"ticker": ..., "price": None,
"error": ...}``.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import yfinance as yf

logger = logging.getLogger(__name__)

_NYSE_TZ = ZoneInfo("America/New_York")


def market_is_open(now: datetime | None = None) -> bool:
    """
    Rough NYSE regular-session check: Mon–Fri, 09:30–16:00 America/New_York.

    Ignores exchange holidays and half-days — good enough to gate the polling
    loop; the frontend still renders whatever the last quote returned.
    """
    ref = (now or datetime.now(timezone.utc)).astimezone(_NYSE_TZ)
    if ref.weekday() >= 5:  # Sat / Sun
        return False
    return dtime(9, 30) <= ref.time() <= dtime(16, 0)


def _one_quote(ticker: str) -> dict:
    fi = yf.Ticker(ticker).fast_info
    last = getattr(fi, "last_price", None)
    prev = getattr(fi, "previous_close", None)
    if last is None:
        raise ValueError("no last_price in fast_info")

    last = float(last)
    change = change_pct = None
    if prev:
        prev = float(prev)
        change = round(last - prev, 4)
        change_pct = round((last / prev - 1.0) * 100, 4) if prev else None

    return {
        "ticker": ticker,
        "price": round(last, 4),
        "previous_close": round(prev, 4) if prev else None,
        "change": change,
        "change_pct": change_pct,
    }


def get_quotes(tickers: list[str]) -> list[dict]:
    """One quote dict per ticker, in request order. Failures degrade in place."""
    out: list[dict] = []
    for t in tickers:
        try:
            out.append(_one_quote(t))
        except Exception as exc:  # noqa: BLE001 - surface as data, never 500
            logger.warning("quote failed for %s: %s", t, exc)
            out.append({"ticker": t, "price": None, "error": exc.__class__.__name__})
    return out
