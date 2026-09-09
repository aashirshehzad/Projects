"""Safe arithmetic evaluator (no eval, AST whitelist only)."""
from __future__ import annotations

import ast
import math
import operator

DECLARATION = {
    "name": "calculator",
    "description": (
        "Evaluate a math expression. Supports + - * / // % **, parentheses, and common "
        "functions: sqrt, sin, cos, tan, log, ln, exp, abs, round, floor, ceil, and pi/e."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The expression to evaluate, e.g. 'sqrt(144) + 3 * (2 ** 5)'.",
            }
        },
        "required": ["expression"],
    },
}

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_NAMES = {"pi": math.pi, "e": math.e, "tau": math.tau}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log10, "ln": math.log, "log2": math.log2, "exp": math.exp,
    "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "factorial": math.factorial,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("only numbers are allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES:
        return _NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise ValueError("keyword arguments are not supported")
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def run(expression: str) -> dict:
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree)
    except ZeroDivisionError:
        return {"error": "division by zero"}
    except Exception as exc:  # noqa: BLE001 - surface a clean message to the model
        return {"error": f"could not evaluate: {exc}"}
    return {"expression": expression, "result": result}
