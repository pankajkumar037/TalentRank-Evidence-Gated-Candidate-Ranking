#!/usr/bin/env python3
"""
extract_bundle.py — Pull candidates.jsonl out of the challenge zip into ./data/.

The organizers ship the pool as candidates.jsonl (or candidates.jsonl.gz). This
convenience script locates the bundle zip in the parent folder and extracts the
candidate file plus the support files (validator, sample, schema) into ./data/.

    python extract_bundle.py
"""
from __future__ import annotations

import glob
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WANT = (
    "candidates.jsonl", "candidates.jsonl.gz", "validate_submission.py",
    "sample_candidates.json", "sample_submission.csv", "candidate_schema.json",
    "submission_metadata_template.yaml",
)


def main():
    os.makedirs(DATA, exist_ok=True)
    candidates_zip = glob.glob(os.path.join(HERE, "..", "*India_runs*challenge*.zip"))
    candidates_zip += glob.glob(os.path.join(HERE, "*.zip"))
    if not candidates_zip:
        print("Could not find the challenge zip next to this script.", file=sys.stderr)
        sys.exit(1)
    zip_path = candidates_zip[0]
    print(f"[extract] using {zip_path}", file=sys.stderr)
    with zipfile.ZipFile(zip_path) as z:
        for entry in z.namelist():
            base = os.path.basename(entry)
            if base in WANT and not entry.startswith("__MACOSX"):
                dest = os.path.join(DATA, base)
                with z.open(entry) as src, open(dest, "wb") as out:
                    out.write(src.read())
                print(f"[extract] -> data/{base}", file=sys.stderr)
    print("[extract] done.", file=sys.stderr)


if __name__ == "__main__":
    main()
