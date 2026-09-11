"""Offline tests for the local web UI backend (static path only)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from web.backend.main import app
from web.backend.service import AuditRequestError, run_audit

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def _zip(members: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _fixture_zip() -> bytes:
    return _zip(
        {
            "proj/vulnerable_sample.py": (FIXTURES / "vulnerable_sample.py").read_bytes(),
            "proj/clean_sample.py": (FIXTURES / "clean_sample.py").read_bytes(),
            "proj/notes.md": "ignored, not python",
        }
    )


def test_service_scans_only_python_and_finds_all_rules() -> None:
    out = run_audit(_fixture_zip(), use_llm=False)
    assert out["files_scanned"] == 2
    assert {v["rule_id"] for v in out["violations"]} == {
        "SEC-001",
        "SEC-002",
        "SEC-003",
        "SEC-004",
        "SEC-005",
    }
    assert out["report"] is None  # use_llm=False
    assert out["sarif"]["version"] == "2.1.0"


def test_service_rejects_non_zip() -> None:
    with pytest.raises(AuditRequestError, match="valid .zip"):
        run_audit(b"not a zip at all", use_llm=False)


def test_service_rejects_archive_without_python() -> None:
    with pytest.raises(AuditRequestError, match="No .py or .ipynb files"):
        run_audit(_zip({"readme.txt": "hi", "data.json": "{}"}), use_llm=False)


def test_service_scans_notebook_from_zip(tmp_path: Path) -> None:
    nb_text = (FIXTURES / "vulnerable_notebook.ipynb").read_text(encoding="utf-8")
    out = run_audit(_zip({"proj/demo.ipynb": nb_text}), use_llm=False)
    assert out["files_scanned"] == 1
    assert {v["rule_id"] for v in out["violations"]} == {"SEC-001", "SEC-003"}
    assert all("notebook cell" in v["message"] for v in out["violations"])


def test_service_ignores_path_traversal_entries() -> None:
    # only entry is a traversal attempt -> treated as "no python"
    with pytest.raises(AuditRequestError):
        run_audit(_zip({"../evil.py": "eval(x)"}), use_llm=False)


def test_health_endpoint() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_audit_endpoint_static() -> None:
    r = client.post(
        "/api/audit",
        files={"file": ("proj.zip", _fixture_zip(), "application/zip")},
        data={"llm": "false"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["violations"]) == 7
    assert body["counts"]["CRITICAL"] == 3
    assert body["llm_used"] is False


def test_audit_endpoint_bad_upload() -> None:
    r = client.post(
        "/api/audit",
        files={"file": ("x.txt", b"hello", "text/plain")},
        data={"llm": "false"},
    )
    assert r.status_code == 400
    assert "zip" in r.json()["detail"].lower()


def test_audit_endpoint_empty_upload() -> None:
    r = client.post(
        "/api/audit",
        files={"file": ("empty.zip", b"", "application/zip")},
        data={"llm": "false"},
    )
    assert r.status_code == 400


def test_report_pdf_endpoint() -> None:
    audit = client.post(
        "/api/audit",
        files={"file": ("proj.zip", _fixture_zip(), "application/zip")},
        data={"llm": "false"},
    ).json()
    r = client.post("/api/report.pdf", json={**audit, "project_label": "proj.zip"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_report_pdf_rejects_non_audit_payload() -> None:
    r = client.post("/api/report.pdf", json={"hello": "world"})
    assert r.status_code == 400
