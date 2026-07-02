"""
gates.py — Hard deal-breakers the JD says it "actually applies".

A gate returns a multiplier applied to the whole score. It is checked over the
ENTIRE career, never a single row — the JD is explicit that "only worked at
consulting firms ... in their entire career" is the disqualifier, and that
"currently at one of these companies but have prior product-company experience,
that's fine."
"""
from __future__ import annotations

from dataclasses import dataclass

from . import jd_config as cfg
from .loader import Candidate


@dataclass
class GateVerdict:
    multiplier: float
    reason: str  # empty string if the candidate passes clean


def _is_consultancy_job(company: str, industry: str) -> bool:
    comp = company.lower().strip()
    ind = industry.lower().strip()
    if comp in cfg.CONSULTANCY_COMPANIES:
        return True
    # Industry alone is weak (many product cos are "IT Services"); require it to
    # pair with a non-product-looking company. Company match is the reliable signal.
    return False


def _looks_academic(company: str, title: str) -> bool:
    c = company.lower()
    t = title.lower()
    if any(tok in c for tok in cfg.ACADEMIC_TOKENS):
        return True
    if any(tok in t for tok in cfg.ACADEMIC_TITLES):
        return True
    return False


def evaluate(c: Candidate) -> GateVerdict:
    # --- Gate A: outside India ---------------------------------------------
    # JD: "Located in or willing to relocate to Noida or Pune." / "Outside India:
    # case-by-case, but we don't sponsor work visas."
    if c.country and c.country.lower() not in cfg.INDIA_NAMES:
        relocate = bool(c.signals.get("willing_to_relocate", False))
        if not relocate:
            return GateVerdict(
                cfg.GATE_MULTIPLIER,
                f"based in {c.country} and not willing to relocate to India",
            )
        # Willing to relocate from abroad: allowed but visa caveat -> soft demote.
        soft = cfg.SOFT_ABROAD_RELOCATE
    else:
        soft = 1.0

    # --- Gate B: consultancy-only entire career -----------------------------
    if c.jobs:
        consult_flags = [_is_consultancy_job(j.company, j.industry) for j in c.jobs]
        if all(consult_flags):
            return GateVerdict(
                cfg.GATE_MULTIPLIER,
                "entire career at IT-services/consulting firms with no product-company experience",
            )

    # --- Gate C: pure academic / research-only with no production ------------
    if c.jobs:
        academic_flags = [_looks_academic(j.company, j.title) for j in c.jobs]
        if all(academic_flags) and len(academic_flags) >= 1:
            text = c.all_description_text.lower()
            has_production = any(tok in text for tok in cfg.PRODUCTION_TOKENS)
            if not has_production:
                return GateVerdict(
                    cfg.GATE_MULTIPLIER,
                    "pure research/academic career with no evidence of production deployment",
                )

    # Passed all gates (possibly with a soft abroad-relocate demote).
    reason = "" if soft == 1.0 else f"based in {c.country} but willing to relocate (visa caveat)"
    return GateVerdict(soft, reason)
