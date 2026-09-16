"""Per-session Gmail OAuth connect flow and draft creation."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend import db, gmail_oauth
from src.config import FRONTEND_URL
from src.drafter import EmailDraft

log = logging.getLogger("jobagent.gmail")
router = APIRouter(prefix="/api/gmail", tags=["gmail"])


def _result_page(success: bool, detail: str = "") -> str:
    title = "Gmail connected" if success else "Connection failed"
    message = (
        "You're all set - go back to Discord (or wherever you started this from) and send a job."
        if success
        else f"Something went wrong{f' ({detail})' if detail else ''}. Go back and try the connect link again."
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


@router.get("/authorize")
async def authorize(request: Request):
    session_id = request.state.session_id
    db.ensure_session(session_id)
    url = gmail_oauth.get_authorization_url(state=session_id)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    is_external = bool(state and ":" in state)  # e.g. "discord:<user_id>" - not a browser session

    if error:
        if is_external:
            return HTMLResponse(_result_page(False, error))
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error={error}")

    session_id = state or request.state.session_id
    if not code:
        if is_external:
            return HTMLResponse(_result_page(False, "missing_code"))
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error=missing_code")

    try:
        token_data = gmail_oauth.exchange_code_for_token(code)
    except Exception:
        log.exception("Gmail token exchange failed (state=%s)", state)
        if is_external:
            return HTMLResponse(_result_page(False, "token_exchange_failed"))
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error=token_exchange_failed")

    db.ensure_session(session_id)
    db.update_session(session_id, gmail_token=token_data)

    if is_external:
        return HTMLResponse(_result_page(True))
    return RedirectResponse(f"{FRONTEND_URL}/?gmail=connected")


@router.get("/status")
async def status(request: Request):
    session = db.get_session(request.state.session_id)
    return {"connected": bool(session and session.get("gmail_token"))}


@router.post("/disconnect")
async def disconnect(request: Request):
    db.update_session(request.state.session_id, gmail_token=None)
    return {"status": "disconnected"}


@router.post("/save-draft")
async def save_draft(request: Request):
    session_id = request.state.session_id
    session = db.get_session(session_id)

    if not session or not session.get("gmail_token"):
        raise HTTPException(400, "Connect Gmail first.")
    if not session.get("current_draft"):
        raise HTTPException(400, "Generate an email draft first.")
    if not session.get("current_job") or not session.get("current_match"):
        raise HTTPException(400, "Missing job context for this draft.")

    token_data = session["gmail_token"]
    try:
        token_data, changed = gmail_oauth.refresh_if_needed(token_data)
        if changed:
            db.update_session(session_id, gmail_token=token_data)
    except RuntimeError as e:
        raise HTTPException(401, str(e)) from e

    email = EmailDraft.model_validate(session["current_draft"])

    try:
        draft_id = gmail_oauth.create_draft(token_data, email)
    except RuntimeError as e:
        job = session["current_job"]
        match = session["current_match"]
        db.add_history_entry(
            session_id=session_id,
            company=job["company_name"],
            title=job["job_title"],
            match_score=match["match_score"],
            is_aligned=match["is_aligned"],
            draft_status="draft_failed",
        )
        raise HTTPException(502, str(e)) from e

    job = session["current_job"]
    match = session["current_match"]
    db.add_history_entry(
        session_id=session_id,
        company=job["company_name"],
        title=job["job_title"],
        match_score=match["match_score"],
        is_aligned=match["is_aligned"],
        draft_status="draft_created",
        draft_id=draft_id,
    )

    return {"draft_id": draft_id}
