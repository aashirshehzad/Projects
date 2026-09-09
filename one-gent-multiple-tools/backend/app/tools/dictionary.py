"""English dictionary definitions.

Primary source: dictionaryapi.dev. Falls back to Wiktionary (Wikimedia) when
that service is down or has no entry.
"""
from __future__ import annotations

import html
import re

import httpx

from ._http import get_json

DECLARATION = {
    "name": "define_word",
    "description": "Get the definition(s), part of speech, and example usage for an English word.",
    "parameters": {
        "type": "object",
        "properties": {
            "word": {"type": "string", "description": "The word to define."}
        },
        "required": ["word"],
    },
}

_TAGS = re.compile(r"<[^>]+>")


def _strip(raw: str) -> str:
    return html.unescape(_TAGS.sub("", raw or "")).strip()


def _from_dictionaryapi(word: str) -> dict | None:
    try:
        data = get_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
    except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException):
        return None
    entry = data[0]
    meanings = []
    for m in entry.get("meanings", [])[:3]:
        defs = [d["definition"] for d in m.get("definitions", [])[:2]]
        example = next(
            (d["example"] for d in m.get("definitions", []) if d.get("example")), None
        )
        meanings.append({
            "part_of_speech": m.get("partOfSpeech"),
            "definitions": defs,
            "example": example,
        })
    return {
        "word": entry.get("word", word),
        "phonetic": entry.get("phonetic"),
        "meanings": meanings,
        "source": "dictionaryapi.dev",
    }


def _from_wiktionary(word: str) -> dict | None:
    try:
        data = get_json(f"https://en.wiktionary.org/api/rest_v1/page/definition/{word}")
    except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException):
        return None
    groups = data.get("en") or []
    if not groups:
        return None
    meanings = []
    for g in groups[:3]:
        defs = [_strip(d.get("definition", "")) for d in g.get("definitions", [])[:2]]
        example = next(
            (_strip(ex) for d in g.get("definitions", []) for ex in d.get("examples", [])),
            None,
        )
        meanings.append({
            "part_of_speech": g.get("partOfSpeech"),
            "definitions": [d for d in defs if d],
            "example": example,
        })
    return {"word": word, "phonetic": None, "meanings": meanings, "source": "wiktionary"}


def run(word: str) -> dict:
    word = word.strip()
    result = _from_dictionaryapi(word) or _from_wiktionary(word)
    if result is None:
        return {"error": f"No definition found for '{word}'."}
    return result
