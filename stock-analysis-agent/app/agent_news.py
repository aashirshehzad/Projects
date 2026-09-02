"""
Agent 2.5 – News / Search Agent.

Responsibilities
────────────────
• For each ticker, pull recent dated headlines from the **Tavily** search API
  (`topic="news"`, last ~180 days) so Agent 3 can cite real, date-stamped
  catalysts instead of hallucinating them.
• Package the hits as `TickerNews` (a provider-synthesised `summary` plus a
  list of `NewsItem`s) into `StockAnalysisState.news_context`.

Contract
────────
Same as the other agents: a per-ticker failure is caught and recorded in that
ticker's `notes`; the agent never raises past its own loop. If the `tavily`
package is missing or `TAVILY_API_KEY` is unset, every ticker comes back with
an empty `items` list and a `notes` string — Agent 3 then states outright that
no verified catalysts were available rather than inventing them.
"""

from __future__ import annotations

import logging
import os

from app.state import NewsItem, StockAnalysisState, TickerNews

try:  # optional dependency — the pipeline still runs without it
    from tavily import TavilyClient
except ImportError:  # pragma: no cover
    TavilyClient = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_MAX_RESULTS = int(os.getenv("NEWS_MAX_RESULTS", "8"))
_LOOKBACK_DAYS = int(os.getenv("NEWS_LOOKBACK_DAYS", "180"))
_SEARCH_TIMEOUT = float(os.getenv("NEWS_SEARCH_TIMEOUT", "30"))


def _search_ticker(client: "TavilyClient", ticker: str) -> TickerNews:
    """One Tavily `news` query for *ticker*; failures become a `notes` string."""
    query = (
        f"{ticker} stock earnings results, analyst notes, guidance changes, "
        f"and price-moving catalysts"
    )
    try:
        resp = client.search(
            query=query,
            topic="news",
            days=_LOOKBACK_DAYS,
            max_results=_MAX_RESULTS,
            include_answer="basic",
            timeout=_SEARCH_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 — isolate per-ticker failures
        logger.exception("Tavily search failed for %s", ticker)
        return TickerNews(ticker=ticker, notes=f"News search failed ({exc}).")

    items = [
        NewsItem(
            title=str(r.get("title") or "").strip(),
            url=str(r.get("url") or "").strip(),
            published_date=(r.get("published_date") or None),
            snippet=(str(r.get("content") or "").strip()[:400] or None),
        )
        for r in resp.get("results", [])
        if r.get("title") and r.get("url")
    ]
    return TickerNews(
        ticker=ticker,
        summary=(resp.get("answer") or None),
        items=items,
        notes=None if items else "No recent news returned for this symbol.",
    )


def news_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    LangGraph **node** that fills ``state.news_context``.

    Reads only ``state.tickers``.
    """
    if TavilyClient is None or not _TAVILY_API_KEY:
        reason = (
            "the 'tavily-python' package is not installed"
            if TavilyClient is None
            else "no TAVILY_API_KEY set"
        )
        logger.warning("news_agent: %s — skipping news retrieval", reason)
        bundles = [
            TickerNews(ticker=t, notes=f"News retrieval skipped: {reason}.")
            for t in state.tickers
        ]
        return state.model_copy(update={"news_context": bundles})

    client = TavilyClient(api_key=_TAVILY_API_KEY)
    bundles: list[TickerNews] = []
    for ticker in state.tickers:
        bundle = _search_ticker(client, ticker)
        bundles.append(bundle)
        logger.info("news %s — %d headline(s)", ticker, len(bundle.items))

    return state.model_copy(update={"news_context": bundles})
