"""SQLite-backed per-session storage for the multi-tenant web app.

Each visitor gets an anonymous session (cookie-based). Their uploaded
profile text, in-flight job analysis, and Gmail OAuth token are all
scoped to that session id - nothing is shared across visitors.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from src.config import SESSION_DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    profile_text TEXT,
    resume_file_path TEXT,
    resume_file_name TEXT,
    current_job TEXT,
    current_match TEXT,
    current_draft TEXT,
    gmail_token TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    match_score INTEGER NOT NULL,
    is_aligned INTEGER NOT NULL,
    draft_status TEXT NOT NULL,
    draft_id TEXT,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SESSION_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(_SCHEMA)
        # Idempotent migrations for DBs created before these columns existed.
        for ddl in (
            "ALTER TABLE sessions ADD COLUMN resume_file_path TEXT",
            "ALTER TABLE sessions ADD COLUMN resume_file_name TEXT",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # column already exists


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_session(session_id: str) -> None:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            now = _now()
            conn.execute(
                "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )


def get_session(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    for field in ("current_job", "current_match", "current_draft", "gmail_token"):
        if data.get(field):
            data[field] = json.loads(data[field])
    return data


def update_session(session_id: str, **fields: Any) -> None:
    if not fields:
        return
    serialized: dict[str, Any] = {}
    for key, value in fields.items():
        if key in ("current_job", "current_match", "current_draft", "gmail_token") and value is not None:
            serialized[key] = json.dumps(value)
        else:
            serialized[key] = value
    serialized["updated_at"] = _now()

    set_clause = ", ".join(f"{k} = ?" for k in serialized)
    values = list(serialized.values()) + [session_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)


def add_history_entry(
    *,
    session_id: str,
    company: str,
    title: str,
    match_score: int,
    is_aligned: bool,
    draft_status: str,
    draft_id: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO job_history
               (session_id, company, title, match_score, is_aligned, draft_status, draft_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, company, title, match_score, int(is_aligned), draft_status, draft_id, _now()),
        )


def find_history_entry(session_id: str, company: str, title: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM job_history
               WHERE session_id = ? AND lower(company) = lower(?) AND lower(title) = lower(?)
               ORDER BY id DESC LIMIT 1""",
            (session_id, company, title),
        ).fetchone()
    return dict(row) if row else None


def list_history(session_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_history WHERE session_id = ? ORDER BY id DESC", (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]
