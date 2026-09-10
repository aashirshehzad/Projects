"""Zero-shot prompt construction for the remediation call.

Token discipline is the whole point of Stage 3: the model sees the rule, the
+/- N line snippet and nothing else -- never the full file.
"""

from __future__ import annotations

from app.static_scanner.ast_rules import RULES, Violation

SYSTEM_PROMPT = (
    "You are a senior application-security engineer performing targeted code "
    "remediation. You are given a set of violations found by a deterministic AST "
    "scanner. For each one you must:\n"
    "1. Decide if it is genuinely exploitable in this context (is_exploitable). "
    "Mark clearly-safe patterns as false positives with a short justification.\n"
    "2. Explain the root cause in two or three sentences, concretely.\n"
    "3. Provide drop-in `patched_code` that replaces ONLY the shown snippet and "
    "keeps the surrounding style, names and indentation.\n"
    "4. Provide a standalone, runnable `pytest` test in `unit_test` that would "
    "fail against the vulnerable code and pass against your patch.\n"
    "Be terse. Do not invent files or imports that are not implied by the snippet. "
    "Return every input violation exactly once."
)


def _describe_rule(rule_id: str) -> str:
    meta = RULES.get(rule_id, {})
    return f"{rule_id} [{meta.get('severity', '?')}] {meta.get('title', 'unknown rule')}"


def build_user_prompt(violations: list[Violation]) -> str:
    """Compact, deterministic rendering of the violations to remediate."""
    blocks: list[str] = [
        f"Evaluate and remediate the following {len(violations)} violation(s).",
        "",
    ]
    for i, v in enumerate(violations, start=1):
        blocks.append(f"### Violation {i}")
        blocks.append(f"rule: {_describe_rule(v.rule_id)}")
        blocks.append(f"file: {v.file_path}")
        blocks.append(f"line: {v.line_number}")
        blocks.append(f"finding: {v.message}")
        blocks.append(f"snippet (starts at line {v.context_start_line or v.line_number}):")
        blocks.append("```python")
        blocks.append(v.snippet or "<snippet unavailable>")
        blocks.append("```")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"
