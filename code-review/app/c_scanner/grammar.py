"""Pick and cache the right tree-sitter grammar for a C/C++ file's suffix."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from tree_sitter import Language, Parser

C_SUFFIXES = (".c", ".h")
CPP_SUFFIXES = (".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++")
ALL_SUFFIXES = C_SUFFIXES + CPP_SUFFIXES


@lru_cache(maxsize=1)
def _c_language() -> Language:
    import tree_sitter_c as tsc

    return Language(tsc.language())


@lru_cache(maxsize=1)
def _cpp_language() -> Language:
    import tree_sitter_cpp as tscpp

    return Language(tscpp.language())


@lru_cache(maxsize=8)
def _parser_for_suffix(suffix: str) -> Parser | None:
    if suffix in CPP_SUFFIXES:
        return Parser(_cpp_language())
    if suffix in C_SUFFIXES:
        # `.h` is ambiguous (C or C++ header); the C grammar parses the
        # syntax this engine's rules look at (calls, declarations, #define)
        # just as well and doesn't need the heavier C++ grammar.
        return Parser(_c_language())
    return None


def get_parser(file_path: str | Path) -> Parser | None:
    """A cached :class:`tree_sitter.Parser` for *file_path*'s suffix, or ``None``."""
    try:
        return _parser_for_suffix(Path(file_path).suffix)
    except Exception:  # grammar package missing/broken -- degrade, don't crash the scan
        return None
