"""App configuration: env variables and paths."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "Your Name")
CANDIDATE_HEADLINE = os.getenv("CANDIDATE_HEADLINE", "Software Engineer")

MATCH_SCORE_THRESHOLD = int(os.getenv("MATCH_SCORE_THRESHOLD", "65"))

PROFILE_PATH = BASE_DIR / os.getenv("PROFILE_PATH", "data/profile.md")
JOBS_HISTORY_PATH = BASE_DIR / os.getenv("JOBS_HISTORY_PATH", "data/jobs_history.json")
GMAIL_CREDENTIALS_PATH = BASE_DIR / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/credentials.json")
GMAIL_TOKEN_PATH = BASE_DIR / os.getenv("GMAIL_TOKEN_PATH", "credentials/token.json")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


def require_anthropic_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ANTHROPIC_API_KEY
