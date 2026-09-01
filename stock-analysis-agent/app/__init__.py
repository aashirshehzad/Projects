# Stock Analysis Agent - Multi-agent workflow powered by LangGraph & FastAPI

# Load a local .env (if present) before any submodule reads os.getenv — covers
# every entry point: `uvicorn app.main:app`, direct `from app.graph import graph`,
# and importing an agent module on its own. Real environment variables always
# win over .env values. No-op if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass
