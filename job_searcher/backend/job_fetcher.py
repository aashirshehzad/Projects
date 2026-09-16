"""Fetches and extracts visible text from a job posting URL (e.g. a LinkedIn link)."""
from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def looks_like_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


def fetch_job_text(url: str) -> str:
    """Follows the URL (including redirects, e.g. lnkd.in short links) and extracts visible page text."""
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0, headers=_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as e:
        raise ValueError(f"Could not fetch the job posting URL: {e}") from e

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    if len(text) < 200:
        raise ValueError(
            "The page didn't return enough readable job content - it may require sign-in or block "
            "automated access, which LinkedIn does for most job pages. Please paste the job description "
            "text directly instead."
        )

    return text
