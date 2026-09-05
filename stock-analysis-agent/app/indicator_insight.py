"""
Runtime single-indicator insight via Gemini.

Powers the dashboard's "Insight Card": when a user enables one indicator
(RSI / EMA / MA / MACD) on a ticker's chart, the frontend POSTs its latest
value here and gets back a strict two-sentence Buy / Sell / Hold read.

Mirrors Agent 3's Gemini plumbing (`google-genai` SDK, `GEMINI_API_KEY` /
`GOOGLE_API_KEY`, `DECISION_MODEL` default) but is a single cheap call with a
tiny output budget. It never raises: a missing package / key or an API error
comes back as a plain-text notice so the endpoint stays 200 and the card can
render it verbatim.
"""

from __future__ import annotations

import logging
import os
from typing import Union

try:  # keep the service importable without the LLM dependency
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - minimal installs only
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Reuse Agent 3's model choice unless a caller overrides it explicitly.
_MODEL = os.getenv("INDICATOR_MODEL") or os.getenv(
    "DECISION_MODEL", "gemini-3.5-flash-lite"
)
_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Two short sentences ≈ well under this; the cap just bounds a runaway reply.
_MAX_OUTPUT_TOKENS = int(os.getenv("INDICATOR_MAX_TOKENS", "160"))

_PROMPT_TEMPLATE = (
    "You are a technical analyst. The current price of {ticker} is "
    "{current_price}. The {indicator_name} is currently at {current_value}. "
    "Reply in exactly two sentences. Sentence 1: State exactly Buy, Sell, or "
    "Hold based solely on this indicator's relationship to the current price. "
    "Sentence 2: Explain the technical reason why (e.g., price is above/below "
    "the moving average, crossover status, etc.)."
)

# float | int for scalar indicators; dict for MACD (line / signal / histogram);
# str tolerated so an already-formatted value passes straight through.
IndicatorValue = Union[float, int, dict, str]


def analyze_indicator(
    ticker: str,
    indicator_name: str,
    current_value: IndicatorValue,
    current_price: float,
) -> str:
    """
    Return a two-sentence Buy / Sell / Hold read on a single indicator,
    evaluated against the ticker's current price.

    Degrades to a plain-text ``"Insight unavailable: …"`` string (never raises)
    when the SDK or API key is missing, or the Gemini call fails.
    """
    prompt = _PROMPT_TEMPLATE.format(
        indicator_name=indicator_name,
        ticker=ticker,
        current_value=current_value,
        current_price=current_price,
    )

    if genai is None:
        return "Insight unavailable: the 'google-genai' package is not installed."
    if not _API_KEY:
        return "Insight unavailable: set GEMINI_API_KEY (or GOOGLE_API_KEY)."

    try:
        client = genai.Client(api_key=_API_KEY)
        response = client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                temperature=0.2,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )
        text = (response.text or "").strip()
        return text or "Insight unavailable: the model returned an empty response."
    except Exception as exc:  # noqa: BLE001 - surface as text, don't 500 the UI
        logger.exception(
            "indicator insight failed for %s / %s", ticker, indicator_name
        )
        return f"Insight unavailable: {exc.__class__.__name__}."
