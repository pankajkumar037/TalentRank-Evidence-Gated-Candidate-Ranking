#!/usr/bin/env python3
"""
precompute_embeddings.py — OFFLINE embedding precomputation (run once).

This step MAY exceed the 5-minute ranking budget (the spec allows pre-computation
outside the window). It embeds each candidate's recency-weighted career-history text
with a small local sentence-transformer and writes:

    artifacts/embeddings.npy   (N, d) float32, L2-normalized
    artifacts/ids.npy          (N,)   candidate_id strings, row-aligned
    artifacts/jd_concepts.npy  (k, d) float32 embeddings of the JD concept sentences

The ranking step (rank.py) then only loads these and does cosine — no model, no network.
Determinism: model in eval mode, fixed input text, no sampling.

    python precompute_embeddings.py --candidates ./data/candidates.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

from src import jd_config as cfg
from src import loader
from src import evidence as evmod

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")


def candidate_text(c) -> str:
    """Compact text for embedding: the current title + the two most recent job
    descriptions, capped short. The opening sentences carry the strongest signal;
    keeping sequences short is what makes CPU embedding of 100k tractable."""
    parts = []
    if c.current_title:
        parts.append(c.current_title + ".")
    for job in c.jobs[:2]:
        if job.description:
            parts.append(job.description)
    if not parts:
        parts.append(c.headline or "")
    return " ".join(parts)[:512]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--model", default=cfg.EMBED_MODEL)
    ap.add_argument("--batch-size", type=int, default=256)
    args = ap.parse_args(argv)

    from sentence_transformers import SentenceTransformer
    import torch

    torch.manual_seed(0)
    torch.set_num_threads(os.cpu_count() or 4)  # use all CPU cores
    model = SentenceTransformer(args.model, device="cpu")
    model.max_seq_length = 128                   # key sentences fit; keeps CPU tractable
    model.eval()

    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    # The booster only ever affects candidates that already carry rule-evidence
    # (>= SEMANTIC_MIN_EVIDENCE); everyone else gets no boost regardless of cosine.
    # So we embed ONLY the evidence-positive set — a few thousand, not 100k — which
    # is both far faster to precompute and semantically identical at ranking time.
    t0 = time.time()
    ids, texts = [], []
    seen = 0
    for c in loader.iter_candidates(args.candidates):
        seen += 1
        if evmod.score(c).score >= cfg.SEMANTIC_MIN_EVIDENCE:
            ids.append(c.cid)
            texts.append(candidate_text(c))
    print(f"[precompute] {len(ids)} evidence-positive of {seen} candidates "
          f"(scanned in {time.time()-t0:.1f}s)", file=sys.stderr)

    t1 = time.time()
    emb = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype(np.float32)
    print(f"[precompute] embedded in {time.time()-t1:.1f}s -> {emb.shape}", file=sys.stderr)

    concepts = model.encode(
        cfg.JD_CONCEPT_SENTENCES,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype(np.float32)

    np.save(os.path.join(ARTIFACT_DIR, "embeddings.npy"), emb)
    np.save(os.path.join(ARTIFACT_DIR, "ids.npy"), np.array(ids, dtype=object))
    np.save(os.path.join(ARTIFACT_DIR, "jd_concepts.npy"), concepts)
    print(f"[precompute] wrote artifacts to {ARTIFACT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    main()
