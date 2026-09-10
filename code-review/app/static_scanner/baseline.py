"""Baseline file: accept the findings that already exist so CI only fails on new ones.

A baseline is JSON: ``{"version": 1, "fingerprints": ["<sha1>", ...]}``. A
fingerprint hashes the rule id, the file path, and the *stripped text of the
offending line* -- stable when nearby code changes, unlike a line number.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from app.static_scanner.ast_rules import Violation


def _offending_line(v: Violation) -> str:
    if not v.snippet:
        return ""
    rows = v.snippet.splitlines()
    idx = v.line_number - (v.context_start_line or v.line_number)
    return rows[idx].strip() if 0 <= idx < len(rows) else ""


def fingerprint(v: Violation) -> str:
    basis = f"{v.rule_id}\x00{v.file_path}\x00{_offending_line(v)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def load(path: str | Path) -> set[str]:
    p = Path(path)
    if not p.is_file():
        return set()
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return set(payload.get("fingerprints", []))
    except (json.JSONDecodeError, OSError, AttributeError):
        return set()


def write(path: str | Path, violations: Iterable[Violation]) -> int:
    fps = sorted({fingerprint(v) for v in violations})
    Path(path).write_text(
        json.dumps({"version": 1, "fingerprints": fps}, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(fps)


def apply(
    violations: list[Violation], known: set[str]
) -> tuple[list[Violation], int]:
    """Return (violations not in the baseline, count suppressed)."""
    if not known:
        return violations, 0
    kept = [v for v in violations if fingerprint(v) not in known]
    return kept, len(violations) - len(kept)
