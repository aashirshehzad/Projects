"""Latest stock quote from the keyless Stooq CSV endpoint."""
from __future__ import annotations

import csv
import io

from ._http import get_text

DECLARATION = {
    "name": "get_stock_price",
    "description": (
        "Get the latest price and daily change for a stock ticker. "
        "Accepts US tickers like 'AAPL', 'MSFT', 'TSLA' and many international ones."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker symbol, e.g. 'AAPL'. Do not include the exchange suffix.",
            }
        },
        "required": ["symbol"],
    },
}


def _quote(symbol: str) -> dict | None:
    url = "https://stooq.com/q/l/"
    text = get_text(url, {"s": symbol, "f": "sd2t2ohlcvn", "h": "", "e": "csv"})
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return None
    row = rows[0]
    if row.get("Close") in (None, "", "N/D"):
        return None
    return row


def run(symbol: str) -> dict:
    sym = symbol.strip().lower()
    candidates = [sym] if "." in sym else [sym, f"{sym}.us"]

    row = None
    for cand in candidates:
        row = _quote(cand)
        if row:
            break
    if not row:
        return {"error": f"No quote found for '{symbol}'."}

    try:
        open_ = float(row["Open"])
        close = float(row["Close"])
        change = close - open_
        change_pct = (change / open_ * 100) if open_ else 0.0
    except (ValueError, KeyError, ZeroDivisionError):
        change = change_pct = None

    return {
        "symbol": row.get("Symbol", sym).upper(),
        "name": row.get("Name") or None,
        "price": row.get("Close"),
        "open": row.get("Open"),
        "day_high": row.get("High"),
        "day_low": row.get("Low"),
        "volume": row.get("Volume"),
        "change": round(change, 4) if change is not None else None,
        "change_percent": round(change_pct, 2) if change_pct is not None else None,
        "as_of": f"{row.get('Date', '')} {row.get('Time', '')}".strip(),
        "currency": "USD (approx; Stooq end-of-day/delayed data)",
    }
