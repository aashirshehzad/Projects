"""App configuration: env variables and paths."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

MATCH_SCORE_THRESHOLD = int(os.getenv("MATCH_SCORE_THRESHOLD", "65"))

PROFILE_PATH = BASE_DIR / os.getenv("PROFILE_PATH", "data/profile.md")
JOBS_HISTORY_PATH = BASE_DIR / os.getenv("JOBS_HISTORY_PATH", "data/jobs_history.json")
GMAIL_CREDENTIALS_PATH = BASE_DIR / os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/credentials.json")
GMAIL_TOKEN_PATH = BASE_DIR / os.getenv("GMAIL_TOKEN_PATH", "credentials/token.json")

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

# --- Web app (backend/) settings ---
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/gmail/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
SESSION_COOKIE_NAME = "job_agent_session"
SESSION_DB_PATH = BASE_DIR / os.getenv("SESSION_DB_PATH", "backend/data/sessions.db")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))  # 5 MB


def require_google_oauth_client() -> tuple[str, str]:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not set. "
            "Create a Web application OAuth client in Google Cloud Console and set them in .env."
        )
    return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET


def require_anthropic_key() -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ANTHROPIC_API_KEY
