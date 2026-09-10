"""Stage 1: multi-file crawler that feeds source into the AST rules.

Also owns the "snippet extractor" milestone -- attaching +/- N lines of context
around every violation so Stage 3 never needs the whole file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings, get_settings
from app.static_scanner.ast_rules import Severity, Violation, scan_source

# Directories that never contain first-party code worth auditing.
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "vendor",
    "third_party",
    "site-packages",
    "dist-packages",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    ".tox",
    ".eggs",
    "migrations",
}
_SKIP_SUFFIXES = {".min.py"}
_SKIP_FILENAMES = {"conftest.py"}  # test wiring, not audit targets


@dataclass(slots=True)
class ScanResult:
    violations: list[Violation] = field(default_factory=list)
    files_scanned: int = 0
    files_skipped: int = 0
    parse_errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def counts_by_severity(self) -> dict[str, int]:
        out: dict[str, int] = {s.value: 0 for s in Severity}
        for v in self.violations:
            out[v.severity.value] += 1
        return out


def _iter_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            if name in _SKIP_FILENAMES or any(name.endswith(s) for s in _SKIP_SUFFIXES):
                continue
            found.append(Path(dirpath) / name)
    return sorted(found)


def _attach_snippet(violation: Violation, lines: list[str], context: int) -> None:
    start = max(1, violation.line_number - context)
    end = min(len(lines), (violation.end_line_number or violation.line_number) + context)
    violation.context_start_line = start
    violation.snippet = "\n".join(lines[start - 1 : end])


def scan_path(
    target: str | Path,
    *,
    settings: Settings | None = None,
    base_dir: str | Path | None = None,
) -> ScanResult:
    """Recursively scan *target* (file or directory) and return a result."""
    settings = settings or get_settings()
    target = Path(target)
    base = Path(base_dir) if base_dir else (target if target.is_dir() else target.parent)

    result = ScanResult()
    for path in _iter_python_files(target):
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            result.files_skipped += 1
            result.parse_errors.append(f"{path}: {exc}")
            continue

        try:
            rel = str(path.relative_to(base))
        except ValueError:
            rel = str(path)
        rel = rel.replace(os.sep, "/")

        violations = scan_source(source, rel)
        if violations:
            source_lines = source.splitlines()
            for v in violations:
                _attach_snippet(v, source_lines, settings.context_lines)
        result.violations.extend(violations)
        result.files_scanned += 1

    result.violations.sort(
        key=lambda v: (v.severity.rank, v.file_path, v.line_number, v.rule_id)
    )
    return result


def scan_paths(
    targets: list[str | Path],
    *,
    settings: Settings | None = None,
    base_dir: str | Path | None = None,
) -> ScanResult:
    """Scan several targets, merging into one :class:`ScanResult`."""
    merged = ScanResult()
    for t in targets:
        r = scan_path(t, settings=settings, base_dir=base_dir)
        merged.violations.extend(r.violations)
        merged.files_scanned += r.files_scanned
        merged.files_skipped += r.files_skipped
        merged.parse_errors.extend(r.parse_errors)
    merged.violations.sort(
        key=lambda v: (v.severity.rank, v.file_path, v.line_number, v.rule_id)
    )
    return merged
