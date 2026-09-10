"""AST ``NodeVisitor`` security rules SEC-001 .. SEC-005.

Each rule is pure and deterministic: given the same source it always yields the
same violations, at the same line and column, forever. That property is what
lets Stage 3 trust the input and lets CI treat a green static pass as a hard
gate.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def rank(self) -> int:
        return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}[self.value]


@dataclass(slots=True)
class Violation:
    """A single deterministic finding located at a precise source position."""

    rule_id: str
    severity: Severity
    title: str
    message: str
    file_path: str
    line_number: int
    col_offset: int = 0
    end_line_number: int | None = None
    # Filled in by the engine once the file's line list is available.
    snippet: str = ""
    context_start_line: int = 0

    def key(self) -> tuple[str, str, int, int]:
        return (self.file_path, self.rule_id, self.line_number, self.col_offset)


# Rule catalogue -- kept as data so the reporter and docs can enumerate it.
RULES: dict[str, dict[str, str]] = {
    "SEC-001": {
        "severity": Severity.CRITICAL.value,
        "title": "Dynamic code execution",
        "target": "eval / exec / __import__",
    },
    "SEC-002": {
        "severity": Severity.HIGH.value,
        "title": "Raw SQL string formatting",
        "target": "cursor.execute() with f-string / % / .format()",
    },
    "SEC-003": {
        "severity": Severity.HIGH.value,
        "title": "Hardcoded secret assignment",
        "target": "key/secret/token/password = '<literal>'",
    },
    "SEC-004": {
        "severity": Severity.CRITICAL.value,
        "title": "Unsafe deserialization",
        "target": "pickle.loads / yaml.load without SafeLoader",
    },
    "SEC-005": {
        "severity": Severity.MEDIUM.value,
        "title": "Command injection",
        "target": "shell=True / os.system() with dynamic arguments",
    },
}

_DANGEROUS_BUILTINS = {"eval", "exec", "__import__"}
_SECRET_TOKENS = {
    "key",
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "apikey",
    "credential",
    "credentials",
    "auth",
}
_SECRET_PLACEHOLDERS = {
    "",
    "changeme",
    "change_me",
    "placeholder",
    "example",
    "your_key_here",
    "xxx",
    "todo",
    "none",
    "null",
}
_SUBPROCESS_FUNCS = {"Popen", "call", "run", "check_call", "check_output"}
_UNSAFE_YAML_LOADERS = {"Loader", "FullLoader", "UnsafeLoader", "CLoader", "CFullLoader"}


def _func_name(node: ast.AST) -> str:
    """Dotted name of a call target, e.g. ``cursor.execute`` -> ``"cursor.execute"``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_func_name(node.value)}.{node.attr}" if node.value else node.attr
    return ""


def _is_dynamic_string(node: ast.expr | None) -> bool:
    """True when *node* builds a string at runtime rather than being a literal."""
    if node is None:
        return False
    if isinstance(node, ast.JoinedStr):  # f"..."
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    if isinstance(node, ast.Call):  # "...".format(...), " ".join(...), etc.
        fn = _func_name(node.func)
        if fn.endswith(".format") or fn.endswith(".join") or fn == "str":
            return True
    if isinstance(node, ast.Name):  # a variable whose contents we cannot see
        return True
    if isinstance(node, (ast.List, ast.Tuple)):
        return any(_is_dynamic_string(elt) for elt in node.elts)
    return False


def _literal_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class SecurityAndQualityVisitor(ast.NodeVisitor):
    """Walks one module and accumulates :class:`Violation` records."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.violations: list[Violation] = []

    # -- helpers ---------------------------------------------------------------
    def _add(
        self,
        rule_id: str,
        node: ast.AST,
        message: str,
        *,
        severity: str | None = None,
    ) -> None:
        meta = RULES[rule_id]
        self.violations.append(
            Violation(
                rule_id=rule_id,
                severity=Severity(severity or meta["severity"]),
                title=meta["title"],
                message=message,
                file_path=self.file_path,
                line_number=getattr(node, "lineno", 1),
                col_offset=getattr(node, "col_offset", 0),
                end_line_number=getattr(node, "end_lineno", None),
            )
        )

    # -- SEC-001 / SEC-002 / SEC-004 / SEC-005 all hang off Call -------------
    def visit_Call(self, node: ast.Call) -> None:
        name = _func_name(node.func)
        bare = name.rsplit(".", 1)[-1]

        # SEC-001 -- dynamic code execution
        if isinstance(node.func, ast.Name) and node.func.id in _DANGEROUS_BUILTINS:
            self._add(
                "SEC-001",
                node,
                f"Call to `{node.func.id}()` executes arbitrary code at runtime.",
            )
        elif isinstance(node.func, ast.Attribute) and bare in _DANGEROUS_BUILTINS:
            self._add(
                "SEC-001",
                node,
                f"Call to `{name}()` executes arbitrary code at runtime.",
            )

        # SEC-002 -- raw SQL string built for cursor.execute()
        if bare in {"execute", "executemany", "executescript", "raw"}:
            first = node.args[0] if node.args else None
            if isinstance(first, ast.JoinedStr):
                self._add(
                    "SEC-002",
                    node,
                    f"`{name}()` receives an f-string; use parameterised queries "
                    "(`execute(sql, params)`).",
                )
            elif isinstance(first, ast.BinOp) and isinstance(first.op, (ast.Mod, ast.Add)):
                op = "%" if isinstance(first.op, ast.Mod) else "+"
                self._add(
                    "SEC-002",
                    node,
                    f"`{name}()` receives a string built with `{op}`; use bound "
                    "parameters instead of interpolation.",
                )
            elif isinstance(first, ast.Call) and _func_name(first.func).endswith(".format"):
                self._add(
                    "SEC-002",
                    node,
                    f"`{name}()` receives a `.format()` string; use bound parameters "
                    "instead of interpolation.",
                )

        # SEC-004 -- unsafe deserialization
        if name in {"pickle.loads", "pickle.load", "cPickle.loads", "cPickle.load"} or (
            bare in {"loads", "load"} and _func_name(getattr(node.func, "value", None)) in {"pickle", "cPickle", "dill"}
        ):
            self._add(
                "SEC-004",
                node,
                f"`{name}()` deserializes untrusted data and can execute arbitrary "
                "code. Use a safe format (JSON) or verified signatures.",
            )
        elif bare == "load" and _func_name(getattr(node.func, "value", None)) == "yaml":
            loader_kw = next((k for k in node.keywords if k.arg == "Loader"), None)
            loader_name = _func_name(loader_kw.value).rsplit(".", 1)[-1] if loader_kw else ""
            if loader_kw is None or loader_name in _UNSAFE_YAML_LOADERS:
                self._add(
                    "SEC-004",
                    node,
                    "`yaml.load()` without `Loader=yaml.SafeLoader` can construct "
                    "arbitrary Python objects. Use `yaml.safe_load()`.",
                )

        # SEC-005 -- command injection
        if name in {"os.system", "os.popen", "commands.getoutput"}:
            arg = node.args[0] if node.args else None
            if _is_dynamic_string(arg):
                self._add(
                    "SEC-005",
                    node,
                    f"`{name}()` runs a shell command assembled at runtime. Use "
                    "`subprocess.run([...], shell=False)` with an argument list.",
                    severity=Severity.HIGH.value,
                )
        subprocess_qualified = (
            bare in _SUBPROCESS_FUNCS
            and _func_name(getattr(node.func, "value", None)) in {"subprocess", "sp"}
        )
        subprocess_bare = (
            isinstance(node.func, ast.Name) and node.func.id in _SUBPROCESS_FUNCS
        )
        if subprocess_qualified or subprocess_bare:
            shell_kw = next((k for k in node.keywords if k.arg == "shell"), None)
            shell_true = (
                shell_kw is not None
                and isinstance(shell_kw.value, ast.Constant)
                and shell_kw.value.value is True
            )
            if shell_true:
                cmd = node.args[0] if node.args else None
                dynamic = _is_dynamic_string(cmd)
                self._add(
                    "SEC-005",
                    node,
                    (
                        f"`{bare}(..., shell=True)` with a runtime-built command is a "
                        "shell-injection sink."
                        if dynamic
                        else f"`{bare}(..., shell=True)` invokes a shell; pass an "
                        "argument list with `shell=False` instead."
                    ),
                    severity=Severity.HIGH.value if dynamic else Severity.MEDIUM.value,
                )

        self.generic_visit(node)

    # -- SEC-003 -- hardcoded secrets ---------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        literal = _literal_str(node.value)
        if literal is not None:
            for target in node.targets:
                self._check_secret_target(target, literal, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        literal = _literal_str(node.value)
        if literal is not None:
            self._check_secret_target(node.target, literal, node)
        self.generic_visit(node)

    def _check_secret_target(self, target: ast.expr, value: str, node: ast.AST) -> None:
        ident = ""
        if isinstance(target, ast.Name):
            ident = target.id
        elif isinstance(target, ast.Attribute):
            ident = target.attr
        if not ident:
            return
        lowered = ident.lower()
        parts = {p for p in lowered.replace("__", "_").split("_") if p}
        hit = parts & _SECRET_TOKENS or any(tok in lowered for tok in _SECRET_TOKENS)
        if not hit:
            return
        if "public" in lowered or lowered.endswith(("_name", "_id", "_path", "_url", "_field")):
            return
        if value.strip().lower() in _SECRET_PLACEHOLDERS or len(value.strip()) < 4:
            return
        if value.startswith(("<", "${", "{{", "os.")):
            return
        self._add(
            "SEC-003",
            node,
            f"`{ident}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets manager.",
        )


def scan_source(source: str, file_path: str = "<string>") -> list[Violation]:
    """Parse *source* and return de-duplicated, severity-sorted violations.

    A ``SyntaxError`` yields an empty list -- the file is simply skipped rather
    than crashing the run (mirrors the "0 syntax errors" milestone).
    """
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    visitor = SecurityAndQualityVisitor(file_path)
    visitor.visit(tree)

    seen: set[tuple[str, str, int, int]] = set()
    unique: list[Violation] = []
    for v in visitor.violations:
        if v.key() in seen:
            continue
        seen.add(v.key())
        unique.append(v)

    unique.sort(key=lambda v: (v.severity.rank, v.line_number, v.rule_id))
    return unique
