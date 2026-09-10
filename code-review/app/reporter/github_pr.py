"""GitHub PR reporting via the REST API (Stage 4).

Uses plain ``requests`` rather than a client library so the only dependency is
one already needed elsewhere. Posts one inline review comment per exploitable
finding plus a single summary comment, and returns a pass/fail for the status
check.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from app.core.config import Settings, get_settings
from app.core.exceptions import ReportingError
from app.llm_remediation.schemas import AuditRemediationReport
from app.static_scanner.ast_rules import Violation
from app.static_scanner.engine import ScanResult

_API = "https://api.github.com"
_TIMEOUT = 20


@dataclass(slots=True)
class PRTarget:
    repository: str  # "owner/repo"
    pr_number: int
    commit_sha: str

    @classmethod
    def from_settings(cls, settings: Settings) -> "PRTarget":
        missing = [
            name
            for name, val in {
                "GITHUB_REPOSITORY": settings.github_repository,
                "GITHUB_PR_NUMBER": settings.github_pr_number,
                "GITHUB_SHA": settings.github_sha,
            }.items()
            if not val
        ]
        if missing:
            raise ReportingError(f"Missing GitHub context: {', '.join(missing)}")
        return cls(
            repository=settings.github_repository,  # type: ignore[arg-type]
            pr_number=int(settings.github_pr_number),  # type: ignore[arg-type]
            commit_sha=settings.github_sha,  # type: ignore[arg-type]
        )


class GitHubPRReporter:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        if not self.settings.github_token:
            raise ReportingError("GITHUB_TOKEN is not set; cannot post PR feedback.")
        self.target = PRTarget.from_settings(self.settings)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    # -- low-level ----------------------------------------------------------
    def _post(self, url: str, payload: dict) -> dict:
        resp = self.session.post(url, json=payload, timeout=_TIMEOUT)
        if resp.status_code >= 300:
            raise ReportingError(
                f"GitHub API {resp.status_code} for {url}: {resp.text[:300]}"
            )
        return resp.json() if resp.content else {}

    # -- public -----------------------------------------------------------
    def post_inline_comments(
        self, result: ScanResult, report: AuditRemediationReport
    ) -> int:
        """One review comment per exploitable finding. Returns count posted."""
        triage = {
            (r.rule_id, r.file_path, r.line_number): r for r in report.remediations
        }
        url = f"{_API}/repos/{self.target.repository}/pulls/{self.target.pr_number}/comments"
        posted = 0
        for v in result.violations:
            r = triage.get((v.rule_id, v.file_path, v.line_number))
            if r is not None and not r.is_exploitable:
                continue
            self._post(url, {
                "commit_id": self.target.commit_sha,
                "path": v.file_path,
                "line": v.line_number,
                "side": "RIGHT",
                "body": _inline_body(v, r),
            })
            posted += 1
        return posted

    def post_summary(self, result: ScanResult, report: AuditRemediationReport) -> None:
        url = (
            f"{_API}/repos/{self.target.repository}"
            f"/issues/{self.target.pr_number}/comments"
        )
        self._post(url, {"body": _summary_body(result, report)})


def _inline_body(v: Violation, remediation) -> str:
    lines = [
        f"### {v.severity.value} - {v.rule_id}: {v.title}",
        "",
        v.message,
    ]
    if remediation is not None and remediation.is_exploitable:
        lines += ["", f"**Root cause.** {remediation.root_cause}"]
        if remediation.patched_code.strip():
            lines += [
                "",
                "**Suggested patch**",
                "```python",
                remediation.patched_code.rstrip(),
                "```",
            ]
        if remediation.unit_test.strip():
            lines += [
                "",
                "<details><summary>Regression test</summary>",
                "",
                "```python",
                remediation.unit_test.rstrip(),
                "```",
                "",
                "</details>",
            ]
    lines += ["", "_Posted by hybrid-code-auditor._"]
    return "\n".join(lines)


def _summary_body(result: ScanResult, report: AuditRemediationReport) -> str:
    counts = result.counts_by_severity()
    exploitable = len(report.exploitable())
    fp = len(report.false_positives())
    tally = ", ".join(f"{k}: {v}" for k, v in counts.items() if v) or "none"
    verdict = "FAIL" if exploitable else "PASS"
    rows = [
        f"## Hybrid Code Auditor - {verdict}",
        "",
        report.summary,
        "",
        f"- Static violations: **{len(result.violations)}** ({tally})",
        f"- Confirmed exploitable: **{exploitable}**",
        f"- Dismissed as false positive: **{fp}**",
        f"- Files scanned: {result.files_scanned}",
    ]
    return "\n".join(rows)
