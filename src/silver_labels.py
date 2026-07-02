"""
silver_labels.py — An INDEPENDENT relevance judge (tiers 0-5) for local evaluation.

There is no public ground truth, so we approximate the organizers' human-judged tiers
with an explicit rubric. To keep the evaluation honest, this judge is deliberately
independent of the ranker: it does NOT import evidence.py / fit.py, and it detects AI
work with its OWN phrase lists (different wording from the ranker's pattern bank). It
shares only the two objective disqualifiers the organizers themselves apply — honeypot
detection and the JD's hard gates.

Tiering (for THIS "Senior AI Engineer" JD):
  Tier 0  honeypot, or hard-gated, or keyword-stuffer (non-tech current role)
  Tier 1  a tech background but no proven ranking/retrieval/rec/eval work
  Tier 2  one AI theme proven
  Tier 3  two AI themes proven               (relevant)
  Tier 4  three AI themes proven             (strong)
  Tier 5  all four AI themes proven          (elite full-stack)
  modifiers: CV/speech/robotics-without-NLP/IR caps at 2; ghost -1; out-of-band exp -1.

This is an ESTIMATE, not the hidden score. Use it for regression detection and for the
relative gap between the ranker and the keyword-trap baselines — not as an oracle.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from . import gates as gatemod
from . import honeypot as hpmod
from . import jd_config as cfg
from .loader import Candidate

# Independent theme vocabularies (intentionally worded differently from evidence.py).
_THEME_RANKING = re.compile(
    r"recommend|recommender|ranking|rank-order|learn(ing)?[- ]to[- ]rank|discovery feed|"
    r"personaliz|relevance|matching (engine|layer|system)|feed ranking|"
    r"surface.{0,20}(relevant|content)|content ranking|search ranking", re.I)
_THEME_RETRIEVAL = re.compile(
    r"embedding|sentence[- ]transformer|semantic search|dense retriev|retriev|"
    r"nearest[- ]neighbou?r|two[- ]tower|dual[- ]encoder|bi[- ]encoder|cross[- ]encoder|"
    r"query (expansion|understanding|rewrit)|vector representation|"
    # Plain-language retrieval/representation a human reader would recognize (the judge
    # must not be blind to prose the way keyword matchers are). Independent of the
    # ranker's own tag/pattern machinery; curated skill tags are deliberately NOT used
    # here, so the judge stays an independent check on the ranker's tag mechanism.
    r"content is represented|how (content|items|documents) (is|are) represented|"
    r"represent(ing|ation of) (content|items|documents)|understand what users are looking for",
    re.I)
_THEME_VECTORDB = re.compile(
    r"faiss|pinecone|weaviate|qdrant|milvus|scann|annoy|hnsw|elasticsearch|opensearch|"
    r"\bsolr\b|hybrid (search|retriev)|\bbm25\b|tf[- ]?idf|inverted index|vector (db|database|store|index)",
    re.I)
_THEME_EVAL = re.compile(
    r"\bndcg\b|\bmrr\b|\bmap\b|precision@|\bp@\d|a/?b test|offline[- ](to[- ])?online|"
    r"click[- ]through|\bctr\b|relevance (label|judg)|eval(uation)? (harness|framework|pipeline)|"
    r"ranking metric|holdout|offline benchmark", re.I)

_WRONG_DOMAIN = re.compile(
    r"computer vision|image classification|object detection|opencv|speech recognition|"
    r"text[- ]to[- ]speech|\btts\b|robotics|slam|lidar|point cloud|medical imaging|segmentation",
    re.I)
_NLP_IR = re.compile(r"nlp|natural language|retriev|ranking|search|recommend|embedding|"
                     r"information retrieval|\btext\b", re.I)

# Non-technical current titles that mark a keyword-stuffer when paired with AI skill tags.
_STUFFER_TITLES = (
    "marketing manager", "hr manager", "sales executive", "accountant", "content writer",
    "business analyst", "operations manager", "project manager", "customer support",
    "graphic designer", "mechanical engineer", "civil engineer", "recruiter",
    "administrative", "office manager", "logistics", "supply chain",
)

_REF = datetime.date.fromisoformat(cfg.REFERENCE_DATE)


@dataclass
class SilverLabel:
    tier: int
    rationale: str


def _parse(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def label(c: Candidate) -> SilverLabel:
    # --- objective tier-0 conditions (shared with the organizers) ----------
    if hpmod.check(c).is_honeypot:
        return SilverLabel(0, "honeypot (impossible profile)")
    gate = gatemod.evaluate(c)
    if gate.multiplier <= cfg.GATE_MULTIPLIER:
        return SilverLabel(0, f"hard-gated: {gate.reason}")

    title = c.current_title.lower()
    text = c.all_description_text

    # --- keyword-stuffer: non-tech role, AI only in the (noise) skill tags ---
    if any(t in title for t in _STUFFER_TITLES):
        # If the described work still proves real AI themes, don't punish on title alone.
        themes_here = sum(bool(rx.search(text)) for rx in
                          (_THEME_RANKING, _THEME_RETRIEVAL, _THEME_VECTORDB, _THEME_EVAL))
        if themes_here == 0:
            return SilverLabel(0, f"keyword-stuffer: non-technical role ({c.current_title})")

    # --- count proven AI themes from description prose ----------------------
    themes = 0
    present = []
    for name, rx in (("ranking", _THEME_RANKING), ("retrieval", _THEME_RETRIEVAL),
                     ("vector-db", _THEME_VECTORDB), ("evaluation", _THEME_EVAL)):
        if rx.search(text):
            themes += 1
            present.append(name)

    if themes == 0:
        return SilverLabel(1, "tech background but no ranking/retrieval/eval evidence")

    tier = min(5, themes + 1)          # 1 theme->2, 2->3, 3->4, 4->5
    rationale = f"{themes} AI theme(s): {', '.join(present)}"

    # --- modifiers ----------------------------------------------------------
    if _WRONG_DOMAIN.search(text) and not _NLP_IR.search(text):
        tier = min(tier, 2)
        rationale += "; capped: CV/speech/robotics without NLP/IR"

    last = _parse(c.signals.get("last_active_date"))
    resp = c.signals.get("recruiter_response_rate", 1.0)
    inactive = last is not None and (_REF - last).days > 180
    if inactive and isinstance(resp, (int, float)) and resp < 0.1:
        tier = max(0, tier - 1)
        rationale += "; ghost (inactive + no recruiter response)"

    if c.years_experience < 2 or c.years_experience > 12:
        tier = max(0, tier - 1)
        rationale += f"; experience out of band ({c.years_experience:.1f}y)"

    return SilverLabel(tier, rationale)
