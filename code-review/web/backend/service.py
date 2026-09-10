"""Zip-upload -> audit orchestration for the local web UI.

Wraps the existing ``app`` library. Uploaded code is only ever parsed by
``ast`` -- never imported or executed -- and everything is extracted into a
throwaway temp dir that is deleted before the response returns.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.llm_remediation.remediator import Remediator, build_unreviewed_report
from app.reporter.sarif import to_sarif
from app.static_scanner.engine import scan_path

# Zip-bomb / abuse guards. Generous, since this is a local tool and real repo
# archives carry node_modules / .git / venv even though we only unpack *.py.
MAX_ENTRIES = 200_000
MAX_TOTAL_UNCOMPRESSED = 150 * 1024 * 1024  # 150 MB of .py source


class AuditRequestError(ValueError):
    """The upload was rejected before scanning (bad zip, no Python, too big)."""


def _extract_python_files(zip_path: Path, dest: Path) -> int:
    """Extract only ``*.py`` entries, with path-traversal and size guards."""
    extracted = 0
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise AuditRequestError(
                f"Archive has too many entries ({len(infos)} > {MAX_ENTRIES})."
            )
        for info in infos:
            if info.is_dir():
                continue
            rel = Path(info.filename)
            if rel.is_absolute() or ".." in rel.parts:
                continue  # traversal attempt -- skip silently
            if rel.suffix != ".py":
                continue
            # Skip vendored / VCS trees even if the archive includes them.
            if {"node_modules", ".git", ".venv", "venv", "site-packages"} & set(rel.parts):
                continue
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise AuditRequestError(
                    "Archive expands to more than 50 MB of Python source."
                )
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, length=64 * 1024)
            extracted += 1
    if extracted == 0:
        raise AuditRequestError("No .py files found in the archive.")
    return extracted


def _violation_payload(v: Any) -> dict[str, Any]:
    return {
        "rule_id": v.rule_id,
        "severity": v.severity.value,
        "title": v.title,
        "message": v.message,
        "file_path": v.file_path,
        "line_number": v.line_number,
        "end_line_number": v.end_line_number,
        "snippet": v.snippet,
        "context_start_line": v.context_start_line,
    }


def run_audit(zip_bytes: bytes, *, use_llm: bool) -> dict[str, Any]:
    """Extract, scan, optionally remediate, and return a JSON-able payload."""
    workspace = Path(tempfile.mkdtemp(prefix="cauditor-web-"))
    zip_path = workspace / "upload.zip"
    src_dir = workspace / "src"
    src_dir.mkdir()
    try:
        zip_path.write_bytes(zip_bytes)
        if not zipfile.is_zipfile(zip_path):
            raise AuditRequestError("Uploaded file is not a valid .zip archive.")
        _extract_python_files(zip_path, src_dir)

        result = scan_path(src_dir, base_dir=src_dir)

        report = None
        llm_error: str | None = None
        if use_llm and result.violations:
            try:
                report = Remediator().remediate(result.violations)
            except Exception as exc:  # AuditorError, transport, etc.
                llm_error = str(exc)
                report = build_unreviewed_report(
                    result.violations, reason="unavailable (Stage 3 failed)"
                )
        elif use_llm:
            report = build_unreviewed_report(result.violations)

        return {
            "files_scanned": result.files_scanned,
            "files_skipped": result.files_skipped,
            "counts": result.counts_by_severity(),
            "violations": [_violation_payload(v) for v in result.violations],
            "report": report.model_dump() if report is not None else None,
            "sarif": to_sarif(result, report),
            "llm_used": use_llm,
            "llm_error": llm_error,
        }
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
