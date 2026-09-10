"""Mocked tests for Stage 3: schema round-trip, batching, error mapping."""

from __future__ import annotations

import types

import pytest

from app.core.config import Settings
from app.core.exceptions import LLMRemediationError
from app.llm_remediation.remediator import Remediator, build_unreviewed_report
from app.llm_remediation.schemas import AuditRemediationReport, IssueRemediation
from app.static_scanner.ast_rules import scan_source
from app.static_scanner.engine import scan_path


def _violations():
    return scan_source(
        'password = "supersecretvalue"\neval(user_input)\n', "sample.py"
    )


class _FakeParse:
    """Stand-in for ``client.beta.chat.completions.parse``."""

    def __init__(self, report: AuditRemediationReport | None, *, refusal=None, boom=None):
        self._report = report
        self._refusal = refusal
        self._boom = boom
        self.last_kwargs: dict | None = None

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        if self._boom is not None:
            raise self._boom
        message = types.SimpleNamespace(parsed=self._report, refusal=self._refusal)
        choice = types.SimpleNamespace(message=message)
        return types.SimpleNamespace(choices=[choice])


def _client_with(parse_callable) -> object:
    completions = types.SimpleNamespace(parse=parse_callable)
    chat = types.SimpleNamespace(completions=completions)
    beta = types.SimpleNamespace(chat=chat)
    return types.SimpleNamespace(beta=beta)


def _settings() -> Settings:
    return Settings(openai_api_key="sk-test", _env_file=None)


def test_happy_path_parses_and_overrides_count() -> None:
    violations = _violations()
    canned = AuditRemediationReport(
        summary="ok",
        total_violations_evaluated=999,  # deliberately wrong; must be corrected
        remediations=[
            IssueRemediation(
                rule_id=v.rule_id,
                file_path=v.file_path,
                line_number=v.line_number,
                is_exploitable=True,
                root_cause="rc",
                patched_code="x = 1",
                unit_test="def test_x():\n    assert True",
            )
            for v in violations
        ],
    )
    fake = _FakeParse(canned)
    report = Remediator(settings=_settings(), client=_client_with(fake)).remediate(violations)

    assert report.total_violations_evaluated == len(violations)
    assert fake.last_kwargs["model"] == "gpt-4o-mini"
    assert fake.last_kwargs["temperature"] == 0.0
    assert fake.last_kwargs["response_format"] is AuditRemediationReport
    assert len(fake.last_kwargs["messages"]) == 2


def test_empty_violations_short_circuits_without_calling_model() -> None:
    fake = _FakeParse(None, boom=AssertionError("should not be called"))
    report = Remediator(settings=_settings(), client=_client_with(fake)).remediate([])
    assert report.total_violations_evaluated == 0
    assert report.remediations == []


def test_batch_is_capped_by_max_violations_to_llm() -> None:
    settings = Settings(openai_api_key="sk-test", max_violations_to_llm=1, _env_file=None)
    violations = _violations()
    assert len(violations) >= 2
    canned = AuditRemediationReport(summary="s", total_violations_evaluated=0, remediations=[])
    fake = _FakeParse(canned)
    report = Remediator(settings=settings, client=_client_with(fake)).remediate(violations)
    assert report.total_violations_evaluated == 1


def test_refusal_becomes_domain_error() -> None:
    fake = _FakeParse(None, refusal="no")
    with pytest.raises(LLMRemediationError, match="refused"):
        Remediator(settings=_settings(), client=_client_with(fake)).remediate(_violations())


def test_transport_exception_is_wrapped() -> None:
    fake = _FakeParse(None, boom=RuntimeError("connection reset"))
    with pytest.raises(LLMRemediationError, match="connection reset"):
        Remediator(settings=_settings(), client=_client_with(fake)).remediate(_violations())


def test_unreviewed_report_is_conservative() -> None:
    result = scan_path(
        __import__("pathlib").Path(__file__).parent / "fixtures" / "vulnerable_sample.py",
    )
    report = build_unreviewed_report(result.violations)
    assert report.total_violations_evaluated == len(result.violations)
    assert all(r.is_exploitable for r in report.remediations)
    assert all(r.patched_code == "" for r in report.remediations)
