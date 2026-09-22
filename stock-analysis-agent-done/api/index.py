"""
Vercel serverless entrypoint.

This file only exists so Vercel's Python runtime (which auto-detects an ASGI
`app` under /api) can serve the exact same FastAPI app used locally — it does
not duplicate or restructure anything. Local dev is unaffected: keep running
`uvicorn app.main:app --reload` from the repo root.

See CLAUDE.md's "Deploying to Vercel" section for the required env vars and
the Hobby-plan function-duration caveat (the full multi-agent /analyze run
can take 40-90s; Hobby's ceiling is well under that even at max maxDuration).
"""

import sys
from pathlib import Path

# Vercel runs this with the project root as CWD, but be defensive about it —
# make `app` importable regardless of how the function is invoked/bundled.
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from app.main import app  # noqa: E402  (import after sys.path fix-up, by design)

__all__ = ["app"]
