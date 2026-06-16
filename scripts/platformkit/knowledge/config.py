"""scripts.platformkit.knowledge.config -- paths, constants, pluggable backend ids.

Single source of truth for the vault-RAG layer.  All other modules import from here;
nothing else hard-codes a path or constant.  <=300 LOC.  ASCII only.

HARD BOUNDARY (tested in tests/test_boundary.py):
  This layer informs SYNTHESIS and NARRATION only.  It never emits a probability,
  odds value, ROI, or edge signal.  assemble() returns a cited markdown bundle only.

BASELINE (installed deps only -- numpy, scipy, pandas, pyarrow, sklearn):
  - TF-IDF cosine lane:   TfidfVectorizer, word+bigram, sublinear_tf, cosine via numpy
  - BM25-like sparse lane: TfidfVectorizer, word unigram, sublinear_tf, dot-product rank
  - Fusion:               Reciprocal Rank Fusion (RRF)
  - Boost:                exact title/category token match added to RRF score
  - Floor:                honest-reject when best score < RELEVANCE_TAU
  - Store:                numpy float32 matrix + parquet metadata (~40 MB for 4K notes)

OPTIONAL UPGRADES (document here; do NOT pip-install automatically):

  EMBEDDING BACKEND (EmbeddingBackend interface, retrieve.py):
    pip install sentence-transformers
    -> set RAG_EMBED_BACKEND=sentence_transformers, EMBED_MODEL_ID="BAAI/bge-small-en-v1.5"
    pip install voyageai   (needs VOYAGE_API_KEY)
    -> set RAG_EMBED_BACKEND=voyage, EMBED_MODEL_ID="voyage-3"

  RERANKER (Reranker interface, retrieve.py):
    pip install FlagEmbedding
    -> set RAG_RERANKER=bge, RERANKER_MODEL_ID="BAAI/bge-reranker-v2-m3"  (~100ms CPU)

  VECTOR STORE (replaces numpy matrix):
    pip install lancedb    (embedded, zero-ops, native hybrid; zero server needed)
    -> set RAG_VECTOR_STORE=lancedb  (triggers lancedb code path in index.py)
    Current corpus: ~4K notes ~40MB -- numpy is instant; lancedb useful at >50K notes.

  CONTEXTUAL PREFIXES (Anthropic Contextual Retrieval):
    pip install anthropic   (needs ANTHROPIC_API_KEY)
    -> set RAG_CTX_PREFIX=haiku
    Model: claude-haiku-4-5 via Message Batches API (50% cost reduction).
    One-time build cost ~$0.50 for 4K notes; re-runs only on sha256-changed notes.
    Prefix stored in corpus.parquet column "contextual" so re-embed only on change.
    Expected recall@5 lift: ~87% baseline -> ~95% with contextual+hybrid+rerank.
"""
from __future__ import annotations

import os
from pathlib import Path

from .text_utils import stem_tokenizer

# ---------------------------------------------------------------------------
# Repo root (resolved relative to this file; tolerates import from any cwd)
# ---------------------------------------------------------------------------
REPO_ROOT: Path = Path(os.environ.get("NBA_AI_ROOT", str(Path(__file__).parents[3])))

# ---------------------------------------------------------------------------
# Corpus sources
# ---------------------------------------------------------------------------
# Vault notes under vault/_Organized/{NBA,MLB,Soccer,Tennis}/ and _Index/
VAULT_ROOT: Path = REPO_ROOT / "vault" / "_Organized"

# Logical sport tags used throughout the system.
SPORTS: tuple = ("NBA", "MLB", "Soccer", "Tennis")

# MEMORY: auto-memory dir (human-written project notes; not vault notes).
# Querying "what do we know about X" can pull from memory too.
MEMORY_SOURCE: str = "MEMORY"
ALL_SOURCES: tuple = SPORTS + (MEMORY_SOURCE,)

# Memory dir: absolute path; tolerate missing (returns empty list in ingest).
MEMORY_DIR: Path = Path(
    os.environ.get(
        "NBA_AI_MEMORY_DIR",
        str(Path.home() / ".claude" / "projects" / "C--Users-neelj" / "memory"),
    )
)

# _Index digest notes get category="_Index"; sport="NBA" (cross-sport, searchable).
INDEX_CATEGORY: str = "_Index"

# ---------------------------------------------------------------------------
# Index storage paths (data/ is gitignored -- never committed)
# ---------------------------------------------------------------------------
INDEX_DIR: Path = REPO_ROOT / "data" / "index" / "vault"

# Files written by index.py (all under INDEX_DIR):
MANIFEST_PATH: Path     = INDEX_DIR / "manifest.json"      # build stats, sha map, model ids
CORPUS_PARQUET: Path    = INDEX_DIR / "corpus.parquet"     # NoteChunk fields (meta + embed_text)
VECTORS_NPY: Path       = INDEX_DIR / "vectors_dense.npy"  # float32 (N, DIM) cosine matrix
TFIDF_DENSE_PKL: Path   = INDEX_DIR / "tfidf_dense.pkl"    # fitted TfidfVectorizer (dense lane)
TFIDF_SPARSE_PKL: Path  = INDEX_DIR / "tfidf_sparse.pkl"   # fitted TfidfVectorizer (sparse/BM25)
LOCK_FILE: Path         = INDEX_DIR / ".lock"              # refresh lockfile (no concurrent runs)

# Pre-warmed per-game intel cache (single-hop, < 200 ms read; gitignored)
WARM_CACHE_DIR: Path = REPO_ROOT / "data" / "cache" / "intel_warm"

# ---------------------------------------------------------------------------
# TF-IDF vectorizer params (baseline -- sklearn only, no extra installs)
# ---------------------------------------------------------------------------
# Dense-ish cosine lane: word + bigrams, sublinear TF, cosine similarity via numpy
# Both lanes share a dependency-free stemming tokenizer (text_utils.stem_tokenizer)
# so "deters"/"deterrence", "blocking"/"blocked" collapse to a common stem. Setting
# `tokenizer` overrides `token_pattern`, so token_pattern is omitted.
TFIDF_DENSE_PARAMS: dict = {
    "tokenizer": stem_tokenizer,
    "ngram_range": (1, 2),
    "sublinear_tf": True,
    "min_df": 1,
    "max_df": 0.9,
    "max_features": 80_000,
}

# BM25-like sparse lane: stemmed unigrams, sublinear TF (BM25-like term saturation)
TFIDF_SPARSE_PARAMS: dict = {
    "tokenizer": stem_tokenizer,
    "ngram_range": (1, 1),
    "sublinear_tf": True,
    "min_df": 1,
    "max_df": 0.9,
    "max_features": 50_000,
}

# Title weighting: the H1 title is the strongest discriminator for these atomic
# concept nodes; repeat it this many times in embed_text to lift its TF-IDF mass
# (offline approximation of a field-boosted index). Tuned on the golden set.
TITLE_WEIGHT: int = 3
# Conceptual core (## Summary / ## Mechanism) is repeated this many times so its
# vocabulary outweighs the numeric Stat-Signature noise for conceptual queries.
CORE_WEIGHT: int = 2

# ---------------------------------------------------------------------------
# Pluggable embedding backend (EmbeddingBackend ABC, retrieve.py)
# ---------------------------------------------------------------------------
# "tfidf"                  -- baseline; ships now (sklearn only)
# "sentence_transformers"  -- pip install sentence-transformers; free/local
# "voyage"                 -- pip install voyageai + VOYAGE_API_KEY
EMBED_BACKEND: str = os.environ.get("RAG_EMBED_BACKEND", "tfidf")
EMBED_MODEL_ID: str = os.environ.get("RAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM: int = 384  # only used by non-tfidf backends (bge-small dim)

# ---------------------------------------------------------------------------
# Pluggable reranker (Reranker ABC, retrieve.py)
# ---------------------------------------------------------------------------
# "none"  -- identity; RRF score is the final rank; ships now
# "bge"   -- BAAI/bge-reranker-v2-m3; pip install FlagEmbedding
RERANKER_BACKEND: str = os.environ.get("RAG_RERANKER", "none")
RERANKER_MODEL_ID: str = os.environ.get(
    "RAG_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"
)

# ---------------------------------------------------------------------------
# Contextual prefix generation (contextual.py)
# ---------------------------------------------------------------------------
# "template"  -- deterministic offline prefix; ships now (no LLM, no pip)
# "haiku"     -- Haiku contextual-prefix via Anthropic Batches API; pip install anthropic
CTX_PREFIX_BACKEND: str = os.environ.get("RAG_CTX_PREFIX", "template")
CTX_MODEL_ID: str = "claude-haiku-4-5"   # only used when CTX_PREFIX_BACKEND="haiku"

# Template (CTX_PREFIX_BACKEND="template"):
# Produces a deterministic ASCII sentence that situates each note before indexing.
# Variables: {sport}, {category}, {title}, {tags}  (tags = comma-joined tag list)
# This single-line prefix is prepended to embed_text BEFORE vectorization -- it is the
# offline approximation of Anthropic Contextual Retrieval (expected ~3-5% recall lift
# vs no-prefix; Haiku-generated contextual gives ~8-10% additional lift).
CTX_TEMPLATE: str = (
    "This {sport} concept node covers '{title}' in the {category} cluster"
    " (tags: {tags}). It is a person-free, archetype-level intelligence"
    " concept in the {sport} knowledge graph."
)

# ---------------------------------------------------------------------------
# Hybrid retrieval / RRF / relevance floor
# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion (Cormack et al.): score_i = sum_lane w_lane / (k + rank_i)
RRF_K: int = 60        # rank-smoothing constant; standard default
DENSE_W: float = 0.55  # TF-IDF cosine lane weight
SPARSE_W: float = 0.45 # BM25-like sparse lane weight
# Note: sparse weight is higher than the blueprint (0.2) because without neural
# embeddings, exact keyword matching carries more signal for sport/concept queries.

# Candidate pool sizes
RETRIEVE_POOL: int = 200  # top-N from each lane fed into RRF
RERANK_POOL: int = 200    # RRF top-N that the exact-boost / reranker can reorder

# Final results returned to caller
TOP_K: int = 6

# Exact-match boost: added to RRF score (0..1) when query tokens overlap with title
# or category.  Applied after RRF, before relevance floor.
TITLE_BOOST: float = 0.6
CATEGORY_BOOST: float = 0.05

# Relevance floor = the ABSOLUTE best-raw-cosine gate (max over the two lanes). When
# the best raw cosine for a query is below this, nothing is relevant enough and the
# retriever honest-rejects ("no relevant intel found"). Calibrated on the golden set
# (golden.calibrate_tau): relevant queries peak ~0.20-0.30 raw cosine, injected
# irrelevant ones ~0.07-0.17, so a gate around here separates them.
RELEVANCE_TAU: float = 0.08

# Secondary normalized-score floor (0..1) that trims weak tail hits after RRF+boost.
RANK_FLOOR: float = 0.03

# ---------------------------------------------------------------------------
# Assembly (assemble.py)
# ---------------------------------------------------------------------------
BUNDLE_MAX_TOKENS: int = 2_000   # max tokens in the cited scouting bundle
GRAPH_HOPS: int = 1               # wikilink graph-follow depth for multi-hop pregame

# ---------------------------------------------------------------------------
# Note parsing
# ---------------------------------------------------------------------------
RELATED_SECTION_HEADER: str = "## Related"   # section containing [[wikilink]] targets
FM_DELIMITER: str = "---"                     # YAML frontmatter delimiters
MIN_BODY_CHARS: int = 50                      # skip near-empty stub notes
SNIPPET_CHARS: int = 280                      # snippet length in Hit (chars, word-boundary)
PARQUET_ENGINE: str = "pyarrow"              # pyarrow is installed; no fastparquet needed

# ---------------------------------------------------------------------------
# Hard boundary constants (tested in tests/test_boundary.py)
# ---------------------------------------------------------------------------
# Tokens that MUST NOT appear in any assembled bundle when an adversarial query asks
# for probabilities, betting edges, or ROI.  Tests assert their absence (case-insensitive).
BOUNDARY_FORBIDDEN_TOKENS: tuple = (
    "win probability",
    "win prob",
    "% chance",
    "expected value",
    " ev ",
    "+ev",
    " roi",
    "return on investment",
    "kelly",
    "bet size",
    "edge claim",
    "positive edge",
    "beat the market",
    "beat the line",
    "beat the close",
    "implied probability",
)

# Disclaimer REQUIRED in any response to an adversarial probability/bet/odds query.
NO_EDGE_DISCLAIMER: str = (
    "No edge claimed. Markets are efficient; this layer provides calibrated"
    " scouting context only, not probability estimates or betting recommendations."
)
