"""TXT-001 / TXT-002: regex-based secret detection for plain-text files."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from app.main import cli
from app.static_scanner.engine import scan_path
from app.static_scanner.ruleconfig import RuleConfig
from app.text_scanner import scan_text_source

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _ids(src: str) -> set[str]:
    return {v.rule_id for v in scan_text_source(src, "notes.txt")}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def test_vulnerable_txt_triggers_both_rules() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.txt", base_dir=FIXTURES)
    found = {v.rule_id for v in result.violations}
    assert found == {"TXT-001", "TXT-002"}
    assert len(result.violations) == 7  # 4 known-format hits + 3 assignment hits


def test_clean_txt_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.txt", base_dir=FIXTURES)
    assert result.violations == [], [
        (v.rule_id, v.line_number, v.message) for v in result.violations
    ]


# --------------------------------------------------------------------------- #
# individual patterns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src, expected",
    [
        ("AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP", "TXT-001"),
        ("token=ghp_AbCdEfGh12345678IjKlMnOp87654321QrStUvWx", "TXT-001"),
        ("SLACK_TOKEN=xoxb-1234567890-abcdefGHIJKL", "TXT-001"),
        ("key=AIzaSyD-abcdefghijklmnopqrstuvwxyz012345", "TXT-001"),
        ("stripe=sk_live_abcdefghijklmnopqrstuvwx", "TXT-001"),
        ("-----BEGIN PRIVATE KEY-----", "TXT-001"),
        (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dQw4w9WgXcQ",
            "TXT-001",
        ),
        ('api_key = "abcd1234EFGH5678"', "TXT-002"),
        ("db_password=hunter2xyz9", "TXT-002"),
        ("secret_token: Tok3nValue99", "TXT-002"),
    ],
)
def test_individual_patterns(src: str, expected: str) -> None:
    assert expected in _ids(src)


@pytest.mark.parametrize(
    "src",
    [
        "password: changeme",
        "public_name: John Smith",
        'description = "a normal short sentence here"',
        "note: remember to buy milk",
        "retry_count = 5",
        "timeout=30",
        "auth_key = simpletext",
        "This is just a paragraph about tokens and secrets in general.",
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert _ids(src) == set()


# --------------------------------------------------------------------------- #
# suppression + config
# --------------------------------------------------------------------------- #
def test_inline_nosec_suppression() -> None:
    assert _ids("api_key = \"abcd1234EFGH5678\"  # nosec") == set()
    assert _ids("api_key = \"abcd1234EFGH5678\"  # nosec TXT-002") == set()
    assert "TXT-002" in _ids("api_key = \"abcd1234EFGH5678\"  # nosec TXT-999")


def test_noqa_must_name_the_rule() -> None:
    assert "TXT-002" in _ids('api_key = "abcd1234EFGH5678"  # noqa')
    assert _ids('api_key = "abcd1234EFGH5678"  # noqa: TXT-002') == set()


def test_ruleconfig_disables_and_overrides_severity() -> None:
    cfg = RuleConfig(disabled=frozenset({"TXT-002"}), severity={"TXT-001": "LOW"})
    src = 'AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\napi_key = "abcd1234EFGH5678"'
    violations = scan_text_source(src, "s.txt", config=cfg)
    ids = {v.rule_id: v for v in violations}
    assert "TXT-002" not in ids
    assert ids["TXT-001"].severity.value == "LOW"


# --------------------------------------------------------------------------- #
# mixed scan + CLI
# --------------------------------------------------------------------------- #
def test_directory_scan_includes_txt_alongside_code(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("eval(x)\n")
    (tmp_path / "notes.txt").write_text("AWS_ACCESS_KEY_ID=AKIAABCDEFGHIJKLMNOP\n")

    result = scan_path(tmp_path, base_dir=tmp_path)
    assert {v.file_path for v in result.violations} == {"a.py", "notes.txt"}


def test_cli_audit_txt_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "vulnerable_sample.txt"), "--no-llm"])
    assert res.exit_code == 1
    assert "TXT-001" in res.output


def test_cli_audit_clean_txt_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "clean_sample.txt"), "--no-llm"])
    assert res.exit_code == 0
