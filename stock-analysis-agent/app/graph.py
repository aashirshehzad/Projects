"""
LangGraph workflow definition **and Agent 3 (decision)** for the stock-analysis
pipeline.

Agents
──────
  • Agent 1   – quantitative (yfinance price metrics)       → app/agent_quantitative.py
  • Agent 2   – fundamental  (SEC EDGAR 10-Q / 10-K)         → app/agent_fundamental.py
  • Agent 2.5 – news         (Tavily dated headlines)        → app/agent_news.py
  • Agent 3   – decision     (Gemini three-section report)   ← defined in this file

Agent 3 and the graph wiring live together here on purpose: the decision step
is the *join point* of the pipeline, so its node function and the topology that
feeds it are easiest to reason about side by side.

Topology
────────
            ┌────────────────────┐
      START ┤ quantitative_agent │──┐
            ├────────────────────┤  │
      START ┤ fundamental_agent  │──┼──►  decision_agent  ──►  END
            ├────────────────────┤  │
      START ┤ news_agent         │──┘
            └────────────────────┘

The three retrieval agents share no data, so all three are wired straight off
``START`` and LangGraph schedules them in the **same superstep** — the sync node
callables run concurrently on its executor threadpool. ``decision_agent`` has an
incoming edge from *each* of them, which makes LangGraph wait for **all three**
to finish before it runs — a fan-in barrier.

State is a ``TypedDict`` (``GraphState``), not a bare ``dict``: that gives each
field its own channel so the parallel agents can write at the same time without
tripping LangGraph's one-write-per-channel-per-step rule. See the note above
``build_graph`` for the details.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.agent_fundamental import fundamental_agent
from app.agent_news import news_agent
from app.agent_quantitative import quantitative_agent
from app.state import (
    DecisionReport,
    StockAnalysisState,
    TickerNews,
    TickerReport,
    TickerSummary,
)

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
# Per-ticker three-section reports are large and the default basket is ~11
# tickers — give the model real room so the JSON isn't truncated mid-array.
_DECISION_MAX_TOKENS = int(os.getenv("DECISION_MAX_TOKENS", "20000"))
# Extra revise-passes of the internal critic loop (0 = single self-critique
# call only, which is what the system prompt already enforces; 1–2 = that many
# additional "audit your draft" round-trips at ~1x cost each).
_CRITIC_PASSES = max(0, min(2, int(os.getenv("DECISION_CRITIC_PASSES", "0"))))

# The SDK reads GEMINI_API_KEY (preferred) or GOOGLE_API_KEY from the env; we
# resolve it explicitly so a missing key degrades gracefully instead of raising
# at client construction.
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

_SYSTEM_PROMPT = (
    "You are an Elite Financial Intelligence Analyst. You are handed machine-"
    "generated inputs for a set of tickers: quantitative price metrics (Agent 1), "
    "a digest of the latest SEC filings (Agent 2), and a list of recent DATED news "
    "headlines (Agent 2.5). Produce one rigorous, data-grounded report per ticker.\n"
    "\n"
    "METHOD — for every ticker:\n"
    "1. Executive thesis: first-principles fundamental analysis — revenue drivers, "
    "moat defensibility, unit economics, balance-sheet health, and macro/sector "
    "alignment (rate sensitivity, competitor positioning, industry head/tailwinds). "
    "Do NOT write a shallow 'Option A vs Option B' pros-and-cons list; reason from "
    "mechanisms and cite specific figures from the inputs. Actively weigh the "
    "14-day RSI supplied for each ticker: explicitly call out an overbought reading "
    "(RSI > 70) or an oversold reading (RSI < 30) in the executive thesis, tying it "
    "to entry timing / momentum risk rather than treating it as a standalone "
    "verdict. Also weigh the 9-day and 20-day EMAs: evaluate the EMA-9 vs EMA-20 "
    "relationship (EMA-9 above and pulling away from EMA-20 = accelerating "
    "short-term momentum; EMA-9 below EMA-20 = fading momentum / bearish "
    "near-term) and both EMAs' position relative to the latest close and the "
    "50-day MA — close above a rising EMA-20 with EMA-20 above the 50-day MA "
    "signals trend strength; the inverse signals weakening momentum or a "
    "possible trend break. State this read explicitly and connect it to the "
    "thesis, not as a standalone verdict. Also read the MACD (12/26/9) snapshot: "
    "identify a bullish crossover (MACD line above the signal line, histogram "
    "positive/rising) or a bearish crossover (MACD line below the signal line, "
    "histogram negative/falling), and gauge momentum expansion vs contraction "
    "from the histogram magnitude and direction. Cross-check MACD against the "
    "14-day RSI and the 20-day EMA trend: call out when they CONFIRM each other "
    "(e.g. bullish MACD crossover + RSI rising through 50 + price above a rising "
    "EMA-20) versus when they DIVERGE (e.g. price/EMA-20 making new highs while "
    "MACD histogram shrinks or RSI rolls over), and weight a confirmed signal "
    "more than a lone one. Also read the Bollinger Bands (SMA-20 ± 2σ): use "
    "bandwidth as a volatility gauge — a low/contracting bandwidth is a squeeze "
    "that often precedes a large directional move, a high/expanding one means "
    "volatility is already elevated. Note where the latest close sits in the "
    "channel: pressing or closing above the UPPER band = strong momentum but "
    "stretched/overbought, pressing or closing below the LOWER band = "
    "oversold/possible rejection, and a close back inside after a band break "
    "often signals exhaustion. Do NOT treat a band touch as a signal on its "
    "own — confirm it against RSI (is it also >70 / <30 or diverging?) and MACD "
    "(is the histogram confirming or fading?) to filter false breakouts, and "
    "say so explicitly.\n"
    "1b. High-beta price action: for volatile, high-beta names (e.g. TSLA, SMCI) "
    "the tape is driven as much by structure as by fundamentals. When you judge "
    "a Bollinger Band breakout or an RSI divergence, actively look for aggressive "
    "price-action mechanics and name them where the data supports it: Fair Value "
    "Gaps / imbalances (a wide unfilled gap between one bar's range and the next "
    "that price tends to revisit), liquidity sweeps / stop runs (a sharp spike "
    "through an obvious prior high or low that immediately reverses), and shifts "
    "in market structure (a decisive break of the last swing high/low that flips "
    "the trend). Treat a band break that coincides with a liquidity sweep and no "
    "structure shift as a probable fake-out; treat one that holds with a "
    "structure break and MACD/RSI confirmation as a real regime change. Be "
    "explicit that this reading is probabilistic, not a call.\n"
    "2. Catalyst timeline: for each meaningful price move or shift, attribute it to "
    "a specific DATED news catalyst FROM THE PROVIDED HEADLINES. Each entry needs a "
    "date, the catalyst + its source, the market reaction (% move / volume / trend "
    "shift), and the specific causal mechanism (e.g. margin compression, missed ARR, "
    "guidance cut, supply bottleneck). If a ticker has no usable dated news, say so "
    "in its timeline — do NOT invent events or dates.\n"
    "3. Scenarios: bull / base / bear, each with concrete drivers and an explicit "
    "fundamental invalidation trigger. Add a probability (0..1) per leg. For "
    "high-beta names the bull and bear triggers MUST explicitly account for "
    "gap risk: a rapid 10–20% single-session gap-up or gap-down driven by an "
    "unexpected catalyst — an earnings pre-announcement, a guidance revision, a "
    "regulatory action, or an SEC 8-K filing (item 2.02 results, 4.02 "
    "non-reliance / restatement, 5.02 executive change, 1.01/2.01 material "
    "deal). State the specific catalyst type that would drive each gap and the "
    "price level or structural break that would confirm it.\n"
    "Also produce basket-level cross_cutting_risks.\n"
    "\n"
    "INTERNAL REFLECTION (do this before you answer, then discard the scratch work):\n"
    "  a. Draft the reports.\n"
    "  b. Critic pass — audit the draft: any superficial 'vs.' comparison instead "
    "of first-principles reasoning? any price move without an exact date and a "
    "specific causal trigger? generic or low-rigor tone? any scenario missing an "
    "invalidation trigger?\n"
    "  c. Revise to fix every issue found.\n"
    "Put a short note of what the critic changed (or 'no changes needed') in "
    "critic_notes.\n"
    "\n"
    "OUTPUT: return ONLY the JSON object matching the provided schema — no prose, "
    "no markdown fences. recommendation MUST be exactly 'Buy', 'Sell', or 'Hold'. "
    "executive_thesis is plain prose with paragraphs separated by blank lines. This "
    "is informational analysis, not personalised financial advice."
)


# ── Gemini response schema (LLM-facing subset of DecisionReport) ────────────

class _LlmDecision(BaseModel):
    """What the model must return; server metadata is added afterwards."""

    reports: list[TickerReport]
    cross_cutting_risks: list[str] = []
    critic_notes: str = ""


# ── Agent 3 helpers ────────────────────────────────────────────────────────

def _fmt_price(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "n/a"


def _format_quant_block(rows: list[TickerSummary]) -> str:
    """Render Agent 1's structured output as a compact text table for the LLM."""
    if not rows:
        return "No quantitative data available."
    lines: list[str] = []
    for r in rows:
        ma = r.moving_averages
        rsi = f"{r.rsi_14:.1f}" if r.rsi_14 is not None else "n/a"
        # Indicator look-backs are in *bars*; on an intraday timeframe "50-bar
        # MA" is not "50-day". Label the period so the model reads it right.
        unit = "day" if r.timeframe in ("6M", "1Y", "ALL") else "bar"
        lines.append(
            f"- {r.ticker} [{r.timeframe}]: latest close {_fmt_price(r.latest_close)} "
            f"({r.period_start} → {r.period_end}); "
            f"period return {r.pct_return:+.2f}%; "
            f"50-{unit} MA {_fmt_price(ma.ma_50)}; "
            f"200-{unit} MA {_fmt_price(ma.ma_200)}; "
            f"9-{unit} EMA {_fmt_price(ma.ema_9)}; "
            f"20-{unit} EMA {_fmt_price(ma.ema_20)}; "
            f"14-{unit} RSI {rsi}; "
            f"MACD {_fmt_macd(r.macd)}; "
            f"Bollinger {_fmt_bollinger(r.bollinger)}; "
            f"{r.data_points} bars"
        )
    return "\n".join(lines)


def _fmt_bollinger(b) -> str:
    """Compact 'upper / middle / lower, bandwidth' rendering of the BB snapshot."""
    if b is None:
        return "n/a"
    bw = f"{b.bandwidth:.3f}" if b.bandwidth is not None else "n/a"
    return (
        f"upper {_fmt_price(b.bb_upper)} / middle {_fmt_price(b.bb_middle)} / "
        f"lower {_fmt_price(b.bb_lower)}, bandwidth {bw}"
    )


def _fmt_macd(m) -> str:
    """Compact 'line / signal / hist' rendering of the latest MACD snapshot."""
    if m is None:
        return "n/a"

    def _n(v: float | None) -> str:
        return f"{v:+.4f}" if v is not None else "n/a"

    return f"line {_n(m.macd_line)} / signal {_n(m.signal_line)} / hist {_n(m.macd_histogram)}"


def _format_news_block(bundles: list[TickerNews]) -> str:
    """Render Agent 2.5's dated headlines as text the model can cite."""
    if not bundles:
        return "No news context available."
    out: list[str] = []
    for b in bundles:
        out.append(f"## {b.ticker}")
        if b.summary:
            out.append(f"Summary: {b.summary}")
        for it in b.items:
            when = it.published_date or "undated"
            out.append(f"- [{when}] {it.title} — {it.url}")
            if it.snippet:
                out.append(f"    {it.snippet}")
        if not b.items:
            out.append(f"(no headlines — {b.notes or 'none returned'})")
        out.append("")
    return "\n".join(out).strip()


def _build_user_prompt(
    tickers: list[str], quant_block: str, fundamental_block: str, news_block: str
) -> str:
    """Combine every agent's output into the single user turn for the LLM."""
    return (
        f"TICKERS TO ANALYSE: {', '.join(tickers)}\n\n"
        "=== AGENT 1 — QUANTITATIVE (price metrics) ===\n"
        f"{quant_block}\n\n"
        "=== AGENT 2 — FUNDAMENTAL (latest SEC filings) ===\n"
        f"{fundamental_block or 'No fundamental data available.'}\n\n"
        "=== AGENT 2.5 — RECENT NEWS (dated headlines for catalyst attribution) ===\n"
        f"{news_block}\n\n"
        "Produce one report per ticker in the required JSON schema."
    )


def _critic_prompt(original_prompt: str, draft_json: str) -> str:
    """Follow-up turn that runs one extra explicit critic + revise pass."""
    return (
        f"{original_prompt}\n\n=== YOUR DRAFT (JSON) ===\n{draft_json}\n\n"
        "Run the CRITIC step now. Audit the draft against the failure modes in "
        "your instructions: superficial 'A vs B' comparison instead of first-"
        "principles analysis; any price move mentioned without an exact date and "
        "a specific causal news trigger; generic, low-rigor tone; any scenario "
        "missing an invalidation trigger; catalysts not grounded in the provided "
        "headlines. Return a corrected report in the SAME JSON schema and set "
        "critic_notes to a short list of what you changed (or 'no changes needed')."
    )


def _generate(contents: str) -> str:
    """One Gemini ``generate_content`` call constrained to ``_LlmDecision``."""
    client = genai.Client(api_key=_GEMINI_API_KEY)
    response = client.models.generate_content(
        model=_DECISION_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=_DECISION_MAX_TOKENS,
            temperature=0.3,
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            response_mime_type="application/json",
            response_schema=_LlmDecision,
        ),
    )
    try:
        finish = getattr(response.candidates[0], "finish_reason", None)
        if finish and "MAX_TOKENS" in str(finish).upper():
            logger.warning(
                "decision_agent: Gemini stopped at max_output_tokens (%d) — reply "
                "is truncated; salvage will recover the complete reports. Raise "
                "DECISION_MAX_TOKENS or reduce the ticker count.",
                _DECISION_MAX_TOKENS,
            )
    except Exception:  # noqa: BLE001 — diagnostics only
        pass
    return (response.text or "").strip()


def _parse_report(raw: str) -> Optional[_LlmDecision]:
    """
    Validate the model JSON against ``_LlmDecision``. If strict validation
    fails (usually a truncated reply, or one report with a schema drift the
    field validators couldn't absorb), fall back to salvaging every individual
    report object that *does* validate — a partial report beats none.
    """
    if not raw:
        return None
    for candidate in (raw, _first_json_object(raw)):
        if not candidate:
            continue
        try:
            return _LlmDecision.model_validate_json(candidate)
        except Exception:  # noqa: BLE001 — try the next candidate / salvage
            continue

    salvaged = _salvage_reports(raw)
    if salvaged:
        logger.warning(
            "decision_agent: strict parse failed — salvaged %d report(s) from "
            "the reply", len(salvaged)
        )
        return _LlmDecision(reports=salvaged)
    return None


def _first_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else ""


def _salvage_reports(raw: str) -> list[TickerReport]:
    """
    Best-effort recovery of individual ``TickerReport`` objects from a reply
    whose top-level JSON won't parse. Scans the ``"reports"`` array with a tiny
    brace/string state machine, validating each complete ``{ … }`` element on
    its own; a trailing half-written object (truncation) is simply skipped.
    """
    anchor = raw.find('"reports"')
    if anchor == -1:
        return []
    lb = raw.find("[", anchor)
    if lb == -1:
        return []

    out: list[TickerReport] = []
    depth, obj_start = 0, -1
    in_str = esc = False
    for i in range(lb + 1, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start != -1:
                try:
                    out.append(TickerReport.model_validate_json(raw[obj_start:i + 1]))
                except Exception:  # noqa: BLE001 — drop the bad one, keep going
                    pass
                obj_start = -1
        elif ch == "]" and depth == 0:
            break
    return out


# ── Agent 3 — public entry point (LangGraph node function) ──────────────────

def decision_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    Agent 3. Ingests Agent 1's ``historical_data``, Agent 2's
    ``fundamental_report`` and Agent 2.5's ``news_context``, asks Gemini for a
    per-ticker three-section report (executive thesis / dated catalyst timeline /
    bull-base-bear matrix), runs an internal critic pass, and writes the result
    to ``state.final_decision`` as a :class:`DecisionReport`.

    Per the agent contract this never raises past its own body: a missing
    ``google-genai`` package, an unset ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``,
    an API error, or an unparseable reply all resolve to a degraded
    ``DecisionReport`` — one ``Hold`` ``TickerReport`` per symbol with an
    ``error`` note — so one flaky call can't abort the graph run.
    """
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    quant_block = _format_quant_block(state.historical_data)
    fundamental_block = (state.fundamental_report or "").strip()
    news_block = _format_news_block(state.news_context)
    has_news = any(b.items for b in state.news_context)

    def _fallback(reason: str) -> StockAnalysisState:
        logger.warning("decision_agent: %s — returning degraded report", reason)
        reports = [
            TickerReport(
                ticker=t,
                recommendation="Hold",
                executive_thesis=f"Automated analysis unavailable: {reason}.",
            )
            for t in state.tickers
        ]
        report = DecisionReport(
            reports=reports,
            model=_DECISION_MODEL,
            generated_at=generated_at,
            error=reason,
        )
        return state.model_copy(update={"final_decision": report})

    if not state.historical_data and not fundamental_block and not has_news:
        return _fallback("no Agent 1 / 2 / 2.5 output to reason over")
    if genai is None:
        return _fallback("the 'google-genai' package is not installed")
    if not _GEMINI_API_KEY:
        return _fallback("no Gemini credentials (set GEMINI_API_KEY)")

    user_prompt = _build_user_prompt(
        state.tickers, quant_block, fundamental_block, news_block
    )
    try:
        raw = _generate(user_prompt)
        for _ in range(_CRITIC_PASSES):
            revised = _generate(_critic_prompt(user_prompt, raw))
            if revised:
                raw = revised
    except Exception as exc:  # noqa: BLE001 – never abort the graph on an LLM error
        logger.exception("decision_agent: LLM call failed")
        return _fallback(f"LLM call failed ({exc or exc.__class__.__name__})")

    parsed = _parse_report(raw)
    if parsed is None or not parsed.reports:
        return _fallback("model reply could not be parsed into a report")

    # A partial parse (salvage, or the model just skipped a ticker) still gives
    # a full report set: fill the gaps with Hold placeholders rather than
    # discarding the reports that DID come back.
    by_ticker = {r.ticker: r for r in parsed.reports}
    reports = [
        by_ticker.get(t) or TickerReport(
            ticker=t,
            recommendation="Hold",
            executive_thesis=(
                "Automated analysis unavailable for this ticker — the model "
                "reply was truncated or omitted it. Other tickers are unaffected."
            ),
        )
        for t in state.tickers
    ]
    missing = [t for t in state.tickers if t not in by_ticker]
    partial_note = (
        f"partial report: {len(missing)}/{len(state.tickers)} tickers "
        f"({', '.join(missing)}) missing from the model reply — filled with Hold"
        if missing else None
    )

    report = DecisionReport(
        reports=reports,
        cross_cutting_risks=parsed.cross_cutting_risks,
        critic_notes=(parsed.critic_notes or None),
        model=_DECISION_MODEL,
        generated_at=generated_at,
        raw_response=raw,
        error=partial_note,
    )
    logger.info(
        "decision_agent: %d report(s)%s — %s",
        len(report.reports),
        f" ({len(missing)} filled)" if missing else "",
        ", ".join(f"{r.ticker}:{r.recommendation}" for r in report.reports),
    )
    return state.model_copy(update={"final_decision": report})


# ── graph assembly ─────────────────────────────────────────────────────────

# Why not ``StateGraph(dict)``
# ───────────────────────────
# The retrieval agents run in the *same* superstep. With a bare ``dict`` schema
# LangGraph stores the whole mapping in one ``__root__`` channel and refuses two
# writes to it per step (``InvalidUpdateError``). A ``TypedDict`` schema gives
# every field its own channel, so the agents can write concurrently as long as
# their fields don't overlap — which they don't.
#
# The Pydantic ↔ dict bridge is unchanged in spirit: each node still does
# ``StockAnalysisState(**state) → agent → model_dump`` — but emits **only its
# own keys** (``model_dump(include=...)``). A full dump from each parallel node
# would collide on ``tickers`` and every other shared field.

def _take_right(_current: Any, incoming: Any) -> Any:
    """Reducer: last write wins. Only one branch writes each field per step, so
    this just documents intent and stays safe if that ever changes."""
    return incoming


class GraphState(TypedDict, total=False):
    """Per-field channel schema for the workflow (mirrors ``StockAnalysisState``)."""

    tickers: list[str]
    timeframe: str
    historical_data: Annotated[list[dict], _take_right]         # Agent 1
    failed_tickers: Annotated[list[dict], _take_right]          # Agent 1
    fundamental_report: Annotated[Optional[str], _take_right]   # Agent 2
    fundamental_highlights: Annotated[list[dict], _take_right]  # Agent 2
    news_context: Annotated[list[dict], _take_right]            # Agent 2.5
    final_decision: Optional[dict[str, Any]]                    # Agent 3


def _quant_node(state: GraphState) -> dict:
    """Run Agent 1; emit only ``historical_data`` + ``failed_tickers``."""
    result = quantitative_agent(StockAnalysisState(**state))
    return result.model_dump(include={"historical_data", "failed_tickers"})


def _fundamental_node(state: GraphState) -> dict:
    """Run Agent 2; emit only ``fundamental_report`` + ``fundamental_highlights``."""
    result = fundamental_agent(StockAnalysisState(**state))
    return result.model_dump(include={"fundamental_report", "fundamental_highlights"})


def _news_node(state: GraphState) -> dict:
    """Run Agent 2.5; emit only ``news_context``."""
    result = news_agent(StockAnalysisState(**state))
    return result.model_dump(include={"news_context"})


def _decision_node(state: GraphState) -> dict:
    """Run Agent 3; emit only ``final_decision``."""
    result = decision_agent(StockAnalysisState(**state))
    return result.model_dump(include={"final_decision"})


def build_graph():
    """
    Construct and compile the LangGraph workflow.

        START → quantitative_agent ┐
        START → fundamental_agent  ┼→ decision_agent → END
        START → news_agent         ┘

    The three retrieval agents run concurrently off ``START``; ``decision_agent``
    only fires once all three have completed (fan-in barrier), so its state
    carries ``historical_data``, ``fundamental_report`` and ``news_context``.

    Returns
    -------
    CompiledGraph
        A compiled LangGraph graph ready for ``.invoke()``.
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("quantitative_agent", _quant_node)
    workflow.add_node("fundamental_agent", _fundamental_node)
    workflow.add_node("news_agent", _news_node)
    workflow.add_node("decision_agent", _decision_node)

    # Fan-out: every retrieval agent starts from START → same superstep → parallel.
    workflow.add_edge(START, "quantitative_agent")
    workflow.add_edge(START, "fundamental_agent")
    workflow.add_edge(START, "news_agent")

    # Fan-in: decision_agent has an incoming edge from EACH retrieval node, so
    # LangGraph holds it until all three have completed.
    workflow.add_edge("quantitative_agent", "decision_agent")
    workflow.add_edge("fundamental_agent", "decision_agent")
    workflow.add_edge("news_agent", "decision_agent")

    workflow.add_edge("decision_agent", END)

    return workflow.compile()


# Pre-built graph instance for import convenience.
graph = build_graph()


def run_analysis(
    tickers: list[str] | None = None, timeframe: str | None = None
) -> StockAnalysisState:
    """
    Execute the full pipeline end to end and return the final typed state.

    This is the single wrapper the FastAPI layer calls: it owns the
    Pydantic → dict → invoke → Pydantic round-trip so the routes don't have to.

    Parameters
    ----------
    tickers : list[str] | None
        Symbols to analyse. ``None`` falls back to ``StockAnalysisState``'s
        default basket.
    timeframe : str | None
        Chart timeframe for Agent 1 (1D…ALL). ``None`` → the state default.

    Returns
    -------
    StockAnalysisState
        Final state with ``historical_data``, ``fundamental_report`` /
        ``fundamental_highlights``, ``news_context`` and ``final_decision``
        populated.
    """
    kwargs: dict[str, Any] = {}
    if tickers:
        kwargs["tickers"] = tickers
    if timeframe:
        kwargs["timeframe"] = timeframe
    initial = StockAnalysisState(**kwargs)
    logger.info(
        "run_analysis: invoking graph for %s [%s]", initial.tickers, initial.timeframe
    )
    # Seed ``tickers`` + ``timeframe``; every other field is produced by a node.
    result = graph.invoke(
        {"tickers": initial.tickers, "timeframe": initial.timeframe}
    )
    return StockAnalysisState(**result)
