"""End-to-end CLI tests (static path only -- no network)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from app.main import cli

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_audit_vulnerable_exits_with_findings() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm"])
    assert res.exit_code == 1
    assert "SEC-001" in res.output


def test_audit_clean_exits_zero() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "clean_sample.py"), "--no-llm"])
    assert res.exit_code == 0
    assert "PASS" in res.output


def test_fail_on_critical_ignores_medium_only(tmp_path: Path) -> None:
    sample = tmp_path / "only_medium.py"
    sample.write_text("import subprocess\nsubprocess.run(x, shell=True)\n")
    # SEC-005 here is HIGH (dynamic), so --fail-on CRITICAL should still pass it.
    res = runner.invoke(cli, ["audit", str(sample), "--no-llm", "--fail-on", "CRITICAL"])
    assert res.exit_code == 0


def test_json_report_is_written(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    res = runner.invoke(
        cli,
        ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm", "--json", str(out)],
    )
    assert res.exit_code == 1
    data = json.loads(out.read_text())
    assert data["total_violations_evaluated"] >= 5
    assert {r["rule_id"] for r in data["remediations"]} >= {"SEC-001", "SEC-004"}


def test_sarif_report_is_written(tmp_path: Path) -> None:
    out = tmp_path / "out.sarif"
    res = runner.invoke(
        cli,
        ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm", "--sarif", str(out)],
    )
    assert res.exit_code == 1
    sarif = json.loads(out.read_text())
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "hybrid-code-auditor"
    assert len(sarif["runs"][0]["results"]) >= 5


def test_fix_requires_llm() -> None:
    res = runner.invoke(cli, ["fix", str(FIXTURES / "vulnerable_sample.py"), "--no-llm"])
    assert res.exit_code == 2  # click.UsageError


def test_help_lists_all_commands() -> None:
    res = runner.invoke(cli, ["--help"])
    assert res.exit_code == 0
    for cmd in ("audit", "diff", "fix"):
        assert cmd in res.output
