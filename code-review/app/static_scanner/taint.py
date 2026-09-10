"""Intra-function taint tracking -- deterministic, flow-insensitive, best-effort.

Not a real dataflow engine: it over-approximates within a single function body
(no branches, no cross-function, no aliasing beyond simple assignment). Its only
jobs are to (a) let SEC-002 catch a query string that was assembled a few lines
before ``execute()``, and (b) mark SEC-001/002/005 findings whose argument
demonstrably reaches user input, so they can be ranked higher.

Same source in -> same taint set out, always.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

# Dotted expressions (or their prefixes) whose value is attacker-controlled.
_SOURCE_PREFIXES = (
    "request.",
    "self.request.",
    "flask.request.",
    "django.http.request.",
)
_SOURCE_SUBSCRIPT_BASES = {
    "request.args", "request.form", "request.values", "request.json",
    "request.data", "request.files", "request.cookies", "request.headers",
    "request.GET", "request.POST", "request.query_params", "request.path_params",
    "sys.argv", "os.environ",
}
_SOURCE_CALLS = {
    "input", "os.getenv", "os.environ.get", "getpass.getpass",
    "request.get_json", "request.get_data",
}
_ROUTE_DECO_RE = re.compile(
    r"(?:^|\.)(?:route|get|post|put|patch|delete|websocket|api_route)$"
)


@dataclass(slots=True)
class TaintInfo:
    tainted: set[str] = field(default_factory=set)
    # tainted names that were built from an f-string / % / + / .format()
    dynamic_strings: set[str] = field(default_factory=set)

    def has(self, name: str) -> bool:
        return name in self.tainted


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _iter_body(func: ast.AST):
    """Yield statements in *func* without descending into nested scopes."""
    stack = list(getattr(func, "body", []))
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            stack.append(child)


def _is_route_handler(func: ast.AST) -> bool:
    for deco in getattr(func, "decorator_list", []):
        target = deco.func if isinstance(deco, ast.Call) else deco
        if _ROUTE_DECO_RE.search(_dotted(target)):
            return True
    return False


def _param_names(func: ast.AST) -> list[str]:
    a = getattr(func, "args", None)
    if a is None:
        return []
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return [n for n in names if n not in {"self", "cls"}]


def _expr_tainted(node: ast.expr | None, tainted: set[str]) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in tainted or node.id in {"request", "req"}
    if isinstance(node, ast.Attribute):
        dotted = _dotted(node)
        if any(dotted.startswith(p) for p in _SOURCE_PREFIXES):
            return True
        return _expr_tainted(node.value, tainted)
    if isinstance(node, ast.Subscript):
        if _dotted(node.value) in _SOURCE_SUBSCRIPT_BASES:
            return True
        return _expr_tainted(node.value, tainted)
    if isinstance(node, ast.Call):
        if _dotted(node.func) in _SOURCE_CALLS:
            return True
        if isinstance(node.func, ast.Attribute) and _expr_tainted(node.func.value, tainted):
            return True  # method call on a tainted object
        return any(_expr_tainted(a, tainted) for a in node.args)
    if isinstance(node, ast.BinOp):
        return _expr_tainted(node.left, tainted) or _expr_tainted(node.right, tainted)
    if isinstance(node, ast.JoinedStr):
        return any(
            isinstance(v, ast.FormattedValue) and _expr_tainted(v.value, tainted)
            for v in node.values
        )
    if isinstance(node, ast.BoolOp):
        return any(_expr_tainted(v, tainted) for v in node.values)
    if isinstance(node, ast.IfExp):
        return _expr_tainted(node.body, tainted) or _expr_tainted(node.orelse, tainted)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_expr_tainted(e, tainted) for e in node.elts)
    return False


def _is_dynamic_string(node: ast.expr | None) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    if isinstance(node, ast.Call):
        fn = _dotted(node.func)
        return fn.endswith(".format") or fn.endswith(".join")
    return False


def _assign_targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    elif isinstance(node, ast.NamedExpr):
        targets = [node.target]
    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
    else:
        return []
    return [t.id for t in targets if isinstance(t, ast.Name)]


def collect_function_taint(func: ast.AST) -> TaintInfo:
    info = TaintInfo()
    if _is_route_handler(func):
        info.tainted.update(_param_names(func))

    assigns: list[tuple[list[str], ast.expr, bool]] = []
    for stmt in _iter_body(func):
        if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.NamedExpr, ast.AugAssign)):
            value = getattr(stmt, "value", None)
            names = _assign_targets(stmt)
            if names and value is not None:
                assigns.append((names, value, _is_dynamic_string(value)))

    # flow-insensitive fixpoint
    changed = True
    while changed:
        changed = False
        for names, value, is_dyn in assigns:
            if _expr_tainted(value, info.tainted):
                for n in names:
                    if n not in info.tainted:
                        info.tainted.add(n)
                        changed = True
                    if is_dyn:
                        info.dynamic_strings.add(n)
    return info
