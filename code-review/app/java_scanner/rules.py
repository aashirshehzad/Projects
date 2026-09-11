"""JAVA-001 .. JAVA-006: deterministic tree-sitter checks for Java.

Same shape as ``app.js_scanner.rules`` / ``app.c_scanner.rules``: walk a
concrete syntax tree, match exact node shapes, never guess. The rule set
mirrors what real Java SAST tools (FindSecBugs/SpotBugs) flag with pattern
matching alone -- unsafe deserialization, string-built SQL, hardcoded
secrets, Runtime.exec injection, weak crypto, predictable randomness.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from app.java_scanner.grammar import get_parser
from app.static_scanner.ast_rules import RULES, Severity, Violation

RULES.update(
    {
        "JAVA-001": {
            "severity": Severity.CRITICAL.value,
            "title": "Unsafe deserialization",
            "target": "ObjectInputStream.readObject() on untrusted data",
        },
        "JAVA-002": {
            "severity": Severity.HIGH.value,
            "title": "SQL built with string concatenation",
            "target": "Statement.execute*() with a `+`-built query",
        },
        "JAVA-003": {
            "severity": Severity.HIGH.value,
            "title": "Hardcoded secret assignment",
            "target": "key/secret/token/password = \"<literal>\"",
        },
        "JAVA-004": {
            "severity": Severity.HIGH.value,
            "title": "Command injection",
            "target": "Runtime.exec() with a runtime-built command string",
        },
        "JAVA-005": {
            "severity": Severity.MEDIUM.value,
            "title": "Weak cryptography",
            "target": "MessageDigest MD5/SHA1, Cipher in ECB mode",
        },
        "JAVA-006": {
            "severity": Severity.MEDIUM.value,
            "title": "Insecure randomness for a secret",
            "target": "new Random() seeding a token/secret/session value",
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
_SQL_METHODS = {"executeQuery", "executeUpdate", "execute", "addBatch"}
_WEAK_HASHES = {"md5", "sha1", "sha-1"}

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
    """Best-effort dotted text for a receiver expression."""
    if node is None:
        return ""
    if node.type in {"identifier", "type_identifier", "this"}:
        return _text(node)
    if node.type == "method_invocation":
        base = _callee_name(node.child_by_field_name("object"))
        name = _text(node.child_by_field_name("name"))
        return f"{base}.{name}" if base else name
    if node.type == "field_access":
        base = _callee_name(node.child_by_field_name("object"))
        field = _text(node.child_by_field_name("field"))
        return f"{base}.{field}" if base else field
    if node.type == "object_creation_expression":
        return _text(node.child_by_field_name("type"))
    return ""


def _string_literal(node) -> str | None:
    if node is None or node.type != "string_literal":
        return None
    frag = next((c for c in node.named_children if c.type == "string_fragment"), None)
    return _text(frag)


def _is_dynamic(node) -> bool:
    if node is None:
        return False
    if _string_literal(node) is not None:
        return False
    return node.type not in {
        "decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
        "decimal_floating_point_literal", "true", "false", "null_literal", "character_literal",
    }


def _arg_nodes(call_node) -> list:
    args = call_node.child_by_field_name("arguments")
    return list(args.named_children) if args is not None else []


def _mentions_new_random(node) -> bool:
    for n in _walk(node):
        if n.type == "object_creation_expression":
            t = _text(n.child_by_field_name("type"))
            if t == "Random":  # SecureRandom is the safe alternative -- don't flag it
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


# --------------------------------------------------------------------------- #
# per-node-type rule checks
# --------------------------------------------------------------------------- #
def _check_call(node, add: Callable) -> None:
    obj = node.child_by_field_name("object")
    bare = _text(node.child_by_field_name("name"))
    obj_name = _callee_name(obj)
    full = f"{obj_name}.{bare}" if obj_name else bare
    args = _arg_nodes(node)

    # JAVA-001 -- unsafe deserialization
    if bare == "readObject":
        add(
            "JAVA-001", node,
            f"`{full}()` deserializes a stream and can instantiate arbitrary "
            "classes / run gadget-chain code if the stream is untrusted. Use a "
            "safe format (JSON) or a validating `ObjectInputFilter`.",
        )

    # JAVA-002 -- SQL built with string concatenation
    if bare in _SQL_METHODS and args and args[0].type == "binary_expression":
        add(
            "JAVA-002", node,
            f"`{full}()` receives a query string built with `+`; use a "
            "`PreparedStatement` with bound parameters instead of concatenation.",
        )

    # JAVA-004 -- command injection
    if bare == "exec" and args and _is_dynamic(args[0]):
        add(
            "JAVA-004", node,
            f"`{full}()` runs a shell command assembled at runtime. Use the "
            "`exec(String[])` / `ProcessBuilder` array form with no shell "
            "interpretation instead of a single command string.",
        )

    # JAVA-005 -- weak cryptography
    if bare == "getInstance" and args:
        algo = _string_literal(args[0])
        if algo is not None:
            algo_l = algo.lower()
            if obj_name == "MessageDigest" and algo_l in _WEAK_HASHES:
                add(
                    "JAVA-005", node,
                    f"`MessageDigest.getInstance({algo!r})` is a broken hash. Use "
                    "SHA-256+ for integrity, or a password KDF (bcrypt/argon2/PBKDF2) "
                    "for passwords.",
                )
            elif obj_name == "Cipher" and "ecb" in algo_l:
                add(
                    "JAVA-005", node,
                    f"`Cipher.getInstance({algo!r})` uses ECB mode, which encrypts "
                    "identical blocks identically and leaks plaintext structure. "
                    "Use an authenticated mode such as AES/GCM.",
                )


def _check_variable_declarator(node, add: Callable) -> None:
    name_node, value = node.child_by_field_name("name"), node.child_by_field_name("value")
    if name_node is None or value is None:
        return
    name = _text(name_node)
    literal = _string_literal(value)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "JAVA-003", node,
            f"`{name}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets manager.",
        )
    if _is_security_named(name) and _mentions_new_random(value):
        add(
            "JAVA-006", node,
            f"`{name}` is derived from `new Random()`, which is predictable and "
            "not cryptographically secure. Use `java.security.SecureRandom`.",
        )


def _check_assignment(node, add: Callable) -> None:
    left, right = node.child_by_field_name("left"), node.child_by_field_name("right")
    if left is None or right is None or left.type != "identifier":
        return
    name = _text(left)
    literal = _string_literal(right)
    if literal is not None and _looks_like_secret(name, literal):
        add(
            "JAVA-003", node,
            f"`{name}` is assigned a hardcoded literal secret. Load it from the "
            "environment or a secrets manager.",
        )
    if _is_security_named(name) and _mentions_new_random(right):
        add(
            "JAVA-006", node,
            f"`{name}` is derived from `new Random()`, which is predictable and "
            "not cryptographically secure. Use `java.security.SecureRandom`.",
        )


_DISPATCH: dict[str, Callable[[Any, Callable], None]] = {
    "method_invocation": _check_call,
    "variable_declarator": _check_variable_declarator,
    "assignment_expression": _check_assignment,
}


def scan_java_source(
    source: str,
    file_path: str = "<string>",
    *,
    config: object | None = None,
) -> list[Violation]:
    """Parse *source* as Java and scan it. Unsupported suffix -> ``[]``."""
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
