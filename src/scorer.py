"""
scorer.py — Compose the final score:  final = gate x quality x availability.

    quality   = (0.70 * evidence + 0.30 * fit) * semantic_boost   (capped at 1.0)
    gate      = hard deal-breaker multiplier (near-zero if gated)
    availability = behavioral multiplier in [0.55, 1.0]

Honeypots are removed from contention entirely (score forced to 0 and flagged),
and rank.py asserts none survive into the top 100.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import availability as availmod
from . import evidence as evmod
from . import fit as fitmod
from . import gates as gatemod
from . import honeypot as hpmod
from . import jd_config as cfg
from . import semantic as semmod
from .loader import Candidate


@dataclass
class Scored:
    cid: str
    final: float
    quality: float
    gate_mult: float
    gate_reason: str
    avail_mult: float
    evidence: evmod.EvidenceResult
    fit: fitmod.FitResult
    avail: availmod.AvailabilityResult
    semantic_sim: float = 0.0
    is_honeypot: bool = False
    honeypot_reasons: list = field(default_factory=list)
    candidate: Candidate = None


_EMPTY_EV = evmod.EvidenceResult(score=0.0, category_scores={}, matched_labels=[], quote="")


def score_candidate(c: Candidate, sem: "semmod.SemanticIndex | None") -> Scored:
    hp = hpmod.check(c)
    gate = gatemod.evaluate(c)
    av = availmod.compute(c)

    # Fast path: a honeypot or a hard-gated candidate can never reach the top 100
    # (≈66k candidates pass clean), so skip the expensive evidence/fit/semantic work.
    hard_gated = gate.multiplier <= cfg.GATE_MULTIPLIER
    if hp.is_honeypot or hard_gated:
        final = 0.0 if hp.is_honeypot else gate.multiplier * av.multiplier * 0.1
        return Scored(
            cid=c.cid, final=round(final, 6), quality=0.0,
            gate_mult=gate.multiplier, gate_reason=gate.reason, avail_mult=av.multiplier,
            evidence=_EMPTY_EV, fit=fitmod.FitResult(score=0.0), avail=av,
            is_honeypot=hp.is_honeypot, honeypot_reasons=hp.reasons, candidate=c,
        )

    ev = evmod.score(c)
    ft = fitmod.score(c)

    sim = sem.similarity(c.cid) if sem is not None else 0.0
    boost = semmod.boost_factor(sim, ev.score) if sem is not None else 1.0

    quality = (cfg.QUALITY_EVIDENCE_WEIGHT * ev.score
               + cfg.QUALITY_DEPTH_WEIGHT * ev.depth
               + cfg.QUALITY_FIT_WEIGHT * ft.score)
    quality = min(1.0, quality * boost)

    final = gate.multiplier * quality * av.multiplier

    return Scored(
        cid=c.cid,
        final=round(final, 6),
        quality=round(quality, 6),
        gate_mult=gate.multiplier,
        gate_reason=gate.reason,
        avail_mult=av.multiplier,
        evidence=ev,
        fit=ft,
        avail=av,
        semantic_sim=round(sim, 4),
        is_honeypot=hp.is_honeypot,
        honeypot_reasons=hp.reasons,
        candidate=c,
    )


def rank_key(s: Scored):
    """Sort key: score desc, then candidate_id ascending (validator tie-break rule)."""
    return (-s.final, s.cid)
