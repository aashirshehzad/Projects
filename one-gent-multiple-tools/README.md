# One Agent · Many Tools

A single AI agent (Google **Gemini**, function-calling) that routes each question to the
right tool. Python + FastAPI backend, React (Vite) frontend.

```
you ──▶ React chat UI ──▶ FastAPI /api/chat ──▶ Agent (Gemini)
                                                   │  picks tool(s), loops
                                                   ▼
                    weather · stocks · calculator · units · wikipedia
                    web search · time · dictionary · news
```

## Why this stack

You said "Python for the main logic, React or Node for the frontend/backend."
The agent and every tool are Python, so the **backend is one Python service (FastAPI)** —
adding a separate Node backend would just be a proxy in front of Python with no benefit.
The **frontend is React (Vite)**. In dev, Vite proxies `/api/*` to FastAPI, so there is no
CORS setup to worry about.

## The 9 tools

| Tool | What it does | Data source (all keyless) |
|------|--------------|---------------------------|
| `get_weather` | current temp / wind / conditions for a city | Open-Meteo |
| `get_stock_price` | latest price + daily change for a ticker | Stooq CSV |
| `calculator` | safe math expression evaluator (AST, no `eval`) | local |
| `convert_units` | length / mass / temperature + live currency | local + Frankfurter (ECB) |
| `wikipedia_lookup` | best-matching article summary | Wikipedia REST |
| `web_search` | instant-answer snippets + links | DuckDuckGo |
| `get_current_time` | current time for any timezone / city | local `zoneinfo` |
| `define_word` | English definitions, part of speech, example | dictionaryapi.dev |
| `get_news` | recent headlines, optionally by topic | Google News RSS |

Only **Gemini** needs an API key.

## Setup

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
copy .env.example .env         # then edit .env and paste your GEMINI_API_KEY
```

Use whatever Python 3.11+ you like. With the existing conda env:

```bash
conda activate oneagentmulti
pip install -r requirements.txt
```

Or a plain venv: `python -m venv .venv` then `.venv\Scripts\Activate.ps1`.

Get a free key at <https://aistudio.google.com/apikey>.

Run it:

```bash
uvicorn app.main:app --reload --port 8000
```

Or skip the browser and chat in the terminal:

```bash
python cli.py
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## How the agent works

`backend/app/agent.py` runs a manual function-calling loop:

1. Send the conversation + all tool declarations to Gemini (`GEMINI_MODEL`,
   default `gemini-3.5-flash-lite` — run `python -m app.list_models` to see valid ids).
2. If the reply contains `function_call` parts, run those tools and feed the results back.
3. Repeat (up to `MAX_STEPS = 6`) until Gemini returns plain text — that's the answer.

Each tool call and its raw result are returned to the UI and shown under the reply.

## Adding a tool

1. Create `backend/app/tools/my_tool.py` with a `DECLARATION` dict and a `run(**kwargs)` function.
2. Import it in `backend/app/tools/__init__.py` and add it to `_MODULES`.

That's it — the agent and the UI pick it up automatically.
