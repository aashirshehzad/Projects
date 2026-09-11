"""C/C++ rules C-001..C-006, parsed with tree-sitter.

A third, independent engine (per CLAUDE.md: a new language is a new engine)
plugging into the same ``Violation`` type as the Python and JS/TS engines, so
every reporter needs no changes.
"""

from app.c_scanner.grammar import ALL_SUFFIXES, get_parser
from app.c_scanner.rules import scan_c_source

# Uniform entry point every language engine exposes, so
# app.static_scanner.engine can dispatch to any of them the same way.
scan = scan_c_source

__all__ = ["scan_c_source", "scan", "get_parser", "ALL_SUFFIXES"]
