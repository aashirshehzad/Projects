"""Minimal OSV.dev client: batch-query pinned packages, then fetch advisory detail."""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from app.deps.manifests import Requirement

_BATCH_URL = "https://api.osv.dev/v1/querybatch"
_VULN_URL = "https://api.osv.dev/v1/vulns/"
_TIMEOUT = 20
_MAX_DETAIL_FETCHES = 60

_GHSA_SEVERITY = {
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MODERATE": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


@dataclass(slots=True)
class Advisory:
    vuln_id: str
    aliases: list[str] = field(default_factory=list)      # CVE / GHSA ids
    summary: str = ""
    severity: str = "HIGH"                                 # CRITICAL/HIGH/MEDIUM/LOW
    fixed_versions: list[str] = field(default_factory=list)

    @property
    def best_id(self) -> str:
        cve = next((a for a in self.aliases if a.startswith("CVE-")), None)
        return cve or self.vuln_id


def _cvss_bucket(vector_or_score: str) -> str | None:
    """Rough CVSS base-score bucket. Accepts a numeric score or a v3 vector."""
    try:
        score = float(vector_or_score)
    except ValueError:
        return None
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def _parse_detail(raw: dict, pkg_name: str) -> Advisory:
    adv = Advisory(vuln_id=raw.get("id", "?"))
    adv.aliases = [a for a in raw.get("aliases", []) if isinstance(a, str)]
    adv.summary = (raw.get("summary") or raw.get("details") or "").strip().split("\n")[0][:300]

    # severity: prefer an explicit GHSA label, else a CVSS score/vector
    sev = None
    for entry in raw.get("severity", []):
        b = _cvss_bucket(str(entry.get("score", "")))
        if b:
            sev = b
            break
    for affected in raw.get("affected", []):
        ds = (affected.get("database_specific") or {}).get("severity")
        if ds and ds.upper() in _GHSA_SEVERITY:
            sev = sev or _GHSA_SEVERITY[ds.upper()]
    adv.severity = sev or "HIGH"

    fixed: list[str] = []
    for affected in raw.get("affected", []):
        apkg = (affected.get("package") or {}).get("name", "")
        if apkg and apkg.lower() != pkg_name.lower():
            continue
        for rng in affected.get("ranges", []):
            for ev in rng.get("events", []):
                if "fixed" in ev:
                    fixed.append(ev["fixed"])
    adv.fixed_versions = sorted(set(fixed))
    return adv


def query(reqs: list[Requirement], *, session: requests.Session | None = None) -> dict[
    tuple[str, str], list[Advisory]
]:
    """Return ``{(name, version): [Advisory, ...]}`` for every affected requirement."""
    if not reqs:
        return {}
    http = session or requests.Session()

    payload = {
        "queries": [
            {"package": {"ecosystem": "PyPI", "name": r.name}, "version": r.version}
            for r in reqs
        ]
    }
    resp = http.post(_BATCH_URL, json=payload, timeout=_TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])

    # collect unique ids, fetch detail once each
    id_to_reqs: dict[str, list[Requirement]] = {}
    for req, result in zip(reqs, results):
        for v in (result or {}).get("vulns", []) or []:
            vid = v.get("id")
            if vid:
                id_to_reqs.setdefault(vid, []).append(req)

    detail_cache: dict[str, Advisory] = {}
    for vid in list(id_to_reqs)[:_MAX_DETAIL_FETCHES]:
        try:
            d = http.get(f"{_VULN_URL}{vid}", timeout=_TIMEOUT)
            d.raise_for_status()
            some_req = id_to_reqs[vid][0]
            detail_cache[vid] = _parse_detail(d.json(), some_req.name)
        except (requests.RequestException, ValueError):
            detail_cache[vid] = Advisory(vuln_id=vid, summary="(advisory detail unavailable)")

    out: dict[tuple[str, str], list[Advisory]] = {}
    for vid, affected_reqs in id_to_reqs.items():
        adv = detail_cache.get(vid)
        if adv is None:
            continue
        for req in affected_reqs:
            out.setdefault((req.name, req.version), []).append(adv)
    return out
