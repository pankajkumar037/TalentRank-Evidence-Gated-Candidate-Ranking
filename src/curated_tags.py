"""
curated_tags.py — The 14 *curated* skill tags (the only tags we trust).

We ignore skill tags by default because they are noise: profiling the 100k pool shows
63 tags each occur ~12,000 times (statistically uniform — "Machine Learning" as common
as "Photoshop"). But 14 tags occur FEWER THAN 10 TIMES each across the whole pool and
name the exact JD must-haves ("Information Retrieval Systems", "Ranking Systems",
"Vector Representations", "Text Encoders", "Model Adaptation", ...). That rarity is a
deliberate curation signal: the dataset planted them on genuine specialists. They
cluster onto ~8 candidates, every one headlined "Information Retrieval at scale".

So we trust ONLY these 14 tags, and only as *corroboration* of described work — a
keyword-stuffer carries the noise tags, never these. Each tag maps to the must-have
category it names; holding it credits that category the way a plain-language mention of
the same work would. Prose evidence still dominates (see evidence.py / scorer.py).

Measured frequencies in the released pool (all < 10):
  Document Processing 1 · Natural Language Processing 2 · Workflow Orchestration 3 ·
  Search Infrastructure 3 · Indexing Algorithms 3 · Open-source ML libraries 3 ·
  Vector Representations 4 · Content Matching 4 · Model Adaptation 4 · Ranking Systems 4 ·
  Search & Discovery 4 · Search Backend 5 · Text Encoders 5 · Information Retrieval Systems 7
"""
from __future__ import annotations

from .loader import Candidate

# tag -> the must-have category it corroborates (keys match cfg.MUST_HAVES).
# A curated tag is a rare, trustworthy claim of the exact skill it names.
CURATED_CATEGORY = {
    # ranking / recommendation / matching
    "Ranking Systems": "ranking_recs",
    "Content Matching": "ranking_recs",
    "Search & Discovery": "ranking_recs",
    # embeddings / retrieval / representation
    "Vector Representations": "embeddings_retrieval",
    "Text Encoders": "embeddings_retrieval",
    "Natural Language Processing": "embeddings_retrieval",
    "Model Adaptation": "embeddings_retrieval",       # fine-tuning / LoRA-adjacent
    "Document Processing": "embeddings_retrieval",
    # vector-db / search infrastructure
    "Information Retrieval Systems": "vector_db_hybrid",
    "Search Infrastructure": "vector_db_hybrid",
    "Search Backend": "vector_db_hybrid",
    "Indexing Algorithms": "vector_db_hybrid",
    "Workflow Orchestration": "vector_db_hybrid",     # search/serving infra plumbing
    # general specialist tooling (counts toward depth, not a single category)
    "Open-source ML libraries": None,
}

CURATED_TAGS = frozenset(CURATED_CATEGORY)

# Per-tag credit added to the named must-have category (capped at 1.0 per category in
# evidence.py). Two curated tags in one category -> full credit for that category.
CURATED_TAG_CREDIT = 0.5


def curated_hits(c: Candidate) -> list:
    """The curated tags this candidate holds (raw skill dicts already on Candidate)."""
    out = []
    for s in c.skills:
        name = s.get("name") if isinstance(s, dict) else None
        if name in CURATED_TAGS:
            out.append(name)
    return out


def category_credit(hits: list) -> dict:
    """Map curated tags -> {must-have category: credit in [0,1]} (pre-cap contribution)."""
    credit = {}
    for name in hits:
        cat = CURATED_CATEGORY.get(name)
        if cat:
            credit[cat] = credit.get(cat, 0.0) + CURATED_TAG_CREDIT
    return credit


def curated_score(hits: list) -> float:
    """Overall corroboration strength in [0,1] (count-based; 4+ curated tags saturate).

    Used as a depth/ordering nudge so the apex specialists float to the very top-10.
    """
    return min(1.0, len(hits) / 4.0)
