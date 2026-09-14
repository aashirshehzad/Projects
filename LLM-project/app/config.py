"""Runtime settings, read once from environment variables (optionally a .env file)."""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    collection_name: str = os.getenv("CACHE_COLLECTION", "llm_semantic_cache")
    qdrant_path: str = os.getenv("QDRANT_PATH", "./qdrant_storage")  # ":memory:" for ephemeral
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    embedding_dim: int = int(os.getenv("EMBEDDING_DIM", "384"))

    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.92"))
    # Reject hits whose salient entities (languages, numbers, proper nouns) differ.
    entity_guard: bool = _bool("ENTITY_GUARD", True)

    # Phase 2: expiry + capacity eviction
    ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", str(24 * 3600)))
    max_entries: int = int(os.getenv("CACHE_MAX_ENTRIES", "50000"))
    eviction_interval_seconds: int = int(os.getenv("EVICTION_INTERVAL_SECONDS", "300"))

    # Upstream: "mock", "groq", "openai", "ollama" or any OpenAI-compatible URL via UPSTREAM_URL
    upstream_provider: str = os.getenv("UPSTREAM_PROVIDER", "mock")
    upstream_url: str = os.getenv("UPSTREAM_URL", "")
    upstream_api_key: str = os.getenv("UPSTREAM_API_KEY", "")
    upstream_timeout: float = float(os.getenv("UPSTREAM_TIMEOUT", "60"))
    mock_latency_ms_min: int = int(os.getenv("MOCK_LATENCY_MS_MIN", "1200"))
    mock_latency_ms_max: int = int(os.getenv("MOCK_LATENCY_MS_MAX", "2500"))


PROVIDER_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
}

settings = Settings()
