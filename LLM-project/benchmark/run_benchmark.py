"""Phase 3 benchmark: direct LLM vs semantic cache proxy on the same 200-query workload.

Start the proxy first, then:

    python -m benchmark.run_benchmark --url http://localhost:8000

Pass 1 sends every query with `X-Cache-Bypass: true` (the direct baseline through
the same HTTP stack). Pass 2 clears the cache and replays the workload normally.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark import charts  # noqa: E402
from benchmark.dataset import build_workload  # noqa: E402

RESULTS = Path(__file__).parent / "results"


async def run_pass(url: str, queries, concurrency: int, bypass: bool, tenant: str) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    headers = {"X-Tenant-ID": tenant}
    if bypass:
        headers["X-Cache-Bypass"] = "true"

    async with httpx.AsyncClient(base_url=url, timeout=120) as client:

        async def one(i, q):
            # Stagger starts so in-flight order follows workload order.
            await asyncio.sleep(i * 0.002)
            async with sem:
                t0 = time.perf_counter()
                res = await client.post(
                    "/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": q.text}]},
                    headers=headers,
                )
                wall_ms = (time.perf_counter() - t0) * 1000
                res.raise_for_status()
                return {"i": i, "query": q, "wall_ms": wall_ms, **res.json()}

        return await asyncio.gather(*(one(i, q) for i, q in enumerate(queries)))


def pct(values) -> dict:
    a = np.asarray(values, dtype=float)
    return {"p50": float(np.percentile(a, 50)), "p95": float(np.percentile(a, 95)),
            "p99": float(np.percentile(a, 99)), "mean": float(a.mean())}


def cost_usd(usage: dict, in_price: float, out_price: float) -> float:
    return (usage["prompt_tokens"] * in_price + usage["completion_tokens"] * out_price) / 1e6


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--input-price", type=float, default=0.05, help="USD per 1M prompt tokens")
    ap.add_argument("--output-price", type=float, default=0.08, help="USD per 1M completion tokens")
    ap.add_argument("--out", type=Path, default=RESULTS, help="directory for JSON + charts")
    args = ap.parse_args()
    out = args.out

    async with httpx.AsyncClient(base_url=args.url) as c:
        cfg = (await c.get("/cache/stats")).json()["config"]
        upstream = (await c.get("/health")).json()["upstream"]

    queries = build_workload(min_gap=2 * args.concurrency)
    tenant = f"bench-{int(time.time())}"
    print(f"{len(queries)} queries, concurrency {args.concurrency}, upstream={upstream}, config={cfg}")

    print("pass 1/2: direct (cache bypass) ...")
    direct = await run_pass(args.url, queries, args.concurrency, bypass=True, tenant=tenant)

    async with httpx.AsyncClient(base_url=args.url) as c:
        await c.delete("/cache")
    print("pass 2/2: semantic cache proxy ...")
    proxy = await run_pass(args.url, queries, args.concurrency, bypass=False, tenant=tenant)

    text_to_group = {q.text: q.group for q in queries}
    hits = [r for r in proxy if r["source"] == "CACHE_HIT"]
    misses = [r for r in proxy if r["source"] != "CACHE_HIT"]
    correct = [r for r in hits if text_to_group.get(r["matched_query"]) == r["query"].group]
    false_hits = [r for r in hits if r not in correct]
    paraphrases = [r for r in proxy if r["query"].kind == "paraphrase"]
    para_hit = [r for r in paraphrases if r["source"] == "CACHE_HIT" and r in correct]

    # Direct pays for every request; the proxy pays only for misses.
    direct_tokens = sum(r["usage"]["total_tokens"] for r in direct)
    proxy_tokens = sum(r["usage"]["total_tokens"] for r in misses)
    direct_cost = sum(cost_usd(r["usage"], args.input_price, args.output_price) for r in direct)
    proxy_cost = sum(cost_usd(r["usage"], args.input_price, args.output_price) for r in misses)

    summary = {
        "requests": len(queries),
        "concurrency": args.concurrency,
        "upstream": upstream,
        "proxy_config": cfg,
        "latency_ms": {
            "direct": pct([r["wall_ms"] for r in direct]),
            "proxy_all": pct([r["wall_ms"] for r in proxy]),
            "proxy_hits": pct([r["wall_ms"] for r in hits]) if hits else None,
            "proxy_hits_server_side": pct([r["latency_ms"] for r in hits]) if hits else None,
            "proxy_misses": pct([r["wall_ms"] for r in misses]),
        },
        "cache": {
            "hits": len(hits),
            "hit_rate": len(hits) / len(proxy),
            "correct_hits": len(correct),
            "false_hits": len(false_hits),
            "precision": len(correct) / len(hits) if hits else None,
            "paraphrase_recall": len(para_hit) / len(paraphrases),
            "false_hit_examples": [
                {"query": r["query"].text, "served": r["matched_query"], "score": r["similarity_score"]}
                for r in false_hits
            ],
        },
        "cost": {
            "pricing_usd_per_1m": {"input": args.input_price, "output": args.output_price},
            "direct_tokens": direct_tokens,
            "proxy_tokens": proxy_tokens,
            "token_reduction": 1 - proxy_tokens / direct_tokens,
            "direct_usd": direct_cost,
            "proxy_usd": proxy_cost,
            "cost_reduction": 1 - proxy_cost / direct_cost,
        },
    }

    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark_results.json").write_text(json.dumps(summary, indent=2))
    lat = summary["latency_ms"]
    charts.latency_percentiles(lat["direct"], lat["proxy_all"], lat["proxy_hits"] or {"p50": 0, "p95": 0, "p99": 0},
                               out / "latency_percentiles.png")
    charts.latency_cdf([r["wall_ms"] for r in direct], [r["wall_ms"] for r in proxy], out / "latency_cdf.png")
    charts.cost(direct_cost, proxy_cost, direct_tokens, proxy_tokens, out / "cost.png")

    print(json.dumps({k: summary[k] for k in ("latency_ms", "cache", "cost")}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
