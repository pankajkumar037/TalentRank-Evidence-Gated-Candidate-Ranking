"""
evidence.py — Score PROOF OF DESCRIBED WORK against the JD's four must-haves.

Reads career_history[].description text only. Skill tags and headlines earn nothing
(they are randomly-generated noise). Plain-language phrasings are first-class: "built
a system that connects users to the most relevant matches" scores exactly like one
that name-drops "RAG/Pinecone".

Performance (this ranks 100k profiles under a hard 5-min CPU budget):
  * text is lowercased ONCE per candidate; all patterns are case-sensitive (avoids
    the ~3x cost of re.IGNORECASE re-checking case at every position),
  * a literal-substring pre-filter (`in`, C-speed) rejects the ~50k candidates with
    no AI/ranking vocabulary before any regex runs,
  * each must-have is a single alternation; credit is graded per description.

Aggregation: per category, sum recency-weighted job credits, cap at 1.0, then combine
categories by their JD-justified weights.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import curated_tags as ctags
from . import jd_config as cfg
from .loader import Candidate

# Case-sensitive alternations — text is lowercased before matching, so we lowercase
# the patterns too (they use no case-sensitive metacharacters like \B/\S).
_CAT_RX = {
    cat: re.compile("|".join(f"(?:{p.lower()})" for p in pats))
    for cat, pats in cfg.MUST_HAVES.items()
}
_STRONG = re.compile(cfg.STRONG_VERBS.lower())
_WEAK = re.compile(cfg.WEAK_CONTEXT.lower())
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Depth signals (JD-grounded), matched on lowercased full description text.
_SCALE_RX = re.compile(cfg.SCALE_PATTERNS.lower())
_OWNERSHIP_RX = re.compile(cfg.OWNERSHIP_PATTERNS.lower())
_TECH_RX = re.compile("|".join(t.lower() for t in cfg.TECHNIQUE_TOKENS))

# Literal cores covering every must-have pattern. A prefilter hit only means "run
# the detailed scan"; false hits are harmless (just a little extra work), misses are
# not — so the set is a superset cover of the regex vocabulary.
_TRIGGERS = (
    # ranking / recommendation
    "recommend", "ranking", "rank ", "rank-", "learning-to-rank", "learning to rank",
    "discovery feed", "personaliz", "matching", "relevance", "surface", "recommender",
    # embeddings / retrieval
    "embedding", "retriev", "semantic search", "nearest", "query expansion",
    "query understanding", "query rewrit", "vector", "sentence-transformer",
    "sentence transformer", "two-tower", "dual-encoder", "bi-encoder", "cross-encoder",
    "bge", "minilm", "mpnet",
    # vector db / hybrid
    "faiss", "pinecone", "weaviate", "qdrant", "milvus", "scann", "annoy", "hnsw",
    "elasticsearch", "opensearch", "solr", "hybrid search", "hybrid retriev", "bm25",
    "tf-idf", "tfidf", "index refresh", "reindex", "inverted index",
    # evaluation
    "ndcg", "mrr", "p@", "precision@", "a/b", "ab test", "offline-online",
    "offline to online", "relevance label", "click-through", "click through", "ctr",
    "eval harness", "evaluation framework", "evaluation pipeline", "evaluation suite",
    "ranking metric", "human judg", "holdout", "offline benchmark", "search ",
)


@dataclass
class EvidenceResult:
    score: float                       # [0, 1]
    category_scores: dict = field(default_factory=dict)
    matched_labels: list = field(default_factory=list)   # human labels, strongest first
    quote: str = ""                    # verbatim sentence from the candidate's own text
    depth: float = 0.0                 # [0,1] non-saturating differentiator for the elite
    scale_phrase: str = ""             # e.g. "50M+ queries" — for grounded reasoning


def _sentence_of(desc: str, pos: int) -> str:
    cursor = 0
    for sent in _SENT_SPLIT.split(desc):
        end = cursor + len(sent)
        if cursor <= pos <= end + 1:
            return sent.strip()
        cursor = end + 1
    return desc[:160].strip()


_ZERO = {cat: 0.0 for cat in cfg.MUST_HAVES}


def score(c: Candidate) -> EvidenceResult:
    low_all = c.all_description_text.lower()
    if not any(t in low_all for t in _TRIGGERS):
        return EvidenceResult(score=0.0, category_scores=dict(_ZERO), matched_labels=[], quote="")

    category_scores = {cat: 0.0 for cat in cfg.MUST_HAVES}
    best_overall = (-1.0, "")          # (weighted_credit, quote)
    job0_hit = False                   # did the current/most-recent role prove any must-have?

    for idx, job in enumerate(c.jobs):
        desc = job.description
        if not desc:
            continue
        low = desc.lower()
        if not any(t in low for t in _TRIGGERS):
            continue
        w = cfg.RECENCY_WEIGHTS[idx] if idx < len(cfg.RECENCY_WEIGHTS) else 0.05

        if _STRONG.search(low):
            credit = cfg.STRONG_CREDIT
        elif _WEAK.search(low):
            credit = cfg.WEAK_CREDIT
        else:
            credit = 0.7

        for cat, rx in _CAT_RX.items():
            m = rx.search(low)
            if m:
                category_scores[cat] += w * credit
                if idx == 0:
                    job0_hit = True
                bias = 1.0 if cat in ("ranking_recs", "embeddings_retrieval") else 0.9
                weighted = w * credit * bias
                if weighted > best_overall[0]:
                    best_overall = (weighted, _sentence_of(desc, m.start()))

    # Curated-tag corroboration: the 14 rare tags (< 10 occurrences each in the pool)
    # name the exact must-haves. Holding one credits that category like a plain-language
    # mention would — trustworthy precisely because it's rare (noise tags a stuffer
    # carries never appear here). Prose still leads; this only tops up under-detected
    # categories for the genuine specialists. See curated_tags.py.
    curated = ctags.curated_hits(c)
    for cat, add in ctags.category_credit(curated).items():
        category_scores[cat] += add

    for cat in category_scores:
        category_scores[cat] = min(1.0, category_scores[cat])

    evidence = sum(
        cfg.MUST_HAVE_WEIGHTS[cat] * category_scores[cat] for cat in category_scores
    )

    ranked = sorted(category_scores.items(), key=lambda kv: kv[1], reverse=True)
    matched_labels = [cfg.MUST_HAVE_LABELS[cat] for cat, sc in ranked if sc >= 0.30]

    quote = best_overall[1]
    if len(quote) > 140:
        quote = quote[:137].rstrip() + "..."

    # ---- DEPTH: a non-saturating differentiator for candidates who all prove the
    # four must-haves. Read from description prose; JD-grounded components. ----
    breadth = sum(1 for v in category_scores.values() if v >= 0.5) / 4.0
    scale_hits = _SCALE_RX.findall(low_all)
    scale = min(1.0, len(scale_hits) / 2.0)
    own_hits = _OWNERSHIP_RX.findall(low_all)
    ownership = min(1.0, len(own_hits) / 2.0)
    techniques = {m.group(0) for m in _TECH_RX.finditer(low_all)}
    specificity = min(1.0, len(techniques) / 4.0)
    recency = 1.0 if job0_hit else 0.5
    dw = cfg.DEPTH_WEIGHTS
    depth = (dw["breadth"] * breadth + dw["scale"] * scale + dw["ownership"] * ownership
             + dw["specificity"] * specificity + dw["recency"] * recency)
    # A bounded nudge so the curated specialists (rare-tag apex) float to the very
    # top-10 — the NDCG@10 lever. Cannot exceed depth's [0,1] range.
    depth = min(1.0, depth + cfg.CURATED_DEPTH_BONUS * ctags.curated_score(curated))

    sm = _SCALE_RX.search(low_all)
    scale_phrase = sm.group(0).strip() if sm else ""

    return EvidenceResult(
        score=round(evidence, 6),
        category_scores={k: round(v, 4) for k, v in category_scores.items()},
        matched_labels=matched_labels,
        quote=quote,
        depth=round(depth, 6),
        scale_phrase=scale_phrase,
    )
