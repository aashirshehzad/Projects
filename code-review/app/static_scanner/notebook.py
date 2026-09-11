"""Extract Python source from Jupyter notebooks (``.ipynb``) for the AST scanner.

A notebook is JSON, not Python -- ``ast.parse`` can't touch it directly. This
module concatenates the *code* cells (markdown/raw cells are skipped) into one
"virtual" Python source, so the exact same rules and taint pass that run on a
``.py`` file run unmodified on a notebook. Line numbers in a finding then refer
to that virtual source, not to byte offsets in the ``.ipynb`` JSON -- which is
why every finding is also tagged with the cell it came from.

Cell magics (``%%bash``, ``%%writefile``, ...) and line magics/shell escapes
(``%timeit``, ``!pip install``) are not valid Python syntax, so they are
blanked out before parsing; blanking preserves line counts so numbering stays
correct for the surrounding code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Cell magics that still leave the rest of the cell as ordinary Python.
_BENIGN_CELL_MAGICS = {"%%time", "%%timeit", "%%capture"}


@dataclass(slots=True)
class NotebookSource:
    source: str
    # 1-based virtual line -> 1-based index among *code* cells (execution order).
    cell_of_line: dict[int, int] = field(default_factory=dict)
    code_cells: int = 0


def _cell_text(cell: dict) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return src if isinstance(src, str) else ""


def _sanitize_cell(body: str) -> list[str]:
    """Blank out magics/shell-escapes; keep the line count unchanged."""
    raw_lines = body.splitlines()
    first_nonblank = next((ln.strip() for ln in raw_lines if ln.strip()), "")
    if first_nonblank.startswith("%%") and first_nonblank.split()[0] not in _BENIGN_CELL_MAGICS:
        return ["" for _ in raw_lines]  # whole cell is a non-Python cell magic
    return [
        "" if ln.lstrip().startswith(("%", "!")) else ln
        for ln in raw_lines
    ]


def parse(text: str) -> NotebookSource | None:
    """Build a :class:`NotebookSource` from raw ``.ipynb`` JSON text.

    Returns ``None`` if *text* is not a parseable notebook (bad JSON, or no
    ``cells`` list) -- the caller treats that like an unreadable file.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, list):
        return None

    lines: list[str] = []
    cell_of_line: dict[int, int] = {}
    code_cell_no = 0
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        code_cell_no += 1
        sanitized = _sanitize_cell(_cell_text(cell))
        start = len(lines) + 1
        lines.extend(sanitized)
        for i in range(len(sanitized)):
            cell_of_line[start + i] = code_cell_no
        lines.append("")  # separator: keeps one cell's trailing statement
        #                    from silently continuing into the next cell.

    return NotebookSource(source="\n".join(lines), cell_of_line=cell_of_line, code_cells=code_cell_no)


def parse_file(path: str | Path) -> NotebookSource | None:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return parse(text)
