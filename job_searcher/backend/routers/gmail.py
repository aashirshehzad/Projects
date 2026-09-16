"""Per-session Gmail OAuth connect flow and draft creation."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from backend import db, gmail_oauth
from src.config import FRONTEND_URL
from src.drafter import EmailDraft

router = APIRouter(prefix="/api/gmail", tags=["gmail"])


@router.get("/authorize")
async def authorize(request: Request):
    session_id = request.state.session_id
    db.ensure_session(session_id)
    url = gmail_oauth.get_authorization_url(state=session_id)
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error={error}")

    session_id = state or request.state.session_id
    if not code:
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error=missing_code")

    try:
        token_data = gmail_oauth.exchange_code_for_token(code)
    except Exception:
        return RedirectResponse(f"{FRONTEND_URL}/?gmail_error=token_exchange_failed")

    db.ensure_session(session_id)
    db.update_session(session_id, gmail_token=token_data)

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
