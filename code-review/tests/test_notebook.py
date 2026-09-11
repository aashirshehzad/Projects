"""Jupyter notebook (.ipynb) support: extraction, cell mapping, end-to-end scan."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from app.main import cli
from app.static_scanner import notebook
from app.static_scanner.engine import scan_path

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


# --------------------------------------------------------------------------- #
# extraction
# --------------------------------------------------------------------------- #
def test_parse_skips_markdown_keeps_code() -> None:
    nb = notebook.parse_file(FIXTURES / "vulnerable_notebook.ipynb")
    assert nb is not None
    assert "Demo notebook" not in nb.source  # markdown text never enters the source
    assert "def run_user_expression" in nb.source
    assert nb.code_cells == 4  # four code cells, one markdown


def test_line_magic_and_shell_escape_are_blanked() -> None:
    nb = notebook.parse_file(FIXTURES / "vulnerable_notebook.ipynb")
    assert "!pip install" not in nb.source
    assert "import pickle" in nb.source  # rest of that cell survives


def test_cell_magic_blanks_whole_cell() -> None:
    nb = notebook.parse_file(FIXTURES / "vulnerable_notebook.ipynb")
    assert "rm -rf" not in nb.source
    assert "%%bash" not in nb.source


def test_cell_of_line_points_at_the_right_code_cell() -> None:
    nb = notebook.parse_file(FIXTURES / "vulnerable_notebook.ipynb")
    eval_line = next(i for i, ln in enumerate(nb.source.splitlines(), 1) if "eval(expr)" in ln)
    assert nb.cell_of_line[eval_line] == 2  # second code cell (0-indexed among code cells: #2)
    secret_line = next(
        i for i, ln in enumerate(nb.source.splitlines(), 1) if "AWS_SECRET_ACCESS_KEY" in ln
    )
    assert nb.cell_of_line[secret_line] == 4


def test_bad_json_returns_none() -> None:
    assert notebook.parse("{not valid json") is None


def test_missing_cells_key_returns_none() -> None:
    assert notebook.parse('{"nbformat": 4}') is None


def test_non_code_only_notebook_has_empty_source() -> None:
    nb = notebook.parse('{"cells": [{"cell_type": "markdown", "source": ["# hi\\n"]}]}')
    assert nb is not None
    assert nb.source.strip() == ""
    assert nb.code_cells == 0


# --------------------------------------------------------------------------- #
# end-to-end scan
# --------------------------------------------------------------------------- #
def test_scan_path_finds_violations_in_notebook() -> None:
    result = scan_path(FIXTURES / "vulnerable_notebook.ipynb", base_dir=FIXTURES)
    ids = {v.rule_id for v in result.violations}
    assert ids == {"SEC-001", "SEC-003"}
    assert result.files_scanned == 1
    for v in result.violations:
        assert "(notebook cell" in v.message
        assert v.file_path == "vulnerable_notebook.ipynb"


def test_scan_path_clean_notebook_is_silent() -> None:
    result = scan_path(FIXTURES / "clean_notebook.ipynb", base_dir=FIXTURES)
    assert result.violations == []
    assert result.files_scanned == 1


def test_directory_scan_covers_both_py_and_ipynb(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("eval(x)\n")
    (tmp_path / "b.ipynb").write_text(
        (FIXTURES / "vulnerable_notebook.ipynb").read_text(encoding="utf-8")
    )
    checkpoints = tmp_path / ".ipynb_checkpoints"
    checkpoints.mkdir()
    (checkpoints / "b-checkpoint.ipynb").write_text("{}")  # must not crash / count

    result = scan_path(tmp_path, base_dir=tmp_path)
    assert result.files_scanned == 2  # a.py + b.ipynb, checkpoint dir skipped
    assert {v.file_path for v in result.violations} == {"a.py", "b.ipynb"}


def test_broken_notebook_json_is_skipped_not_raised(tmp_path: Path) -> None:
    (tmp_path / "broken.ipynb").write_text("{ this is not json")
    result = scan_path(tmp_path, base_dir=tmp_path)
    assert result.files_scanned == 0
    assert result.files_skipped == 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_audit_notebook() -> None:
    res = runner.invoke(
        cli, ["audit", str(FIXTURES / "vulnerable_notebook.ipynb"), "--no-llm"]
    )
    assert res.exit_code == 1
    assert "SEC-001" in res.output
    assert "SEC-003" in res.output


def test_cli_audit_clean_notebook() -> None:
    res = runner.invoke(
        cli, ["audit", str(FIXTURES / "clean_notebook.ipynb"), "--no-llm"]
    )
    assert res.exit_code == 0
