"""
fit.py — Non-evidence fit signals and the JD's explicitly-named penalties.

Produces a fit score in [0, 1] plus a list of penalty reasons (for reasoning) and
concern strings. Nothing here hard-filters — the JD says the year band is "a range,
not a requirement", so experience is a soft curve with a floor.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import jd_config as cfg
from .loader import Candidate

# All patterns are lowercase and matched against lowercased text (no re.I overhead).
_ML_TITLE = re.compile("|".join(re.escape(t.lower()) for t in cfg.ML_TITLE_TOKENS))
_WRONG_DOMAIN = re.compile("|".join(t.lower() for t in cfg.WRONG_DOMAIN_TOKENS))
_NLP_IR = re.compile("|".join(t.lower() for t in cfg.NLP_IR_TOKENS))
_LLM_WRAP = re.compile("|".join(re.escape(t.lower()) for t in cfg.LLM_WRAPPER_TOKENS))
_PRE_LLM = re.compile("|".join(re.escape(t.lower()) for t in cfg.PRE_LLM_ML_TOKENS))
_HANDS_ON = re.compile(
    r"(built|coded|implemented|wrote|developed|designed|trained|deployed|shipped|"
    r"programmed|engineered)")
_MANAGER_ONLY = re.compile(
    r"(managed a team|led a team of|people management|headcount|stakeholder|"
    r"roadmap ownership|hiring plan)")


@dataclass
class FitResult:
    score: float
    penalties: list = field(default_factory=list)   # (name, multiplier, reason)
    concerns: list = field(default_factory=list)    # human-readable concern strings
    ml_years_product: float = 0.0


def _experience_curve(years: float) -> float:
    """Gentle asymmetric gaussian peaking at the JD ideal, floored (never zero)."""
    ideal = cfg.EXPERIENCE_IDEAL
    sigma = cfg.EXPERIENCE_SIGMA_LOW if years < ideal else cfg.EXPERIENCE_SIGMA_HIGH
    g = math.exp(-((years - ideal) ** 2) / (2 * sigma * sigma))
    return cfg.EXPERIENCE_FLOOR + (1.0 - cfg.EXPERIENCE_FLOOR) * g


def _is_product_company(company: str) -> bool:
    c = company.lower().strip()
    if c in cfg.CONSULTANCY_COMPANIES:
        return False
    return True  # default: treat non-consultancy as product-ish


def _ml_years_at_product(c: Candidate) -> float:
    months = 0
    for j in c.jobs:
        if _ML_TITLE.search(j.title.lower()) and _is_product_company(j.company):
            months += j.duration_months
    return months / 12.0


def _location_bonus(c: Candidate) -> float:
    """Soft location alignment (never a gate). JD: offices in Noida/Pune; Hyderabad,
    Mumbai, Delhi-NCR, Bengaluru explicitly welcomed."""
    loc = (c.location or "").lower()
    if any(t in loc for t in cfg.LOCATION_PRIMARY):
        return cfg.LOCATION_PRIMARY_BONUS
    if any(t in loc for t in cfg.LOCATION_WELCOME):
        return cfg.LOCATION_WELCOME_BONUS
    if (c.country or "").lower() in cfg.INDIA_NAMES:
        return cfg.LOCATION_OTHER_INDIA_BONUS
    return 0.80  # abroad (already soft-gated elsewhere); mild extra caution


def _seniority_alignment(c: Candidate) -> float:
    """Small nudge UP for titles matching 'Senior AI Engineer'; never a hard penalty."""
    t = c.current_title.lower()
    eng = any(tok in t for tok in cfg.ENGINEER_TITLE_TOKENS)
    sen = any(tok in t for tok in cfg.SENIORITY_TOKENS)
    if eng and sen:
        return 1.0
    if eng:
        return 0.85
    if sen:
        return 0.60
    return 0.65


def score(c: Candidate) -> FitResult:
    res = FitResult(score=0.0)

    exp = _experience_curve(c.years_experience)

    ml_years = _ml_years_at_product(c)
    res.ml_years_product = round(ml_years, 1)
    # JD ideal: "4-5 [years] in applied ML/AI roles at product companies". Saturate ~5.
    ml_component = min(1.0, ml_years / 5.0)

    # Hands-on in the current/most-recent role. JD: "This role writes code."
    hands_on = 0.5
    if c.jobs:
        cur = c.jobs[0].description.lower()
        if _HANDS_ON.search(cur):
            hands_on = 1.0
        elif _MANAGER_ONLY.search(cur) and not _HANDS_ON.search(cur):
            hands_on = 0.3
            res.concerns.append("recent role reads as management-heavy; JD wants hands-on coding")

    location = _location_bonus(c)
    seniority = _seniority_alignment(c)

    base = (0.38 * exp + 0.34 * ml_component + 0.12 * hands_on
            + 0.10 * location + 0.06 * seniority)
    res.score = base

    # ---- Penalties (each explicitly named in the JD) -----------------------
    text = c.all_description_text.lower()

    # Job hopper / title chaser: several short stints.
    short_stints = sum(
        1 for j in c.jobs if 0 < j.duration_months < cfg.JOB_HOP_MONTHS and not j.is_current
    )
    if short_stints >= cfg.JOB_HOP_MIN_STINTS:
        res.penalties.append(("job_hopper", cfg.PENALTY_JOB_HOPPER,
                              f"{short_stints} stints under {cfg.JOB_HOP_MONTHS} months"))
        res.concerns.append(f"job-hopping pattern ({short_stints} short stints)")

    # LLM-wrapper-only: recent LangChain/OpenAI work with no pre-LLM ML depth.
    if _LLM_WRAP.search(text) and not _PRE_LLM.search(text):
        res.penalties.append(("llm_wrapper", cfg.PENALTY_LLM_WRAPPER,
                              "AI experience is LLM-API wrapping without pre-LLM ML depth"))
        res.concerns.append("AI experience looks LLM-API-wrapper heavy without deeper ML")

    # Wrong domain: CV/speech/robotics dominant without NLP/IR exposure. The
    # expensive findall only runs when a wrong-domain term is present AND no NLP/IR
    # term is (both cheap search()es first) — true for very few candidates.
    if _WRONG_DOMAIN.search(text) and not _NLP_IR.search(text):
        if len(_WRONG_DOMAIN.findall(text)) >= 2:
            res.penalties.append(("wrong_domain", cfg.PENALTY_WRONG_DOMAIN,
                                  "primary domain is CV/speech/robotics without NLP/IR"))
            res.concerns.append("core domain is CV/speech/robotics, not NLP/IR")

    for _name, mult, _reason in res.penalties:
        res.score *= mult

    res.score = max(0.0, min(1.0, res.score))
    return res
