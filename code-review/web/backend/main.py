"""FastAPI app for the local Hybrid Code Auditor web UI.

Run from the project root (D:\\Projects\\code-review):

    python -m uvicorn web.backend.main:app --reload --port 8000
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from web.backend.service import AuditRequestError, run_audit

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB zipped (local tool)

app = FastAPI(title="Hybrid Code Auditor (local web UI)", version="1.0.0")

# Vite dev server origin. Harmless for a local-only tool.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/audit")
async def audit(
    file: UploadFile = File(...),
    llm: str = Form("false"),
) -> dict:
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    use_llm = llm.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return run_audit(data, use_llm=use_llm)
    except AuditRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/report.pdf")
def report_pdf(payload: dict[str, Any] = Body(...)) -> Response:
    """Render an already-computed audit payload as a plain-language PDF."""
    from app.reporter.pdf import render_pdf

    if "violations" not in payload:
        raise HTTPException(status_code=400, detail="Payload is not an audit result.")
    label = str(payload.get("project_label") or "Uploaded project")
    tmp = Path(tempfile.mkdtemp(prefix="cauditor-pdf-"))
    try:
        out = render_pdf(payload, tmp / "report.pdf", project_label=label)
        pdf_bytes = out.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="audit-report.pdf"'},
    )


# If the frontend has been built (`npm run build`), serve it from the same
# origin so `uvicorn` alone is enough. Otherwise use the Vite dev server.
_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
