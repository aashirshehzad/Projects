"""Java rules JAVA-001..JAVA-006, parsed with tree-sitter.

A fourth, independent engine (per CLAUDE.md: a new language is a new engine)
plugging into the same ``Violation`` type as the Python, JS/TS and C/C++
engines, so every reporter needs no changes.
"""

from app.java_scanner.grammar import ALL_SUFFIXES, get_parser
from app.java_scanner.rules import scan_java_source

# Uniform entry point every language engine exposes, so
# app.static_scanner.engine can dispatch to any of them the same way.
scan = scan_java_source

__all__ = ["scan_java_source", "scan", "get_parser", "ALL_SUFFIXES"]
