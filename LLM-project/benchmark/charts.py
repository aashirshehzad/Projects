"""Static PNG charts for the README (matplotlib)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Reference categorical palette, slots 1-2 (validated pair); inks for text.
BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK_2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e6e5e0", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.axisbelow": True, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "legend.frameon": False,
})


def _title(ax, title, subtitle):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=INK_2)


def latency_percentiles(direct: dict, proxy: dict, hits: dict, out: Path) -> None:
    labels = ["p50", "p95", "p99"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), gridspec_kw={"width_ratios": [1.6, 1]})
    x = np.arange(3)
    w = 0.36
    for off, data, color, name in ((-w / 2, direct, ORANGE, "Direct LLM"), (w / 2, proxy, BLUE, "Semantic cache proxy")):
        vals = [data[k] for k in labels]
        bars = a1.bar(x + off, vals, w - 0.03, color=color, label=name)
        a1.bar_label(bars, labels=[f"{v:,.0f}" for v in vals], padding=3, fontsize=8, color=INK_2)
    a1.set_xticks(x, labels)
    a1.set_ylabel("latency (ms)")
    a1.set_ylim(0, max(direct["p99"], proxy["p99"]) * 1.3)
    a1.legend(loc="upper left", ncol=2)
    _title(a1, "End-to-end latency, all 200 requests", "Proxy tail stays near direct: misses still pay full LLM latency")

    vals = [hits[k] for k in labels]
    bars = a2.bar(x, vals, 0.5, color=BLUE)
    a2.bar_label(bars, labels=[f"{v:.1f}" for v in vals], padding=3, fontsize=8, color=INK_2)
    a2.set_xticks(x, labels)
    a2.set_ylabel("latency (ms)")
    _title(a2, "Cache-hit path only", "Embed + vector search + response")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def latency_cdf(direct_ms: list, proxy_ms: list, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for data, color, name in ((direct_ms, ORANGE, "Direct LLM"), (proxy_ms, BLUE, "Semantic cache proxy")):
        s = np.sort(data)
        ax.step(s, np.arange(1, len(s) + 1) / len(s), where="post", color=color, linewidth=2, label=name)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xlabel("latency (ms, log scale)")
    ax.set_ylabel("share of requests")
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(loc="upper left")
    _title(ax, "Latency distribution", "The proxy's first step is the share of requests answered from cache")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def cost(direct_usd: float, proxy_usd: float, direct_tokens: int, proxy_tokens: int, out: Path) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.8))
    for ax, vals, fmt, ylabel, title in (
        (a1, (direct_tokens, proxy_tokens), "{:,.0f}", "tokens billed", "Tokens billed"),
        (a2, (direct_usd, proxy_usd), "${:.5f}", "USD", "Upstream spend"),
    ):
        bars = ax.bar(["Direct LLM", "Proxy"], vals, 0.5, color=[ORANGE, BLUE])
        ax.bar_label(bars, labels=[fmt.format(v) for v in vals], padding=3, fontsize=8, color=INK_2)
        ax.set_ylim(0, max(vals) * 1.15)
        ax.set_ylabel(ylabel)
        saved = 1 - vals[1] / vals[0] if vals[0] else 0
        _title(ax, title, f"{saved:.1%} saved over the workload")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def threshold_sweep(rows: list, current: float, out: Path) -> None:
    """rows: dicts with threshold, guard, recall, false_hits."""
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.2), sharex=True)
    # Guard drawn first and wider so an identical cosine-only curve stays visible on top.
    for guard, color, width, name in ((True, BLUE, 4, "Cosine + entity guard"), (False, ORANGE, 1.6, "Cosine only")):
        rs = [r for r in rows if r["guard"] == guard]
        t = [r["threshold"] for r in rs]
        a1.plot(t, [r["recall"] for r in rs], color=color, linewidth=width, label=name, solid_capstyle="round")
        a2.plot(t, [r["false_hits"] for r in rs], color=color, linewidth=width, label=name, solid_capstyle="round")
    same_recall = all(
        abs(a["recall"] - b["recall"]) < 1e-9
        for a, b in zip([r for r in rows if r["guard"]], [r for r in rows if not r["guard"]])
    )
    for ax in (a1, a2):
        ax.axvline(current, color=MUTED, linewidth=1, linestyle=":")
        ax.set_xlabel("similarity threshold")
    a2.text(current, 1.0, f" configured {current}", transform=a2.get_xaxis_transform(), fontsize=8, color=INK_2, va="top")
    a1.set_ylabel("paraphrases served from cache")
    a1.set_ylim(0, 1.02)
    a1.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    a2.set_ylabel("wrong answers served")
    a2.set_ylim(0, None)
    a2.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    a1.legend(loc="lower left")
    _title(a1, "Recall on paraphrases",
           "Curves coincide: the guard costs no recall here" if same_recall else "Higher is better")
    _title(a2, "False hits (wrong answer served)", "Out of 200 requests, lower is better")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
