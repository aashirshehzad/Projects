"""AST ``NodeVisitor`` security rules SEC-001 .. SEC-010.

Each rule is pure and deterministic: given the same source it always yields the
same violations, at the same line and column, forever. That property is what
lets Stage 3 trust the input and lets CI treat a green static pass as a hard
gate.

Findings can be silenced inline with ``# nosec`` (all rules on that line) or
``# nosec SEC-002`` / ``# noqa: SEC-002`` (named rules only).
"""

from __future__ import annotations

import ast
import re
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
    "SEC-006": {
        "severity": Severity.HIGH.value,
        "title": "TLS verification disabled",
        "target": "verify=False / ssl._create_unverified_context()",
    },
    "SEC-007": {
        "severity": Severity.MEDIUM.value,
        "title": "Weak cryptography",
        "target": "md5/sha1, ECB mode, random module for secrets",
    },
    "SEC-008": {
        "severity": Severity.MEDIUM.value,
        "title": "Insecure framework configuration",
        "target": "debug=True, DEBUG=True, ALLOWED_HOSTS=['*'], host=0.0.0.0",
    },
    "SEC-009": {
        "severity": Severity.HIGH.value,
        "title": "Overly permissive CORS",
        "target": "allow_origins=['*'], especially with credentials",
    },
    "SEC-010": {
        "severity": Severity.CRITICAL.value,
        "title": "Unsafe deserialization (extended)",
        "target": "yaml.unsafe_load, marshal, torch.load, read_pickle, allow_pickle",
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

# SEC-007: security-sensitive variable names that must not be seeded from `random`.
_SECURITY_NAME_TOKENS = {
    "token", "secret", "key", "nonce", "salt", "password", "passwd",
    "otp", "session", "csrf", "apikey",
}
# SEC-010: fully-qualified calls that deserialize untrusted data unsafely.
_EXTENDED_UNSAFE: dict[str, tuple[str, str]] = {
    "yaml.unsafe_load": ("CRITICAL", "constructs arbitrary Python objects"),
    "marshal.loads": ("CRITICAL", "executes arbitrary code from crafted bytecode"),
    "marshal.load": ("CRITICAL", "executes arbitrary code from crafted bytecode"),
    "shelve.open": ("HIGH", "is backed by pickle and runs code from a crafted file"),
    "jsonpickle.decode": ("HIGH", "can instantiate arbitrary classes"),
}

# Inline suppression: `# nosec` (all rules) / `# nosec SEC-002` / `# noqa: SEC-002`.
_NOSEC_RE = re.compile(r"#\s*nosec\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)
_NOQA_RE = re.compile(r"#\s*noqa\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)


def _suppress_ids(raw: str) -> set[str]:
    return {tok.strip().upper() for tok in raw.replace(",", " ").split() if tok.strip()}


def _line_suppresses(line: str, rule_id: str) -> bool:
    m = _NOSEC_RE.search(line)
    if m is not None:
        ids = _suppress_ids(m.group(1))
        if not ids or rule_id in ids:
            return True
    m = _NOQA_RE.search(line)
    if m is not None and rule_id in _suppress_ids(m.group(1)):
        return True
    return False


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


def _contains_wildcard(node: ast.expr | None) -> bool:
    """True if *node* is ``"*"`` or a list/tuple/set that includes ``"*"``."""
    if isinstance(node, ast.Constant):
        return node.value == "*"
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(isinstance(e, ast.Constant) and e.value == "*" for e in node.elts)
    return False


def _mentions_ecb(call: ast.Call) -> bool:
    for sub in ast.walk(call):
        if isinstance(sub, ast.Attribute) and sub.attr == "MODE_ECB":
            return True
        if isinstance(sub, ast.Name) and sub.id == "MODE_ECB":
            return True
    return False


def _target_name(target: ast.expr) -> str:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return ""


def _is_const_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_const_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


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

        # SEC-006 -- TLS verification disabled
        if name in {"ssl._create_unverified_context", "ssl._create_stdlib_context"}:
            self._add(
                "SEC-006", node,
                f"`{name}()` disables TLS certificate verification for every "
                "connection that uses this context.",
            )
        else:
            verify_kw = next((k for k in node.keywords if k.arg == "verify"), None)
            if verify_kw is not None and _is_const_false(verify_kw.value):
                self._add(
                    "SEC-006", node,
                    f"`{bare or name}(..., verify=False)` disables TLS certificate "
                    "checks; a man-in-the-middle can read and alter the traffic.",
                )

        # SEC-007 -- weak cryptography
        if name in {"hashlib.md5", "hashlib.sha1"}:
            self._add(
                "SEC-007", node,
                f"`{name}()` is a broken hash. Use SHA-256+ for integrity, or "
                "`hashlib.pbkdf2_hmac` / bcrypt / argon2 for passwords.",
            )
        elif bare == "new" and _func_name(getattr(node.func, "value", None)) == "hashlib":
            algo = _literal_str(node.args[0]) if node.args else None
            if algo and algo.lower().replace("-", "") in {"md5", "sha1"}:
                self._add(
                    "SEC-007", node,
                    f"`hashlib.new({algo!r})` selects a broken hash. Use SHA-256+ "
                    "or a password KDF.",
                )
        if (bare == "new" or name.endswith(".new")) and _mentions_ecb(node):
            self._add(
                "SEC-007", node,
                "ECB mode encrypts identical blocks identically and leaks plaintext "
                "structure. Use an authenticated mode such as AES-GCM.",
            )

        # SEC-008 -- insecure framework configuration (call form)
        if bare == "run":
            for k in node.keywords:
                if k.arg == "debug" and _is_const_true(k.value):
                    self._add(
                        "SEC-008", node,
                        "`run(debug=True)` exposes the interactive debugger (remote "
                        "code execution) if the server is reachable. Never enable it "
                        "outside local development.",
                        severity=Severity.HIGH.value,
                    )
                if k.arg == "host" and _literal_str(k.value) in {"0.0.0.0", "::"}:
                    self._add(
                        "SEC-008", node,
                        "Binding to `0.0.0.0` exposes the server on every network "
                        "interface. Bind to `127.0.0.1` for local use.",
                    )

        # SEC-009 -- overly permissive CORS
        origins_kw = next(
            (k for k in node.keywords if k.arg in {"allow_origins", "origins"}), None
        )
        if origins_kw is not None and _contains_wildcard(origins_kw.value):
            creds_kw = next(
                (k for k in node.keywords
                 if k.arg in {"allow_credentials", "supports_credentials"}),
                None,
            )
            with_creds = creds_kw is not None and _is_const_true(creds_kw.value)
            self._add(
                "SEC-009", node,
                "CORS allows any origin (`*`)"
                + (
                    " together with credentials, letting any website make "
                    "authenticated cross-origin requests as the victim."
                    if with_creds
                    else "; restrict it to a known allowlist of origins."
                ),
                severity=Severity.HIGH.value if with_creds else Severity.MEDIUM.value,
            )

        # SEC-010 -- extended unsafe deserialization
        meta010 = _EXTENDED_UNSAFE.get(name)
        if meta010:
            sev, why = meta010
            self._add("SEC-010", node, f"`{name}()` {why}. Use a safe format instead.",
                      severity=sev)
        elif name == "torch.load":
            wo = next((k for k in node.keywords if k.arg == "weights_only"), None)
            if not (wo and _is_const_true(wo.value)):
                self._add(
                    "SEC-010", node,
                    "`torch.load()` unpickles the checkpoint and can run code from a "
                    "crafted file. Pass `weights_only=True`.",
                    severity=Severity.HIGH.value,
                )
        elif bare == "read_pickle" and _func_name(getattr(node.func, "value", None)) in {
            "pandas", "pd",
        }:
            self._add(
                "SEC-010", node,
                "`read_pickle()` executes code embedded in a crafted file. Use "
                "Parquet or CSV for untrusted data.",
                severity=Severity.HIGH.value,
            )
        elif name in {"numpy.load", "np.load"}:
            ap = next((k for k in node.keywords if k.arg == "allow_pickle"), None)
            if ap and _is_const_true(ap.value):
                self._add(
                    "SEC-010", node,
                    "`numpy.load(allow_pickle=True)` can execute code from a crafted "
                    ".npy/.npz file.",
                    severity=Severity.HIGH.value,
                )

        self.generic_visit(node)

    # -- SEC-003 / SEC-007 / SEC-008 / SEC-009 -- assignment-shaped rules --
    def visit_Assign(self, node: ast.Assign) -> None:
        literal = _literal_str(node.value)
        if literal is not None:
            for target in node.targets:
                self._check_secret_target(target, literal, node)
        self._check_config_assign(node.targets, node.value, node)
        self.generic_visit(node)

    def _check_config_assign(
        self, targets: list[ast.expr], value: ast.expr, node: ast.AST
    ) -> None:
        # SEC-007 -- `random` seeding a security-sensitive value
        if isinstance(value, ast.Call):
            fn = _func_name(value.func)
            root = fn.split(".", 1)[0]
            if root == "random" and fn != "random.SystemRandom":
                for t in targets:
                    nm = _target_name(t).lower()
                    parts = {p for p in nm.replace("__", "_").split("_") if p}
                    if nm and parts & _SECURITY_NAME_TOKENS:
                        self._add(
                            "SEC-007", node,
                            f"`{fn}()` is not cryptographically secure; derive "
                            f"`{nm}` from the `secrets` module instead.",
                        )

        for t in targets:
            nm = _target_name(t)
            # SEC-008 -- settings-style booleans / wildcards
            if nm in {"DEBUG", "DJANGO_DEBUG", "FLASK_DEBUG"} and _is_const_true(value):
                self._add(
                    "SEC-008", node,
                    f"`{nm} = True` at import time ships debug mode to production. "
                    "Read it from the environment and default to False.",
                    severity=Severity.HIGH.value,
                )
            if nm in {"ALLOWED_HOSTS", "CORS_ALLOWED_ORIGINS", "CORS_ORIGIN_WHITELIST"} \
                    and _contains_wildcard(value):
                self._add(
                    "SEC-008", node,
                    f"`{nm}` contains `*`, disabling host/origin filtering.",
                )
            # SEC-009 -- Django flask-cors "allow everything" switch
            if nm == "CORS_ORIGIN_ALLOW_ALL" and _is_const_true(value):
                self._add(
                    "SEC-009", node,
                    "`CORS_ORIGIN_ALLOW_ALL = True` allows requests from every origin.",
                    severity=Severity.MEDIUM.value,
                )

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


def scan_source(
    source: str,
    file_path: str = "<string>",
    *,
    config: object | None = None,
) -> list[Violation]:
    """Parse *source* and return de-duplicated, severity-sorted violations.

    A ``SyntaxError`` yields an empty list -- the file is simply skipped rather
    than crashing the run (mirrors the "0 syntax errors" milestone).

    Inline ``# nosec`` / ``# noqa: SEC-00X`` comments on a violation's first or
    last line silence it. *config* (duck-typed: ``.disabled`` set, ``.severity``
    mapping) applies project-level rule toggles and severity overrides.
    """
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return []

    visitor = SecurityAndQualityVisitor(file_path)
    visitor.visit(tree)

    disabled: frozenset[str] = getattr(config, "disabled", frozenset())
    overrides: dict[str, str] = getattr(config, "severity", {})
    lines = source.splitlines()

    def line_at(n: int) -> str:
        return lines[n - 1] if 1 <= n <= len(lines) else ""

    seen: set[tuple[str, str, int, int]] = set()
    unique: list[Violation] = []
    for v in visitor.violations:
        if v.rule_id in disabled or v.key() in seen:
            continue
        if _line_suppresses(line_at(v.line_number), v.rule_id) or (
            v.end_line_number
            and _line_suppresses(line_at(v.end_line_number), v.rule_id)
        ):
            continue
        if v.rule_id in overrides:
            v.severity = Severity(overrides[v.rule_id])
        seen.add(v.key())
        unique.append(v)

    unique.sort(key=lambda v: (v.severity.rank, v.line_number, v.rule_id))
    return unique
