"""
reasoning.py — Assemble a 1-2 sentence explanation for each pick.

Every clause is built ONLY from facts the scorer actually used: the matched JD
must-haves, a verbatim quote from the candidate's own description, their real title
and years, and honest concerns surfaced by the fit / availability scorers. No text
generation, so nothing can be hallucinated.

Variation (Stage-4 requirement): templates rotate by rank position and the lead
facts differ per candidate, so sampled rows read as substantively different rather
than templated.
"""
from __future__ import annotations

from .scorer import Scored

# Strong-tone openers (high quality). {labels} {quote} {title} {yrs}
_STRONG = [
    "Strong on the core must-haves — {labels}{quote}; currently {title}, {yrs} yrs.",
    "{yrs} yrs as {title} with {labels}{quote} — squarely the JD's target profile.",
    "Top-tier match: {labels}{quote} over a {yrs}-yr career ({title}).",
    "Clear fit: {yrs} yrs, {title}; {labels}{quote}.",
]
# Measured-tone openers (mid quality).
_MID = [
    "Solid partial fit: {title}, {yrs} yrs, with {labels}{quote}.",
    "{yrs} yrs ({title}); shows {labels}{quote}, though not the full stack the JD asks for.",
    "Reasonable match on {labels}{quote}; {title}, {yrs} yrs.",
]
# Hedged-tone openers when SOME evidence exists but it is thin.
_WEAK = [
    "Partial fit: {title}, {yrs} yrs; only light evidence of {labels}{quote}.",
    "Below the strong-fit cutoff: {title}, {yrs} yrs; limited {labels}{quote}.",
    "Adjacent: {title}, {yrs} yrs, with just a thin {labels} signal{quote}.",
]
# Filler openers when the profile shows NO direct ranking/retrieval evidence.
# Honest by construction — claims no AI work, ranks on seniority + engagement only.
_FILLER = [
    "Filler pick — {title}, {yrs} yrs; no shipped ranking/retrieval work in the profile, ranked on seniority and platform engagement.",
    "Below the AI-fit line: {title}, {yrs} yrs; profile shows no direct AI/ranking evidence, included as list depth on experience and activity.",
    "No direct evidence of the JD's ranking/retrieval must-haves; {title}, {yrs} yrs, kept as filler on general seniority and engagement.",
]


def _labels_phrase(labels):
    if not labels:
        return "relevant applied-ML work"
    if len(labels) == 1:
        return labels[0]
    return f"{labels[0]} and {labels[1]}"


def generate(s: Scored, rank_index: int) -> str:
    c = s.candidate
    yrs = f"{c.years_experience:.0f}" if c.years_experience == int(c.years_experience) else f"{c.years_experience:.1f}"
    title = c.current_title or "candidate"
    labels = _labels_phrase(s.evidence.matched_labels)
    q = s.evidence.quote
    quote = f" ('{q}')" if q else ""

    has_evidence = bool(s.evidence.matched_labels)
    if not has_evidence:
        pool = _FILLER
    elif s.quality >= 0.55:
        pool = _STRONG
    elif s.quality >= 0.30:
        pool = _MID
    else:
        pool = _WEAK

    template = pool[rank_index % len(pool)]
    text = template.format(
        labels=labels,
        quote=quote,
        title=title,
        yrs=yrs,
    )

    # One grounded detail (rotated for variation) — all facts the scorer actually used.
    if has_evidence:
        details = []
        if s.evidence.scale_phrase:
            details.append(f"Operated at scale ({s.evidence.scale_phrase.strip()})")
        loc = (c.location or "").strip()
        if loc:
            near = any(city in loc.lower() for city in ("noida", "pune"))
            details.append(f"Based in {loc}" + (" (their Noida/Pune office region)" if near else ""))
        if s.fit.ml_years_product >= 3:
            details.append(f"~{s.fit.ml_years_product:.0f}y applied ML at product companies")
        if details:
            text += " " + details[rank_index % len(details)] + "."

    # Honest concern (first available), appended so tone matches rank.
    concerns = list(s.fit.concerns) + list(s.avail.concerns)
    if s.gate_reason:
        concerns.insert(0, s.gate_reason)
    if concerns:
        text += f" Concern: {concerns[0]}."

    # Collapse any accidental double spaces.
    return " ".join(text.split())
