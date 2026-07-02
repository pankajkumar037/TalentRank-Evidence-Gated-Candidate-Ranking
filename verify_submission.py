#!/usr/bin/env python3
"""
verify_submission.py — Independent checks beyond the format validator.

  * honeypot rate in the top 100 (must be 0 for us; DQ threshold is >10%),
  * reasoning variation (Stage-4 penalizes templated/identical reasoning),
  * a readable top-N dump for manual coherence review against the JD.

    python verify_submission.py --candidates ./data/candidates.jsonl --submission ./submission.csv
"""
from __future__ import annotations

import argparse
import csv

from src import loader, honeypot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--submission", required=True)
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    rows = []
    with open(args.submission, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    top_ids = {r["candidate_id"] for r in rows}
    assert len(rows) == 100, f"expected 100 rows, got {len(rows)}"

    # Pull the full records for the 100 picked ids.
    picked = {}
    for c in loader.iter_candidates(args.candidates):
        if c.cid in top_ids:
            picked[c.cid] = c
            if len(picked) == len(top_ids):
                break

    hp = [cid for cid, c in picked.items() if honeypot.check(c).is_honeypot]
    print(f"honeypots in top 100: {len(hp)}  ({len(hp)}% rate) {'OK' if not hp else 'FAIL: '+str(hp)}")

    reasonings = [r["reasoning"] for r in rows]
    uniq = len(set(reasonings))
    print(f"distinct reasoning strings: {uniq}/100 (higher is better; identical strings are penalized)")

    print(f"\n--- top {args.show} (manual coherence read) ---")
    for r in rows[: args.show]:
        c = picked.get(r["candidate_id"])
        loc = f"{c.country}" if c else "?"
        yrs = f"{c.years_experience}" if c else "?"
        title = c.current_title if c else "?"
        print(f"#{r['rank']:>3} {r['candidate_id']} score={r['score']}  [{title}, {yrs}y, {loc}]")
        print(f"      {r['reasoning']}")


if __name__ == "__main__":
    main()
