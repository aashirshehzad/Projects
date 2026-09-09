"""Tiny shared HTTP client for the tools (one retry on flaky connections)."""
from __future__ import annotations

import httpx

_client = httpx.Client(
    timeout=httpx.Timeout(20.0, connect=10.0),
    headers={
        "User-Agent": "Mozilla/5.0 (compatible; one-gent-multiple-tools/1.0)",
        "Accept": "*/*",
    },
    follow_redirects=True,
)


def _get(url: str, params: dict | None = None) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = _client.get(url, params=params)
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc  # transient - retry once
    raise last_exc  # type: ignore[misc]


def get_json(url: str, params: dict | None = None) -> dict:
    return _get(url, params).json()


def get_text(url: str, params: dict | None = None) -> str:
    return _get(url, params).text
