"""Project-level rule configuration, read from ``[tool.code-auditor]``.

```toml
[tool.code-auditor]
disabled_rules = ["SEC-007"]          # never report these

[tool.code-auditor.severity]
SEC-005 = "HIGH"                       # override the built-in severity
```

Missing file / missing section / malformed TOML all resolve to an empty config
(every rule on, built-in severities) -- configuration never breaks a scan.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.static_scanner.ast_rules import RULES, Severity

_VALID_SEVERITIES = {s.value for s in Severity}


@dataclass(frozen=True)
class RuleConfig:
    disabled: frozenset[str] = frozenset()
    severity: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RuleConfig":
        candidate = Path(path) if path else Path("pyproject.toml")
        if not candidate.is_file():
            return cls()
        try:
            data = tomllib.loads(candidate.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError, ValueError):
            return cls()

        tool = (data.get("tool") or {}).get("code-auditor") or {}
        disabled = {
            str(r).upper() for r in (tool.get("disabled_rules") or []) if str(r).upper() in RULES
        }
        severity: dict[str, str] = {}
        for rid, sev in (tool.get("severity") or {}).items():
            rid_u, sev_u = str(rid).upper(), str(sev).upper()
            if rid_u in RULES and sev_u in _VALID_SEVERITIES:
                severity[rid_u] = sev_u
        return cls(frozenset(disabled), severity)

    def is_active(self) -> bool:
        return bool(self.disabled or self.severity)
