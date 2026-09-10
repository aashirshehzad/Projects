"""SARIF 2.1.0 export for GitHub Advanced Security / code-scanning dashboards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import __version__
from app.llm_remediation.schemas import AuditRemediationReport
from app.static_scanner.ast_rules import RULES, Severity
from app.static_scanner.engine import ScanResult

_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
}
_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"


def _rules_metadata() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rule_id, meta in RULES.items():
        out.append(
            {
                "id": rule_id,
                "name": meta["title"].replace(" ", ""),
                "shortDescription": {"text": meta["title"]},
                "fullDescription": {"text": f"Target pattern: {meta['target']}"},
                "defaultConfiguration": {
                    "level": _SARIF_LEVEL[Severity(meta["severity"])]
                },
                "properties": {"security-severity": _security_severity(meta["severity"])},
            }
        )
    return out


def _security_severity(sev: str) -> str:
    return {"CRITICAL": "9.5", "HIGH": "8.0", "MEDIUM": "5.5", "LOW": "3.0"}[sev]


def to_sarif(
    result: ScanResult,
    report: AuditRemediationReport | None = None,
) -> dict[str, Any]:
    triage: dict[tuple[str, str, int], Any] = {}
    if report is not None:
        for r in report.remediations:
            triage[(r.rule_id, r.file_path, r.line_number)] = r

    results: list[dict[str, Any]] = []
    for v in result.violations:
        r = triage.get((v.rule_id, v.file_path, v.line_number))
        if r is not None and not r.is_exploitable:
            continue  # suppress confirmed false positives from the dashboard
        text = v.message
        if r is not None and r.is_exploitable:
            text = f"{v.message}\n\nRoot cause: {r.root_cause}"
        results.append(
            {
                "ruleId": v.rule_id,
                "level": _SARIF_LEVEL[v.severity],
                "message": {"text": text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": v.file_path},
                            "region": {
                                "startLine": v.line_number,
                                "endLine": v.end_line_number or v.line_number,
                                "startColumn": max(1, v.col_offset + 1),
                            },
                        }
                    }
                ],
                "partialFingerprints": {
                    "primaryLocationLineHash": f"{v.file_path}:{v.rule_id}:{v.line_number}"
                },
            }
        )

    return {
        "$schema": _SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "hybrid-code-auditor",
                        "informationUri": "https://github.com/aashirshehzad/Projects",
                        "version": __version__,
                        "rules": _rules_metadata(),
                    }
                },
                "results": results,
            }
        ],
    }


def write_sarif(
    path: str | Path,
    result: ScanResult,
    report: AuditRemediationReport | None = None,
) -> Path:
    out = Path(path)
    out.write_text(json.dumps(to_sarif(result, report), indent=2), encoding="utf-8")
    return out
