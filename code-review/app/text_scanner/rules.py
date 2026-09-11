"""TXT-001 / TXT-002: regex-based secret detection for plain-text files.

Not a language engine like the other four -- ``.txt`` has no syntax to build a
tree from, so this is line-by-line pattern matching instead of an AST walk.
Same idea as gitleaks/trufflehog: (1) a small set of well-known, high-confidence
secret *formats* (AWS/GitHub/Slack/Google/Stripe keys, PEM key blocks, JWTs),
and (2) the same ``name = value`` heuristic every other engine's "hardcoded
secret" rule already uses. Deterministic -- same regex, same input, same
output, always -- but line-based scanning over prose has a higher false-positive
ceiling than an AST match, so results here deserve a closer look than SEC-003.
"""

from __future__ import annotations

import re

from app.static_scanner.ast_rules import RULES, Severity, Violation

RULES.update(
    {
        "TXT-001": {
            "severity": Severity.CRITICAL.value,
            "title": "Known secret format detected",
            "target": "AWS/GitHub/Slack/Google/Stripe key patterns, PEM private key blocks, JWTs",
        },
        "TXT-002": {
            "severity": Severity.HIGH.value,
            "title": "Hardcoded secret assignment",
            "target": "key/secret/token/password = <value> in a plain-text file",
        },
    }
)

_SECRET_TOKENS = {
    "key", "secret", "token", "password", "passwd", "pwd",
    "apikey", "credential", "credentials", "auth",
}
_SECRET_PLACEHOLDERS = {
    "", "changeme", "change_me", "placeholder", "example",
    "your_key_here", "xxx", "todo", "none", "null",
}

# (label, pattern, severity) -- specific enough that a match is worth flagging
# on its own, with no name-based heuristic needed.
_KNOWN_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), Severity.CRITICAL.value),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), Severity.CRITICAL.value),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"), Severity.CRITICAL.value),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35,}\b"), Severity.HIGH.value),
    ("Stripe live key", re.compile(r"\bsk_live_[0-9a-zA-Z]{16,}\b"), Severity.CRITICAL.value),
    (
        "PEM private key block",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        Severity.CRITICAL.value,
    ),
    (
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        Severity.MEDIUM.value,
    ),
]

# `name = value` / `name: value`, optionally quoted. A trailing `# comment`
# (including a suppression marker) is stripped before matching.
_ASSIGN_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z0-9_.\-]*)\s*[:=]\s*['\"]?([^\s'\"#]{4,})['\"]?\s*$"
)

_NOSEC_RE = re.compile(r"#\s*nosec\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)
_NOQA_RE = re.compile(r"#\s*noqa\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)


def _suppress_ids(raw: str) -> set[str]:
    return {tok.strip().upper() for tok in raw.replace(",", " ").split() if tok.strip()}


def _line_suppresses(line: str, rule_id: str) -> bool:
    m = _NOSEC_RE.search(line)
    if m is not None:
        ids = _suppress_ids(m.group(1))
        if not ids or rule_id in ids:
            return True
    m = _NOQA_RE.search(line)
    return m is not None and rule_id in _suppress_ids(m.group(1))


def _split_identifier(name: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return {p.lower() for p in re.split(r"[_\-]+", spaced) if p}


def _value_looks_secretish(value: str) -> bool:
    """Filter out ordinary prose ("note: remember the milk") from real secrets."""
    if len(value) >= 20:
        return True
    has_digit = any(c.isdigit() for c in value)
    has_upper = any(c.isupper() for c in value)
    has_symbol = any(not c.isalnum() for c in value)
    return has_digit or has_symbol or has_upper


def _looks_like_secret(name: str, value: str) -> bool:
    lowered = name.lower()
    parts = _split_identifier(name)
    if not (parts & _SECRET_TOKENS or any(tok in lowered for tok in _SECRET_TOKENS)):
        return False
    if "public" in lowered or lowered.endswith(("name", "id", "path", "url", "field")):
        return False
    v = value.strip()
    if len(v) < 8 or v.lower() in _SECRET_PLACEHOLDERS:
        return False
    if v.startswith(("<", "${", "{{")):
        return False
    return _value_looks_secretish(v)


def scan_text_source(
    source: str,
    file_path: str = "<string>",
    *,
    config: object | None = None,
) -> list[Violation]:
    """Line-scan *source* for well-known secret formats and secret-shaped assignments."""
    found: list[Violation] = []

    def add(rule_id: str, line_no: int, message: str, *, severity: str | None = None) -> None:
        meta = RULES[rule_id]
        found.append(
            Violation(
                rule_id=rule_id,
                severity=Severity(severity or meta["severity"]),
                title=meta["title"],
                message=message,
                file_path=file_path,
                line_number=line_no,
                col_offset=0,
                end_line_number=line_no,
            )
        )

    lines = source.splitlines()
    for i, line in enumerate(lines, start=1):
        for label, pattern, sev in _KNOWN_PATTERNS:
            if pattern.search(line):
                add(
                    "TXT-001", i,
                    f"This line contains what looks like a {label}. Treat it as "
                    "compromised: rotate it and remove it from the file.",
                    severity=sev,
                )

        code = line.split("#", 1)[0]  # ignore trailing comment when matching the assignment
        m = _ASSIGN_RE.match(code)
        if m:
            name, value = m.group(1), m.group(2)
            if _looks_like_secret(name, value):
                add(
                    "TXT-002", i,
                    f"`{name}` is set to what looks like a hardcoded secret. Move it "
                    "to an environment variable or a secrets manager.",
                )

    disabled: frozenset[str] = getattr(config, "disabled", frozenset())
    overrides: dict[str, str] = getattr(config, "severity", {})

    def line_at(n: int) -> str:
        return lines[n - 1] if 1 <= n <= len(lines) else ""

    seen: set[tuple[str, str, int, int]] = set()
    out: list[Violation] = []
    for v in found:
        if v.rule_id in disabled or v.key() in seen:
            continue
        if _line_suppresses(line_at(v.line_number), v.rule_id):
            continue
        if v.rule_id in overrides:
            v.severity = Severity(overrides[v.rule_id])
        seen.add(v.key())
        out.append(v)

    out.sort(key=lambda v: (v.severity.rank, v.line_number, v.rule_id))
    return out
