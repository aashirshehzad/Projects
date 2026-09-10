"""Stage 1 pruner: restrict the scan to lines actually touched by a PR.

Parses ``git diff --unified=0`` output into ``{relative_path: {changed line
numbers}}`` and filters a violation list down to those lines. This is what keeps
a 100k-line repo scan proportional to the size of the change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.core.exceptions import GitDiffError
from app.static_scanner.ast_rules import Violation

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_RENAME_TO_RE = re.compile(r"^\+\+\+ b/(.+)$")


def _run_git(args: list[str], cwd: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # git not installed
        raise GitDiffError("`git` executable not found on PATH.") from exc
    if proc.returncode != 0:
        raise GitDiffError(
            f"`git {' '.join(args)}` failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def changed_line_map(
    base_ref: str,
    *,
    repo_root: str | Path = ".",
    include_context: int = 0,
) -> dict[str, set[int]]:
    """Return added/modified line numbers per file, relative to *repo_root*.

    ``base_ref`` may be a branch, tag or SHA. The three-dot form is used so the
    diff is against the merge base, matching what a PR shows.
    """
    root = Path(repo_root).resolve()
    merge_base = _run_git(["merge-base", base_ref, "HEAD"], root).strip() or base_ref
    diff = _run_git(
        ["diff", "--unified=0", "--no-color", "--diff-filter=d", f"{merge_base}...HEAD"],
        root,
    )

    result: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        m = _RENAME_TO_RE.match(line)
        if m:
            current = m.group(1).strip()
            result.setdefault(current, set())
            continue
        m = _HUNK_RE.match(line)
        if m and current:
            start = int(m.group(1))
            count = int(m.group(2) or "1")
            if count == 0:  # pure deletion hunk -- nothing added on the new side
                continue
            lo = max(1, start - include_context)
            hi = start + count - 1 + include_context
            result[current].update(range(lo, hi + 1))
    return {f: lines for f, lines in result.items() if lines}


def filter_to_diff(
    violations: list[Violation],
    changed: dict[str, set[int]],
) -> list[Violation]:
    """Keep only violations whose line was added/modified in the diff."""
    kept: list[Violation] = []
    for v in violations:
        touched = changed.get(v.file_path)
        if touched is None:
            continue
        span = range(v.line_number, (v.end_line_number or v.line_number) + 1)
        if any(ln in touched for ln in span):
            kept.append(v)
    return kept


def changed_python_files(base_ref: str, *, repo_root: str | Path = ".") -> list[str]:
    """Relative paths of ``*.py`` files changed since the merge base with *base_ref*."""
    return sorted(f for f in changed_line_map(base_ref, repo_root=repo_root) if f.endswith(".py"))
