"""OpenAI-backed remediation client (Stage 3).

One violation batch -> one ``chat.completions.parse`` call -> one validated
``AuditRemediationReport``. No multi-turn agent loop, no ret['tool'] chatter.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings, get_settings
from app.core.exceptions import LLMRemediationError
from app.llm_remediation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm_remediation.schemas import AuditRemediationReport, IssueRemediation
from app.static_scanner.ast_rules import Violation


class _ParseClient(Protocol):
    """Structural type for the slice of the OpenAI client we touch (eases mocking)."""

    @property
    def beta(self) -> Any: ...


def _default_client(settings: Settings) -> _ParseClient:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - import guard
        raise LLMRemediationError(
            "The `openai` package is not installed; run `pip install openai` "
            "or pass --no-llm."
        ) from exc
    return OpenAI(api_key=settings.require_openai_key(), timeout=settings.llm_timeout_seconds)


def build_unreviewed_report(
    violations: list[Violation],
    *,
    reason: str = "skipped (--no-llm)",
) -> AuditRemediationReport:
    """Static-only fallback -- no fixes, no false-positive triage.

    Used both for ``--no-llm`` and when the Stage 3 call fails; *reason* is
    surfaced in the summary so the two cases are distinguishable.
    """
    return AuditRemediationReport(
        summary=(
            f"{len(violations)} static violation(s) found. LLM remediation was "
            f"{reason}; findings are unverified and unpatched."
        ),
        total_violations_evaluated=len(violations),
        remediations=[
            IssueRemediation(
                rule_id=v.rule_id,
                file_path=v.file_path,
                line_number=v.line_number,
                is_exploitable=True,
                root_cause=v.message,
                patched_code="",
                unit_test="",
            )
            for v in violations
        ],
    )


class Remediator:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: _ParseClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def client(self) -> _ParseClient:
        if self._client is None:
            self._client = _default_client(self.settings)
        return self._client

    def remediate(self, violations: list[Violation]) -> AuditRemediationReport:
        if not violations:
            return AuditRemediationReport(
                summary="No static violations were found; nothing to remediate.",
                total_violations_evaluated=0,
                remediations=[],
            )

        batch = violations[: self.settings.max_violations_to_llm]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(batch)},
        ]

        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.settings.llm_model,
                messages=messages,
                response_format=AuditRemediationReport,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
        except LLMRemediationError:
            raise
        except Exception as exc:  # network / API / timeout
            raise LLMRemediationError(f"Remediation model call failed: {exc}") from exc

        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMRemediationError(
                f"Model refused to remediate: {choice.message.refusal}"
            )
        report = choice.message.parsed
        if report is None:
            raise LLMRemediationError("Model returned no parseable structured output.")

        # The scanner is the source of truth for how many issues went in.
        report.total_violations_evaluated = len(batch)
        return report


def remediate(
    violations: list[Violation],
    *,
    settings: Settings | None = None,
    client: _ParseClient | None = None,
) -> AuditRemediationReport:
    """Module-level convenience wrapper around :class:`Remediator`."""
    return Remediator(settings=settings, client=client).remediate(violations)
