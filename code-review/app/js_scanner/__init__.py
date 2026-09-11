"""JavaScript/TypeScript rules JS-001..JS-006, parsed with tree-sitter.

A second, independent engine (per CLAUDE.md: a new language is a new engine,
not an extension of the Python one) that plugs into the same ``Violation``
type, so every reporter (console/SARIF/PDF/web) needs no changes at all.
"""

from app.js_scanner.grammar import ALL_SUFFIXES, get_parser
from app.js_scanner.rules import scan_js_source

# Uniform entry point every language engine exposes, so
# app.static_scanner.engine can dispatch to any of them the same way.
scan = scan_js_source

__all__ = ["scan_js_source", "scan", "get_parser", "ALL_SUFFIXES"]
