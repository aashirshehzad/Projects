"""Lightweight keyless web search via the DuckDuckGo Instant Answer API.

Note: this returns instant-answer / related-topic results, not a full SERP.
Swap in a paid search API here if you need deeper results.
"""
from __future__ import annotations

from ._http import get_json

DECLARATION = {
    "name": "web_search",
    "description": (
        "Search the web for a query and return a handful of result snippets with links. "
        "Use for current events, facts, or things not covered by the other tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for."}
        },
        "required": ["query"],
    },
}


def _walk_topics(topics: list, out: list, limit: int) -> None:
    for t in topics:
        if len(out) >= limit:
            return
        if "Topics" in t:
            _walk_topics(t["Topics"], out, limit)
        elif t.get("Text"):
            out.append({"snippet": t["Text"], "url": t.get("FirstURL")})


def run(query: str) -> dict:
    data = get_json(
        "https://api.duckduckgo.com/",
        {"q": query, "format": "json", "no_html": 1, "no_redirect": 1, "skip_disambig": 1},
    )

    results: list = []
    if data.get("AbstractText"):
        results.append({
            "snippet": data["AbstractText"],
            "url": data.get("AbstractURL"),
            "source": data.get("AbstractSource"),
        })
    _walk_topics(data.get("RelatedTopics", []), results, limit=6)

    if not results:
        return {
            "query": query,
            "results": [],
            "note": "No instant-answer results. Try rephrasing or use wikipedia_lookup / get_news.",
        }
    return {"query": query, "results": results}
