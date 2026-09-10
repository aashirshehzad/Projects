"""Dependency vulnerability scanning (Tier 2).

A *separate stage* from the AST engine: it reads lockfiles / requirement files,
asks OSV.dev whether any pinned version has a known advisory, and reports the
hits. Network lives here and only here -- the static scanner stays offline.
"""

from app.deps.scanner import DepScanError, scan_dependencies

__all__ = ["scan_dependencies", "DepScanError"]
