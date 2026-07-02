"""
loader.py — Stream candidates from JSONL(.gz) into compact, clean fact objects.

We never hold all 100k raw dicts at once if we can help it: the caller iterates.
Skill tags ARE parsed but flagged untrusted — they feed honeypot cross-checks only,
never scoring.
"""
from __future__ import annotations

import datetime
import gzip
import io
from dataclasses import dataclass, field
from typing import Iterator, Optional

try:
    import orjson as _json

    def _loads(b):
        return _json.loads(b)
except Exception:  # pragma: no cover - orjson is in requirements
    import json as _json

    def _loads(b):
        return _json.loads(b)


def _parse_date(s: Optional[str]) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


@dataclass
class Job:
    company: str
    title: str
    start: Optional[datetime.date]
    end: Optional[datetime.date]
    duration_months: int
    is_current: bool
    industry: str
    company_size: str
    description: str

    @property
    def span_months(self) -> Optional[int]:
        if self.start and self.end:
            return (self.end.year - self.start.year) * 12 + (self.end.month - self.start.month)
        return None


@dataclass
class Skill:
    name: str
    proficiency: str
    endorsements: int
    duration_months: int


@dataclass
class Candidate:
    cid: str
    name: str
    headline: str
    summary: str
    location: str
    country: str
    years_experience: float
    current_title: str
    current_company: str
    current_company_size: str
    current_industry: str
    jobs: list = field(default_factory=list)          # list[Job], newest first
    education: list = field(default_factory=list)      # raw dicts
    skills: list = field(default_factory=list)         # list[Skill] (UNTRUSTED)
    signals: dict = field(default_factory=dict)        # raw redrob_signals

    # ---- convenience views over described work (the only thing we score) ----
    @property
    def all_description_text(self) -> str:
        return " \n ".join(j.description for j in self.jobs)

    @property
    def career_span_months(self) -> Optional[int]:
        starts = [j.start for j in self.jobs if j.start]
        ends = [j.end for j in self.jobs if j.end]
        if starts and ends:
            lo, hi = min(starts), max(ends)
            return (hi.year - lo.year) * 12 + (hi.month - lo.month)
        return None


def _to_candidate(rec: dict) -> Candidate:
    p = rec.get("profile", {})
    jobs = []
    for j in rec.get("career_history", []):
        end = _parse_date(j.get("end_date"))
        if j.get("is_current") and end is None:
            end = _parse_date(_REFERENCE_DATE_STR)
        jobs.append(
            Job(
                company=(j.get("company") or "").strip(),
                title=(j.get("title") or "").strip(),
                start=_parse_date(j.get("start_date")),
                end=end,
                duration_months=int(j.get("duration_months") or 0),
                is_current=bool(j.get("is_current")),
                industry=(j.get("industry") or "").strip(),
                company_size=(j.get("company_size") or "").strip(),
                description=(j.get("description") or "").strip(),
            )
        )
    # Skills are UNTRUSTED noise used only by the honeypot cross-check; keep the raw
    # dicts rather than build ~1.7M Skill objects across the pool (a real hot path).
    skills = rec.get("skills", []) or []
    return Candidate(
        cid=rec["candidate_id"],
        name=p.get("anonymized_name", ""),
        headline=p.get("headline", ""),
        summary=p.get("summary", ""),
        location=p.get("location", ""),
        country=(p.get("country") or "").strip(),
        years_experience=float(p.get("years_of_experience") or 0.0),
        current_title=(p.get("current_title") or "").strip(),
        current_company=(p.get("current_company") or "").strip(),
        current_company_size=(p.get("current_company_size") or "").strip(),
        current_industry=(p.get("current_industry") or "").strip(),
        jobs=jobs,
        education=rec.get("education", []),
        skills=skills,
        signals=rec.get("redrob_signals", {}) or {},
    )


# The reference "today" is injected once so is_current end-dates are deterministic.
_REFERENCE_DATE_STR = "2026-06-15"


def set_reference_date(s: str) -> None:
    global _REFERENCE_DATE_STR
    _REFERENCE_DATE_STR = s


def _open_any(path: str):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def iter_candidates(path: str) -> Iterator[Candidate]:
    """Stream candidates one at a time from a .jsonl or .jsonl.gz file."""
    if path.endswith(".gz"):
        fh = gzip.open(path, "rb")
        binary = True
    else:
        fh = open(path, "rb")
        binary = True
    try:
        for line in fh:
            if not line.strip():
                continue
            yield _to_candidate(_loads(line))
    finally:
        fh.close()


def load_all(path: str) -> list:
    return list(iter_candidates(path))
