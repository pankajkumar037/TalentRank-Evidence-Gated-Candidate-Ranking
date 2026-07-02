"""
app.py — TalentRank sandbox (Streamlit).

A hosted environment where anyone can upload a small candidate sample (<=100) and
watch the identical pipeline rank and explain them on screen — the Stage-10.5
sandbox requirement. Every pick decomposes into gate x quality x availability, down
to the exact sentence in the candidate's history that earned it.

Run locally:   streamlit run app.py
Deploy:        Streamlit Community Cloud / HuggingFace Spaces (free tier is enough).
"""
from __future__ import annotations

import io
import json

import streamlit as st

from src import loader, scorer, reasoning
from src import semantic as semmod
from precompute_embeddings import candidate_text

st.set_page_config(page_title="TalentRank — evidence-gated ranking", layout="wide")
st.title("TalentRank — evidence-gated candidate ranking")
st.caption(
    "Credit attaches to *described work*, never to claimed skill tags. Upload up to "
    "100 candidate profiles (JSON array or JSONL) and see the same ranker the "
    "submission uses — gate × quality × availability, fully explained."
)

use_sem = st.sidebar.checkbox("Use embedding booster (slower first run)", value=False)
up = st.file_uploader("Candidate profiles (.json array or .jsonl)", type=["json", "jsonl"])
st.sidebar.markdown(
    "**Scoring**\n\n`final = gate × quality × availability`\n\n"
    "- **gate**: JD deal-breakers (consultancy-only career, abroad+no-relocate, pure academia)\n"
    "- **quality**: evidence of the 4 JD must-haves (+ soft fit), read from job descriptions only\n"
    "- **availability**: recency, response rate, notice, open-to-work\n\n"
    "Honeypots (impossible profiles) are flagged and removed."
)


def _read(upload) -> list:
    raw = upload.read().decode("utf-8")
    recs = []
    stripped = raw.lstrip()
    if stripped.startswith("["):
        recs = json.loads(raw)
    else:
        for line in io.StringIO(raw):
            if line.strip():
                recs.append(json.loads(line))
    return recs[:100]


if up is not None:
    recs = _read(up)
    cands = [loader._to_candidate(r) for r in recs]
    st.success(f"Loaded {len(cands)} candidates.")

    sem = None
    if use_sem:
        with st.spinner("Embedding sample on CPU..."):
            sem = semmod.build_inmemory(cands, [candidate_text(c) for c in cands])
        if sem is None:
            st.warning("sentence-transformers unavailable — falling back to pure rules.")

    scored = [scorer.score_candidate(c, sem) for c in cands]
    scored.sort(key=scorer.rank_key)

    hp = [s for s in scored if s.is_honeypot]
    if hp:
        st.warning(f"Flagged {len(hp)} honeypot(s), removed from the ranking: "
                   + ", ".join(s.cid for s in hp))

    live = [s for s in scored if not s.is_honeypot]
    st.subheader("Ranking")
    table = [{
        "rank": i + 1, "candidate_id": s.cid, "score": round(s.final, 4),
        "title": s.candidate.current_title, "yrs": s.candidate.years_experience,
        "reasoning": reasoning.generate(s, i),
    } for i, s in enumerate(live)]
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("Score anatomy")
    pick = st.selectbox("Inspect a candidate", [s.cid for s in live])
    s = next(s for s in live if s.cid == pick)
    c1, c2, c3 = st.columns(3)
    c1.metric("gate", round(s.gate_mult, 3), s.gate_reason or "passes clean")
    c2.metric("quality", round(s.quality, 3))
    c3.metric("availability", round(s.avail_mult, 3))
    st.write("**Evidence by JD must-have**", s.evidence.category_scores)
    if s.evidence.quote:
        st.write("**Earned by:**", f"“{s.evidence.quote}”")
    if s.fit.concerns or s.avail.concerns:
        st.write("**Concerns:**", "; ".join(s.fit.concerns + s.avail.concerns))
