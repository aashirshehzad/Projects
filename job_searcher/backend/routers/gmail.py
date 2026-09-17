"""Gmail OAuth callback - the only route Google's consent screen actually redirects to.

The Discord bot builds its own authorize URL via gmail_oauth.get_authorization_url()
as a plain Python call (see discord_bot/bot.py) and never hits this router over HTTP -
it just needs this endpoint to exist somewhere publicly reachable so the user's browser
has somewhere to land after they approve access.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend import db, gmail_oauth

log = logging.getLogger("jobagent.gmail")
router = APIRouter(prefix="/api/gmail", tags=["gmail"])


def _result_page(success: bool, detail: str = "") -> str:
    title = "Gmail connected" if success else "Connection failed"
    message = (
        "You're all set - go back to Discord and send a job."
        if success
        else f"Something went wrong{f' ({detail})' if detail else ''}. Go back to Discord and try the connect link again."
    )
    color = "#4caf50" if success else "#ff6b6b"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font: 16px/1.5 system-ui, sans-serif; background: #111; color: #eee;
          display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .card {{ max-width: 420px; padding: 2rem; text-align: center; }}
  h1 {{ color: {color}; font-size: 1.4rem; }}
</style></head>
<body><div class="card"><h1>{title}</h1><p>{message}</p></div></body></html>"""


@router.get("/callback")
async def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return HTMLResponse(_result_page(False, error))
    if not state:
        return HTMLResponse(_result_page(False, "missing_state"))
    if not code:
        return HTMLResponse(_result_page(False, "missing_code"))

    try:
        token_data = gmail_oauth.exchange_code_for_token(code)
    except Exception:
        log.exception("Gmail token exchange failed (state=%s)", state)
        return HTMLResponse(_result_page(False, "token_exchange_failed"))

    db.ensure_session(state)
    db.update_session(state, gmail_token=token_data)

    return HTMLResponse(_result_page(True))
