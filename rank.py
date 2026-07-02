#!/usr/bin/env python3
"""
rank.py — Produce the top-100 submission CSV from candidates.jsonl.

    python rank.py --candidates ./data/candidates.jsonl --out ./submission.csv

Constraints honored: CPU-only, no network, deterministic (byte-identical output),
streams the 100k pool, and (with shipped artifacts) completes well under 5 minutes.

The embedding matrix in artifacts/ is precomputed OFFLINE by precompute_embeddings.py;
this ranking step only loads it and does cosine — no model inference, no network.
Use --no-semantic for the pure-rules fallback (still valid, slightly lower recall).
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time

from src import jd_config as cfg
from src import loader, scorer, reasoning
from src import semantic as semmod

TOP_N = 100


def main(argv=None):
    ap = argparse.ArgumentParser(description="TalentRank ranker")
    ap.add_argument("--candidates", required=True, help="path to candidates.jsonl(.gz)")
    ap.add_argument("--out", required=True, help="output submission CSV path")
    # Semantic embeddings are OFF by default: we measured that cosine similarity to
    # JD concept sentences rewards buzzword-heavy text and penalizes the plain-language
    # stars this challenge is built around — the opposite of what we want. Kept as an
    # opt-in experiment (--semantic) only. See README "what we did NOT use".
    ap.add_argument("--semantic", action="store_true",
                    help="(experimental, not recommended) enable the embedding booster")
    ap.add_argument("--reference-date", default=cfg.REFERENCE_DATE)
    # Every run also writes an .xlsx mirror of the CSV. The portal asks for BOTH the .csv
    # and the .xlsx, so we always produce both. Use --no-xlsx to skip it (e.g. a minimal
    # Stage-3 reproduction env that only needs the CSV).
    ap.add_argument("--no-xlsx", action="store_true",
                    help="skip writing the .xlsx (CSV only)")
    ap.add_argument("--xlsx", default=None,
                    help="explicit .xlsx output path (default: alongside the CSV)")
    args = ap.parse_args(argv)

    loader.set_reference_date(args.reference_date)

    t0 = time.time()
    sem = semmod.load() if args.semantic else None
    if sem is not None:
        print(f"[semantic] loaded {sem.emb.shape[0]} embeddings (dim {sem.emb.shape[1]})",
              file=sys.stderr)
    else:
        print("[semantic] no artifacts / disabled -> pure-rules ranking", file=sys.stderr)

    scored = []
    honeypots_flagged = 0
    n = 0
    for c in loader.iter_candidates(args.candidates):
        n += 1
        s = scorer.score_candidate(c, sem)
        if s.is_honeypot:
            honeypots_flagged += 1
            continue  # never eligible for the top 100
        scored.append(s)

    scored.sort(key=scorer.rank_key)
    top = scored[:TOP_N]

    # Belt-and-suspenders: assert no flagged honeypot slipped through.
    assert not any(s.is_honeypot for s in top), "honeypot reached the top 100"

    # Enforce strictly non-increasing scores by rank (validator requirement) while
    # keeping the model's ordering. If a later rank has an equal-or-higher rounded
    # score, nudge it down by an epsilon so the CSV is monotone and tie-breaks hold.
    rows = []
    prev = None
    for rank, s in enumerate(top, start=1):
        score_val = s.final
        if prev is not None and score_val >= prev:
            score_val = max(0.0, prev - 1e-6)
        prev = score_val
        reason = reasoning.generate(s, rank - 1)
        rows.append((s.cid, rank, f"{score_val:.6f}", reason))

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["candidate_id", "rank", "score", "reasoning"])
        for cid, rank, score_s, reason in rows:
            w.writerow([cid, rank, score_s, reason])

    # Also write the .xlsx (default on) — the portal asks for both .csv and .xlsx. Kept
    # non-fatal: a missing openpyxl or write error must never invalidate the CSV.
    if not args.no_xlsx:
        xlsx_path = args.xlsx or re.sub(r"\.csv$", "", args.out) + ".xlsx"
        try:
            from make_xlsx import write_xlsx
            nx = write_xlsx(args.out, xlsx_path)
            print(f"[xlsx] wrote {nx} rows to {xlsx_path} (submit this alongside the .csv)",
                  file=sys.stderr)
        except Exception as e:  # openpyxl missing, disk error, etc. — CSV is still valid.
            print(f"[xlsx] skipped ({type(e).__name__}: {e}); the .csv is unaffected",
                  file=sys.stderr)

    dt = time.time() - t0
    print(f"[done] ranked {n} candidates, flagged {honeypots_flagged} honeypots, "
          f"wrote {len(rows)} rows to {args.out} in {dt:.1f}s", file=sys.stderr)
    # Quick top-5 peek to stderr for sanity.
    for cid, rank, score_s, reason in rows[:5]:
        print(f"  #{rank} {cid} {score_s}  {reason[:90]}", file=sys.stderr)


if __name__ == "__main__":
    main()
