"""JS-001 .. JS-006: deterministic tree-sitter checks for JavaScript/TypeScript.

Same design as ``app.static_scanner.ast_rules``, ported to a different parser:
walk a concrete syntax tree, match exact node shapes, never guess. tree-sitter
is error-tolerant (it never raises on malformed input, unlike Python's ``ast``),
so a syntax-broken file degrades to fewer matches rather than a crash.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.js_scanner.grammar import get_parser
from app.static_scanner.ast_rules import RULES, Severity, Violation

RULES.update(
    {
        "JS-001": {
            "severity": Severity.CRITICAL.value,
            "title": "Dynamic code execution (JS)",
            "target": "eval() / new Function() / setTimeout|setInterval with a string",
        },
        "JS-002": {
            "severity": Severity.HIGH.value,
            "title": "DOM-based XSS sink",
            "target": "innerHTML/outerHTML assignment, document.write, "
            "insertAdjacentHTML, dangerouslySetInnerHTML",
        },
        "JS-003": {
            "severity": Severity.HIGH.value,
            "title": "Hardcoded secret assignment",
            "target": "key/secret/token/password = \"<literal>\"",
        },
        "JS-004": {
            "severity": Severity.HIGH.value,
            "title": "Command injection (Node child_process)",
            "target": "exec()/execSync() with a runtime-built command",
        },
        "JS-005": {
            "severity": Severity.MEDIUM.value,
            "title": "Insecure randomness for a secret",
            "target": "Math.random() seeding a token/secret/key/session value",
        },
        "JS-006": {
            "severity": Severity.HIGH.value,
            "title": "TLS verification disabled",
            "target": "rejectUnauthorized: false / NODE_TLS_REJECT_UNAUTHORIZED=0",
        },
    }
)

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
    """Dotted name of a call/member target: ``foo.bar.baz`` -> ``"foo.bar.baz"``."""
    if node is None:
        return ""
    if node.type == "identifier":
        return _text(node)
    if node.type == "member_expression":
        base = _callee_name(node.child_by_field_name("object"))
        prop = _text(node.child_by_field_name("property"))
        return f"{base}.{prop}" if base else prop
    return ""


def _string_literal(node) -> str | None:
    """Literal text of a plain string or a template string with no ``${...}``."""
    if node is None:
        return None
    if node.type == "string":
        frag = next((c for c in node.named_children if c.type == "string_fragment"), None)
        return _text(frag)
    if node.type == "template_string":
        if any(c.type == "template_substitution" for c in node.children):
            return None
        frag = next((c for c in node.named_children if c.type == "string_fragment"), None)
        return _text(frag)
    return None


def _is_dynamic(node) -> bool:
    """True when *node* is built at runtime rather than a plain literal."""
    if node is None:
        return False
    if _string_literal(node) is not None:
        return False
    return node.type not in {"number", "true", "false", "null", "undefined"}


def _arg_nodes(call_node) -> list:
    args = call_node.child_by_field_name("arguments")
    return list(args.named_children) if args is not None else []


def _mentions_math_random(node) -> bool:
    for n in _walk(node):
        if n.type == "call_expression" and _callee_name(n.child_by_field_name("function")) == "Math.random":
            return True
    return False


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


def _key_text(pair_or_property) -> str | None:
    key = pair_or_property.child_by_field_name("key")
    if key is None:
        return None
    if key.type == "property_identifier":
        return _text(key)
    if key.type == "string":
        return _string_literal(key)
    return None


# --------------------------------------------------------------------------- #
# per-node-type rule checks
# --------------------------------------------------------------------------- #
def _check_call(node, add: Callable) -> None:
    callee = node.child_by_field_name("function")
    name = _callee_name(callee)
    bare = name.rsplit(".", 1)[-1]
    args = _arg_nodes(node)

    # JS-001
    if name == "eval":
        add("JS-001", node, "`eval()` executes arbitrary code at runtime.")
    elif bare in {"setTimeout", "setInterval"} and args and args[0].type in {"string", "template_string"}:
        add(
            "JS-001", node,
            f"`{bare}()` was passed a string instead of a function; the string is "
            "evaluated as code. Pass a function reference instead.",
        )

    # JS-002
    if name in {"document.write", "document.writeln"} and args and _is_dynamic(args[0]):
        add(
            "JS-002", node,
            f"`{name}()` writes a runtime-built value into the page, which can "
            "inject a script (XSS). Use DOM APIs (textContent, createElement) instead.",
        )
    elif bare == "insertAdjacentHTML" and len(args) >= 2 and _is_dynamic(args[1]):
        add(
            "JS-002", node,
            "`insertAdjacentHTML()` inserts a runtime-built HTML string, which can "
            "inject a script (XSS). Sanitize the value or build DOM nodes instead.",
        )

    # JS-004 -- Node child_process command injection
    if bare in {"exec", "execSync"} and args and _is_dynamic(args[0]):
        add(
            "JS-004", node,
            f"`{bare}()` runs a shell command assembled at runtime. Use "
            "`execFile`/`spawn` with an argument array instead of a shell string.",
        )


def _check_new(node, add: Callable) -> None:
    ctor = node.child_by_field_name("constructor")
    if _callee_name(ctor) == "Function":
        add("JS-001", node, "`new Function(...)` compiles and executes arbitrary code at runtime.")


def _check_assignment(node, add: Callable) -> None:
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None:
        return

    if left.type == "member_expression":
        prop = _text(left.child_by_field_name("property"))
        dotted = _callee_name(left)
        if prop in {"innerHTML", "outerHTML"} and _is_dynamic(right):
            add(
                "JS-002", node,
                f"`.{prop}` is assigned a runtime-built value, which can inject a "
                "script (XSS). Use `.textContent` or build DOM nodes instead.",
            )
        if dotted == "process.env.NODE_TLS_REJECT_UNAUTHORIZED" and _string_literal(right) == "0":
            add(
                "JS-006", node,
                "`process.env.NODE_TLS_REJECT_UNAUTHORIZED = \"0\"` disables TLS "
                "certificate verification for the whole process.",
            )
        literal = _string_literal(right)
        if literal is not None and _looks_like_secret(prop, literal):
            add(
                "JS-003", node,
                f"`{dotted}` is assigned a hardcoded literal secret. Load it from "
                "the environment or a secrets manager.",
            )
        if _is_security_named(prop) and _mentions_math_random(right):
            add(
                "JS-005", node,
                f"`{dotted}` is derived from `Math.random()`, which is not "
                "cryptographically secure. Use `crypto.randomBytes()` / "
                "`crypto.randomUUID()`.",
            )

    elif left.type == "identifier":
        name = _text(left)
        literal = _string_literal(right)
        if literal is not None and _looks_like_secret(name, literal):
            add(
                "JS-003", node,
                f"`{name}` is assigned a hardcoded literal secret. Load it from "
                "the environment or a secrets manager.",
            )
        if _is_security_named(name) and _mentions_math_random(right):
            add(
                "JS-005", node,
                f"`{name}` is derived from `Math.random()`, which is not "
                "cryptographically secure. Use `crypto.randomBytes()` / "
                "`crypto.randomUUID()`.",
            )


def _check_variable_declarator(node, add: Callable) -> None:
    name_node, value = node.child_by_field_name("name"), node.child_by_field_name("value")
    if name_node is None or value is None or name_node.type != "identifier":
        return
    name = _text(name_node)
    literal = _string_literal(value)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "JS-003", node,
            f"`{name}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets manager.",
        )
    if _is_security_named(name) and _mentions_math_random(value):
        add(
            "JS-005", node,
            f"`{name}` is derived from `Math.random()`, which is not "
            "cryptographically secure. Use `crypto.randomBytes()` / "
            "`crypto.randomUUID()`.",
        )


def _check_pair(node, add: Callable) -> None:
    key = _key_text(node)
    value = node.child_by_field_name("value")
    if key is None or value is None:
        return
    if key == "rejectUnauthorized" and value.type == "false":
        add(
            "JS-006", node,
            "`rejectUnauthorized: false` disables TLS certificate verification "
            "for this client/request.",
        )
    literal = _string_literal(value)
    if literal is not None and _looks_like_secret(key, literal):
        add(
            "JS-003", node,
            f"`{key}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets manager.",
        )
    if _is_security_named(key) and _mentions_math_random(value):
        add(
            "JS-005", node,
            f"`{key}` is derived from `Math.random()`, which is not "
            "cryptographically secure. Use `crypto.randomBytes()` / "
            "`crypto.randomUUID()`.",
        )


def _check_jsx_attribute(node, add: Callable) -> None:
    named = node.named_children
    if named and _text(named[0]) == "dangerouslySetInnerHTML":
        add(
            "JS-002", node,
            "`dangerouslySetInnerHTML` renders raw HTML with no sanitization; "
            "only use it with trusted, sanitized content.",
        )


_DISPATCH: dict[str, Callable[[Any, Callable], None]] = {
    "call_expression": _check_call,
    "new_expression": _check_new,
    "assignment_expression": _check_assignment,
    "variable_declarator": _check_variable_declarator,
    "pair": _check_pair,
    "jsx_attribute": _check_jsx_attribute,
}


def scan_js_source(
    source: str,
    file_path: str = "<string>",
    *,
    config: object | None = None,
) -> list[Violation]:
    """Parse *source* with the grammar matching *file_path*'s suffix and scan it.

    An unsupported suffix or an unreadable/undecodable source returns ``[]``,
    same convention as ``ast_rules.scan_source`` on a ``SyntaxError``.
    """
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
