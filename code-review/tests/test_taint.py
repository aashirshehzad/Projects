"""Intra-function taint tracking and its effect on SEC-001/002/005."""

from __future__ import annotations

import ast

from app.static_scanner.ast_rules import scan_source
from app.static_scanner.taint import collect_function_taint


def _func(src: str) -> ast.AST:
    return ast.parse(src).body[0]


def _ids(src: str) -> set[str]:
    return {v.rule_id for v in scan_source(src, "s.py")}


def _by_rule(src: str, rule_id: str):
    return [v for v in scan_source(src, "s.py") if v.rule_id == rule_id]


# --------------------------------------------------------------------------- #
# the analyzer itself
# --------------------------------------------------------------------------- #
def test_route_handler_params_are_tainted() -> None:
    info = collect_function_taint(_func(
        "@app.get('/x')\n"
        "def handler(user_id):\n"
        "    q = user_id\n"
        "    return q\n"
    ))
    assert "user_id" in info.tainted
    assert "q" in info.tainted


def test_request_source_propagates_through_fstring() -> None:
    info = collect_function_taint(_func(
        "def view():\n"
        "    name = request.args['name']\n"
        "    greeting = f'hello {name}'\n"
        "    plain = 'static'\n"
    ))
    assert {"name", "greeting"} <= info.tainted
    assert "greeting" in info.dynamic_strings
    assert "plain" not in info.tainted


def test_plain_function_params_are_not_tainted() -> None:
    info = collect_function_taint(_func("def helper(a, b):\n    c = a + b\n"))
    assert info.tainted == set()


def test_analyzer_is_deterministic() -> None:
    src = (
        "def v():\n"
        "    a = request.form['x']\n"
        "    b = a.strip()\n"
        "    c = b + '!'\n"
    )
    first = collect_function_taint(_func(src))
    second = collect_function_taint(_func(src))
    assert first.tainted == second.tainted == {"a", "b", "c"}


# --------------------------------------------------------------------------- #
# SEC-002 -- the false negative taint fixes
# --------------------------------------------------------------------------- #
def test_sec002_catches_query_built_earlier() -> None:
    src = (
        "def view(cursor):\n"
        "    uid = request.args['id']\n"
        "    sql = f'SELECT * FROM users WHERE id = {uid}'\n"
        "    cursor.execute(sql)\n"
    )
    hits = _by_rule(src, "SEC-002")
    assert len(hits) == 1
    assert hits[0].tainted is True


def test_sec002_ignores_static_query_in_variable() -> None:
    src = (
        "def view(cursor):\n"
        "    sql = 'SELECT * FROM users'\n"
        "    cursor.execute(sql)\n"
    )
    assert _by_rule(src, "SEC-002") == []


def test_sec002_still_catches_inline_fstring() -> None:
    src = "def view(cursor, uid):\n    cursor.execute(f'SELECT {uid}')\n"
    assert "SEC-002" in _ids(src)


# --------------------------------------------------------------------------- #
# SEC-001 / SEC-005 -- taint marking
# --------------------------------------------------------------------------- #
def test_sec005_marks_tainted_when_arg_from_request() -> None:
    src = (
        "@router.post('/run')\n"
        "def run_cmd(target):\n"
        "    import subprocess\n"
        "    subprocess.run(target, shell=True)\n"
    )
    (v,) = _by_rule(src, "SEC-005")
    assert v.tainted is True
    assert v.severity.value == "HIGH"
    assert "user-controlled input" in v.message


def test_sec005_not_marked_when_arg_is_plain_local() -> None:
    src = (
        "def run_cmd(target):\n"
        "    import subprocess\n"
        "    subprocess.run(target, shell=True)\n"
    )
    (v,) = _by_rule(src, "SEC-005")
    assert v.tainted is False  # still reported, just not escalated as user-driven


def test_sec001_marked_for_route_param() -> None:
    src = "@app.route('/e')\ndef e(expr):\n    return eval(expr)\n"
    (v,) = _by_rule(src, "SEC-001")
    assert v.tainted is True
