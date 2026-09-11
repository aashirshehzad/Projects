"""JAVA-001 .. JAVA-006: tree-sitter-backed Java rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from app.java_scanner import scan_java_source
from app.main import cli
from app.static_scanner.engine import scan_path
from app.static_scanner.ruleconfig import RuleConfig

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _ids(src: str, suffix: str = "Snippet.java") -> set[str]:
    return {v.rule_id for v in scan_java_source(src, suffix)}


# --------------------------------------------------------------------------- #
# fixtures: every rule fires, the safe file stays silent
# --------------------------------------------------------------------------- #
def test_vulnerable_java_triggers_every_rule() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.java", base_dir=FIXTURES)
    found = {v.rule_id for v in result.violations}
    for rule_id in ("JAVA-001", "JAVA-002", "JAVA-003", "JAVA-004", "JAVA-005", "JAVA-006"):
        assert rule_id in found, f"{rule_id} not detected; got {sorted(found)}"


def test_clean_java_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.java", base_dir=FIXTURES)
    assert result.violations == [], [
        (v.rule_id, v.line_number, v.message) for v in result.violations
    ]


def test_snippets_are_attached() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.java", base_dir=FIXTURES)
    for v in result.violations:
        assert v.snippet.strip(), f"{v.rule_id} has no snippet"


# --------------------------------------------------------------------------- #
# individual patterns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src, expected",
    [
        ("class X { void f(ObjectInputStream in) throws Exception { in.readObject(); } }", "JAVA-001"),
        (
            "class X { void f(Statement s, String id) throws Exception { "
            's.executeQuery("SELECT * FROM t WHERE id=" + id); } }',
            "JAVA-002",
        ),
        ('class X { String apiKey = "abcd1234efgh5678"; }', "JAVA-003"),
        ('class X { void f() { password = "hunter2xyz"; } }', "JAVA-003"),
        ("class X { void f(String cmd) throws Exception { Runtime.getRuntime().exec(cmd); } }", "JAVA-004"),
        ('class X { void f() throws Exception { MessageDigest.getInstance("MD5"); } }', "JAVA-005"),
        ('class X { void f() throws Exception { Cipher.getInstance("AES/ECB/PKCS5Padding"); } }', "JAVA-005"),
        ("class X { void f() { int sessionToken = new Random().nextInt(); } }", "JAVA-006"),
    ],
)
def test_individual_patterns(src: str, expected: str) -> None:
    assert expected in _ids(src)


@pytest.mark.parametrize(
    "src",
    [
        "class X { void f(ObjectMapper m, String j) throws Exception { m.readValue(j, Object.class); } }",
        (
            "class X { void f(PreparedStatement s) throws Exception { "
            "s.setString(1, \"x\"); s.executeQuery(); } }"
        ),
        'class X { String apiKeyPath = "/etc/keys/api.pem"; }',
        "class X { void f(String[] args) throws Exception { new ProcessBuilder(args).start(); } }",
        'class X { void f() throws Exception { MessageDigest.getInstance("SHA-256"); } }',
        "class X { void f() { SecureRandom r = new SecureRandom(); int id = r.nextInt(); } }",
        "class X { void f() { int diceRoll = new Random().nextInt(6); } }",  # not security-named
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert _ids(src) == set()


def test_unknown_suffix_returns_empty() -> None:
    assert scan_java_source("class X {}", "Snippet.py") == []


# --------------------------------------------------------------------------- #
# suppression + config
# --------------------------------------------------------------------------- #
def test_inline_nosec_suppression() -> None:
    src = "class X { void f(ObjectInputStream in) throws Exception { in.readObject(); } }  // nosec"
    assert _ids(src) == set()

    named = "class X { void f(ObjectInputStream in) throws Exception { in.readObject(); // nosec JAVA-001\n} }"
    assert _ids(named) == set()


def test_noqa_must_name_the_rule() -> None:
    src = "class X { void f(ObjectInputStream in) throws Exception { in.readObject(); // noqa\n} }"
    assert "JAVA-001" in _ids(src)

    named = "class X { void f(ObjectInputStream in) throws Exception { in.readObject(); // noqa: JAVA-001\n} }"
    assert _ids(named) == set()


def test_ruleconfig_disables_and_overrides_severity() -> None:
    cfg = RuleConfig(disabled=frozenset({"JAVA-001"}), severity={"JAVA-005": "LOW"})
    src = (
        "class X { "
        "void f(ObjectInputStream in) throws Exception { in.readObject(); } "
        'void g() throws Exception { MessageDigest.getInstance("MD5"); } '
        "}"
    )
    violations = scan_java_source(src, "s.java", config=cfg)
    ids = {v.rule_id: v for v in violations}
    assert "JAVA-001" not in ids
    assert ids["JAVA-005"].severity.value == "LOW"


# --------------------------------------------------------------------------- #
# mixed-language directory scan + CLI
# --------------------------------------------------------------------------- #
def test_directory_scan_covers_all_four_languages(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("eval(x)\n")
    (tmp_path / "b.js").write_text("eval(y);\n")
    (tmp_path / "c.c").write_text("gets(buf);\n")
    (tmp_path / "D.java").write_text(
        "class D { void f(String cmd) throws Exception { Runtime.getRuntime().exec(cmd); } }\n"
    )

    result = scan_path(tmp_path, base_dir=tmp_path)
    assert {v.file_path for v in result.violations} == {"a.py", "b.js", "c.c", "D.java"}
    assert result.files_scanned == 4


def test_cli_audit_java_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "vulnerable_sample.java"), "--no-llm"])
    assert res.exit_code == 1
    assert "JAVA-001" in res.output and "JAVA-004" in res.output


def test_cli_audit_clean_java_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "clean_sample.java"), "--no-llm"])
    assert res.exit_code == 0
