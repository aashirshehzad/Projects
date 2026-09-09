"""Tool registry.

Every tool module exposes:
  - DECLARATION: a Gemini function-declaration dict (name, description, parameters)
  - run(**kwargs) -> JSON-serializable dict

To add a tool: create a module here, then add it to `_MODULES` below.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any, Callable

from . import (
    calculator,
    dictionary,
    news,
    send_email,
    stocks,
    timetool,
    units,
    weather,
    websearch,
    wikipedia,
)

_MODULES: list[ModuleType] = [
    weather,
    stocks,
    calculator,
    units,
    wikipedia,
    websearch,
    timetool,
    dictionary,
    news,
    send_email,
]

DECLARATIONS: list[dict] = [m.DECLARATION for m in _MODULES]
_HANDLERS: dict[str, Callable[..., dict]] = {m.DECLARATION["name"]: m.run for m in _MODULES}


def tool_names() -> list[str]:
    return list(_HANDLERS)


def call_tool(name: str, args: dict[str, Any]) -> dict:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"Unknown tool '{name}'."}
    try:
        return handler(**(args or {}))
    except TypeError as exc:
        return {"error": f"Bad arguments for '{name}': {exc}"}
    except Exception as exc:  # noqa: BLE001 - never crash the agent loop on a tool failure
        return {"error": f"Tool '{name}' failed: {exc}"}
