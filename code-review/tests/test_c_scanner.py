"""C-001 .. C-006: tree-sitter-backed C/C++ rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from app.c_scanner import scan_c_source
from app.main import cli
from app.static_scanner.engine import scan_path
from app.static_scanner.ruleconfig import RuleConfig

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _ids(src: str, suffix: str = "snippet.c") -> set[str]:
    return {v.rule_id for v in scan_c_source(src, suffix)}


# --------------------------------------------------------------------------- #
# fixtures: every rule fires, the safe file stays silent
# --------------------------------------------------------------------------- #
def test_vulnerable_c_triggers_every_rule() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.c", base_dir=FIXTURES)
    found = {v.rule_id for v in result.violations}
    for rule_id in ("C-001", "C-002", "C-003", "C-004", "C-005", "C-006"):
        assert rule_id in found, f"{rule_id} not detected; got {sorted(found)}"


def test_clean_c_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.c", base_dir=FIXTURES)
    assert result.violations == [], [
        (v.rule_id, v.line_number, v.message) for v in result.violations
    ]


def test_snippets_are_attached() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.c", base_dir=FIXTURES)
    for v in result.violations:
        assert v.snippet.strip(), f"{v.rule_id} has no snippet"


# --------------------------------------------------------------------------- #
# individual patterns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src, expected",
    [
        ("gets(buf);", "C-001"),
        ("strcpy(dst, src);", "C-001"),
        ("strcat(dst, src);", "C-001"),
        ('sprintf(buf, "%s", name);', "C-001"),
        ("printf(userfmt);", "C-002"),
        ("fprintf(fp, userfmt);", "C-002"),
        ("syslog(LOG_INFO, msg);", "C-002"),
        ('char *api_key = "abc123xyz999";', "C-003"),
        ('#define SECRET_TOKEN "abc123xyz999"', "C-003"),
        ("password = \"hunter2xyz\";", "C-003"),
        ("system(cmd);", "C-004"),
        ("popen(cmd, \"r\");", "C-004"),
        ("int session_token = rand();", "C-005"),
        ("csrf_key = rand();", "C-005"),
        ("char *p = alloca(n);", "C-006"),
    ],
)
def test_individual_patterns(src: str, expected: str) -> None:
    assert expected in _ids(src)


@pytest.mark.parametrize(
    "src",
    [
        "fgets(buf, n, stdin);",
        "strncpy(dst, src, n);",
        'printf("%s", userfmt);',
        'fprintf(fp, "%s", userfmt);',
        'char *api_key_path = "/etc/keys/api.pem";',
        '#define PUBLIC_NAME "not-a-secret-value"',
        'const char *g_public_name = "not-a-secret-value";',
        'char *args[] = {"tar", path, NULL}; execv("/bin/tar", args);',
        "int dice_roll = rand();",  # not a security-named var
        "int x = 5;",
        "char *p = alloca(64);",  # constant size
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert _ids(src) == set()


def test_gets_is_critical_others_are_high() -> None:
    gets_v = next(v for v in scan_c_source("gets(buf);", "s.c") if v.rule_id == "C-001")
    strcpy_v = next(v for v in scan_c_source("strcpy(a,b);", "s.c") if v.rule_id == "C-001")
    assert gets_v.severity.value == "CRITICAL"
    assert strcpy_v.severity.value == "HIGH"


# --------------------------------------------------------------------------- #
# C vs C++ grammar selection
# --------------------------------------------------------------------------- #
def test_cpp_suffix_uses_cpp_grammar() -> None:
    src = 'std::string s; strcpy(a, b);'
    assert "C-001" in _ids(src, "snippet.cpp")


def test_header_suffix_is_scanned() -> None:
    assert "C-001" in _ids("gets(buf);", "snippet.h")


def test_unknown_suffix_returns_empty() -> None:
    assert scan_c_source("gets(buf);", "snippet.py") == []


# --------------------------------------------------------------------------- #
# suppression + config
# --------------------------------------------------------------------------- #
def test_inline_nosec_suppression() -> None:
    assert _ids("gets(buf); // nosec") == set()
    assert _ids("gets(buf); // nosec C-001") == set()
    assert "C-001" in _ids("gets(buf); // nosec C-999")


def test_noqa_must_name_the_rule() -> None:
    assert "C-001" in _ids("gets(buf); // noqa")
    assert _ids("gets(buf); // noqa: C-001") == set()


def test_ruleconfig_disables_and_overrides_severity() -> None:
    cfg = RuleConfig(disabled=frozenset({"C-003"}), severity={"C-001": "LOW"})
    src = 'gets(buf); char *api_key = "abc123xyz999";'
    violations = scan_c_source(src, "s.c", config=cfg)
    ids = {v.rule_id: v for v in violations}
    assert "C-003" not in ids
    assert ids["C-001"].severity.value == "LOW"


# --------------------------------------------------------------------------- #
# mixed-language directory scan + CLI
# --------------------------------------------------------------------------- #
def test_directory_scan_covers_python_js_and_c(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("eval(x)\n")
    (tmp_path / "b.js").write_text("eval(y);\n")
    (tmp_path / "c.c").write_text("gets(buf);\n")

    result = scan_path(tmp_path, base_dir=tmp_path)
    assert {v.file_path for v in result.violations} == {"a.py", "b.js", "c.c"}
    assert result.files_scanned == 3


def test_cli_audit_c_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "vulnerable_sample.c"), "--no-llm"])
    assert res.exit_code == 1
    assert "C-001" in res.output and "C-004" in res.output


def test_cli_audit_clean_c_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "clean_sample.c"), "--no-llm"])
    assert res.exit_code == 0
