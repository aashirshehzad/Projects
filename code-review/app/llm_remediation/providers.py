"""Structured-output backends for Stage 3.

Each provider takes a system + user prompt and returns a validated
``AuditRemediationReport`` -- exactly one request, no tool loop. Swap backends
with ``AUDITOR_LLM_PROVIDER`` (``gemini`` default, or ``openai``).
"""

from __future__ import annotations

from typing import Any, Protocol

from app.core.config import Settings
from app.core.exceptions import AuditorError, ConfigurationError, LLMRemediationError
from app.llm_remediation.schemas import AuditRemediationReport


class LLMProvider(Protocol):
    def parse(self, system_prompt: str, user_prompt: str) -> AuditRemediationReport: ...


# --------------------------------------------------------------------------- #
# Google Gemini (default)
# --------------------------------------------------------------------------- #
class GeminiProvider:
    """Uses ``google-genai`` with a Pydantic ``response_schema``."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover - import guard
                raise LLMRemediationError(
                    "The `google-genai` package is not installed; run "
                    "`pip install google-genai` or pass --no-llm."
                ) from exc
            self._client = genai.Client(api_key=self.settings.require_llm_key())
        return self._client

    def parse(self, system_prompt: str, user_prompt: str) -> AuditRemediationReport:
        config: dict[str, Any] = {
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": AuditRemediationReport,
            "temperature": self.settings.llm_temperature,
            "max_output_tokens": self.settings.llm_max_tokens,
            # We are not doing tool calling; silences the AFC advisory and path.
            "automatic_function_calling": {"disable": True},
        }
        try:
            response = self.client.models.generate_content(
                model=self.settings.llm_model,
                contents=user_prompt,
                config=config,
            )
        except AuditorError:
            raise
        except Exception as exc:  # network / API / timeout
            raise LLMRemediationError(f"Remediation model call failed: {exc}") from exc

        _raise_on_bad_finish(response)
        return _coerce_report(
            getattr(response, "parsed", None), getattr(response, "text", None)
        )


# --------------------------------------------------------------------------- #
# OpenAI
# --------------------------------------------------------------------------- #
class OpenAIProvider:
    """Uses ``client.beta.chat.completions.parse`` with ``response_format``."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - import guard
                raise LLMRemediationError(
                    "The `openai` package is not installed; run `pip install openai` "
                    "or pass --no-llm."
                ) from exc
            self._client = OpenAI(
                api_key=self.settings.require_llm_key(),
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._client

    def parse(self, system_prompt: str, user_prompt: str) -> AuditRemediationReport:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            completion = self.client.beta.chat.completions.parse(
                model=self.settings.llm_model,
                messages=messages,
                response_format=AuditRemediationReport,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
        except AuditorError:
            raise
        except Exception as exc:
            raise LLMRemediationError(f"Remediation model call failed: {exc}") from exc

        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise LLMRemediationError(
                f"Model refused to remediate: {choice.message.refusal}"
            )
        return _coerce_report(getattr(choice.message, "parsed", None), None)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _raise_on_bad_finish(response: Any) -> None:
    """Turn a truncated / blocked Gemini response into an actionable error."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return
    reason = getattr(candidates[0], "finish_reason", None)
    name = getattr(reason, "name", str(reason)) if reason is not None else ""
    if name == "MAX_TOKENS":
        raise LLMRemediationError(
            "Gemini hit the output token limit and the JSON was truncated. "
            "Raise AUDITOR_LLM_MAX_TOKENS or lower AUDITOR_MAX_VIOLATIONS_TO_LLM."
        )
    if name in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
        raise LLMRemediationError(f"Gemini stopped the response early: {name}.")


def _coerce_report(parsed: Any, raw_text: str | None) -> AuditRemediationReport:
    if isinstance(parsed, AuditRemediationReport):
        return parsed
    if isinstance(parsed, dict):
        return AuditRemediationReport.model_validate(parsed)
    if raw_text:
        try:
            return AuditRemediationReport.model_validate_json(raw_text)
        except Exception as exc:
            raise LLMRemediationError(f"Model returned invalid JSON: {exc}") from exc
    raise LLMRemediationError("Model returned no parseable structured output.")


def get_provider(settings: Settings, *, client: Any | None = None) -> LLMProvider:
    if settings.llm_provider == "gemini":
        return GeminiProvider(settings, client=client)
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings, client=client)
    raise ConfigurationError(f"Unknown llm_provider: {settings.llm_provider!r}")
