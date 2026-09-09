"""The single agent: one Gemini model that decides which tool(s) to call."""
from __future__ import annotations

import os
import re
import time
from typing import Any

from google import genai
from google.genai import types

from .tools import DECLARATIONS, call_tool, tool_names

SYSTEM_PROMPT = (
    "You are a helpful multi-tool assistant. You have one job: answer the user's question, "
    "using the tools available to you whenever they help.\n\n"
    "Guidelines:\n"
    "- Call a tool whenever it can give you fresher or more precise data than your own memory "
    "(weather, stock prices, current time, news, definitions, unit/currency conversion, math).\n"
    "- You may call several tools, one after another, to fully answer a question.\n"
    "- If a tool returns an 'error' field, tell the user plainly what went wrong.\n"
    "- After you have what you need, reply in clear, concise prose. Show numbers with units.\n"
    "- Do not invent data you could have looked up."
)

MAX_STEPS = 6


def _normalize_schema_types(node: Any) -> Any:
    """Gemini's Schema.type wants an enum value (e.g. 'OBJECT'); uppercase JSON-schema types."""
    if isinstance(node, dict):
        out = {}
        for key, val in node.items():
            if key == "type" and isinstance(val, str):
                out[key] = val.upper()
            else:
                out[key] = _normalize_schema_types(val)
        return out
    if isinstance(node, list):
        return [_normalize_schema_types(v) for v in node]
    return node


_TOOLS = [types.Tool(function_declarations=_normalize_schema_types(DECLARATIONS))]


class Agent:
    def __init__(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key or api_key.startswith("paste-"):
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy backend/.env.example to backend/.env "
                "and add your key from https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=api_key)
        self.model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

    def available_models(self) -> list[str]:
        """Model ids on this key that can run generateContent (for error messages / debugging)."""
        out = []
        try:
            for m in self.client.models.list():
                if "generateContent" in (getattr(m, "supported_actions", None) or []):
                    out.append((m.name or "").removeprefix("models/"))
        except Exception:  # noqa: BLE001
            pass
        return sorted(out)

    def _config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=_TOOLS,
            temperature=0.2,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def _generate(self, contents: list[types.Content]):
        for attempt in range(3):
            try:
                return self.client.models.generate_content(
                    model=self.model, contents=contents, config=self._config()
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                low = msg.lower()

                if "not found" in low or "404" in low or "not supported" in low:
                    models = self.available_models()
                    hint = f" Available models: {', '.join(models)}" if models else ""
                    raise RuntimeError(
                        f"Model '{self.model}' is not available. Set GEMINI_MODEL in "
                        f"backend/.env to a valid id.{hint}"
                    ) from exc

                if ("429" in low or "resource_exhausted" in low) and attempt < 2:
                    m = re.search(r"retry in ([\d.]+)s", msg) or re.search(
                        r"retryDelay['\"]?:\s*['\"]?(\d+)", msg
                    )
                    delay = min(float(m.group(1)) + 1, 30) if m else 20.0
                    time.sleep(delay)
                    continue

                if "429" in low or "resource_exhausted" in low:
                    raise RuntimeError(
                        f"Gemini rate limit hit for model '{self.model}'. The free tier allows "
                        "only a few requests per minute - wait a minute or use a paid key."
                    ) from exc
                raise
        raise RuntimeError("Gemini request failed after retries.")

    def run(self, message: str, history: list[dict] | None = None) -> dict:
        contents: list[types.Content] = []
        for turn in history or []:
            role = "model" if turn.get("role") == "assistant" else "user"
            text = (turn.get("content") or "").strip()
            if text:
                contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

        steps: list[dict] = []
        for _ in range(MAX_STEPS):
            response = self._generate(contents)

            candidate = response.candidates[0] if response.candidates else None
            parts = candidate.content.parts if candidate and candidate.content else []
            calls = [p.function_call for p in parts if getattr(p, "function_call", None)]

            if not calls:
                return {"reply": (response.text or "").strip(), "steps": steps, "model": self.model}

            contents.append(candidate.content)
            for fc in calls:
                args = dict(fc.args or {})
                result = call_tool(fc.name, args)
                steps.append({"tool": fc.name, "args": args, "result": result})
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(
                            name=fc.name, response={"result": result}
                        )],
                    )
                )

        # Ran out of steps - ask for a final answer with what we have.
        response = self._generate(contents)
        return {"reply": (response.text or "").strip(), "steps": steps, "model": self.model}


__all__ = ["Agent", "tool_names"]
