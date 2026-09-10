"""Stage 3 orchestration.

One violation batch -> one provider call -> one validated
``AuditRemediationReport``. Provider selection (Gemini / OpenAI) lives in
``providers.py``; this module only owns batching and the empty-input case.
"""

from __future__ import annotations

from typing import Any

from app.core.config import Settings, get_settings
from app.llm_remediation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.llm_remediation.providers import LLMProvider, get_provider
from app.llm_remediation.schemas import AuditRemediationReport, IssueRemediation
from app.static_scanner.ast_rules import Violation


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
        client: Any | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._provider = provider or get_provider(self.settings, client=client)

    def remediate(self, violations: list[Violation]) -> AuditRemediationReport:
        if not violations:
            return AuditRemediationReport(
                summary="No static violations were found; nothing to remediate.",
                total_violations_evaluated=0,
                remediations=[],
            )

        batch = violations[: self.settings.max_violations_to_llm]
        report = self._provider.parse(SYSTEM_PROMPT, build_user_prompt(batch))

        # The scanner is the source of truth for how many issues went in.
        report.total_violations_evaluated = len(batch)
        return report


def remediate(
    violations: list[Violation],
    *,
    settings: Settings | None = None,
    client: Any | None = None,
    provider: LLMProvider | None = None,
) -> AuditRemediationReport:
    """Module-level convenience wrapper around :class:`Remediator`."""
    return Remediator(
        settings=settings, client=client, provider=provider
    ).remediate(violations)
