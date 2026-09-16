"""JobAgent web backend: multi-tenant FastAPI app.

Each visitor is identified by an anonymous session cookie. Their uploaded
resume, in-flight job analysis, and Gmail OAuth token are scoped to that
session (see backend/db.py) - nothing is shared between visitors.
"""
from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend import db
from backend.routers import gmail, jobs, profile
from src.config import FRONTEND_URL, SESSION_COOKIE_NAME

app = FastAPI(title="JobAgent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    db.init_db()


@app.middleware("http")
async def session_middleware(request: Request, call_next):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    is_new = session_id is None
    if is_new:
        session_id = str(uuid.uuid4())

    request.state.session_id = session_id
    db.ensure_session(session_id)

    response = await call_next(request)

    if is_new:
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 30,
        )
    return response


app.include_router(profile.router)
app.include_router(jobs.router)
app.include_router(gmail.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
