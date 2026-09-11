"""JS-001 .. JS-006: tree-sitter-backed JavaScript/TypeScript rules."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from app.js_scanner import scan_js_source
from app.main import cli
from app.static_scanner.engine import scan_path
from app.static_scanner.ruleconfig import RuleConfig

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _ids(src: str, suffix: str = "snippet.js") -> set[str]:
    return {v.rule_id for v in scan_js_source(src, suffix)}


# --------------------------------------------------------------------------- #
# fixtures: every rule fires, the safe file stays silent
# --------------------------------------------------------------------------- #
def test_vulnerable_js_triggers_every_rule() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.js", base_dir=FIXTURES)
    found = {v.rule_id for v in result.violations}
    for rule_id in ("JS-001", "JS-002", "JS-003", "JS-004", "JS-005", "JS-006"):
        assert rule_id in found, f"{rule_id} not detected; got {sorted(found)}"


def test_clean_js_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.js", base_dir=FIXTURES)
    assert result.violations == [], [
        (v.rule_id, v.line_number, v.message) for v in result.violations
    ]


def test_jsx_dangerously_set_inner_html() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.jsx", base_dir=FIXTURES)
    assert {v.rule_id for v in result.violations} == {"JS-002"}


def test_clean_jsx_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_sample.jsx", base_dir=FIXTURES)
    assert result.violations == []


def test_snippets_are_attached() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.js", base_dir=FIXTURES)
    for v in result.violations:
        assert v.snippet.strip(), f"{v.rule_id} has no snippet"


# --------------------------------------------------------------------------- #
# individual patterns
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src, expected",
    [
        ("eval(x);", "JS-001"),
        ('setTimeout("doStuff()", 10);', "JS-001"),
        ('setInterval(`run(${cmd})`, 10);', "JS-001"),
        ("new Function(src)();", "JS-001"),
        ("el.innerHTML = data;", "JS-002"),
        ("el.outerHTML = data;", "JS-002"),
        ('document.write("<b>" + name + "</b>");', "JS-002"),
        ("node.insertAdjacentHTML('beforeend', data);", "JS-002"),
        ('const apiKey = "sk-live-abcdefghijklmnop";', "JS-003"),
        ('cfg.password = "hunter2xyz";', "JS-003"),
        ('const o = { token: "abcd1234efgh5678" };', "JS-003"),
        ('exec("rm -rf " + dir);', "JS-004"),
        ('execSync(`build ${target}`);', "JS-004"),
        ("const sessionToken = Math.random().toString(36);", "JS-005"),
        ("obj.csrfToken = Math.random();", "JS-005"),
        ("const agent = { rejectUnauthorized: false };", "JS-006"),
        ('process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";', "JS-006"),
    ],
)
def test_individual_patterns(src: str, expected: str) -> None:
    assert expected in _ids(src)


@pytest.mark.parametrize(
    "src",
    [
        "JSON.parse(x);",
        "setTimeout(doStuff, 10);",
        "setInterval(runner, 10);",
        "el.textContent = data;",
        "document.title = name;",
        "node.insertAdjacentText('beforeend', data);",
        'const apiKeyPath = "/etc/keys/api.pem";',
        'const publicKey = "not-a-real-secret-value";',
        'execFile("tar", ["czf", "backup.tgz", path]);',
        "const id = crypto.randomUUID();",
        "const jitter = Math.random() * 100;",  # not a security-named var
        "const agent = { rejectUnauthorized: true };",
        'process.env.NODE_TLS_REJECT_UNAUTHORIZED = "1";',
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert _ids(src) == set()


# --------------------------------------------------------------------------- #
# TypeScript / TSX grammar selection
# --------------------------------------------------------------------------- #
def test_typescript_suffix_uses_ts_grammar() -> None:
    src = 'const apiKey: string = "sk-live-abcdefghijklmnop";'
    assert "JS-003" in _ids(src, "snippet.ts")


def test_tsx_suffix_parses_jsx() -> None:
    src = "export const C = () => <div dangerouslySetInnerHTML={{__html: h}} />;"
    assert "JS-002" in _ids(src, "snippet.tsx")


def test_unknown_suffix_returns_empty() -> None:
    assert scan_js_source("eval(x)", "snippet.py") == []


# --------------------------------------------------------------------------- #
# suppression + config (same conventions as the Python engine)
# --------------------------------------------------------------------------- #
def test_inline_nosec_suppression() -> None:
    assert _ids("eval(x); // nosec") == set()
    assert _ids("eval(x); // nosec JS-001") == set()
    assert "JS-001" in _ids("eval(x); // nosec JS-999")


def test_noqa_must_name_the_rule() -> None:
    assert "JS-001" in _ids("eval(x); // noqa")
    assert _ids("eval(x); // noqa: JS-001") == set()


def test_ruleconfig_disables_and_overrides_severity() -> None:
    cfg = RuleConfig(disabled=frozenset({"JS-003"}), severity={"JS-001": "LOW"})
    src = 'eval(x); const apiKey = "sk-live-abcdefghijklmnop";'
    violations = scan_js_source(src, "s.js", config=cfg)
    ids = {v.rule_id: v for v in violations}
    assert "JS-003" not in ids
    assert ids["JS-001"].severity.value == "LOW"


# --------------------------------------------------------------------------- #
# mixed-language directory scan + CLI
# --------------------------------------------------------------------------- #
def test_directory_scan_covers_python_and_js(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("eval(x)\n")
    (tmp_path / "b.js").write_text("eval(y);\n")
    (tmp_path / "c.ts").write_text('const secret = "abcd1234efgh5678";\n')

    result = scan_path(tmp_path, base_dir=tmp_path)
    assert {v.file_path for v in result.violations} == {"a.py", "b.js", "c.ts"}
    assert result.files_scanned == 3


def test_cli_audit_js_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "vulnerable_sample.js"), "--no-llm"])
    assert res.exit_code == 1
    assert "JS-001" in res.output and "JS-006" in res.output


def test_cli_audit_clean_js_file() -> None:
    res = runner.invoke(cli, ["audit", str(FIXTURES / "clean_sample.js"), "--no-llm"])
    assert res.exit_code == 0
