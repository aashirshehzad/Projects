"""Unit tests for the deterministic AST rules SEC-001 .. SEC-010."""

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
        ("requests.get(u, verify=False)", "SEC-006"),
        ("ssl._create_unverified_context()", "SEC-006"),
        ("hashlib.md5(b).hexdigest()", "SEC-007"),
        ('hashlib.new("sha1", b)', "SEC-007"),
        ("cipher = AES.new(key, AES.MODE_ECB)", "SEC-007"),
        ("auth_token = random.getrandbits(64)", "SEC-007"),
        ("app.run(debug=True)", "SEC-008"),
        ('srv.run(host="0.0.0.0")', "SEC-008"),
        ("DEBUG = True", "SEC-008"),
        ('ALLOWED_HOSTS = ["*"]', "SEC-008"),
        ('add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)', "SEC-009"),
        ("CORS_ORIGIN_ALLOW_ALL = True", "SEC-009"),
        ("marshal.loads(b)", "SEC-010"),
        ("yaml.unsafe_load(s)", "SEC-010"),
        ("torch.load(p)", "SEC-010"),
        ("numpy.load(p, allow_pickle=True)", "SEC-010"),
        ("pandas.read_pickle(p)", "SEC-010"),
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
        "requests.get(u, verify=True)",
        "requests.get(u, timeout=5)",
        "hashlib.sha256(b).hexdigest()",
        'hashlib.new("sha256", b)',
        "cipher = AES.new(key, AES.MODE_GCM)",
        "jitter = random.random()",             # name not security-sensitive
        "retry_delay = random.uniform(1, 3)",
        "app.run(debug=False)",
        'srv.run(host="127.0.0.1")',
        "DEBUG = False",
        'ALLOWED_HOSTS = ["example.com"]',
        'add_middleware(CORSMiddleware, allow_origins=["https://x.com"], allow_credentials=True)',
        "yaml.safe_load(s)",
        "torch.load(p, weights_only=True)",
        "numpy.load(p)",
        "numpy.load(p, allow_pickle=False)",
    ],
)
def test_safe_patterns_do_not_fire(src: str) -> None:
    assert scan_source(src, "snippet.py") == []


def test_insecure_extra_fixture_triggers_006_to_010() -> None:
    result = scan_path(FIXTURES / "insecure_extra.py", base_dir=FIXTURES)
    found = _rule_ids(result.violations)
    for rule_id in ("SEC-006", "SEC-007", "SEC-008", "SEC-009", "SEC-010"):
        assert rule_id in found, f"{rule_id} not detected; got {sorted(found)}"


def test_inline_nosec_suppression() -> None:
    bare = "eval(x)  # nosec\n"
    assert scan_source(bare, "s.py") == []

    named = "eval(x)  # nosec SEC-001\n"
    assert scan_source(named, "s.py") == []

    wrong_id = "eval(x)  # nosec SEC-999\n"
    assert _rule_ids(scan_source(wrong_id, "s.py")) == {"SEC-001"}


def test_noqa_must_name_the_rule() -> None:
    assert _rule_ids(scan_source("eval(x)  # noqa\n", "s.py")) == {"SEC-001"}
    assert scan_source("eval(x)  # noqa: SEC-001\n", "s.py") == []


def test_violations_are_severity_sorted() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    ranks = [v.severity.rank for v in result.violations]
    assert ranks == sorted(ranks)
    assert Severity.CRITICAL in {v.severity for v in result.violations}
