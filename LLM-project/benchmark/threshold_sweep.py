"""Offline threshold sweep: replay the workload against an in-memory model of the
cache (same top-k + guard logic) for many thresholds. No server or LLM needed.

    python -m benchmark.threshold_sweep
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cache import CANDIDATES  # noqa: E402
from app.guard import entities_match  # noqa: E402
from benchmark import charts  # noqa: E402
from benchmark.dataset import build_workload  # noqa: E402

RESULTS = Path(__file__).parent / "results"


def replay(queries, vectors, threshold: float, guard: bool) -> dict:
    stored: list[int] = []  # indices of queries that missed and were cached
    correct = false = para_hits = 0
    false_examples = []
    for i, q in enumerate(queries):
        chosen = None
        if stored:
            sims = vectors[stored] @ vectors[i]
            for j in np.argsort(-sims)[:CANDIDATES]:
                if sims[j] < threshold:
                    break
                cand = queries[stored[j]]
                if guard and not entities_match(q.text, cand.text):
                    continue
                chosen = (cand, float(sims[j]))
                break
        if chosen is None:
            stored.append(i)
            continue
        cand, score = chosen
        if cand.group == q.group:
            correct += 1
            para_hits += q.kind == "paraphrase"
        else:
            false += 1
            false_examples.append({"query": q.text, "served": cand.text, "score": round(score, 4)})
    n_para = sum(q.kind == "paraphrase" for q in queries)
    return {
        "threshold": round(threshold, 3),
        "guard": guard,
        "hits": correct + false,
        "correct_hits": correct,
        "false_hits": false,
        "recall": para_hits / n_para,
        "precision": correct / (correct + false) if correct + false else 1.0,
        "false_examples": false_examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.92, help="configured threshold to highlight")
    ap.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    args = ap.parse_args()

    from fastembed import TextEmbedding

    queries = build_workload()
    emb = np.array(list(TextEmbedding(model_name=args.model).embed([q.text for q in queries])))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)

    rows = [replay(queries, emb, float(t), g) for g in (False, True) for t in np.arange(0.80, 0.991, 0.005)]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "threshold_sweep.json").write_text(json.dumps(rows, indent=2))
    charts.threshold_sweep(rows, args.threshold, RESULTS / "threshold_sweep.png")

    print(f"{'thr':>6} {'guard':>6} {'recall':>7} {'precision':>9} {'false':>6}")
    for r in rows:
        if abs(r["threshold"] * 100 - round(r["threshold"] * 100)) < 1e-6:  # print every 0.01
            print(f"{r['threshold']:>6} {str(r['guard']):>6} {r['recall']:>7.1%} {r['precision']:>9.1%} {r['false_hits']:>6}")
    for g in (False, True):
        cur = next(r for r in rows if r["guard"] == g and abs(r["threshold"] - args.threshold) < 1e-6)
        print(f"\n@{args.threshold} guard={g}: false hits:")
        for ex in cur["false_examples"]:
            print(f"  {ex['score']}  {ex['query']!r}  <- served {ex['served']!r}")


if __name__ == "__main__":
    main()
