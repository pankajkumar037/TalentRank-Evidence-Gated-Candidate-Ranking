"""
honeypot.py — Detect logically-impossible ("honeypot") profiles.

The dataset plants ~80 profiles with subtly impossible facts. Ranking any of them
into the top 100 risks disqualification (>10% honeypot rate = DQ). We do NOT need
to special-case them to rank well — real honeypots carry ~0 evidence — but we flag
them and assert none reach the output as belt-and-suspenders.

Profiling finding: the sharpest signal by far is an `expert`-proficiency skill with
`duration_months == 0` (84 candidates in 100k; "expert" is otherwise rare and always
has non-zero duration). That single rule ≈ catches the whole planted set. We add two
more cross-field impossibility rules for robustness. We deliberately do NOT use
"skill duration > career span" (fires 13,462 times — a data artifact, not a fake)
nor "activity before signup" (7,496 profiles — an acknowledged generation artifact).
"""
from __future__ import annotations

from dataclasses import dataclass

from .loader import Candidate


@dataclass
class HoneypotVerdict:
    is_honeypot: bool
    reasons: list


def check(c: Candidate) -> HoneypotVerdict:
    reasons = []

    # Rule 1 — "expert" skill claimed but used for 0 months. Impossible by
    # definition ("expert" implies substantial use). Primary signal. Skills are
    # kept as raw dicts (they are untrusted noise used only here).
    for s in c.skills:
        if s.get("proficiency") == "expert" and int(s.get("duration_months") or 0) == 0:
            reasons.append(f"'expert' proficiency in {s.get('name')!r} with 0 months of use")
            break

    # Rule 2 — a single job whose stated duration_months wildly exceeds the span
    # between its own start and end dates (e.g. 166 months inside a 33-month window).
    for j in c.jobs:
        span = j.span_months
        if span is not None and span >= 0 and j.duration_months > span + 6:
            reasons.append(
                f"job at {j.company!r} claims {j.duration_months} months but its "
                f"dates span only {span}"
            )
            break

    # Rule 3 — claimed years_of_experience EGREGIOUSLY exceeds what the whole career
    # spans (e.g. 13.7 years claimed over a 1.3-year history). Kept deliberately
    # strict (needs BOTH a large ratio AND a large absolute gap) so a real candidate
    # who simply lists only their recent jobs is never mistaken for a fake.
    span = c.career_span_months
    if (span is not None and span > 0
            and c.years_experience * 12 > span * 1.6
            and c.years_experience * 12 > span + 48):
        reasons.append(
            f"claims {c.years_experience:.1f} years of experience but entire history "
            f"spans only {span / 12:.1f} years"
        )

    return HoneypotVerdict(is_honeypot=bool(reasons), reasons=reasons)
