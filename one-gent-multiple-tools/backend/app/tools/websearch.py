"""Keyless web search.

Tries the DuckDuckGo Instant Answer API first (fast, structured), then falls
back to scraping the DuckDuckGo HTML endpoint for real result snippets.
Swap in a paid search API here if you need production-grade results.
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

from ._http import get_json, get_text

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

_TAGS = re.compile(r"<[^>]+>")
_LINK = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIP = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', re.S)


def _clean(raw: str) -> str:
    return html.unescape(_TAGS.sub("", raw)).strip()


def _real_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    q = parse_qs(urlparse(href).query)
    return unquote(q["uddg"][0]) if "uddg" in q else href


def _instant_answers(query: str) -> list:
    data = get_json(
        "https://api.duckduckgo.com/",
        {"q": query, "format": "json", "no_html": 1, "no_redirect": 1, "skip_disambig": 1},
    )
    out: list = []
    if data.get("AbstractText"):
        out.append({
            "snippet": data["AbstractText"],
            "url": data.get("AbstractURL"),
            "source": data.get("AbstractSource"),
        })

    def walk(topics: list) -> None:
        for t in topics:
            if len(out) >= 6:
                return
            if "Topics" in t:
                walk(t["Topics"])
            elif t.get("Text"):
                out.append({"snippet": t["Text"], "url": t.get("FirstURL")})

    walk(data.get("RelatedTopics", []))
    return out


def _html_results(query: str) -> list:
    page = get_text("https://html.duckduckgo.com/html/", {"q": query})
    links = _LINK.findall(page)
    snips = _SNIP.findall(page)
    out = []
    for i, (href, title) in enumerate(links[:6]):
        out.append({
            "title": _clean(title),
            "url": _real_url(href),
            "snippet": _clean(snips[i]) if i < len(snips) else None,
        })
    return out


def run(query: str) -> dict:
    try:
        results = _instant_answers(query)
    except Exception:  # noqa: BLE001
        results = []

    if not results:
        try:
            results = _html_results(query)
        except Exception as exc:  # noqa: BLE001
            return {"query": query, "results": [], "note": f"search failed: {exc}"}

    if not results:
        return {"query": query, "results": [], "note": "No results found."}
    return {"query": query, "results": results}
