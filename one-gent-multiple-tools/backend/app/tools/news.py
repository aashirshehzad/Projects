"""Top headlines via the keyless Google News RSS feed."""
from __future__ import annotations

import feedparser

from ._http import get_text

DECLARATION = {
    "name": "get_news",
    "description": "Get recent news headlines, optionally about a specific topic, person, or place.",
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Optional search topic. Leave empty for general top headlines.",
            }
        },
        "required": [],
    },
}


def run(topic: str = "") -> dict:
    topic = (topic or "").strip()
    if topic:
        url = "https://news.google.com/rss/search"
        xml = get_text(url, {"q": topic, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    else:
        url = "https://news.google.com/rss"
        xml = get_text(url, {"hl": "en-US", "gl": "US", "ceid": "US:en"})

    feed = feedparser.parse(xml)
    items = []
    for entry in feed.entries[:6]:
        items.append({
            "title": entry.get("title"),
            "source": entry.get("source", {}).get("title") if entry.get("source") else None,
            "published": entry.get("published"),
            "link": entry.get("link"),
        })
    if not items:
        return {"topic": topic or "top headlines", "headlines": [], "note": "No headlines returned."}
    return {"topic": topic or "top headlines", "headlines": items}
