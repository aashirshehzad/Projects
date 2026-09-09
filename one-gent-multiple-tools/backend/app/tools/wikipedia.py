"""Wikipedia lookup: resolve the best-matching article, return its summary."""
from __future__ import annotations

from ._http import get_json

DECLARATION = {
    "name": "wikipedia_lookup",
    "description": "Look up a topic on Wikipedia and return a short factual summary of the best-matching article.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The topic or person to look up."}
        },
        "required": ["query"],
    },
}


def run(query: str) -> dict:
    search = get_json(
        "https://en.wikipedia.org/w/api.php",
        {
            "action": "query", "list": "search", "srsearch": query,
            "srlimit": 1, "format": "json", "origin": "*",
        },
    )
    hits = search.get("query", {}).get("search", [])
    if not hits:
        return {"error": f"No Wikipedia article found for '{query}'."}

    title = hits[0]["title"]
    summary = get_json(
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
    )
    return {
        "title": summary.get("title", title),
        "description": summary.get("description"),
        "extract": summary.get("extract"),
        "url": summary.get("content_urls", {}).get("desktop", {}).get("page"),
    }
