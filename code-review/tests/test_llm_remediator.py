"""Mocked tests for Stage 3: provider dispatch, schema round-trip, error mapping.

No network: every provider is fed a fake transport object.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import LLMRemediationError
from app.llm_remediation.providers import GeminiProvider, OpenAIProvider
from app.llm_remediation.remediator import Remediator, build_unreviewed_report
from app.llm_remediation.schemas import AuditRemediationReport, IssueRemediation
from app.static_scanner.ast_rules import scan_source
from app.static_scanner.engine import scan_path

FIXTURES = Path(__file__).parent / "fixtures"


def _violations():
    return scan_source(
        'password = "supersecretvalue"\neval(user_input)\n', "sample.py"
    )


def _report_for(violations, *, bad_count=999) -> AuditRemediationReport:
    return AuditRemediationReport(
        summary="ok",
        total_violations_evaluated=bad_count,  # deliberately wrong; must be corrected
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


def _gemini_settings(**overrides) -> Settings:
    return Settings(
        llm_provider="gemini", gemini_api_key="k", _env_file=None, **overrides
    )


def _openai_settings(**overrides) -> Settings:
    return Settings(
        llm_provider="openai",
        openai_api_key="sk-test",
        llm_model="gpt-4o-mini",
        _env_file=None,
        **overrides,
    )


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _FakeGeminiModels:
    def __init__(self, *, parsed=None, text=None, boom=None):
        self._parsed, self._text, self._boom = parsed, text, boom
        self.last_kwargs: dict | None = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        if self._boom is not None:
            raise self._boom
        return types.SimpleNamespace(parsed=self._parsed, text=self._text)


def _fake_gemini(**kw):
    models = _FakeGeminiModels(**kw)
    return types.SimpleNamespace(models=models), models


class _FakeOpenAIParse:
    def __init__(self, report=None, *, refusal=None, boom=None):
        self._report, self._refusal, self._boom = report, refusal, boom
        self.last_kwargs: dict | None = None

    def __call__(self, **kwargs):
        self.last_kwargs = kwargs
        if self._boom is not None:
            raise self._boom
        message = types.SimpleNamespace(parsed=self._report, refusal=self._refusal)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _fake_openai(parse_callable):
    completions = types.SimpleNamespace(parse=parse_callable)
    chat = types.SimpleNamespace(completions=completions)
    return types.SimpleNamespace(beta=types.SimpleNamespace(chat=chat))


# --------------------------------------------------------------------------- #
# Gemini (default provider)
# --------------------------------------------------------------------------- #
def test_gemini_happy_path_parses_and_fixes_count() -> None:
    violations = _violations()
    client, models = _fake_gemini(parsed=_report_for(violations))
    report = Remediator(settings=_gemini_settings(), client=client).remediate(violations)

    assert report.total_violations_evaluated == len(violations)
    assert models.last_kwargs["model"] == "gemini-3.5-flash-lite"
    cfg = models.last_kwargs["config"]
    assert cfg["response_schema"] is AuditRemediationReport
    assert cfg["response_mime_type"] == "application/json"
    assert cfg["temperature"] == 0.0


def test_gemini_falls_back_to_raw_json_text() -> None:
    violations = _violations()
    raw = _report_for(violations).model_dump_json()
    client, _ = _fake_gemini(parsed=None, text=raw)
    report = Remediator(settings=_gemini_settings(), client=client).remediate(violations)
    assert len(report.remediations) == len(violations)


def test_gemini_transport_error_is_wrapped() -> None:
    client, _ = _fake_gemini(boom=RuntimeError("deadline exceeded"))
    with pytest.raises(LLMRemediationError, match="deadline exceeded"):
        Remediator(settings=_gemini_settings(), client=client).remediate(_violations())


def test_gemini_empty_output_raises() -> None:
    client, _ = _fake_gemini(parsed=None, text=None)
    with pytest.raises(LLMRemediationError, match="no parseable"):
        Remediator(settings=_gemini_settings(), client=client).remediate(_violations())


def test_default_provider_is_gemini() -> None:
    assert Settings(_env_file=None).llm_provider == "gemini"
    assert isinstance(
        Remediator(settings=_gemini_settings(), client=_fake_gemini()[0])._provider,
        GeminiProvider,
    )


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #
def test_openai_happy_path() -> None:
    violations = _violations()
    fake = _FakeOpenAIParse(_report_for(violations))
    r = Remediator(settings=_openai_settings(), client=_fake_openai(fake))
    report = r.remediate(violations)

    assert isinstance(r._provider, OpenAIProvider)
    assert report.total_violations_evaluated == len(violations)
    assert fake.last_kwargs["model"] == "gpt-4o-mini"
    assert fake.last_kwargs["response_format"] is AuditRemediationReport
    assert len(fake.last_kwargs["messages"]) == 2


def test_openai_refusal_becomes_domain_error() -> None:
    fake = _FakeOpenAIParse(None, refusal="no")
    with pytest.raises(LLMRemediationError, match="refused"):
        Remediator(settings=_openai_settings(), client=_fake_openai(fake)).remediate(
            _violations()
        )


def test_openai_transport_exception_is_wrapped() -> None:
    fake = _FakeOpenAIParse(None, boom=RuntimeError("connection reset"))
    with pytest.raises(LLMRemediationError, match="connection reset"):
        Remediator(settings=_openai_settings(), client=_fake_openai(fake)).remediate(
            _violations()
        )


# --------------------------------------------------------------------------- #
# provider-agnostic
# --------------------------------------------------------------------------- #
def test_empty_violations_short_circuits_without_calling_model() -> None:
    client, models = _fake_gemini(boom=AssertionError("should not be called"))
    report = Remediator(settings=_gemini_settings(), client=client).remediate([])
    assert report.total_violations_evaluated == 0
    assert report.remediations == []
    assert models.last_kwargs is None


def test_batch_is_capped_by_max_violations_to_llm() -> None:
    violations = _violations()
    assert len(violations) >= 2
    client, _ = _fake_gemini(parsed=_report_for([]))
    settings = _gemini_settings(max_violations_to_llm=1)
    report = Remediator(settings=settings, client=client).remediate(violations)
    assert report.total_violations_evaluated == 1


def test_unreviewed_report_is_conservative() -> None:
    result = scan_path(FIXTURES / "vulnerable_sample.py", base_dir=FIXTURES)
    report = build_unreviewed_report(result.violations, reason="skipped (--no-llm)")
    assert report.total_violations_evaluated == len(result.violations)
    assert all(r.is_exploitable for r in report.remediations)
    assert all(r.patched_code == "" for r in report.remediations)
