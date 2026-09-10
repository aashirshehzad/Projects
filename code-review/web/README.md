# Local web UI

Drag-drop a `.zip` of a Python project, get the audit back in the browser:
severity summary, every finding with its snippet, and — if you tick the box —
Gemini's triage, patch and regression test per finding. Downloadable JSON / SARIF.

Uploaded code is only ever parsed with `ast`; it is extracted into a temp dir
that is deleted before the response returns, and only `.py` entries are unpacked.

## Run it (two terminals, from the repo root)

**1. Backend** — `D:\Projects\code-review`

```
conda activate code-review
pip install -r web/backend/requirements.txt
python -m uvicorn web.backend.main:app --reload --port 8000
```

**2. Frontend** — `D:\Projects\code-review\web\frontend`

```
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api` to the backend.

## One-process alternative

```
cd web/frontend && npm run build
cd ../.. && python -m uvicorn web.backend.main:app --port 8000
```

`main.py` serves `web/frontend/dist/` when it exists, so the whole app is then
at <http://localhost:8000>.

## Limits

| Guard | Value |
|-------|-------|
| Upload size | 200 MB (zipped) |
| Uncompressed `.py` | 150 MB |
| Entries in archive | 200,000 |
| Non-`.py` files | ignored |
| `node_modules` / `.git` / `venv` / `site-packages` | ignored even if zipped |

The AI toggle uses whatever `AUDITOR_LLM_PROVIDER` / key is in `.env` (Gemini by
default). Leave it off for a free, instant static-only scan.
