"""Tiny shared HTTP client for the tools."""
from __future__ import annotations

import httpx

_client = httpx.Client(
    timeout=httpx.Timeout(12.0),
    headers={"User-Agent": "one-gent-multiple-tools/1.0 (+https://github.com/)"},
    follow_redirects=True,
)


def get_json(url: str, params: dict | None = None) -> dict:
    resp = _client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_text(url: str, params: dict | None = None) -> str:
    resp = _client.get(url, params=params)
    resp.raise_for_status()
    return resp.text
