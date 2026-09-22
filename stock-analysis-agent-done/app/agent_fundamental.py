"""
Agent 2 – Fundamental Analysis Agent.

Responsibilities
────────────────
• Resolve each ticker to a SEC Central Index Key (CIK).
• Fetch the company's most recent **10-Q** or **10-K** filing from
  SEC EDGAR (whichever is newer).
• Extract key financial highlights from the filing text — revenue,
  net income and any forward-looking guidance — via
  ``extract_financial_highlights``.
• Cross-check the numbers against SEC XBRL structured facts, which are
  authoritative when available.
• Build a concise narrative report and **append** it to
  ``StockAnalysisState.fundamental_report``; the structured figures land
  in ``StockAnalysisState.fundamental_highlights``.

Data source
───────────
The paid ``sec-api`` package is *not* used. This agent talks directly to
the free, public **SEC EDGAR REST API** (``data.sec.gov`` +
``www.sec.gov/Archives``) over stdlib ``urllib`` — no API key, no extra
dependency. SEC asks every automated client to send a descriptive
``User-Agent`` with a contact email; set one via the
``SEC_EDGAR_USER_AGENT`` environment variable before running against the
live service.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from typing import Any, Optional

from app.state import FundamentalHighlights, StockAnalysisState

logger = logging.getLogger(__name__)

# ── configuration ────────────────────────────────────────────────────────────

# SEC policy: every automated client must send a User-Agent that contains a
# contact email, otherwise EDGAR replies 403. Override the placeholder below
# with your own address via the SEC_EDGAR_USER_AGENT env var.
_USER_AGENT = os.getenv(
    "SEC_EDGAR_USER_AGENT",
    "stock-analysis-agent/0.1 (contact: your-email@example.com)",
)
_HTTP_TIMEOUT = float(os.getenv("SEC_EDGAR_TIMEOUT", "20"))
_REQUEST_PAUSE = 0.2  # seconds between EDGAR requests (SEC fair-use ~10 req/s)
_WANTED_FORMS = ("10-Q", "10-K")

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_CONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn}/{doc}"

# us-gaap tags tried in order when reading authoritative structured facts.
_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)
_NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss")

_cik_map_cache: Optional[dict[str, str]] = None


# ── low-level HTTP ───────────────────────────────────────────────────────────

def _http_get(url: str) -> bytes:
    """GET *url* with the SEC-required User-Agent; raises on HTTP errors."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return resp.read()


def _http_get_json(url: str) -> Any:
    return json.loads(_http_get(url).decode("utf-8", "replace"))


# ── EDGAR lookups ───────────────────────────────────────────────────────────

def _cik_map() -> dict[str, str]:
    """Cached ``{TICKER: zero-padded-10-digit-CIK}`` map from EDGAR."""
    global _cik_map_cache
    if _cik_map_cache is None:
        raw = _http_get_json(_TICKERS_URL)
        _cik_map_cache = {
            str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
            for row in raw.values()
        }
    return _cik_map_cache


def _resolve_cik(ticker: str) -> tuple[Optional[str], Optional[str]]:
    """
    Map *ticker* to its CIK.

    Returns ``(cik, note)`` — exactly one is non-None. ``note`` distinguishes a
    genuine "not an SEC registrant" from a transport failure (e.g. EDGAR
    unreachable, or a 403 from a User-Agent with no contact email).
    """
    try:
        cik = _cik_map().get(ticker.upper())
    except Exception as exc:  # noqa: BLE001 – transport issues are non-fatal
        logger.exception("CIK map fetch failed")
        return None, f"Could not reach SEC EDGAR to resolve CIK ({exc})."
    if cik is None:
        return None, (
            "No SEC EDGAR registration found for this symbol — likely a foreign "
            "private issuer (files 20-F, not 10-K/10-Q) or an unregistered "
            "OTC/ADR line. No fundamentals retrieved."
        )
    return cik, None


def _recent_filing(cik: str) -> Optional[dict[str, str]]:
    """Return a small dict describing the newest 10-Q / 10-K for *cik*, or None."""
    data = _http_get_json(_SUBMISSIONS_URL.format(cik=cik))
    recent = data.get("filings", {}).get("recent", {})
    forms: list[str] = recent.get("form", [])

    def col(name: str) -> list[str]:
        return recent.get(name, [""] * len(forms))

    for i, form in enumerate(forms):  # arrays are ordered newest-first
        if form in _WANTED_FORMS:
            accn = col("accessionNumber")[i]
            doc = col("primaryDocument")[i]
            return {
                "form": form,
                "filing_date": col("filingDate")[i],
                "period_of_report": col("reportDate")[i],
                "url": _ARCHIVE_URL.format(
                    cik_int=int(cik), accn=accn.replace("-", ""), doc=doc
                )
                if doc
                else "",
            }
    return None


def _period_days(start: str, end: str) -> int:
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except (ValueError, TypeError):
        return 999


def _tag_period_value(
    cik: str, tag: str, period_end: Optional[str]
) -> Optional[float]:
    """
    Value of a single us-gaap *tag* for the most recent discrete quarter.

    Revenue and net income are *duration* facts, so one period end can carry
    both a quarterly (~90-day) and a year-to-date (~180/270-day) value. We
    anchor on the filing's ``period_end`` and take the **shortest** duration
    there, breaking ties by newest ``filed`` date.
    """
    try:
        data = _http_get_json(_CONCEPT_URL.format(cik=cik, tag=tag))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # company simply doesn't report this tag
            return None
        raise
    facts = [
        f
        for f in data.get("units", {}).get("USD", [])
        if f.get("form") in _WANTED_FORMS
        and "val" in f
        and f.get("start")
        and f.get("end")
    ]
    if not facts:
        return None

    pool = [f for f in facts if f["end"] == period_end] if period_end else []
    if not pool:  # fall back to whatever the latest reported period is
        latest_end = max(f["end"] for f in facts)
        pool = [f for f in facts if f["end"] == latest_end]

    min_dur = min(_period_days(f["start"], f["end"]) for f in pool)
    quarter = [f for f in pool if _period_days(f["start"], f["end"]) == min_dur]
    best = max(quarter, key=lambda f: f.get("filed", ""))
    return float(best["val"])


def _xbrl_fact(
    cik: str,
    tags: tuple[str, ...],
    period_end: Optional[str],
    *,
    prefer_largest: bool = False,
) -> Optional[float]:
    """
    Resolve a metric across candidate *tags*.

    ``prefer_largest=True`` (revenue): companies split total revenue across
    different us-gaap concepts, and some also tag a *disaggregated* subset
    under one of them — the consolidated total is always the largest, so pick
    that. ``prefer_largest=False`` (net income): the first tag that reports
    wins, since ``NetIncomeLoss`` is effectively universal.
    """
    values: list[float] = []
    for tag in tags:
        value = _tag_period_value(cik, tag, period_end)
        if value is None:
            continue
        if not prefer_largest:
            return value
        values.append(value)
    if not values:
        return None
    return max(values)


# ── text extraction (the requested "extract from text" function) ─────────────

# A US-thousands-grouped number, optionally $-prefixed and/or parenthesised
# (accounting notation for negatives), e.g. "$ 391,035" or "(2,930)".
_NUM = r"\(?\$?\s?([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?)\)?"

_REVENUE_LABELS = (
    r"total net sales",
    r"net sales",
    r"total net revenues?",
    r"total revenues?",
    r"net revenues?",
    r"revenues?",
)
_NET_INCOME_LABELS = (r"net income \(loss\)", r"net income", r"net earnings")

_GUIDANCE_TOPICS = (
    "revenue", "sales", "margin", "growth", "earnings", "demand", "guidance",
    "outlook",
)


def _strip_html(html: str) -> str:
    """Crude tag stripper — good enough to regex financial phrases out of."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    replacements = {
        "&nbsp;": " ", "&#160;": " ", "&amp;": "&", "&#38;": "&",
        "&#8217;": "'", "&#8216;": "'", "&#8220;": '"', "&#8221;": '"',
        "&#8212;": "-", "&#8211;": "-", "&quot;": '"', "&apos;": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def _units_multiplier(text: str) -> float:
    """Detect a document-level 'in thousands / in millions' scale hint."""
    head = text[:20_000].lower()
    if "in thousands" in head:
        return 1_000.0
    if "in millions" in head:
        return 1_000_000.0
    return 1.0


def _first_number_after(text: str, labels: tuple[str, ...]) -> Optional[float]:
    for label in labels:
        m = re.search(label + r".{0,60}?" + _NUM, text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


_GUIDANCE_TRIGGER = re.compile(
    r"expect|anticipat|outlook|guidance|going forward|full[ -]year|"
    r"next quarter|in the (?:coming|current|next) (?:quarter|year)|"
    r"we (?:believe|estimate|project|forecast)",
    re.IGNORECASE,
)
# Phrases that mark a window as boilerplate rather than genuine guidance.
_GUIDANCE_NEGATIVE = (
    "deferred revenue", "earnings per share", "critical accounting",
    "risk factor", "cautionary", "could adversely", "could be adversely",
    "may face", "no assurance", "forward-looking statements",
)


def _extract_guidance(text: str, max_snippets: int = 2) -> Optional[str]:
    """
    Pull short context windows around forward-looking language.

    Sentence splitting is unreliable on stripped filing text, so instead we
    take ~450-char windows centred on each guidance trigger phrase that also
    mentions a financial topic (revenue, margin, demand, …).
    """
    snippets: list[str] = []
    for m in _GUIDANCE_TRIGGER.finditer(text):
        start, end = max(0, m.start() - 200), min(len(text), m.end() + 250)
        window = text[start:end]
        # Trim partial words at the cut points.
        if start > 0 and " " in window:
            window = window[window.index(" ") + 1 :]
        if end < len(text) and " " in window:
            window = window[: window.rindex(" ")]
        window = re.sub(r"\s+", " ", window).strip()
        low = window.lower()
        if any(neg in low for neg in _GUIDANCE_NEGATIVE):
            continue
        if window and any(t in low for t in _GUIDANCE_TOPICS):
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(text) else ""
            snippets.append(f"{prefix}{window}{suffix}")
        if len(snippets) >= max_snippets:
            break
    if not snippets:
        return None
    excerpt = " ".join(dict.fromkeys(snippets))
    return excerpt[:597] + "..." if len(excerpt) > 600 else excerpt


def extract_financial_highlights(text: str) -> dict[str, Any]:
    """
    Best-effort extraction of the headline figures from the plain text of a
    10-Q / 10-K filing.

    Parameters
    ----------
    text : str
        Filing body with HTML already stripped (see ``_strip_html``).

    Returns
    -------
    dict
        ``{"revenue": float | None, "net_income": float | None,
           "forward_guidance": str | None}``. Numeric values are scaled with a
        document-level "in millions / in thousands" hint, so treat them as
        approximate — ``fundamental_agent`` overrides them with SEC XBRL facts
        whenever those are available.
    """
    mult = _units_multiplier(text)
    revenue = _first_number_after(text, _REVENUE_LABELS)
    net_income = _first_number_after(text, _NET_INCOME_LABELS)
    return {
        "revenue": revenue * mult if revenue is not None else None,
        "net_income": net_income * mult if net_income is not None else None,
        "forward_guidance": _extract_guidance(text),
    }


# ── per-ticker orchestration ────────────────────────────────────────────────

def _analyse_ticker(ticker: str) -> FundamentalHighlights:
    cik, cik_note = _resolve_cik(ticker)
    if cik is None:
        return FundamentalHighlights(ticker=ticker, notes=cik_note)

    hl = FundamentalHighlights(ticker=ticker, cik=cik)
    notes: list[str] = []

    try:
        filing = _recent_filing(cik)
    except Exception as exc:  # noqa: BLE001
        filing = None
        notes.append(f"Could not list filings ({exc}).")

    if filing:
        hl.form_type = filing["form"]
        hl.filing_date = filing["filing_date"] or None
        hl.period_of_report = filing["period_of_report"] or None
        hl.filing_url = filing["url"] or None

        if filing["url"]:
            try:
                text = _strip_html(_http_get(filing["url"]).decode("utf-8", "replace"))
                extracted = extract_financial_highlights(text)
                hl.revenue = extracted["revenue"]
                hl.net_income = extracted["net_income"]
                hl.forward_guidance = extracted["forward_guidance"]
            except Exception as exc:  # noqa: BLE001
                notes.append(f"Could not parse filing text ({exc}).")
    elif not notes:
        notes.append("No 10-Q or 10-K present in recent EDGAR submissions.")

    # Authoritative numbers win over text scraping.
    try:
        xbrl_rev = _xbrl_fact(
            cik, _REVENUE_TAGS, hl.period_of_report, prefer_largest=True
        )
        xbrl_ni = _xbrl_fact(cik, _NET_INCOME_TAGS, hl.period_of_report)
        if xbrl_rev is not None:
            hl.revenue = xbrl_rev
        if xbrl_ni is not None:
            hl.net_income = xbrl_ni
    except Exception as exc:  # noqa: BLE001
        notes.append(f"XBRL facts unavailable ({exc}).")

    if hl.forward_guidance is None:
        notes.append("No explicit forward guidance detected in the filing text.")

    hl.notes = " ".join(notes) or None
    return hl


# ── report formatting ──────────────────────────────────────────────────────

def _fmt_usd(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    sign, v = ("-" if value < 0 else ""), abs(value)
    if v >= 1e9:
        return f"{sign}${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"{sign}${v / 1e6:.2f}M"
    return f"{sign}${v:,.0f}"


def _format_report(items: list[FundamentalHighlights]) -> str:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "=== FUNDAMENTAL ANALYSIS REPORT (Agent 2) ===",
        f"Generated : {generated}",
        "Source    : SEC EDGAR — most recent 10-Q / 10-K per issuer",
        "",
    ]
    for hl in items:
        header = hl.ticker
        if hl.form_type:
            header += f" - {hl.form_type}"
            if hl.period_of_report:
                header += f" (period ending {hl.period_of_report})"
        lines.append(header)
        lines.append("-" * len(header))
        if hl.filing_date:
            lines.append(f"  Filed            : {hl.filing_date}")
        lines.append(f"  Revenue          : {_fmt_usd(hl.revenue)}")
        lines.append(f"  Net income       : {_fmt_usd(hl.net_income)}")
        if hl.revenue and hl.net_income is not None and hl.revenue != 0:
            lines.append(
                f"  Net margin       : {hl.net_income / hl.revenue * 100:.1f}%"
            )
        lines.append(
            "  Forward guidance : "
            + (hl.forward_guidance or "none disclosed / not detected")
        )
        if hl.filing_url:
            lines.append(f"  Filing           : {hl.filing_url}")
        if hl.notes:
            lines.append(f"  Notes            : {hl.notes}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ── public entry point (LangGraph node function) ────────────────────────────

def fundamental_agent(state: StockAnalysisState) -> StockAnalysisState:
    """
    LangGraph **node** that fills ``state.fundamental_report`` (text, appended)
    and ``state.fundamental_highlights`` (structured).

    Only ``state.tickers`` is read. A failure on one ticker is captured in that
    ticker's ``notes`` and never aborts the run.
    """
    highlights: list[FundamentalHighlights] = []

    for ticker in state.tickers:
        try:
            hl = _analyse_ticker(ticker)
        except Exception as exc:  # noqa: BLE001 – isolate per-ticker failures
            logger.exception("Fundamental analysis failed for %s", ticker)
            hl = FundamentalHighlights(ticker=ticker, notes=f"Unhandled error: {exc}")
        highlights.append(hl)
        logger.info(
            "fundamentals %s  rev=%s  ni=%s", ticker, hl.revenue, hl.net_income
        )
        time.sleep(_REQUEST_PAUSE)  # stay under SEC fair-use limits

    report_block = _format_report(highlights)
    existing = state.fundamental_report
    combined = (
        f"{existing.rstrip()}\n\n{report_block}" if existing else report_block
    )

    return state.model_copy(
        update={
            "fundamental_report": combined,
            "fundamental_highlights": highlights,
        }
    )
