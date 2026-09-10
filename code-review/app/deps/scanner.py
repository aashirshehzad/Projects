"""Tie manifest discovery + OSV lookup into a list of :class:`Violation` records.

Reusing ``Violation`` (rule id ``DEP-001``) lets dependency findings flow through
the existing console / SARIF / PDF / exit-code machinery unchanged. Stage 3
skips them -- an "upgrade the pin" fix is not a code patch.
"""

from __future__ import annotations

import requests

from app.core.exceptions import AuditorError
from app.deps.manifests import Requirement, discover
from app.deps.osv import Advisory, query
from app.static_scanner.ast_rules import RULES, Severity, Violation

RULES.setdefault(
    "DEP-001",
    {
        "severity": Severity.HIGH.value,
        "title": "Known-vulnerable dependency",
        "target": "OSV.dev advisory for a pinned PyPI package",
    },
)


class DepScanError(AuditorError):
    """OSV was unreachable or returned an unusable response."""


def _message(req: Requirement, adv: Advisory) -> str:
    fix = (
        f" Fixed in {', '.join(adv.fixed_versions)}."
        if adv.fixed_versions
        else " No fixed version is listed."
    )
    summary = f" {adv.summary}" if adv.summary else ""
    return f"`{req.name}=={req.version}` is affected by {adv.best_id}.{summary}{fix}"


def scan_dependencies(
    root: str,
    *,
    session: requests.Session | None = None,
) -> list[Violation]:
    """Discover pins under *root* and return one ``DEP-001`` Violation per advisory."""
    reqs = discover(root)
    if not reqs:
        return []
    try:
        hits = query(reqs, session=session)
    except requests.RequestException as exc:
        raise DepScanError(f"OSV.dev query failed: {exc}") from exc
    except ValueError as exc:  # bad JSON
        raise DepScanError(f"OSV.dev returned an unreadable response: {exc}") from exc

    by_key = {(r.name, r.version): r for r in reqs}
    violations: list[Violation] = []
    for key, advisories in hits.items():
        req = by_key[key]
        seen_ids: set[str] = set()
        for adv in advisories:
            # OSV often returns GHSA + PYSEC + CVE records for one flaw.
            if adv.best_id in seen_ids:
                continue
            seen_ids.add(adv.best_id)
            violations.append(
                Violation(
                    rule_id="DEP-001",
                    severity=Severity(adv.severity),
                    title="Known-vulnerable dependency",
                    message=_message(req, adv),
                    file_path=req.manifest,
                    line_number=req.line_number or 1,
                    snippet=req.raw,
                    context_start_line=req.line_number or 1,
                )
            )
    violations.sort(key=lambda v: (v.severity.rank, v.file_path, v.message))
    return violations
