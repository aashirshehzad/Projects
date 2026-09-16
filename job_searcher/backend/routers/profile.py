"""Upload/paste a resume; store its extracted text against the visitor's session."""
from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from backend import db
from backend.pdf_extract import extract_text
from src.config import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("")
async def upload_profile(
    request: Request,
    file: UploadFile | None = None,
    text: str | None = Form(default=None),
):
    session_id = request.state.session_id

    if file is not None:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File too large (max 5 MB).")
        try:
            profile_text = extract_text(file.filename or "", content)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
    elif text and text.strip():
        profile_text = text.strip()
    else:
        raise HTTPException(400, "Provide either a file upload or pasted text.")

    if len(profile_text) < 50:
        raise HTTPException(422, "Extracted profile text looks too short to be a resume.")

    db.update_session(session_id, profile_text=profile_text)

    return {
        "length": len(profile_text),
        "preview": profile_text[:500],
    }


@router.get("")
async def get_profile(request: Request):
    session = db.get_session(request.state.session_id)
    profile_text = (session or {}).get("profile_text")
    if not profile_text:
        return {"has_profile": False, "preview": None, "length": 0}
    return {"has_profile": True, "preview": profile_text[:500], "length": len(profile_text)}
