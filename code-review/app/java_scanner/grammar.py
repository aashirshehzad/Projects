"""tree-sitter-java grammar loader for the Java engine."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from tree_sitter import Language, Parser

ALL_SUFFIXES = (".java",)


@lru_cache(maxsize=1)
def _java_language() -> Language:
    import tree_sitter_java as tsj

    return Language(tsj.language())


@lru_cache(maxsize=1)
def _parser() -> Parser:
    return Parser(_java_language())


def get_parser(file_path: str | Path) -> Parser | None:
    """A cached :class:`tree_sitter.Parser` for *file_path*, or ``None`` if unsupported."""
    if Path(file_path).suffix not in ALL_SUFFIXES:
        return None
    try:
        return _parser()
    except Exception:  # grammar package missing/broken -- degrade, don't crash the scan
        return None
