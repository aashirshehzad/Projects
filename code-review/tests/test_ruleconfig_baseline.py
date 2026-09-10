"""RuleConfig (pyproject) + baseline suppression."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from app.main import cli
from app.static_scanner import baseline
from app.static_scanner.ast_rules import scan_source
from app.static_scanner.engine import scan_path
from app.static_scanner.ruleconfig import RuleConfig

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()

_DIRTY = 'eval(x)\npassword = "hunter2xyz"\n'


# --- RuleConfig ----------------------------------------------------------
def test_ruleconfig_missing_or_empty_is_noop(tmp_path: Path) -> None:
    assert RuleConfig.load(tmp_path / "nope.toml") == RuleConfig()
    (tmp_path / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    assert RuleConfig.load(tmp_path / "pyproject.toml").is_active() is False


def test_ruleconfig_disables_rule(tmp_path: Path) -> None:
    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text('[tool.code-auditor]\ndisabled_rules = ["SEC-001"]\n')
    cfg = RuleConfig.load(cfg_file)
    ids = {v.rule_id for v in scan_source(_DIRTY, "s.py", config=cfg)}
    assert ids == {"SEC-003"}


def test_ruleconfig_overrides_severity(tmp_path: Path) -> None:
    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text('[tool.code-auditor.severity]\nSEC-003 = "LOW"\n')
    cfg = RuleConfig.load(cfg_file)
    sev = {
        v.rule_id: v.severity.value
        for v in scan_source(_DIRTY, "s.py", config=cfg)
    }
    assert sev["SEC-003"] == "LOW"
    assert sev["SEC-001"] == "CRITICAL"  # untouched


def test_ruleconfig_ignores_garbage(tmp_path: Path) -> None:
    cfg_file = tmp_path / "pyproject.toml"
    cfg_file.write_text(
        '[tool.code-auditor]\ndisabled_rules = ["SEC-999", "nonsense"]\n'
        '[tool.code-auditor.severity]\nSEC-002 = "BOGUS"\n'
    )
    cfg = RuleConfig.load(cfg_file)
    assert cfg.disabled == frozenset()
    assert cfg.severity == {}


# --- baseline --------------------------------------------------------
def test_baseline_roundtrip_suppresses_known(tmp_path: Path) -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    assert result.violations

    bfile = tmp_path / "baseline.json"
    written = baseline.write(bfile, result.violations)
    assert written == len(result.violations)

    known = baseline.load(bfile)
    kept, suppressed = baseline.apply(list(result.violations), known)
    assert kept == []
    assert suppressed == len(result.violations)


def test_baseline_lets_new_findings_through(tmp_path: Path) -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    bfile = tmp_path / "baseline.json"
    baseline.write(bfile, result.violations[:-1])  # omit one

    kept, suppressed = baseline.apply(list(result.violations), baseline.load(bfile))
    assert len(kept) == 1
    assert suppressed == len(result.violations) - 1


# --- CLI wiring --------------------------------------------------------
def test_cli_update_baseline_then_clean(tmp_path: Path) -> None:
    bfile = tmp_path / "b.json"
    r1 = runner.invoke(
        cli,
        ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm",
         "--baseline", str(bfile), "--update-baseline"],
    )
    assert r1.exit_code == 0
    assert bfile.is_file()

    r2 = runner.invoke(
        cli,
        ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm",
         "--baseline", str(bfile)],
    )
    assert r2.exit_code == 0  # every finding is baselined -> clean
    assert "suppressed by baseline" in r2.output


def test_cli_update_baseline_without_path_errors() -> None:
    r = runner.invoke(
        cli, ["audit", str(FIXTURES / "vulnerable_sample.py"), "--no-llm",
              "--update-baseline"],
    )
    assert r.exit_code == 2
