"""Typed runtime configuration.

Values resolve from (highest precedence first): explicit constructor args,
environment variables, an ``.env`` file, then the defaults declared here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDITOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Stage 3: LLM remediation -------------------------------------------------
    llm_provider: LLMProviderName = Field(
        default="gemini",
        description="Which structured-output backend Stage 3 calls.",
    )
    llm_model: str = Field(
        default="gemini-3.5-flash-lite",
        description="Fast, cheap, structured-output-capable model for the chosen provider.",
    )
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        description="Key for Google Gemini (AI Studio / Generative Language API).",
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="Key for OpenAI, used only when llm_provider='openai'.",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_tokens: int = Field(
        default=8192,
        gt=0,
        description="Output budget. Patches + tests for many violations need room; "
        "too low truncates the JSON and the run falls back to static-only.",
    )

    # --- Stage 1-2: static scan ------------------------------------------------------
    context_lines: int = Field(
        default=5,
        ge=0,
        description="Lines of surrounding source to attach on each side of a violation.",
    )
    max_violations_to_llm: int = Field(
        default=50,
        gt=0,
        description="Hard cap on violations forwarded to Stage 3 in a single run.",
    )

    # --- Stage 4: GitHub reporting -------------------------------------------------
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_repository: str | None = Field(
        default=None, validation_alias="GITHUB_REPOSITORY"
    )
    github_pr_number: int | None = Field(default=None, validation_alias="GITHUB_PR_NUMBER")
    github_sha: str | None = Field(default=None, validation_alias="GITHUB_SHA")

    def require_llm_key(self) -> str:
        """Return the API key for the configured provider, or explain what's missing."""
        from app.core.exceptions import ConfigurationError

        if self.llm_provider == "gemini":
            if not self.gemini_api_key:
                raise ConfigurationError(
                    "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set; the LLM "
                    "remediation stage cannot run. Use --no-llm for static findings only."
                )
            return self.gemini_api_key
        if not self.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set; the LLM remediation stage cannot run. "
                "Use --no-llm for static findings only."
            )
        return self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton so env parsing happens once."""
    return Settings()
