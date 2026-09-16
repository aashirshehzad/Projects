"""Parse a job description, match it against the session's profile, and draft a pitch."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend import db
from src.drafter import draft_email
from src.matcher import MatchResult, evaluate_match
from src.parser import ParsedJob, parse_job_description

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class AnalyzeRequest(BaseModel):
    job_text: str


class DraftRequest(BaseModel):
    force: bool = False


def _require_profile(session: dict | None) -> str:
    if not session or not session.get("profile_text"):
        raise HTTPException(400, "Upload or paste a resume first.")
    return session["profile_text"]


@router.post("/analyze")
async def analyze(body: AnalyzeRequest, request: Request):
    session_id = request.state.session_id
    session = db.get_session(session_id)
    profile_text = _require_profile(session)

    if not body.job_text.strip():
        raise HTTPException(400, "job_text is required.")

    try:
        job: ParsedJob = parse_job_description(body.job_text)
        match: MatchResult = evaluate_match(job, profile_text)
    except Exception as e:
        raise HTTPException(502, f"Failed to analyze job: {e}") from e

    db.update_session(
        session_id,
        current_job=job.model_dump(),
        current_match=match.model_dump(),
        current_draft=None,
    )

    duplicate = db.find_history_entry(session_id, job.company_name, job.job_title)

    return {
        "job": job.model_dump(),
        "match": match.model_dump(),
        "duplicate": duplicate,
    }


@router.post("/skip")
async def skip(request: Request):
    """Log a role-mismatch job as intentionally skipped, without drafting."""
    session_id = request.state.session_id
    session = db.get_session(session_id)
    if not session or not session.get("current_job") or not session.get("current_match"):
        raise HTTPException(400, "No analyzed job in this session.")

    job = session["current_job"]
    match = session["current_match"]
    db.add_history_entry(
        session_id=session_id,
        company=job["company_name"],
        title=job["job_title"],
        match_score=match["match_score"],
        is_aligned=match["is_aligned"],
        draft_status="skipped_mismatch",
    )
    return {"status": "logged"}


@router.post("/draft")
async def draft(body: DraftRequest, request: Request):
    session_id = request.state.session_id
    session = db.get_session(session_id)
    profile_text = _require_profile(session)

    if not session.get("current_job") or not session.get("current_match"):
        raise HTTPException(400, "Analyze a job first.")

    job = ParsedJob.model_validate(session["current_job"])
    match = MatchResult.model_validate(session["current_match"])

    if not match.is_aligned and not body.force:
        raise HTTPException(
            409,
            f"Role mismatch detected ({match.match_score}%). Resend with force=true to draft anyway.",
        )

    try:
        email = draft_email(job, match, profile_text)
    except Exception as e:
        raise HTTPException(502, f"Failed to draft email: {e}") from e
    db.update_session(session_id, current_draft=email.model_dump())

    return {"draft": email.model_dump()}


@router.post("/mark-opened")
async def mark_opened(request: Request):
    """Log that the user opened the generated draft in their own email client/Gmail compose."""
    session_id = request.state.session_id
    session = db.get_session(session_id)
    if not session or not session.get("current_job") or not session.get("current_match") or not session.get(
        "current_draft"
    ):
        raise HTTPException(400, "No drafted job in this session.")

    job = session["current_job"]
    match = session["current_match"]
    db.add_history_entry(
        session_id=session_id,
        company=job["company_name"],
        title=job["job_title"],
        match_score=match["match_score"],
        is_aligned=match["is_aligned"],
        draft_status="opened_in_email_client",
    )
    return {"status": "logged"}


@router.get("/history")
async def history(request: Request):
    return {"entries": db.list_history(request.state.session_id)}
