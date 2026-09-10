"""Pydantic contract for the remediation model's Structured Output.

The model is *required* to return an ``AuditRemediationReport``; anything that
does not parse is a hard failure, never a "best effort" string.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueRemediation(BaseModel):
    rule_id: str = Field(description="The static rule ID (e.g. SEC-001)")
    file_path: str = Field(description="Relative path of the target file")
    line_number: int = Field(description="Line number of detected vulnerability")
    is_exploitable: bool = Field(
        description="True if exploitable; False if benign/false positive"
    )
    root_cause: str = Field(
        description="Clear explanation of the underlying security or architectural risk"
    )
    patched_code: str = Field(
        description="Drop-in replacement code snippet fixing the issue"
    )
    unit_test: str = Field(
        description="Standalone, runnable pytest test case validating the fix"
    )


class AuditRemediationReport(BaseModel):
    summary: str = Field(description="High-level executive summary of audit findings")
    total_violations_evaluated: int = Field(
        description="Total static violations sent for LLM review"
    )
    remediations: list[IssueRemediation] = Field(
        default_factory=list, description="List of remediations per issue"
    )

    def exploitable(self) -> list[IssueRemediation]:
        return [r for r in self.remediations if r.is_exploitable]

    def false_positives(self) -> list[IssueRemediation]:
        return [r for r in self.remediations if not r.is_exploitable]
