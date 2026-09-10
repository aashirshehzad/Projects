"""Unit tests for the deterministic AST rules SEC-001 .. SEC-005."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.static_scanner.ast_rules import Severity, scan_source
from app.static_scanner.engine import scan_path

FIXTURES = Path(__file__).parent / "fixtures"


def _rule_ids(violations) -> set[str]:
    return {v.rule_id for v in violations}


def test_vulnerable_sample_triggers_every_rule() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    found = _rule_ids(result.violations)
    for rule_id in ("SEC-001", "SEC-002", "SEC-003", "SEC-004", "SEC-005"):
        assert rule_id in found, f"{rule_id} not detected; got {sorted(found)}"


def test_clean_sample_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.py", base_dir=FIXTURES)
    assert result.violations == [], [
        (v.rule_id, v.line_number, v.message) for v in result.violations
    ]
    assert result.ok


def test_snippet_and_context_are_attached() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    for v in result.violations:
        assert v.snippet.strip(), f"{v.rule_id} has no snippet"
        assert v.context_start_line >= 1
        assert v.context_start_line <= v.line_number


def test_syntax_error_is_skipped_not_raised() -> None:
    assert scan_source("def broken(:\n    pass\n", "bad.py") == []


@pytest.mark.parametrize(
    "src, expected",
    [
        ("eval(x)", "SEC-001"),
        ("exec(code)", "SEC-001"),
        ("__import__(name)", "SEC-001"),
        ('cur.execute("SELECT %s" % v)', "SEC-002"),
        ('cur.execute("SELECT " + v)', "SEC-002"),
        ('cur.execute("SELECT {}".format(v))', "SEC-002"),
        ('password = "hunter2xyz"', "SEC-003"),
        ("pickle.loads(b)", "SEC-004"),
        ("yaml.load(s)", "SEC-004"),
        ("os.system('rm ' + p)", "SEC-005"),
        ("subprocess.run(cmd, shell=True)", "SEC-005"),
    ],
)
def test_individual_patterns(src: str, expected: str) -> None:
    assert expected in _rule_ids(scan_source(src, "snippet.py"))


@pytest.mark.parametrize(
    "src",
    [
        "ast.literal_eval(x)",
        'cur.execute("SELECT * FROM t WHERE id = ?", (v,))',
        'public_key = "not-a-secret-value"',
        "yaml.safe_load(s)",
        "json.loads(b)",
        "subprocess.run(['ls', '-l'])",
        "os.system('static command with no input')",
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert scan_source(src, "snippet.py") == []


def test_violations_are_severity_sorted() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    ranks = [v.severity.rank for v in result.violations]
    assert ranks == sorted(ranks)
    assert Severity.CRITICAL in {v.severity for v in result.violations}
