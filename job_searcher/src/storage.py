"""Read/write access to data/jobs_history.json."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.config import JOBS_HISTORY_PATH


def load_history() -> list[dict[str, Any]]:
    if not JOBS_HISTORY_PATH.exists():
        return []
    try:
        with open(JOBS_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_history(entries: list[dict[str, Any]]) -> None:
    JOBS_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JOBS_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def find_existing(company: str, title: str) -> dict[str, Any] | None:
    company_norm = company.strip().lower()
    title_norm = title.strip().lower()
    for entry in load_history():
        if entry.get("company", "").strip().lower() == company_norm and entry.get(
            "title", ""
        ).strip().lower() == title_norm:
            return entry
    return None


def append_entry(
    *,
    company: str,
    title: str,
    match_score: int,
    is_aligned: bool,
    draft_status: str,
    draft_id: str | None = None,
) -> dict[str, Any]:
    entries = load_history()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "company": company,
        "title": title,
        "match_score": match_score,
        "is_aligned": is_aligned,
        "draft_status": draft_status,
        "draft_id": draft_id,
    }
    entries.append(entry)
    save_history(entries)
    return entry
