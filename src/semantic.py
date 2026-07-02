"""
semantic.py — Offline-precomputed embedding booster.

The ranking step does NO model inference and NO network I/O: it loads a precomputed
candidate-embedding matrix (built offline by precompute_embeddings.py, shipped in
artifacts/) plus a tiny set of JD concept vectors, and computes cosine similarity.

The result is a *bounded booster* on the quality score: it can only lift candidates
that already carry real evidence (>= SEMANTIC_MIN_EVIDENCE). It can never rescue a
gated, honeypot, or no-evidence profile, and explanations never cite it (they cite
the candidate's own sentence), so it cannot introduce hallucination.

If the artifacts are absent, the booster is a no-op (pure-rules fallback still ranks
and validates) — see rank.py --no-semantic.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

from . import jd_config as cfg

ARTIFACT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "artifacts")
EMB_PATH = os.path.join(ARTIFACT_DIR, "embeddings.npy")
IDS_PATH = os.path.join(ARTIFACT_DIR, "ids.npy")
CONCEPT_PATH = os.path.join(ARTIFACT_DIR, "jd_concepts.npy")


@dataclass
class SemanticIndex:
    id_to_row: dict
    emb: np.ndarray            # (N, d) L2-normalized float32
    concept: np.ndarray        # (d,) L2-normalized mean of JD concept vectors

    def similarity(self, cid: str) -> float:
        row = self.id_to_row.get(cid)
        if row is None:
            return 0.0
        # cosine in [-1, 1]; clamp negatives to 0 (irrelevant text shouldn't help).
        return float(max(0.0, np.dot(self.emb[row], self.concept)))


def load() -> "SemanticIndex | None":
    if not (os.path.exists(EMB_PATH) and os.path.exists(IDS_PATH) and os.path.exists(CONCEPT_PATH)):
        return None
    emb = np.load(EMB_PATH).astype(np.float32)
    ids = np.load(IDS_PATH, allow_pickle=True)
    concepts = np.load(CONCEPT_PATH).astype(np.float32)  # (k, d)
    # L2-normalize rows (idempotent if already normalized).
    emb /= (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)
    concept = concepts.mean(axis=0)
    concept /= (np.linalg.norm(concept) + 1e-9)
    id_to_row = {str(cid): i for i, cid in enumerate(ids)}
    return SemanticIndex(id_to_row=id_to_row, emb=emb, concept=concept)


def build_inmemory(candidates, texts) -> "SemanticIndex | None":
    """Build a semantic index on the fly for a SMALL sample (used by the sandbox app,
    <=100 candidates). Loads the model lazily; returns None if unavailable so the app
    degrades to pure-rules."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    model = SentenceTransformer(cfg.EMBED_MODEL, device="cpu")
    model.eval()
    emb = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True).astype(np.float32)
    concepts = model.encode(cfg.JD_CONCEPT_SENTENCES, convert_to_numpy=True,
                            normalize_embeddings=True).astype(np.float32)
    concept = concepts.mean(axis=0)
    concept /= (np.linalg.norm(concept) + 1e-9)
    id_to_row = {c.cid: i for i, c in enumerate(candidates)}
    return SemanticIndex(id_to_row=id_to_row, emb=emb, concept=concept)


def boost_factor(sim: float, evidence: float) -> float:
    """Map a cosine similarity to a multiplicative uplift on quality.

    Returns a factor in [1.0, 1 + SEMANTIC_MAX_BOOST]. No uplift when the candidate
    lacks real evidence (nothing genuine to lift). Similarity is remapped so only
    genuinely on-topic text (cosine >~0.25) earns meaningful boost.
    """
    if evidence < cfg.SEMANTIC_MIN_EVIDENCE:
        return 1.0
    # remap cosine 0.25..0.65 -> 0..1
    scaled = (sim - 0.25) / (0.65 - 0.25)
    scaled = max(0.0, min(1.0, scaled))
    return 1.0 + cfg.SEMANTIC_MAX_BOOST * scaled
