"""English dictionary definitions via the keyless dictionaryapi.dev."""
from __future__ import annotations

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


def run(word: str) -> dict:
    try:
        data = get_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word.strip()}")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return {"error": f"No definition found for '{word}'."}
        raise

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
    }
