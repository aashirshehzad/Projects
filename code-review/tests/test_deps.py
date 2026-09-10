"""Dependency scanner: manifest parsing, OSV mapping, CLI wiring -- all offline."""

from __future__ import annotations

import types
from pathlib import Path

import pytest
import requests
from click.testing import CliRunner

from app.deps import manifests
from app.deps.osv import Advisory, _parse_detail, query
from app.deps.scanner import DepScanError, scan_dependencies
from app.main import cli

runner = CliRunner()


# --------------------------------------------------------------------------- #
# manifest parsing
# --------------------------------------------------------------------------- #
def test_requirements_txt_parsing(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "# comment\n"
        "Flask==2.0.1\n"
        "requests==2.25.1  # inline note\n"
        "urllib3>=1.26        # range -> skipped\n"
        "-e .\n"
        "PyYAML==5.3.1 ; python_version < '3.10'\n"
        "cryptography==3.4.7 \\\n    --hash=sha256:deadbeef\n"
    )
    reqs = manifests.discover(tmp_path)
    got = {(r.name, r.version) for r in reqs}
    assert got == {
        ("flask", "2.0.1"),
        ("requests", "2.25.1"),
        ("pyyaml", "5.3.1"),
        ("cryptography", "3.4.7"),
    }
    flask = next(r for r in reqs if r.name == "flask")
    assert flask.line_number == 2 and flask.manifest == "requirements.txt"


def test_poetry_lock_parsing(tmp_path: Path) -> None:
    (tmp_path / "poetry.lock").write_text(
        '[[package]]\nname = "jinja2"\nversion = "2.11.2"\n\n'
        '[[package]]\nname = "click"\nversion = "8.1.7"\n'
    )
    got = {(r.name, r.version) for r in manifests.discover(tmp_path)}
    assert got == {("jinja2", "2.11.2"), ("click", "8.1.7")}


def test_pipfile_lock_parsing(tmp_path: Path) -> None:
    (tmp_path / "Pipfile.lock").write_text(
        '{"default": {"django": {"version": "==3.2.0"}},'
        ' "develop": {"pytest": {"version": "==7.0.0"}}}'
    )
    got = {(r.name, r.version) for r in manifests.discover(tmp_path)}
    assert got == {("django", "3.2.0"), ("pytest", "7.0.0")}


def test_normalize_and_dedupe(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("Foo.Bar==1.0\n")
    (tmp_path / "requirements-dev.txt").write_text("foo_bar==1.0\nextra==2.0\n")
    got = {(r.name, r.version) for r in manifests.discover(tmp_path)}
    assert got == {("foo-bar", "1.0"), ("extra", "2.0")}


# --------------------------------------------------------------------------- #
# OSV detail parsing
# --------------------------------------------------------------------------- #
def test_parse_detail_extracts_severity_and_fix() -> None:
    raw = {
        "id": "GHSA-aaaa",
        "aliases": ["CVE-2021-1111", "PYSEC-2021-1"],
        "summary": "Remote code execution in widget",
        "severity": [{"type": "CVSS_V3", "score": "9.1"}],
        "affected": [
            {
                "package": {"name": "widget"},
                "ranges": [{"events": [{"introduced": "0"}, {"fixed": "1.4.2"}]}],
            }
        ],
    }
    adv = _parse_detail(raw, "widget")
    assert adv.severity == "CRITICAL"
    assert adv.fixed_versions == ["1.4.2"]
    assert adv.best_id == "CVE-2021-1111"


def test_parse_detail_defaults_to_high_without_severity() -> None:
    adv = _parse_detail({"id": "OSV-1", "affected": []}, "x")
    assert adv.severity == "HIGH"


# --------------------------------------------------------------------------- #
# fake OSV transport
# --------------------------------------------------------------------------- #
class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, batch, vulns):
        self._batch, self._vulns = batch, vulns
        self.calls = 0

    def post(self, url, json=None, timeout=None):
        self.calls += 1
        return _Resp(self._batch)

    def get(self, url, timeout=None):
        vid = url.rstrip("/").rsplit("/", 1)[-1]
        return _Resp(self._vulns[vid])


def _fake_session():
    batch = {"results": [{"vulns": [{"id": "GHSA-x"}]}, {}]}
    vulns = {
        "GHSA-x": {
            "id": "GHSA-x",
            "aliases": ["CVE-2020-9999"],
            "summary": "SSTI in templater",
            "severity": [{"type": "CVSS_V3", "score": "8.2"}],
            "affected": [
                {
                    "package": {"name": "templater"},
                    "ranges": [{"events": [{"introduced": "0"}, {"fixed": "2.0.0"}]}],
                }
            ],
        }
    }
    return _FakeSession(batch, vulns)


def test_query_maps_advisories_to_requirements() -> None:
    reqs = [
        manifests.Requirement("templater", "1.9.0", "requirements.txt", 3),
        manifests.Requirement("safe-pkg", "1.0.0", "requirements.txt", 4),
    ]
    hits = query(reqs, session=_fake_session())
    assert set(hits) == {("templater", "1.9.0")}
    (adv,) = hits[("templater", "1.9.0")]
    assert adv.best_id == "CVE-2020-9999" and adv.severity == "HIGH"


def test_scan_dependencies_returns_dep_violations(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("templater==1.9.0\nsafe-pkg==1.0.0\n")
    violations = scan_dependencies(str(tmp_path), session=_fake_session())
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == "DEP-001"
    assert v.file_path == "requirements.txt"
    assert "CVE-2020-9999" in v.message and "2.0.0" in v.message


def test_scan_dependencies_no_manifest_is_empty(tmp_path: Path) -> None:
    assert scan_dependencies(str(tmp_path), session=_fake_session()) == []


def test_scan_dependencies_wraps_network_error(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("templater==1.9.0\n")

    class Boom:
        def post(self, *a, **k):
            raise requests.ConnectionError("no route to host")

    with pytest.raises(DepScanError, match="OSV.dev query failed"):
        scan_dependencies(str(tmp_path), session=Boom())


# --------------------------------------------------------------------------- #
# CLI wiring
# --------------------------------------------------------------------------- #
def test_cli_deps_flag_reports_and_fails(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("templater==1.9.0\n")
    (tmp_path / "clean.py").write_text("x = 1\n")

    def fake_scan(root, *, session=None):
        return scan_dependencies(str(root), session=_fake_session())

    monkeypatch.setattr("app.main.scan_dependencies", fake_scan, raising=False)
    monkeypatch.setattr("app.deps.scan_dependencies", fake_scan)

    res = runner.invoke(cli, ["audit", str(tmp_path), "--no-llm", "--deps"])
    assert res.exit_code == 1
    assert "DEP-001" in res.output
    assert "OSV.dev" in res.output


def test_cli_deps_failure_only_warns(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("templater==1.9.0\n")
    (tmp_path / "clean.py").write_text("x = 1\n")

    def boom(root, *, session=None):
        raise DepScanError("OSV.dev query failed: timeout")

    monkeypatch.setattr("app.deps.scan_dependencies", boom)
    res = runner.invoke(cli, ["audit", str(tmp_path), "--no-llm", "--deps"])
    assert res.exit_code == 0
    assert "dependency scan skipped" in res.output
