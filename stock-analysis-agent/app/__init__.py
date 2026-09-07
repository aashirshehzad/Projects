# Stock Analysis Agent - Multi-agent workflow powered by LangGraph & FastAPI

# yfinance triggers this NumPy-timedelta DeprecationWarning on essentially every
# `.history()` / `.get_shares_full()` call — it comes from yfinance's own code,
# not ours, and floods the logs (one line per ticker per fetch). yfinance also
# registers, on import, a `default` filter for its own DeprecationWarnings
# (module `^yfinance`) that would let this through — so import it first, then
# prepend our narrower `ignore` ahead of it. Everything else still warns.
import warnings

try:
    import yfinance  # noqa: F401  (import for filter ordering, not use)
except ImportError:  # pragma: no cover
    pass

warnings.filterwarnings(
    "ignore",
    message="The 'generic' unit for NumPy timedelta is deprecated",
    category=DeprecationWarning,
)

# Load a local .env (if present) before any submodule reads os.getenv — covers
# every entry point: `uvicorn app.main:app`, direct `from app.graph import graph`,
# and importing an agent module on its own. Real environment variables always
# win over .env values. No-op if python-dotenv isn't installed.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass
