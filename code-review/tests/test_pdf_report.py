"""The PDF report renders valid output for both the clean and dirty cases."""

from __future__ import annotations

from pathlib import Path

from app.llm_remediation.remediator import build_unreviewed_report
from app.reporter.pdf import payload_from_scan, render_pdf
from app.static_scanner.engine import scan_path

FIXTURES = Path(__file__).parent / "fixtures"


def _assert_pdf(path: Path) -> None:
    assert path.exists()
    head = path.read_bytes()[:5]
    assert head == b"%PDF-", head
    assert path.stat().st_size > 1200


def test_pdf_with_findings_and_no_llm(tmp_path: Path) -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    payload = payload_from_scan(result, None)
    out = render_pdf(payload, tmp_path / "r.pdf", project_label="demo.zip")
    _assert_pdf(out)


def test_pdf_with_remediations(tmp_path: Path) -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    report = build_unreviewed_report(result.violations)
    payload = payload_from_scan(result, report)
    out = render_pdf(payload, tmp_path / "r.pdf")
    _assert_pdf(out)


def test_pdf_clean_project(tmp_path: Path) -> None:
    result = scan_path(FIXTURES / "clean_sample.py", base_dir=FIXTURES)
    out = render_pdf(payload_from_scan(result, None), tmp_path / "clean.pdf")
    _assert_pdf(out)


def test_pdf_from_web_payload_shape(tmp_path: Path) -> None:
    # Minimal hand-built payload like the frontend would POST back.
    payload = {
        "files_scanned": 1,
        "files_skipped": 0,
        "counts": {"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "violations": [
            {
                "rule_id": "SEC-001",
                "severity": "CRITICAL",
                "title": "Dynamic code execution",
                "message": "Call to `eval()` executes arbitrary code at runtime.",
                "file_path": "app/x.py",
                "line_number": 12,
                "snippet": "def run(e):\n    return eval(e)",
            }
        ],
        "report": {
            "summary": "one issue",
            "total_violations_evaluated": 1,
            "remediations": [
                {
                    "rule_id": "SEC-001",
                    "file_path": "app/x.py",
                    "line_number": 12,
                    "is_exploitable": True,
                    "root_cause": "User input reaches eval().",
                    "patched_code": "return ast.literal_eval(e)",
                    "unit_test": "def test_run():\n    assert True",
                }
            ],
        },
        "llm_used": True,
        "llm_error": None,
    }
    out = render_pdf(payload, tmp_path / "web.pdf", project_label="proj.zip")
    _assert_pdf(out)
