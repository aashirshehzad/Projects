"""Latest stock quote from Yahoo Finance's keyless chart endpoint."""
from __future__ import annotations

import httpx

from ._http import get_json

DECLARATION = {
    "name": "get_stock_price",
    "description": (
        "Get the latest price and daily change for a stock ticker. "
        "Accepts tickers like 'AAPL', 'MSFT', 'TSLA', indices like '^GSPC', and "
        "crypto pairs like 'BTC-USD'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "Ticker symbol, e.g. 'AAPL' or 'BTC-USD'.",
            }
        },
        "required": ["symbol"],
    },
}


def run(symbol: str) -> dict:
    sym = symbol.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    try:
        data = get_json(url, {"interval": "1d", "range": "1d"})
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (404, 400):
            return {"error": f"No quote found for '{symbol}'."}
        return {"error": f"Quote lookup failed ({exc.response.status_code})."}

    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return {"error": f"No quote found for '{symbol}'."}

    meta = result[0].get("meta", {})
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return {"error": f"No price available for '{symbol}'."}

    change = round(price - prev, 4) if prev else None
    change_pct = round((price - prev) / prev * 100, 2) if prev else None

    return {
        "symbol": meta.get("symbol", sym),
        "name": meta.get("longName") or meta.get("shortName"),
        "price": price,
        "previous_close": prev,
        "day_high": meta.get("regularMarketDayHigh"),
        "day_low": meta.get("regularMarketDayLow"),
        "volume": meta.get("regularMarketVolume"),
        "change": change,
        "change_percent": change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName"),
    }
