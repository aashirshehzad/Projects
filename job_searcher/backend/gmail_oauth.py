"""Per-session Gmail OAuth (web authorization-code flow) for the multi-tenant app.

Unlike src/gmail_client.py (which uses the desktop InstalledAppFlow and a single
local token.json for the CLI), this uses a Web application OAuth client and
stores each visitor's token against their own session row in SQLite.
"""
from __future__ import annotations

import base64
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import (
    GMAIL_SCOPES,
    GOOGLE_REDIRECT_URI,
    require_google_oauth_client,
)
from src.drafter import EmailDraft


def _client_config() -> dict[str, Any]:
    client_id, client_secret = require_google_oauth_client()
    return {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }


def _build_flow() -> Flow:
    # PKCE is off on purpose: authorize (get_authorization_url) and exchange
    # (exchange_code_for_token) each build a fresh Flow instance - possibly in
    # a different process entirely for the Discord bot - so there's no shared
    # code_verifier to reuse. Fine here: this is a confidential server-side
    # client already authenticated via client_secret, which is what PKCE
    # exists to substitute for in public clients that can't hold a secret.
    return Flow.from_client_config(
        _client_config(),
        scopes=GMAIL_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
        autogenerate_code_verifier=False,
    )


def get_authorization_url(state: str) -> str:
    """Returns the Google consent URL for this session. `state` carries the session id."""
    flow = _build_flow()
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url


def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Exchanges an OAuth authorization code for credentials, returned as a JSON-safe dict."""
    flow = _build_flow()
    flow.fetch_token(code=code)
    return credentials_to_dict(flow.credentials)


def credentials_to_dict(creds: Credentials) -> dict[str, Any]:
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


def _dict_to_credentials(data: dict[str, Any]) -> Credentials:
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )


def refresh_if_needed(token_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Refreshes an expired token if possible. Returns (token_dict, changed)."""
    creds = _dict_to_credentials(token_data)
    if creds.valid:
        return token_data, False
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        return credentials_to_dict(creds), True
    raise RuntimeError("Gmail authorization expired or invalid. Please reconnect Gmail.")


def create_draft(token_data: dict[str, Any], email: EmailDraft, resume_path: str | None = None) -> str:
    """Creates a Gmail draft using this session's stored credentials. Returns the draft ID."""
    creds = _dict_to_credentials(token_data)
    service = build("gmail", "v1", credentials=creds)

    resume_file = Path(resume_path) if resume_path else None
    if resume_file and resume_file.exists():
        message = MIMEMultipart()
        message.attach(MIMEText(email.body))

        content_type, _ = mimetypes.guess_type(str(resume_file))
        maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
        with open(resume_file, "rb") as f:
            attachment = MIMEApplication(f.read(), _subtype=subtype)
        attachment.add_header("Content-Disposition", "attachment", filename=resume_file.name)
        message.attach(attachment)
    else:
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
