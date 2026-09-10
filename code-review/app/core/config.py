"""Typed runtime configuration.

Values resolve from (highest precedence first): explicit constructor args,
environment variables, an ``.env`` file, then the defaults declared here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUDITOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Stage 3: LLM remediation -------------------------------------------------
    openai_api_key: str | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
        description="Key for the remediation model. Only required when violations are found.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Fast, cheap, structured-output-capable model.",
    )
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_tokens: int = Field(default=1200, gt=0)

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

    def require_openai_key(self) -> str:
        from app.core.exceptions import ConfigurationError

        if not self.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set; the LLM remediation stage cannot run. "
                "Run with --no-llm to get static findings only."
            )
        return self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide singleton so env parsing happens once."""
    return Settings()
