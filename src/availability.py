"""
availability.py — Behavioral availability multiplier in [0.55, 1.0].

JD: "a perfect-on-paper candidate who hasn't logged in for 6 months and has a 5%
recruiter response rate is, for hiring purposes, not actually available. Down-weight
them appropriately." The multiplier can demote a ghost but NEVER erase a strong fit.

Sentinel-safe: github_activity_score and offer_acceptance_rate use -1 to mean
"no data" — that must count as neutral, not as a bad score. We also ignore the
signup>last_active artifact entirely (7,496 profiles; acknowledged generation quirk).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from . import jd_config as cfg
from .loader import Candidate

_REF = datetime.date.fromisoformat(cfg.REFERENCE_DATE)


@dataclass
class AvailabilityResult:
    multiplier: float
    parts: dict = field(default_factory=dict)
    concerns: list = field(default_factory=list)


def _parse(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _recency_score(last_active) -> float:
    d = _parse(last_active)
    if d is None:
        return 0.6  # unknown -> neutral-ish
    days = (_REF - d).days
    if days <= cfg.RECENCY_FULL_DAYS:
        return 1.0
    if days >= cfg.RECENCY_DEAD_DAYS:
        return 0.0
    # linear decay between full and dead
    return 1.0 - (days - cfg.RECENCY_FULL_DAYS) / (cfg.RECENCY_DEAD_DAYS - cfg.RECENCY_FULL_DAYS)


def _notice_score(days) -> float:
    try:
        d = float(days)
    except (ValueError, TypeError):
        return 0.6
    if d <= cfg.NOTICE_GREAT_DAYS:
        return 1.0
    if d >= cfg.NOTICE_BAD_DAYS:
        return 0.3
    return 1.0 - 0.7 * (d - cfg.NOTICE_GREAT_DAYS) / (cfg.NOTICE_BAD_DAYS - cfg.NOTICE_GREAT_DAYS)


def compute(c: Candidate) -> AvailabilityResult:
    s = c.signals
    parts = {}

    parts["recency"] = _recency_score(s.get("last_active_date"))

    rr = s.get("recruiter_response_rate")
    parts["response"] = float(rr) if isinstance(rr, (int, float)) and rr >= 0 else 0.6

    parts["open"] = 1.0 if s.get("open_to_work_flag") else 0.5

    parts["notice"] = _notice_score(s.get("notice_period_days"))

    ic = s.get("interview_completion_rate")
    parts["interview"] = float(ic) if isinstance(ic, (int, float)) and ic >= 0 else 0.6

    raw = sum(cfg.AVAIL_WEIGHTS[k] * parts[k] for k in cfg.AVAIL_WEIGHTS)
    mult = cfg.AVAIL_FLOOR + (cfg.AVAIL_CEIL - cfg.AVAIL_FLOOR) * raw

    res = AvailabilityResult(multiplier=round(mult, 6), parts={k: round(v, 3) for k, v in parts.items()})

    # Concerns for reasoning (honest gaps).
    if parts["recency"] <= 0.2:
        res.concerns.append("inactive on the platform for months")
    if parts["response"] <= 0.2:
        res.concerns.append(f"low recruiter response rate ({parts['response']:.0%})")
    if parts["notice"] <= 0.35:
        nd = s.get("notice_period_days")
        res.concerns.append(f"long notice period ({nd} days)")
    if not s.get("open_to_work_flag"):
        res.concerns.append("not flagged open-to-work")
    return res
