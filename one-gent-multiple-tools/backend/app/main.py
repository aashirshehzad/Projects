"""FastAPI server exposing the single agent over HTTP."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # read backend/.env before anything else

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from .agent import Agent  # noqa: E402
from .tools import DECLARATIONS  # noqa: E402

app = FastAPI(title="one-agent-multiple-tools", version="1.0.0")

_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent: Agent | None = None


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent()
    return _agent


class Turn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[Turn] = Field(default_factory=list)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "key_configured": bool(os.environ.get("GEMINI_API_KEY"))}


@app.get("/api/tools")
def list_tools() -> dict:
    return {
        "tools": [
            {"name": d["name"], "description": d["description"]} for d in DECLARATIONS
        ]
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    try:
        agent = get_agent()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        return agent.run(req.message, [t.model_dump() for t in req.history])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}") from exc
