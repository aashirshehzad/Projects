"""
LangGraph workflow definition **and Agent 3 (decision)** for the stock-analysis
pipeline.

Agents
──────
  • Agent 1 – quantitative (yfinance price metrics)       → app/agent_quantitative.py
  • Agent 2 – fundamental  (SEC EDGAR 10-Q / 10-K)         → app/agent_fundamental.py
  • Agent 3 – decision     (Gemini Buy / Sell / Hold synthesis)   ← defined in this file

Agent 3 and the graph wiring live together here on purpose: the decision step
is the *join point* of the pipeline, so its node function and the topology that
feeds it are easiest to reason about side by side.

Topology
────────
            ┌────────────────────┐
      START ┤ quantitative_agent │──┐
            └────────────────────┘  │
                                    ├──►  decision_agent  ──►  END
            ┌────────────────────┐  │
      START ┤ fundamental_agent  │──┘
            └────────────────────┘

Agent 1 and Agent 2 share no data, so both are wired straight off ``START`` and
LangGraph schedules them in the **same superstep** — the sync node callables run
concurrently on LangGraph's executor threadpool. ``decision_agent`` has an
incoming edge from *each* of them, which makes LangGraph wait for **both** to
finish before it runs — a fan-in barrier.

State is a ``TypedDict`` (``GraphState``), not a bare ``dict``: that gives each
field its own channel so the two parallel agents can write at the same time
without tripping LangGraph's one-write-per-channel-per-step rule. See the note
above ``build_graph`` for the details.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent_fundamental import fundamental_agent
from app.agent_quantitative import quantitative_agent
from app.state import StockAnalysisState, TickerSummary

try:  # keep the rest of the service importable without the LLM dependency
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - exercised only in minimal installs
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Agent 3 configuration ───────────────────────────────────────────────────

# Agent 3 talks to the Google Gemini API via the `google-genai` SDK.
# Model + limits are env-overridable so ops can dial cost/latency without a
# code change. Default is the small, cheap Flash-Lite tier; override with
# DECISION_MODEL to whatever string Google AI Studio currently lists.
_DECISION_MODEL = os.getenv("DECISION_MODEL", "gemini-3.5-flash-lite")
_DECISION_MAX_TOKENS = int(os.getenv("DECISION_MAX_TOKENS", "2048"))

# The SDK reads GEMINI_API_KEY (preferred) or GOOGLE_API_KEY from the env; we
# resolve it explicitly so a missing key degrades gracefully instead of raising
# at client construction.
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# The recommendation is a closed set — anything else is coerced to "Hold".
_VALID_RECOMMENDATIONS = ("Buy", "Sell", "Hold")

_SYSTEM_PROMPT = (
    "You are a disciplined equity analyst. You are handed two machine-generated "
    "inputs for one or more tickers: quantitative price metrics (Agent 1) and a "
    "fundamental report scraped from the latest SEC 10-Q / 10-K filings "
    "(Agent 2). Weigh price trend and momentum (latest close vs 50/200-day "
    "moving averages, 6-month return) against revenue, profitability, margins "
    "and management guidance, then issue ONE overall recommendation for the "
    "basket as a whole.\n\n"
    "Respond with a SINGLE JSON object and nothing else, in exactly this shape:\n"
    '{"recommendation": "Buy" | "Sell" | "Hold", '
    '"thesis": ["supporting point", "supporting point", ...]}\n\n'
    "Rules:\n"
    '- "recommendation" MUST be exactly one of "Buy", "Sell", or "Hold".\n'
    '- "thesis" MUST be a list of 3-6 concise bullet strings, each under 240 '
    "characters, and each citing a specific figure from the inputs.\n"
    "- Do NOT wrap the JSON in markdown fences and do NOT add any prose before "
    "or after it."
)


# ── Agent 3 helpers ────────────────────────────────────────────────────────

def _flatten_ws(text: str) -> str:
    """Collapse runs of whitespace to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _fmt_price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def _format_quant_block(rows: list[TickerSummary]) -> str:
    """Render Agent 1's structured output as a compact text table for the LLM."""
    if not rows:
        return "No quantitative data available."
    lines: list[str] = []
    for r in rows:
        ma = r.moving_averages
        lines.append(
            f"- {r.ticker}: latest close {_fmt_price(r.latest_close)} "
            f"({r.period_start} → {r.period_end}); "
            f"6-month return {r.pct_return:+.2f}%; "
            f"50-day MA {_fmt_price(ma.ma_50)}; "
            f"200-day MA {_fmt_price(ma.ma_200)}; "
            f"{r.data_points} trading days"
        )
    return "\n".join(lines)


def _build_user_prompt(quant_block: str, fundamental_block: str) -> str:
    """Combine both agents' outputs into the single user turn for the LLM."""
    return (
        "=== AGENT 1 — QUANTITATIVE (historical_data) ===\n"
        f"{quant_block}\n\n"
        "=== AGENT 2 — FUNDAMENTAL (fundamental_report) ===\n"
        f"{fundamental_block or 'No fundamental data available.'}\n"
    )


def _call_llm(user_prompt: str) -> str:
    """One Gemini ``generate_content`` call; returns the response text, stripped.

    ``response_mime_type="application/json"`` puts the model in JSON mode and
    ``response_schema`` pins the shape (``recommendation`` is an enum), so
    ``_parse_decision`` is left only as a defensive backstop.
    """
    client = genai.Client(api_key=_GEMINI_API_KEY)
    response = client.models.generate_content(
        model=_DECISION_MODEL,
        contents=user_prompt,
        config=genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=_DECISION_MAX_TOKENS,
            temperature=0.2,
            # No tools here — turn off the SDK's automatic function calling so it
            # doesn't warn and doesn't take that codepath.
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            response_mime_type="application/json",
            response_schema={
                "type": "object",
                "properties": {
                    "recommendation": {
                        "type": "string",
                        "enum": list(_VALID_RECOMMENDATIONS),
                    },
                    "thesis": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["recommendation", "thesis"],
            },
        ),
    )
    return (response.text or "").strip()


def _parse_decision(raw: str) -> tuple[str, list[str]]:
    """
    Coerce the model's reply into ``(recommendation, thesis)``.

    Defensive on purpose — the prompt asks for bare JSON, but we tolerate
    markdown fences, stray prose and a missing or malformed ``thesis``. The
    recommendation is forced into ``_VALID_RECOMMENDATIONS``; a blank thesis
    falls back to a trimmed echo of the raw text.
    """
    recommendation: str | None = None
    thesis: list[str] = []

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    payload = match.group(0) if match else raw
    try:
        data = json.loads(payload)
        recommendation = str(data.get("recommendation", "")).strip().capitalize()
        raw_thesis = data.get("thesis", [])
        if isinstance(raw_thesis, str):
            raw_thesis = [raw_thesis]
        if isinstance(raw_thesis, list):
            thesis = [
                _flatten_ws(str(item)).strip(" -*•\t")
                for item in raw_thesis
                if _flatten_ws(str(item))
            ]
    except (ValueError, TypeError):
        pass

    if recommendation not in _VALID_RECOMMENDATIONS:
        # Last-ditch: pick the first valid keyword that appears in the reply.
        for candidate in _VALID_RECOMMENDATIONS:
            if re.search(rf"\b{candidate}\b", raw, re.IGNORECASE):
                recommendation = candidate
                break
    if recommendation not in _VALID_RECOMMENDATIONS:
        recommendation = "Hold"

    if not thesis:
        thesis = [_flatten_ws(raw)[:240] or "Model returned no parseable thesis."]

    return recommendation, thesis


# ── Agent 3 — public entry point (LangGraph node function) ──────────────────

def decision_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    Agent 3. Ingests ``state.historical_data`` (Agent 1) and
    ``state.fundamental_report`` (Agent 2), asks an LLM for a single
    Buy / Sell / Hold call plus a bulleted thesis, and writes the result to
    ``state.final_decision``.

    ``final_decision`` shape
    ────────────────────────
        {
          "recommendation": "Buy" | "Sell" | "Hold",
          "thesis":         [str, ...],          # bulleted supporting points
          "model":          "<model id>",
          "generated_at":   "<UTC ISO-8601>",
          "raw_response":   "<verbatim LLM text>",   # present on success
          "error":          "<reason>",              # present on any fallback
        }

    Per the agent contract this never raises past its own body: a missing
    ``google-genai`` package, an unset ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``,
    or any API error all resolve to a conservative ``"Hold"`` with an ``error``
    note, so one flaky LLM call can't abort the graph run.
    """
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base: dict[str, Any] = {"model": _DECISION_MODEL, "generated_at": generated_at}

    quant_block = _format_quant_block(state.historical_data)
    fundamental_block = (state.fundamental_report or "").strip()

    def _fallback(reason: str) -> StockAnalysisState:
        logger.warning("decision_agent: %s — returning conservative Hold", reason)
        return state.model_copy(
            update={
                "final_decision": {
                    **base,
                    "recommendation": "Hold",
                    "thesis": [f"Automated recommendation unavailable: {reason}."],
                    "error": reason,
                }
            }
        )

    if not state.historical_data and not fundamental_block:
        return _fallback("no Agent 1 or Agent 2 output to reason over")
    if genai is None:
        return _fallback("the 'google-genai' package is not installed")
    if not _GEMINI_API_KEY:
        return _fallback("no Gemini credentials (set GEMINI_API_KEY)")

    user_prompt = _build_user_prompt(quant_block, fundamental_block)
    try:
        raw = _call_llm(user_prompt)
    except Exception as exc:  # noqa: BLE001 – never abort the graph on an LLM error
        logger.exception("decision_agent: LLM call failed")
        return _fallback(f"LLM call failed ({exc or exc.__class__.__name__})")

    recommendation, thesis = _parse_decision(raw)
    logger.info(
        "decision_agent: %s  (%d thesis point(s))", recommendation, len(thesis)
    )
    return state.model_copy(
        update={
            "final_decision": {
                **base,
                "recommendation": recommendation,
                "thesis": thesis,
                "raw_response": raw,
            }
        }
    )


# ── graph assembly ─────────────────────────────────────────────────────────

# Why not ``StateGraph(dict)`` any more
# ────────────────────────────────────
# The old topology was linear, so a single ``dict`` state channel was fine.
# Running Agent 1 and Agent 2 in the *same* superstep breaks that: with a bare
# ``dict`` schema LangGraph stores the whole mapping in one ``__root__`` channel
# and refuses two writes to it per step (``InvalidUpdateError``). A ``TypedDict``
# schema instead gives every field its own channel, so the two agents can write
# concurrently as long as their fields don't overlap — which they don't.
#
# The Pydantic ↔ dict bridge is unchanged in spirit: each node still does
# ``StockAnalysisState(**state) → agent → model_dump`` — but now emits **only
# its own keys** (``model_dump(include=...)``). A full dump from each parallel
# node would collide on ``tickers`` and every other shared field.

def _take_right(_current: Any, incoming: Any) -> Any:
    """Reducer: last write wins. Only one branch writes each field per step, so
    this just documents intent and stays safe if that ever changes."""
    return incoming


class GraphState(TypedDict, total=False):
    """Per-field channel schema for the workflow (mirrors ``StockAnalysisState``)."""

    tickers: list[str]
    historical_data: Annotated[list[dict], _take_right]        # Agent 1
    failed_tickers: Annotated[list[dict], _take_right]         # Agent 1
    fundamental_report: Annotated[Optional[str], _take_right]  # Agent 2
    fundamental_highlights: Annotated[list[dict], _take_right]  # Agent 2
    final_decision: Optional[dict[str, Any]]                   # Agent 3


def _quant_node(state: GraphState) -> dict:
    """Run Agent 1; emit only ``historical_data`` + ``failed_tickers``."""
    result = quantitative_agent(StockAnalysisState(**state))
    return result.model_dump(include={"historical_data", "failed_tickers"})


def _fundamental_node(state: GraphState) -> dict:
    """Run Agent 2; emit only ``fundamental_report`` + ``fundamental_highlights``."""
    result = fundamental_agent(StockAnalysisState(**state))
    return result.model_dump(include={"fundamental_report", "fundamental_highlights"})


def _decision_node(state: GraphState) -> dict:
    """Run Agent 3; emit only ``final_decision``."""
    result = decision_agent(StockAnalysisState(**state))
    return result.model_dump(include={"final_decision"})


def build_graph():
    """
    Construct and compile the LangGraph workflow.

        START → quantitative_agent ┐
                                   ├→ decision_agent → END
        START → fundamental_agent  ┘

    Agent 1 and Agent 2 run concurrently off ``START``; ``decision_agent`` only
    fires once both have completed (fan-in barrier), so its state carries both
    ``historical_data`` and ``fundamental_report``.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph graph ready for ``.invoke()``.
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("quantitative_agent", _quant_node)
    workflow.add_node("fundamental_agent", _fundamental_node)
    workflow.add_node("decision_agent", _decision_node)

    # Fan-out: both analysis agents start from START → same superstep → parallel.
    workflow.add_edge(START, "quantitative_agent")
    workflow.add_edge(START, "fundamental_agent")

    # Fan-in: decision_agent has an incoming edge from EACH upstream node, so
    # LangGraph holds it until both have completed.
    workflow.add_edge("quantitative_agent", "decision_agent")
    workflow.add_edge("fundamental_agent", "decision_agent")

    workflow.add_edge("decision_agent", END)

    return workflow.compile()


# Pre-built graph instance for import convenience.
graph = build_graph()


def run_analysis(tickers: list[str] | None = None) -> StockAnalysisState:
    """
    Execute the full pipeline end to end and return the final typed state.

    This is the single wrapper the FastAPI layer calls: it owns the
    Pydantic → dict → invoke → Pydantic round-trip so the routes don't have to.

    Parameters
    ----------
    tickers : list[str] | None
        Symbols to analyse. ``None`` falls back to ``StockAnalysisState``'s
        default basket.

    Returns
    -------
    StockAnalysisState
        Final state with ``historical_data``, ``fundamental_report`` /
        ``fundamental_highlights`` and ``final_decision`` populated.
    """
    initial = (
        StockAnalysisState(tickers=tickers) if tickers else StockAnalysisState()
    )
    logger.info("run_analysis: invoking graph for %s", initial.tickers)
    # Seed only ``tickers``; every other field is produced by a node.
    result = graph.invoke({"tickers": initial.tickers})
    return StockAnalysisState(**result)
