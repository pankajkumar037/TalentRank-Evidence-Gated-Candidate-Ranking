"""
Adversarial regression suite. Each fake candidate encodes one trap the dataset
plants; the ranker must handle each correctly. Run: pytest tests/ -q

These tests are the guardrail: if a change regresses trap behavior (a stuffer
climbs, a honeypot stops being flagged, a consultant stops being gated), the build
breaks before it ever reaches a submission.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import loader, scorer  # noqa: E402


def _cand(**over):
    """Build a candidate dict with sensible defaults, overriding as needed."""
    base = {
        "candidate_id": "CAND_0000000",
        "profile": {
            "anonymized_name": "Test User",
            "headline": "Engineer",
            "summary": "",
            "location": "Bangalore",
            "country": "India",
            "years_of_experience": 7.0,
            "current_title": "Software Engineer",
            "current_company": "Acme Corp",
            "current_company_size": "1001-5000",
            "current_industry": "Software",
        },
        "career_history": [],
        "education": [],
        "skills": [],
        "redrob_signals": {
            "last_active_date": "2026-06-01",
            "signup_date": "2024-01-01",
            "open_to_work_flag": True,
            "recruiter_response_rate": 0.7,
            "notice_period_days": 30,
            "interview_completion_rate": 0.9,
            "willing_to_relocate": True,
            "github_activity_score": -1,
            "offer_acceptance_rate": -1,
        },
    }
    base.update(over)
    return loader._to_candidate(base)


def _job(desc, company="Acme Corp", title="ML Engineer", months=84, current=True,
         start="2019-06-01", end=None, industry="Software"):
    return {
        "company": company, "title": title, "start_date": start, "end_date": end,
        "duration_months": months, "is_current": current, "industry": industry,
        "company_size": "1001-5000", "description": desc,
    }


CLEAN_FIT_DESC = (
    "Built and shipped a production recommendation and ranking system at a marketplace "
    "product serving millions of users. Designed embeddings-based semantic retrieval with "
    "sentence-transformers and FAISS, and owned the evaluation with NDCG and online A/B tests."
)


def score(c):
    return scorer.score_candidate(c, None)


def test_clean_fit_scores_high():
    c = _cand(career_history=[_job(CLEAN_FIT_DESC)])
    s = score(c)
    assert not s.is_honeypot
    assert s.evidence.score > 0.7, s.evidence.category_scores
    assert s.final > 0.5


def test_keyword_stuffer_scores_near_zero():
    # Marketing Manager with AI skill TAGS but no AI work in the description.
    c = _cand(
        career_history=[_job(
            "Owned demand-generation: content marketing, paid acquisition, SEO and email nurture. "
            "Managed the marketing team and the campaign calendar.",
            title="Marketing Manager")],
        skills=[{"name": "Machine Learning", "proficiency": "expert", "endorsements": 99, "duration_months": 40},
                {"name": "RAG", "proficiency": "advanced", "endorsements": 50, "duration_months": 30},
                {"name": "Pinecone", "proficiency": "advanced", "endorsements": 40, "duration_months": 20}],
    )
    s = score(c)
    assert s.evidence.score < 0.1, s.evidence.category_scores
    clean = score(_cand(career_history=[_job(CLEAN_FIT_DESC)]))
    assert clean.final > 4 * max(s.final, 1e-6)


def test_honeypot_expert_zero_months_flagged():
    c = _cand(
        career_history=[_job(CLEAN_FIT_DESC)],
        skills=[{"name": "MLflow", "proficiency": "expert", "endorsements": 3, "duration_months": 0}],
    )
    s = score(c)
    assert s.is_honeypot
    assert s.final == 0.0


def test_honeypot_impossible_experience_flagged():
    # Claims 14 years but career history spans ~1 year.
    c = _cand(
        profile={
            "anonymized_name": "X", "headline": "", "summary": "", "location": "Pune",
            "country": "India", "years_of_experience": 14.0, "current_title": "ML Engineer",
            "current_company": "Acme Corp", "current_company_size": "1001-5000",
            "current_industry": "Software",
        },
        career_history=[_job(CLEAN_FIT_DESC, months=12, start="2025-01-01", end="2026-01-01", current=False)],
    )
    s = score(c)
    assert s.is_honeypot


def test_consultant_only_career_gated():
    c = _cand(
        profile={
            "anonymized_name": "X", "headline": "", "summary": "", "location": "Pune",
            "country": "India", "years_of_experience": 8.0, "current_title": "ML Engineer",
            "current_company": "TCS", "current_company_size": "10001+", "current_industry": "IT Services",
        },
        career_history=[
            _job(CLEAN_FIT_DESC, company="TCS", industry="IT Services"),
            _job(CLEAN_FIT_DESC, company="Infosys", industry="IT Services", current=False,
                 start="2018-01-01", end="2022-12-01", months=59),
        ],
    )
    s = score(c)
    assert s.gate_mult < 0.1, s.gate_reason


def test_consultant_now_but_prior_product_passes():
    # Currently at TCS but previously at a product company -> NOT gated (JD is explicit).
    c = _cand(
        profile={
            "anonymized_name": "X", "headline": "", "summary": "", "location": "Pune",
            "country": "India", "years_of_experience": 8.0, "current_title": "ML Engineer",
            "current_company": "TCS", "current_company_size": "10001+", "current_industry": "IT Services",
        },
        career_history=[
            _job(CLEAN_FIT_DESC, company="TCS", industry="IT Services"),
            _job(CLEAN_FIT_DESC, company="Flipkart", industry="Software", current=False,
                 start="2018-01-01", end="2022-12-01", months=59),
        ],
    )
    s = score(c)
    assert s.gate_mult == 1.0, s.gate_reason


def test_abroad_no_relocate_gated():
    c = _cand(
        profile={
            "anonymized_name": "X", "headline": "", "summary": "", "location": "Toronto",
            "country": "Canada", "years_of_experience": 7.0, "current_title": "ML Engineer",
            "current_company": "Acme Corp", "current_company_size": "1001-5000", "current_industry": "Software",
        },
        career_history=[_job(CLEAN_FIT_DESC)],
        redrob_signals={**_cand().signals, "willing_to_relocate": False},
    )
    s = score(c)
    assert s.gate_mult < 0.1, s.gate_reason


def test_ghost_demoted_not_erased():
    active = _cand(career_history=[_job(CLEAN_FIT_DESC)])
    ghost = _cand(
        career_history=[_job(CLEAN_FIT_DESC)],
        redrob_signals={
            "last_active_date": "2025-09-01", "signup_date": "2024-01-01",
            "open_to_work_flag": False, "recruiter_response_rate": 0.03,
            "notice_period_days": 150, "interview_completion_rate": 0.2,
            "willing_to_relocate": True, "github_activity_score": -1, "offer_acceptance_rate": -1,
        },
    )
    a, g = score(active), score(ghost)
    assert g.final < a.final                 # ghost demoted
    assert g.avail_mult >= 0.55              # but never erased (floor holds)
    assert g.final > 0                       # still on the board


def test_wrong_domain_penalized():
    cv = _cand(career_history=[_job(
        "Built computer vision models for object detection and image classification using OpenCV. "
        "Worked on medical imaging segmentation and point cloud processing for robotics.",
        title="Computer Vision Engineer")])
    s = score(cv)
    assert any(p[0] == "wrong_domain" for p in s.fit.penalties)


def test_output_deterministic():
    c = _cand(career_history=[_job(CLEAN_FIT_DESC)])
    assert score(c).final == score(c).final


# ---- v2 (JD-grounded) behaviors -------------------------------------------

_LOW_DEPTH = "Built a ranking model. Built embedding retrieval. Built a vector index. Measured NDCG."


def test_depth_differentiates_equal_coverage():
    # Both prove all four must-haves; the one with scale + ownership + named techniques
    # (CLEAN_FIT_DESC) must score a higher depth and rank above the terse one.
    rich = score(_cand(career_history=[_job(CLEAN_FIT_DESC)]))
    terse = score(_cand(career_history=[_job(_LOW_DEPTH)]))
    assert rich.evidence.depth > terse.evidence.depth, (rich.evidence.depth, terse.evidence.depth)
    assert rich.final > terse.final


def test_location_breaks_ties():
    # Identical strong candidates; the one in Noida (their office) outranks one elsewhere.
    def at(city):
        return _cand(
            profile={"anonymized_name": "X", "headline": "", "summary": "", "location": city,
                     "country": "India", "years_of_experience": 7.0, "current_title": "ML Engineer",
                     "current_company": "Acme Corp", "current_company_size": "1001-5000",
                     "current_industry": "Software"},
            career_history=[_job(CLEAN_FIT_DESC)])
    assert score(at("Noida")).final > score(at("Jaipur")).final


def test_availability_floor_is_higher():
    ghost = _cand(
        career_history=[_job(CLEAN_FIT_DESC)],
        redrob_signals={
            "last_active_date": "2025-01-01", "signup_date": "2024-01-01",
            "open_to_work_flag": False, "recruiter_response_rate": 0.0,
            "notice_period_days": 180, "interview_completion_rate": 0.0,
            "willing_to_relocate": True, "github_activity_score": -1, "offer_acceptance_rate": -1,
        })
    s = score(ghost)
    assert s.avail_mult >= 0.75          # fit-first: availability swing capped at 25%


def test_strong_ghost_beats_weak_active_filler():
    strong_ghost = _cand(
        career_history=[_job(CLEAN_FIT_DESC)],
        redrob_signals={
            "last_active_date": "2025-01-01", "signup_date": "2024-01-01",
            "open_to_work_flag": False, "recruiter_response_rate": 0.05,
            "notice_period_days": 150, "interview_completion_rate": 0.2,
            "willing_to_relocate": True, "github_activity_score": -1, "offer_acceptance_rate": -1,
        })
    weak_active = _cand(career_history=[_job(
        "Built React frontends and REST APIs for a SaaS product.", title="Frontend Engineer")])
    assert score(strong_ghost).final > score(weak_active).final
