"""OAuth 2.0 Gmail Draft integration."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import GMAIL_CREDENTIALS_PATH, GMAIL_SCOPES, GMAIL_TOKEN_PATH
from src.drafter import EmailDraft


def _load_credentials() -> Credentials:
    creds: Credentials | None = None

    if GMAIL_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_PATH), GMAIL_SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception:
            pass  # fall through to full re-auth

    if not GMAIL_CREDENTIALS_PATH.exists():
        raise RuntimeError(
            f"Missing Gmail OAuth client file at {GMAIL_CREDENTIALS_PATH}. "
            "Download it from Google Cloud Console (OAuth client, Desktop app type) "
            "and save it there."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS_PATH), GMAIL_SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds: Credentials) -> None:
    GMAIL_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GMAIL_TOKEN_PATH, "w", encoding="utf-8") as f:
        f.write(creds.to_json())


def create_draft(email: EmailDraft) -> str:
    """Create an unread Gmail draft from an EmailDraft. Returns the draft ID."""
    creds = _load_credentials()
    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(email.body)
    message["to"] = email.recipient_email
    message["subject"] = email.subject_line
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        draft = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": raw}})
            .execute()
        )
    except HttpError as e:
        raise RuntimeError(f"Gmail API error while creating draft: {e}") from e

    return draft["id"]
