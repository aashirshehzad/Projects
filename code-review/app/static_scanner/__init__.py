"""Stage 1-2: deterministic static analysis over the Python AST.

No subprocesses, no network, no model downloads -- just ``ast`` walks that turn
source strings into violation records with zero hallucination risk.
"""

from app.static_scanner.ast_rules import (
    RULES,
    Severity,
    Violation,
    scan_source,
)
from app.static_scanner.engine import ScanResult, scan_path, scan_paths

__all__ = [
    "RULES",
    "Severity",
    "Violation",
    "scan_source",
    "ScanResult",
    "scan_path",
    "scan_paths",
]
