"""Pick and cache the right tree-sitter grammar for a JS/TS file's suffix."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from tree_sitter import Language, Parser

# `.ts` has no JSX; `.tsx` and plain `.js`/`.jsx` do.
JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs")
TS_SUFFIXES = (".ts", ".mts", ".cts")
TSX_SUFFIXES = (".tsx",)
ALL_SUFFIXES = JS_SUFFIXES + TS_SUFFIXES + TSX_SUFFIXES


@lru_cache(maxsize=1)
def _js_language() -> Language:
    import tree_sitter_javascript as tsjs

    return Language(tsjs.language())


@lru_cache(maxsize=1)
def _ts_language() -> Language:
    import tree_sitter_typescript as tsts

    return Language(tsts.language_typescript())


@lru_cache(maxsize=1)
def _tsx_language() -> Language:
    import tree_sitter_typescript as tsts

    return Language(tsts.language_tsx())


@lru_cache(maxsize=8)
def _parser_for_suffix(suffix: str) -> Parser | None:
    if suffix in JS_SUFFIXES:
        return Parser(_js_language())
    if suffix in TS_SUFFIXES:
        return Parser(_ts_language())
    if suffix in TSX_SUFFIXES:
        return Parser(_tsx_language())
    return None


def get_parser(file_path: str | Path) -> Parser | None:
    """A cached :class:`tree_sitter.Parser` for *file_path*'s suffix, or ``None``."""
    try:
        return _parser_for_suffix(Path(file_path).suffix)
    except Exception:  # grammar package missing/broken -- degrade, don't crash the scan
        return None
