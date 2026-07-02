"""
jd_config.py — Every threshold, weight, gate, and pattern used by the ranker,
with the sentence of the job description that justifies it.

Design rule (from the JD's own hackathon note and confirmed by profiling the data):
    Credit attaches to *described work*, never to *claimed labels*.
    Skill tags and headlines are randomly-generated noise (every tag appears
    ~12,000 times; a Toronto backend engineer lists "Milvus/LoRA/GANs/Photoshop").
    So scoring reads career_history[].description text ONLY.

Nothing in this file is a black box: each constant cites the JD line behind it.
"""

# --------------------------------------------------------------------------
# The four things the JD says it *absolutely needs*. Evidence is scored against
# these, read from career-history description prose (plain language counts fully).
#
# JD: "Production experience with embeddings-based retrieval systems ... deployed
#      to real users." / "Production experience with vector databases or hybrid
#      search infrastructure." / "designing evaluation frameworks for ranking
#      systems — NDCG, MRR, MAP ... A/B test interpretation." / "shipped at least
#      one end-to-end ranking, search, or recommendation system to real users."
# --------------------------------------------------------------------------

# Each must-have is a list of (regex, is_plain_language) evidence patterns.
# Plain-language patterns are first-class — they score identically to buzzwords.
# NB: patterns are matched case-insensitively against description text.

RANKING_RECS = [  # shipped ranking / recommendation / matching systems
    r"recommendation (system|engine|model|pipeline)",
    r"\brecommender\b",
    r"ranking (model|system|layer|pipeline|algorithm|function)",
    r"learning[- ]to[- ]rank",
    r"\bLTR\b",
    r"discovery feed",
    r"personaliz(e|ation|ed)",
    r"matching (layer|system|engine|algorithm)",
    r"relevance (ranking|tuning|calibration|labeling|scoring)",
    r"surface (relevant|the most relevant)",
    r"connect .{0,30}(relevant|matches)",       # plain language
    r"search (ranking|relevance|quality)",
    r"content (recommendation|ranking)",
    r"candidate[- ]JD matching|job[- ]matching|talent matching",
]

EMBEDDINGS_RETRIEVAL = [  # production embeddings / retrieval work
    r"embedding(s)?",
    r"sentence[- ]transformers?",
    r"\bbge\b|\be5\b|all-MiniLM|all-mpnet",
    r"semantic search",
    r"dense retriev(al|er)",
    r"nearest[- ]neighbou?r",
    r"\bANN\b|approximate nearest",
    r"retriev(al|er|e)\b",
    r"query (expansion|understanding|rewriting)",
    r"vector (search|representation|similarity)",
    r"two[- ]tower|dual[- ]encoder|bi[- ]encoder|cross[- ]encoder",
    # --- Plain-language phrasings (JD: "A Tier-5 candidate may not use the words
    # 'RAG' or 'Pinecone' ... plain language counts fully"). "How content is
    # represented internally" == learned representations/embeddings; "understand
    # what users are looking for" == query understanding. Mined from the corpus;
    # these fire on the plain-language retrieval descriptions that jargon patterns
    # miss (measured: matches only genuine IR-at-scale profiles, no distractors).
    r"how content is represented|content is represented internally",
    r"how (items|content|documents) (are|is) represented",
    r"represent(ing|ed|ation of) (content|items|documents)",
    r"understand what users are looking for",
    r"learns from user behavior",
    r"most relevant (results|matches|content|items)",
]

VECTOR_DB_HYBRID = [  # vector DB / hybrid search infra & operations
    r"\bfaiss\b|\bpinecone\b|\bweaviate\b|\bqdrant\b|\bmilvus\b|\bscann\b|\bannoy\b|\bhnsw\b",
    r"elasticsearch|opensearch|\bsolr\b",
    r"hybrid (search|retrieval)",
    r"\bBM25\b|\bTF[- ]?IDF\b",
    r"index (refresh|rebuild|refreshing)|reindex",
    r"vector (database|db|index|store)",
    r"inverted index",
]

EVALUATION = [  # rigorous ranking evaluation
    r"\bNDCG\b|\bMRR\b|\bMAP\b|\bp@\d|precision@",
    r"A/?B test",
    r"offline[- ](to[- ])?online (correlation|evaluation|metric)",
    r"relevance (labeling|judgment|judgement)",
    r"click[- ]through (data|rate)|CTR",
    r"eval(uation)? (harness|framework|pipeline|suite)",
    r"ranking metric",
    r"human (judgment|judgement|label|quality) (data|scores)?",
    r"holdout|offline benchmark",
]

MUST_HAVES = {
    "ranking_recs": RANKING_RECS,
    "embeddings_retrieval": EMBEDDINGS_RETRIEVAL,
    "vector_db_hybrid": VECTOR_DB_HYBRID,
    "evaluation": EVALUATION,
}

# Human-readable labels for reasoning strings.
MUST_HAVE_LABELS = {
    "ranking_recs": "shipped ranking/recommendation systems",
    "embeddings_retrieval": "production embeddings/retrieval work",
    "vector_db_hybrid": "vector-database / hybrid-search operations",
    "evaluation": "ranking-evaluation rigor (NDCG/A-B style)",
}

# Weight per must-have inside the evidence score. JD lists all four as "absolutely
# need"; ranking/recs and embeddings/retrieval are the two most-emphasised so they
# lead, evaluation and vector-db round it out. They sum to 1.0.
MUST_HAVE_WEIGHTS = {
    "ranking_recs": 0.35,
    "embeddings_retrieval": 0.30,
    "vector_db_hybrid": 0.15,
    "evaluation": 0.20,
}

# Graded proof. JD wants people who *built/shipped/operated*, not dabbled.
# A strong action verb near the match -> full credit; a weak/adjacent phrase -> partial.
STRONG_VERBS = r"(built|shipped|owned|designed|led|deployed|trained|implemented|developed|" \
               r"architected|scaled|launched|created|drove|overhaul|re-?built|evolv)"
WEAK_CONTEXT = r"(worked with|exposed to|familiar|assisted|helped|adjacent|some exposure|" \
               r"learning|self-directed|side project|kaggle|coursework|hobby|exploring|" \
               r"interested in|transitioning)"
STRONG_CREDIT = 1.0
WEAK_CREDIT = 0.4

# Recency weighting across the career history (newest job first). The current /
# most recent role matters most. JD: "hasn't written production code in the last
# 18 months ... we will probably not move forward" => recent work dominates.
RECENCY_WEIGHTS = [1.0, 0.75, 0.55, 0.40, 0.30, 0.22, 0.16, 0.12, 0.09, 0.07]

# --------------------------------------------------------------------------
# Hard gates (near-zero multiplier). JD: "here are the disqualifiers we actually
# apply". A gate is applied over the WHOLE career, never a single row.
# --------------------------------------------------------------------------
GATE_MULTIPLIER = 0.02          # not exactly 0 -> keeps ordering stable among gated
SOFT_ABROAD_RELOCATE = 0.55     # non-India but willing to relocate: visa caveat, not a wall

# JD: "People who have only worked at consulting firms (TCS, Infosys, Wipro,
# Accenture, Cognizant, Capgemini, etc.) in their entire career." — note "entire
# career": a candidate CURRENTLY at one but with prior product experience passes.
CONSULTANCY_COMPANIES = {
    "tcs", "tata consultancy services", "infosys", "wipro", "accenture",
    "cognizant", "capgemini", "hcl", "hcl technologies", "tech mahindra",
    "mphasis", "mindtree", "ltimindtree", "l&t infotech", "igate", "syntel",
    "dxc", "dxc technology", "birlasoft", "hexaware", "coforge", "nttdata",
    "ntt data", "persistent systems",
}
CONSULTANCY_INDUSTRIES = {"it services", "consulting", "it consulting", "outsourcing"}

# JD: "pure research environments (academic labs, research-only roles) without any
# production deployment — we will not move forward."
ACADEMIC_TOKENS = ("university", "institute of technology", "iit ", "iisc",
                   "research institute", "national laboratory", "academia",
                   "college", "postdoctoral", "ph.d. researcher")
ACADEMIC_TITLES = ("professor", "postdoc", "postdoctoral", "phd student",
                   "phd researcher", "research scholar", "lecturer", "teaching assistant")
# Signs of production deployment that RESCUE an otherwise academic-looking career.
PRODUCTION_TOKENS = ("production", "deployed", "shipped", "real users", "at scale",
                     "a/b", "latency", "serving", "in production", "customers")

INDIA_NAMES = {"india"}

# --------------------------------------------------------------------------
# Fit scoring. JD: "5-9 years ... This is a range, not a requirement." -> soft curve.
# "the 'ideal candidate' ... 6-8 years total ... of which 4-5 are in applied ML/AI."
# --------------------------------------------------------------------------
EXPERIENCE_IDEAL = 7.0          # JD midpoint of "6-8 years total"
EXPERIENCE_SIGMA_LOW = 3.0      # gentle on juniors (a 5y star, our test #4, is fine)
EXPERIENCE_SIGMA_HIGH = 4.5     # gentle on seniors too
EXPERIENCE_FLOOR = 0.45         # never zero — "seriously consider candidates outside the band"

# Titles that indicate applied ML/AI product work (used to count "ML years at
# product companies" and hands-on signal — NOT used as keyword credit for evidence).
ML_TITLE_TOKENS = ("machine learning", "ml engineer", "applied scientist",
                   "applied ml", "ai engineer", "nlp engineer", "data scientist",
                   "research engineer", "recommendation", "search engineer",
                   "relevance engineer", "ranking", "deep learning", "mlops")

# JD penalties, each explicitly named in the JD.
# "career trajectory ... switching companies every 1.5 years" -> job hopper.
JOB_HOP_MONTHS = 18
JOB_HOP_MIN_STINTS = 3          # need several short stints to call it a pattern
PENALTY_JOB_HOPPER = 0.80

# "'AI experience' consists primarily of recent (<12 months) projects using
# LangChain to call OpenAI ... unless ... substantial pre-LLM-era ML production."
LLM_WRAPPER_TOKENS = ("langchain", "llamaindex", "gpt-4", "gpt-3", "openai api",
                      "openai's api", "prompt engineering", "chatgpt", "rag chatbot",
                      "wrapper")
PRE_LLM_ML_TOKENS = ("xgboost", "lightgbm", "collaborative filtering", "matrix factorization",
                     "learning-to-rank", "learning to rank", "bm25", "tf-idf",
                     "random forest", "logistic regression", "svm", "gradient boost",
                     "recommendation system", "ranking model", "faiss")
PENALTY_LLM_WRAPPER = 0.70

# "primary expertise is computer vision, speech, or robotics without significant
# NLP/IR exposure."
WRONG_DOMAIN_TOKENS = ("computer vision", "image classification", "object detection",
                       "opencv", "speech recognition", "text-to-speech", "\btts\b",
                       "robotics", "slam", "autonomous", "point cloud", "lidar",
                       "medical imaging", "segmentation")
NLP_IR_TOKENS = ("nlp", "natural language", "retrieval", "ranking", "search",
                 "recommendation", "embedding", "information retrieval", "text")
PENALTY_WRONG_DOMAIN = 0.65

# Product-company signal: current_company that is clearly a product company (not a
# consultancy). We invert the consultancy set; also treat known Indian product cos.
PRODUCT_COMPANY_HINTS = {
    "swiggy", "zomato", "flipkart", "cred", "razorpay", "meesho", "inmobi",
    "phonepe", "paytm", "myntra", "ola", "sharechat", "dream11", "unacademy",
    "pied piper", "hooli", "stark industries", "wayne enterprises", "globex inc",
    "acme corp", "initech", "dunder mifflin",
}

# --------------------------------------------------------------------------
# Availability multiplier. JD: "a perfect-on-paper candidate who hasn't logged in
# for 6 months and has a 5% recruiter response rate is, for hiring purposes, not
# actually available. Down-weight them appropriately." Bounded so it demotes a
# ghost but can NEVER erase a genuinely strong candidate.
# --------------------------------------------------------------------------
# Fit-first: availability BREAKS TIES but must never sink a clearly-stronger fit below a
# weaker one. The JD says "down-weight" ghosts, not "rank by availability" — so the swing
# is capped at 25% (floor 0.75), not 45%.
AVAIL_FLOOR = 0.75
AVAIL_CEIL = 1.00
# Sub-weights within availability (sum to 1.0).
AVAIL_WEIGHTS = {
    "recency": 0.30,            # days since last_active_date
    "response": 0.30,          # recruiter_response_rate
    "open": 0.15,              # open_to_work_flag
    "notice": 0.15,            # notice_period_days (JD: "sub-30-day notice" preferred)
    "interview": 0.10,         # interview_completion_rate
}
RECENCY_FULL_DAYS = 30         # active within 30d -> full marks
RECENCY_DEAD_DAYS = 180        # ~6 months -> the JD's "ghost" threshold
NOTICE_GREAT_DAYS = 30         # JD: "We'd love sub-30-day notice."
NOTICE_BAD_DAYS = 120
# Sentinels meaning "no data", which must count as neutral, NOT as bad.
NO_DATA_SENTINEL = -1

# A fixed "today" so runs are byte-identical and reproducible (competition rule).
# Chosen from the data: latest last_active dates sit in mid-2026.
REFERENCE_DATE = "2026-06-15"

# --------------------------------------------------------------------------
# Semantic booster (offline-precomputed embeddings). Bounded so it can only lift
# real work the regex missed — it never rescues a gated / honeypot / no-evidence
# profile. Model runs OFFLINE; the ranking step just loads a matrix and does cosine.
# --------------------------------------------------------------------------
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_MAX_BOOST = 0.25       # max fractional uplift to the quality score
SEMANTIC_MIN_EVIDENCE = 0.08    # below this evidence, no boost (nothing real to lift)
# JD must-have concept sentences the candidate text is compared against.
JD_CONCEPT_SENTENCES = [
    "Built and shipped a production recommendation and ranking system serving real users at scale.",
    "Designed embeddings-based semantic retrieval with sentence-transformers and a vector database.",
    "Operated hybrid search infrastructure combining BM25 with dense retrieval and nearest-neighbor indexes.",
    "Built rigorous ranking evaluation with NDCG, MRR and MAP plus online A/B testing and offline-online correlation.",
    "Owned learning-to-rank models over click-through and human relevance labels for search and discovery.",
]

# --------------------------------------------------------------------------
# Composition weights for quality = f(evidence, depth, fit). Evidence stays primary
# (the JD's whole point). `depth` differentiates the many candidates who saturate at
# evidence=1.0 — the key lever for ordering the top-10 (NDCG@10 = 50% of the score).
# `fit` aligns the JD-profile (experience/location/seniority). Sums to 1.0; quality in [0,1].
# --------------------------------------------------------------------------
QUALITY_EVIDENCE_WEIGHT = 0.55
QUALITY_DEPTH_WEIGHT = 0.20
QUALITY_FIT_WEIGHT = 0.25

# --------------------------------------------------------------------------
# Evidence DEPTH — a non-saturating quality signal read from description prose, used to
# order candidates who all prove the four must-haves. Every component is JD-grounded.
# depth in [0,1] = weighted blend of breadth, scale, ownership, specificity, recency.
# --------------------------------------------------------------------------
DEPTH_WEIGHTS = {
    "breadth": 0.30,       # JD lists all four must-haves as "absolutely need" -> full-stack > partial
    "scale": 0.25,         # JD: "shipped ... at meaningful scale"
    "ownership": 0.20,     # JD: "own the intelligence layer", ships end-to-end
    "specificity": 0.15,   # JD names the exact modern techniques it cares about
    "recency": 0.10,       # JD: production code in the last 18 months
}
# Additive depth nudge for holders of the 14 curated rare tags (see curated_tags.py).
# Bounded: at most +0.15 to depth (which is only 0.20 of quality), so it refines the
# ordering of proven specialists without ever rescuing a weak/gated/honeypot profile.
CURATED_DEPTH_BONUS = 0.15
# Scale phrases (bigger production footprint = a more impressive, higher-relevance fit).
# Carefully avoids matching durations like "5 months" (a common false positive): a bare
# number+m only counts when it is "m+" or precedes a scale noun or is spelled "million".
_SCALE_NOUN = r"(users|queries|requests|documents|docs|items|records|events|profiles|candidates|rows|qps|rps)"
SCALE_PATTERNS = (
    r"(\d{1,4}\s*m(illion)?\s*\+"                                    # 50m+, 10 m+
    r"|\d{1,4}\s*m(illion)?\s+" + _SCALE_NOUN +                      # 2m users, 500 million docs
    r"|\d{1,4}\s*b(illion)?\s*\+"                                    # 2b+
    r"|\d{1,4}\s*billion"                                            # 3 billion
    r"|millions?\s+of\s+" + _SCALE_NOUN +                            # millions of users
    r"|billions?\s+of\s+" + _SCALE_NOUN +                            # billions of documents
    r"|at scale|large[- ]scale|web[- ]scale|internet[- ]scale"
    r"|low[- ]latency|high[- ]throughput|petabyte|terabyte)"
)
# End-to-end ownership language.
OWNERSHIP_PATTERNS = r"(end[- ]to[- ]end|owned the|from offline .{0,40}(a/?b|production|online)|" \
                     r"in production|drove the|led the (design|team|migration|effort)|from scratch|" \
                     r"soup[- ]to[- ]nuts|full ownership|owned .{0,20}(pipeline|system|stack))"
# Concrete named techniques the JD explicitly calls out (specificity/depth of practice).
TECHNIQUE_TOKENS = (
    "sentence-transformer", "sentence transformers", "bge", "e5", "all-minilm", "mpnet",
    "faiss", "hnsw", "pinecone", "qdrant", "milvus", "weaviate", "scann", "annoy",
    "lora", "qlora", "peft", "xgboost", "lightgbm", "learning-to-rank", "learning to rank",
    "cross-encoder", "bi-encoder", "two-tower", "dual-encoder", "collaborative filtering",
    "matrix factorization", "\\bbm25\\b", "tf-idf", "\\brag\\b", "reranker", "re-ranker",
    "re-ranking", "reranking", "distillation", "knowledge distillation", "elasticsearch",
    "opensearch", "vector database", "approximate nearest",
)

# --------------------------------------------------------------------------
# JD-profile fit refinements.
# --------------------------------------------------------------------------
# Location tiers (soft bonus, NEVER a gate). JD: "Located in or willing to relocate to
# Noida or Pune" (their offices); "Candidates in Hyderabad, Pune, Mumbai, Delhi NCR welcome".
LOCATION_PRIMARY = ("noida", "pune")                       # their offices
LOCATION_WELCOME = ("hyderabad", "mumbai", "delhi", "new delhi", "gurgaon", "gurugram",
                    "noida", "ghaziabad", "faridabad", "bengaluru", "bangalore", "ncr")
LOCATION_PRIMARY_BONUS = 1.00
LOCATION_WELCOME_BONUS = 0.92
LOCATION_OTHER_INDIA_BONUS = 0.85

# Seniority/title alignment with "Senior AI Engineer — Founding Team" (small nudge UP only;
# never a penalty that could override real evidence).
SENIORITY_TOKENS = ("senior", "staff", "lead", "principal")
ENGINEER_TITLE_TOKENS = ("engineer", "applied scientist", "machine learning", "ml ",
                         "ai ", "nlp", "research engineer", "mlops")
