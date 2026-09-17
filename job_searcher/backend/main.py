"""JobAgent backend: the OAuth callback the Discord bot's Gmail auth links redirect to,
plus a bare static homepage/privacy page (both required for Google's OAuth consent screen).

There's no web UI here on purpose - the Discord bot (discord_bot/bot.py) is the product.
It calls backend/db.py, backend/gmail_oauth.py, backend/job_fetcher.py, and
backend/pdf_extract.py as plain Python imports, not over HTTP; this process only needs to
exist because Google's OAuth redirect has to land on a real, publicly reachable web server.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import db
from backend.routers import gmail
from src.config import BASE_DIR

STATIC_DIR = Path(BASE_DIR) / "backend" / "static"

app = FastAPI(title="JobAgent")


@app.on_event("startup")
async def on_startup() -> None:
    db.init_db()


app.include_router(gmail.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def homepage():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/privacy.html")
async def privacy():
    return FileResponse(STATIC_DIR / "privacy.html")
