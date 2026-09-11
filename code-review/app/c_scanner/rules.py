"""C-001 .. C-006: deterministic tree-sitter checks for C/C++.

Same shape as ``app.js_scanner.rules``: walk a concrete syntax tree, match
exact node shapes, never guess. These are the same "banned function" /
non-literal-format-string patterns real C linters (flawfinder, cppcheck,
Microsoft's banned.h) flag without needing pointer/data-flow analysis --
genuine buffer-overflow and memory-safety analysis is a much bigger
undertaking and out of scope here (see CLAUDE.md).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.c_scanner.grammar import get_parser
from app.static_scanner.ast_rules import RULES, Severity, Violation

RULES.update(
    {
        "C-001": {
            "severity": Severity.HIGH.value,
            "title": "Unbounded string function",
            "target": "gets/strcpy/strcat/sprintf/vsprintf -- classic buffer overflow sinks",
        },
        "C-002": {
            "severity": Severity.HIGH.value,
            "title": "Format string vulnerability",
            "target": "printf/fprintf/syslog/scanf family with a non-literal format argument",
        },
        "C-003": {
            "severity": Severity.HIGH.value,
            "title": "Hardcoded secret assignment",
            "target": "key/secret/token/password = \"<literal>\" or #define ... \"<literal>\"",
        },
        "C-004": {
            "severity": Severity.HIGH.value,
            "title": "Command injection",
            "target": "system()/popen() with a runtime-built command",
        },
        "C-005": {
            "severity": Severity.MEDIUM.value,
            "title": "Insecure randomness for a secret",
            "target": "rand() seeding a token/secret/key/session value",
        },
        "C-006": {
            "severity": Severity.MEDIUM.value,
            "title": "Unbounded stack allocation",
            "target": "alloca() with a non-constant size",
        },
    }
)

_UNBOUNDED_STRING_FUNCS = {"gets", "strcpy", "strcat", "sprintf", "vsprintf"}
# (call, index-of-the-format-argument)
_FORMAT_FUNCS = {
    "printf": 0, "wprintf": 0,
    "fprintf": 1, "fwprintf": 1, "syslog": 1,
    "scanf": 0, "fscanf": 1, "sscanf": 1,
}
_SECRET_TOKENS = {
    "key", "secret", "token", "password", "passwd", "pwd",
    "apikey", "credential", "credentials", "auth",
}
_SECURITY_NAME_TOKENS = {
    "token", "secret", "key", "nonce", "salt", "password", "passwd",
    "otp", "session", "csrf", "apikey",
}
_SECRET_PLACEHOLDERS = {
    "", "changeme", "change_me", "placeholder", "example",
    "your_key_here", "xxx", "todo", "none", "null",
}

_NOSEC_RE = re.compile(r"//\s*nosec\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)
_NOQA_RE = re.compile(r"//\s*noqa\b\s*:?\s*([A-Za-z0-9,\s\-]*)", re.IGNORECASE)


def _suppress_ids(raw: str) -> set[str]:
    return {tok.strip().upper() for tok in raw.replace(",", " ").split() if tok.strip()}


def _line_suppresses(line: str, rule_id: str) -> bool:
    m = _NOSEC_RE.search(line)
    if m is not None:
        ids = _suppress_ids(m.group(1))
        if not ids or rule_id in ids:
            return True
    m = _NOQA_RE.search(line)
    return m is not None and rule_id in _suppress_ids(m.group(1))


# --------------------------------------------------------------------------- #
# tree helpers
# --------------------------------------------------------------------------- #
def _walk(node):
    yield node
    for c in node.children:
        yield from _walk(c)


def _text(node) -> str:
    return node.text.decode("utf-8", "replace") if node is not None else ""


def _callee_name(node) -> str:
    if node is None:
        return ""
    if node.type in {"identifier", "field_identifier"}:
        return _text(node)
    if node.type == "field_expression":  # obj.method / obj->method (C++)
        base = _callee_name(node.child_by_field_name("argument"))
        field = _text(node.child_by_field_name("field"))
        return f"{base}.{field}" if base else field
    if node.type == "qualified_identifier":  # std::system (C++)
        return _text(node.child_by_field_name("name"))
    return ""


def _string_literal(node) -> str | None:
    if node is None:
        return None
    if node.type == "string_literal":
        frag = next((c for c in node.named_children if c.type == "string_content"), None)
        return _text(frag)
    return None


def _is_dynamic(node) -> bool:
    if node is None:
        return False
    if _string_literal(node) is not None:
        return False
    return node.type not in {"number_literal", "char_literal", "true", "false", "null", "nullptr"}


def _arg_nodes(call_node) -> list:
    args = call_node.child_by_field_name("arguments")
    return list(args.named_children) if args is not None else []


def _mentions_rand(node) -> bool:
    for n in _walk(node):
        if n.type == "call_expression" and _callee_name(n.child_by_field_name("function")) == "rand":
            return True
    return False


def _declared_name(declarator) -> str | None:
    """First identifier inside a (possibly pointer/array-wrapped) declarator."""
    if declarator is None:
        return None
    for n in _walk(declarator):
        if n.type == "identifier":
            return _text(n)
    return None


def _split_identifier(name: str) -> set[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return {p.lower() for p in re.split(r"[_\-]+", spaced) if p}


def _looks_like_secret(name: str, value: str) -> bool:
    lowered = name.lower()
    parts = _split_identifier(name)
    if not (parts & _SECRET_TOKENS or any(tok in lowered for tok in _SECRET_TOKENS)):
        return False
    if "public" in lowered or lowered.endswith(("name", "id", "path", "url", "field")):
        return False
    v = value.strip()
    if v.lower() in _SECRET_PLACEHOLDERS or len(v) < 4:
        return False
    if v.startswith(("<", "${", "{{")):
        return False
    return True


def _is_security_named(name: str) -> bool:
    return bool(_split_identifier(name) & _SECURITY_NAME_TOKENS)


def _preproc_string_value(value_node) -> str | None:
    """``#define NAME "literal"`` -- the value is a raw, unparsed token; unquote it by hand."""
    text = _text(value_node).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return None


# --------------------------------------------------------------------------- #
# per-node-type rule checks
# --------------------------------------------------------------------------- #
def _check_call(node, add: Callable) -> None:
    callee = node.child_by_field_name("function")
    name = _callee_name(callee)
    args = _arg_nodes(node)

    # C-001
    if name in _UNBOUNDED_STRING_FUNCS:
        add(
            "C-001", node,
            f"`{name}()` writes to a fixed-size buffer with no bound and no "
            "NUL-termination guarantee -- a classic overflow. Use the `n`-bounded "
            "variant (`strncpy`/`strncat`/`snprintf`) and check the return value.",
            severity=Severity.CRITICAL.value if name == "gets" else None,
        )

    # C-002
    if name in _FORMAT_FUNCS:
        idx = _FORMAT_FUNCS[name]
        if len(args) > idx and _is_dynamic(args[idx]):
            add(
                "C-002", node,
                f"`{name}()` uses a runtime value as the format string. If it "
                "contains user input, `%n`/`%s` specifiers can read or write "
                "arbitrary memory. Pass a literal format string.",
            )

    # C-004
    if name in {"system", "popen"} and args and _is_dynamic(args[0]):
        add(
            "C-004", node,
            f"`{name}()` runs a shell command assembled at runtime. Validate/allow-list "
            "the input, or use `execve()` with an argument array (no shell).",
        )

    # C-006
    if name == "alloca" and args and args[0].type != "number_literal":
        add(
            "C-006", node,
            "`alloca()` with a non-constant size can overflow the stack if the "
            "size is attacker-influenced. Bound it or use heap allocation.",
        )


def _check_init_declarator(node, add: Callable) -> None:
    name = _declared_name(node.child_by_field_name("declarator"))
    value = node.child_by_field_name("value")
    if name is None or value is None:
        return
    literal = _string_literal(value)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "C-003", node,
            f"`{name}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets store.",
        )
    if _is_security_named(name) and _mentions_rand(value):
        add(
            "C-005", node,
            f"`{name}` is derived from `rand()`, which is not cryptographically "
            "secure and often not even seeded unpredictably. Use a CSPRNG "
            "(`arc4random()`, `getrandom()`, `/dev/urandom`, or a crypto library).",
        )


def _check_assignment(node, add: Callable) -> None:
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None or left.type != "identifier":
        return
    name = _text(left)
    literal = _string_literal(right)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "C-003", node,
            f"`{name}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets store.",
        )
    if _is_security_named(name) and _mentions_rand(right):
        add(
            "C-005", node,
            f"`{name}` is derived from `rand()`, which is not cryptographically "
            "secure and often not even seeded unpredictably. Use a CSPRNG "
            "(`arc4random()`, `getrandom()`, `/dev/urandom`, or a crypto library).",
        )


def _check_preproc_def(node, add: Callable) -> None:
    name_node, value_node = node.child_by_field_name("name"), node.child_by_field_name("value")
    if name_node is None or value_node is None:
        return
    name = _text(name_node)
    literal = _preproc_string_value(value_node)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "C-003", node,
            f"`#define {name}` is a hardcoded literal secret compiled into the "
            "binary. Load it from the environment or a secrets store.",
        )


_DISPATCH: dict[str, Callable[[Any, Callable], None]] = {
    "call_expression": _check_call,
    "init_declarator": _check_init_declarator,
    "assignment_expression": _check_assignment,
    "preproc_def": _check_preproc_def,
}


def scan_c_source(
    source: str,
    file_path: str = "<string>",
    *,
    config: object | None = None,
) -> list[Violation]:
    """Parse *source* with the grammar matching *file_path*'s suffix (.c vs .cpp/...) and scan it."""
    parser = get_parser(file_path)
    if parser is None:
        return []
    try:
        tree = parser.parse(source.encode("utf-8"))
    except (UnicodeEncodeError, ValueError):
        return []

    found: list[Violation] = []

    def add(rule_id: str, node, message: str, *, severity: str | None = None) -> Violation:
        meta = RULES[rule_id]
        v = Violation(
            rule_id=rule_id,
            severity=Severity(severity or meta["severity"]),
            title=meta["title"],
            message=message,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            col_offset=node.start_point[1],
            end_line_number=node.end_point[0] + 1,
        )
        found.append(v)
        return v

    for node in _walk(tree.root_node):
        handler = _DISPATCH.get(node.type)
        if handler is not None:
            handler(node, add)

    disabled: frozenset[str] = getattr(config, "disabled", frozenset())
    overrides: dict[str, str] = getattr(config, "severity", {})
    lines = source.splitlines()

    def line_at(n: int) -> str:
        return lines[n - 1] if 1 <= n <= len(lines) else ""

    seen: set[tuple[str, str, int, int]] = set()
    out: list[Violation] = []
    for v in found:
        if v.rule_id in disabled or v.key() in seen:
            continue
        if _line_suppresses(line_at(v.line_number), v.rule_id) or (
            v.end_line_number and _line_suppresses(line_at(v.end_line_number), v.rule_id)
        ):
            continue
        if v.rule_id in overrides:
            v.severity = Severity(overrides[v.rule_id])
        seen.add(v.key())
        out.append(v)

    out.sort(key=lambda v: (v.severity.rank, v.line_number, v.rule_id))
    return out
