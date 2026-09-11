"""TXT-001/TXT-002: regex-based secret detection for plain-text (``.txt``) files.

Not a fifth *language* engine -- there's no syntax tree here, just line
scanning -- but it plugs into the same ``Violation`` type and the same
``ALL_SUFFIXES`` + ``scan(source, file_path, *, config=None)`` interface as
the parser-based engines, so ``app.static_scanner.engine`` dispatches to it
identically.
"""

from app.text_scanner.rules import scan_text_source

ALL_SUFFIXES = (".txt",)
scan = scan_text_source

__all__ = ["scan_text_source", "scan", "ALL_SUFFIXES"]
