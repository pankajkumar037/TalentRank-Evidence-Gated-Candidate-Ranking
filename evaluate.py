#!/usr/bin/env python3
"""
evaluate.py — Estimate ranking quality against a SILVER-labeled pool.

There is no public ground truth, so we build an independent silver-label set
(src/silver_labels.py) and compute the official-style metrics on it:

    composite = 0.50*NDCG@10 + 0.30*NDCG@50 + 0.15*MAP + 0.05*P@10

We evaluate our ranker against three baselines on the SAME labeled pool:
  * skill-tag trap  — rank by count of AI-ish SKILL TAGS (the planted trap)
  * keyword matcher — rank by AI keyword hits in the profile text (naive)
  * random          — seeded shuffle
If the harness were just echoing our ranker, everything would score ~1.0; the baseline
gap is what makes the number meaningful.

IMPORTANT: this is an ESTIMATE and a regression detector, not the hidden competition
score. The ranker's weights are not tuned to this labeler.

    python evaluate.py --candidates ./data/candidates.jsonl
"""
from __future__ import annotations

import argparse
import heapq
import math
import random
import re
from collections import Counter

from src import loader, scorer, silver_labels

# AI-ish skill tags (for the "trap" baseline — the thing the challenge warns against).
_AI_SKILL_TAGS = {
    "machine learning", "deep learning", "nlp", "natural language processing", "llm",
    "large language models", "rag", "fine-tuning llms", "transformers", "pytorch",
    "tensorflow", "embeddings", "vector search", "recommendation", "recommendation systems",
    "ranking", "information retrieval", "computer vision", "reinforcement learning",
    "lora", "semantic search", "sentence transformers", "bert", "gpt", "hugging face",
    "mlops", "feature engineering", "xgboost", "lightgbm", "faiss", "pinecone",
}
_AI_KEYWORDS = re.compile(
    r"machine learning|deep learning|\bnlp\b|\bllm\b|\brag\b|embedding|ranking|recommend|"
    r"retriev|semantic|vector|transformer|fine-tun|pytorch|tensorflow|faiss|pinecone|"
    r"a/b|ndcg|learning to rank|search", re.I)


def skill_tag_score(c):
    return sum(1 for s in c.skills if (s.get("name") or "").lower() in _AI_SKILL_TAGS)


def keyword_score(c):
    return len(_AI_KEYWORDS.findall(c.all_description_text))


# ----------------------------- metrics -----------------------------
def _dcg(tiers):
    return sum((2 ** t - 1) / math.log2(i + 2) for i, t in enumerate(tiers))


def ndcg_at_k(ranked_tiers, all_tiers, k):
    dcg = _dcg(ranked_tiers[:k])
    ideal = _dcg(sorted(all_tiers, reverse=True)[:k])
    return dcg / ideal if ideal > 0 else 0.0


def average_precision(ranked_tiers, total_relevant, rel_threshold=3):
    if total_relevant == 0:
        return 0.0
    hits = 0
    ap = 0.0
    for i, t in enumerate(ranked_tiers, start=1):
        if t >= rel_threshold:
            hits += 1
            ap += hits / i
    return ap / min(total_relevant, len(ranked_tiers))


def precision_at_k(ranked_tiers, k, rel_threshold=3):
    top = ranked_tiers[:k]
    return sum(1 for t in top if t >= rel_threshold) / k if top else 0.0


def composite(ndcg10, ndcg50, mAP, p10):
    return 0.50 * ndcg10 + 0.30 * ndcg50 + 0.15 * mAP + 0.05 * p10


def evaluate_method(name, order, tiers_by_id, total_relevant):
    ranked_tiers = [tiers_by_id[cid] for cid in order]
    n10 = ndcg_at_k(ranked_tiers, list(tiers_by_id.values()), 10)
    n50 = ndcg_at_k(ranked_tiers, list(tiers_by_id.values()), 50)
    mAP = average_precision(ranked_tiers, total_relevant)
    p10 = precision_at_k(ranked_tiers, 10)
    comp = composite(n10, n50, mAP, p10)
    return {"method": name, "ndcg10": n10, "ndcg50": n50, "map": mAP, "p10": p10, "composite": comp}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--field-sample", type=int, default=4000)
    ap.add_argument("--top-keep", type=int, default=150)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    # Single stream: keep the ranker's top-N, a seeded random field sample, and all
    # honeypots. Each structure stores the Candidate; we union them into the pool at the end.
    top_heap = []          # min-heap of (score, cid, candidate), capped at top-keep
    reservoir = []         # reservoir sample of Candidate objects
    honeypot_cands = []
    our_score = {}
    n = 0
    for c in loader.iter_candidates(args.candidates):
        n += 1
        s = scorer.score_candidate(c, None)
        our_score[c.cid] = s.final

        if s.is_honeypot:
            honeypot_cands.append(c)

        if len(top_heap) < args.top_keep:
            heapq.heappush(top_heap, (s.final, c.cid, c))
        elif s.final > top_heap[0][0]:
            heapq.heappushpop(top_heap, (s.final, c.cid, c))

        if len(reservoir) < args.field_sample:
            reservoir.append(c)
        else:
            j = rng.randint(0, n - 1)
            if j < args.field_sample:
                reservoir[j] = c

    pool = {}
    for c in reservoir:
        pool[c.cid] = c
    for _score, cid, c in top_heap:
        pool[cid] = c
    for c in honeypot_cands:
        pool[c.cid] = c
    print(f"[eval] streamed {n} candidates; labeled pool size = {len(pool)} "
          f"(top-{args.top_keep} + field-{args.field_sample} + {len(honeypot_cands)} honeypots)",
          flush=True)

    # Silver-label the pool.
    tiers = {}
    rationale = {}
    for cid, c in pool.items():
        lab = silver_labels.label(c)
        tiers[cid] = lab.tier
        rationale[cid] = lab.rationale

    hist = Counter(tiers.values())
    total_relevant = sum(1 for t in tiers.values() if t >= 3)
    print("[eval] pool tier histogram (0..5):",
          {k: hist.get(k, 0) for k in range(6)}, f"| relevant(tier>=3)={total_relevant}")

    ids = list(pool.keys())

    def order_by(scorefn):
        return sorted(ids, key=lambda cid: (-scorefn(cid), cid))

    orders = {
        "ours (evidence-gated)": order_by(lambda cid: our_score[cid]),
        "skill-tag trap":        order_by(lambda cid: skill_tag_score(pool[cid])),
        "keyword matcher":       order_by(lambda cid: keyword_score(pool[cid])),
        "random":                sorted(ids, key=lambda cid: rng.random()),
    }

    results = [evaluate_method(name, order, tiers, total_relevant)
               for name, order in orders.items()]

    print("\n=== Estimated metrics on the silver-labeled pool "
          "(ESTIMATE, not the hidden score) ===")
    print(f"{'method':<24}{'NDCG@10':>9}{'NDCG@50':>9}{'MAP':>8}{'P@10':>8}{'composite':>11}")
    for r in results:
        print(f"{r['method']:<24}{r['ndcg10']:>9.3f}{r['ndcg50']:>9.3f}"
              f"{r['map']:>8.3f}{r['p10']:>8.3f}{r['composite']:>11.3f}")

    # Red-flag check: any low-tier candidate in OUR top-10?
    our_top10 = orders["ours (evidence-gated)"][:10]
    flags = [(cid, tiers[cid]) for cid in our_top10 if tiers[cid] <= 1]
    print(f"\n[red-flag] low-tier (<=1) candidates in our top-10: "
          f"{len(flags)} {'OK' if not flags else flags}")
    print("[our top-10 silver tiers]:", [tiers[cid] for cid in our_top10])


if __name__ == "__main__":
    main()
