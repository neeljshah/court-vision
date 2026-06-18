# RAG and Retrieval State of the Art 2025-2026
_Researched 2026-06-16. Scope: embeddings, vector DBs, hybrid search, reranking, contextual retrieval, GraphRAG, agentic retrieval, and how to build a sports intelligence knowledge layer._

---

## TL;DR (highest-leverage takeaways)

- **Naive RAG is a prototype, not production.** The "chunk -> embed -> cosine -> stuff" pattern is the floor, not the ceiling. Every serious 2025-2026 deployment uses at least hybrid search + reranking on top.
- **Anthropic Contextual Retrieval is the single best documented accuracy lift.** Prepending LLM-generated situating context to each chunk before embedding + BM25 cuts retrieval failures by 47-49%. Prompt caching makes it ~69% cheaper at ingestion; zero per-query cost.
- **The production RAG pipeline is: semantic + BM25 -> RRF -> reranker -> LLM.** Retrieve 100-150 candidates via hybrid search, rerank to top 5-20 with a cross-encoder (Cohere Rerank 3.5 or BGE-Reranker), pass to LLM. This is now the consensus baseline.
- **Vector DB choice is 5-10% of RAG quality.** Chunking strategy and retrieval pipeline matter far more. Use pgvector if you already run Postgres; LanceDB if your corpus exceeds RAM; Qdrant if you need rich pre-filter metadata before search.
- **GraphRAG (Microsoft) is for narrative/relational corpora, not timeseries rows.** It builds entity-community knowledge graphs useful for "who/how are X and Y related" queries but adds heavy indexing overhead; poor fit for box-score parquets, good fit for scouting reports and player narrative intel.
- **Agentic RAG (2025-2026 frontier) routes retrieval dynamically.** An LLM agent decides whether to hit the vector store, run SQL, call a live API, or web-search, then reflects on retrieved evidence. This is the pattern that matters most for an in-game live intelligence system where data sources are heterogeneous (PBP stream, news, odds, vault notes).
- **For sports: the killer use case is "retrieve the right intel node at query time" not "store everything in one embedding space."** Structured data (box scores, PBP) belongs in SQL/Parquet; unstructured intel (scouting notes, news, vault articles) is where RAG adds value.

---

## Key capabilities / techniques

### 1. Contextual Retrieval (Anthropic, 2024 -> production 2025)
- **What:** Before embedding each chunk, call Claude with the FULL document + chunk and generate a 1-2 sentence situating context ("This chunk is from the NYK vs SAS G4 game log for Q3 ..."). Prepend that context to the chunk, THEN embed and BM25-index it.
- **Why it works:** Solves "chunk isolation" -- a chunk that says "he scored 12" without player/game context embeds badly. Contextualized chunk embeds correctly.
- **Numbers:** Pass@10 goes from 87.2% (baseline) -> 92.3% (contextual embeddings alone) -> 93.2% (+ BM25 hybrid) -> 95.3% (+ Cohere reranking). Retrieval failure rate drops 47%.
- **Cost:** One-time at ingestion. With prompt caching on the parent document, ~69% discount on tokens -> ~$1/million document tokens total. No per-query overhead.
- **API pattern:** `cache_control: {"type": "ephemeral"}` on the document in the messages array; all chunks from the same doc hit the cache on subsequent calls (cache lives 5 min, enough to process all chunks per doc in one pass).
- **Embeddings:** Anthropic cookbook uses Voyage AI embeddings (`voyage-2` or `voyage-large-2`). Any high-quality embedding model (OpenAI text-embedding-3-large, Cohere embed-v3) works for the actual vector search step.

### 2. Hybrid Search + Reciprocal Rank Fusion (RRF)
- **What:** Run semantic (dense vector) retrieval AND BM25 (sparse keyword) retrieval independently, merge ranked lists using RRF formula: score(d) = sum(1 / (k + rank_i(d))) where k=60 is common.
- **Weights:** 80% semantic / 20% BM25 is the Anthropic cookbook default. Adjust for keyword-heavy corpora (exact player names, stat types) -> lean BM25 higher.
- **Why:** Dense embeddings miss exact keyword matches (e.g., "Brunson 3PA Q4"); BM25 misses paraphrases and semantic similarity. Hybrid catches both. Consistently beats either alone.
- **Tools:** BM25 via Elasticsearch, Typesense, or pure Python `rank_bm25`. Dense via any vector DB. RRF is simple arithmetic, implement it yourself or use LangChain/LlamaIndex built-ins.

### 3. Reranking (cross-encoder)
- **What:** After hybrid retrieval returns 100-150 candidates, a cross-encoder model scores (query, doc) pairs jointly (not via cached embeddings), so it can see full interaction. Keep top 5-20 for LLM context.
- **Models:** Cohere Rerank 3.5 (API, ~$0.002/query for 100 docs), BGE-Reranker-Large or BGE-Reranker-v2-m3 (self-hosted, free), Jina Reranker v2.
- **Latency:** 100-200ms added per query. Acceptable for non-real-time; too slow for sub-100ms live overlays.
- **ColBERT v2:** Alternative -- late interaction model that approximates cross-encoder accuracy at bi-encoder speed. RAGatouille library wraps it. Good for latency-sensitive paths.

### 4. Chunking strategies
- **Fixed-size:** Simple (e.g., 512 tokens, 20% overlap). Baseline. Fragile for structured game logs.
- **Semantic chunking:** Embed sentences, split at embedding-distance breakpoints (>90th percentile shift). Keeps related content together. Better for narrative scouting reports.
- **Parent-child / small-to-big:** Embed small "child" chunks (100 tokens) for precision; on hit, retrieve parent page/section (1000 tokens) for LLM context. Best of both: precise retrieval, rich generation context.
- **Document-level summary index:** For each doc, store a high-level summary embedding for topic routing, then drill into chunk index. Two-tier retrieval.

### 5. Query transformation
- **HyDE (Hypothetical Document Embeddings):** Generate a hypothetical answer to the query, embed THAT, retrieve against it. Helps when the query ("will Wembanyama foul out?") is phrased differently from the stored document ("Wemby averages 4.2 fouls/36 in playoffs").
- **Multi-query expansion:** Generate 3-5 paraphrases of the query, retrieve for each, union results. Improves recall for ambiguous or short queries.
- **Step-back prompting:** Abstract the query up one level before retrieving (e.g., "in-game foul rate" -> "player foul tendency profiles"). Useful for strategic/analytical questions.

### 6. GraphRAG (Microsoft, github.com/microsoft/graphrag)
- **What:** Processes a text corpus through entity extraction, relationship mapping, and LLM-summarized community detection. Builds a hierarchical knowledge graph (leaf entities -> communities -> global summaries). Queries can target local (specific entity) or global (cross-community synthesis) scopes.
- **Strengths:** Excellent for "how are X and Y related", thematic synthesis, discovery over dense narrative corpora (scouting databases, coaching theory docs).
- **Weaknesses:** Expensive to build (many LLM calls per document). Not designed for structured/tabular data. Overkill for query types answerable by direct SQL.
- **When to use:** Rich unstructured narrative corpora (team scheme notes, player career arcs, news articles) where relational queries matter. NOT for box-score parquets.
- **Alternative - Graphiti (Neo4j):** Lighter-weight temporal knowledge graph designed for agentic memory. Better fit for an incrementally updated sports intel layer.

### 7. Agentic RAG
- **What:** An LLM agent (ReAct, LangGraph, or Claude tool-use loop) decides at inference time WHICH retrieval tool to call: vector store, SQL DB, web search, live API, code executor. Iterates: retrieve -> inspect -> decide if sufficient -> retrieve more or generate.
- **Patterns:** ReAct (Reason + Act), Self-Ask (decompose multi-hop into sub-questions), Search-o1 (interleave generation with retrieval).
- **Key benefit:** Multi-source heterogeneous data. A sports query ("what is the live win probability given current score and Brunson foul trouble?") requires: (a) structured PBP state from SQL, (b) unstructured foul-tendency intel from vault embeddings, (c) calibrated model output. An agentic router handles all three.
- **Tools:** LangGraph (stateful agent loops), LlamaIndex Agentic RAG, Claude tool-use natively supports this pattern.

### 8. Vector DB landscape 2026

| DB | Best fit | Scale sweet spot | Notes |
|----|----------|-----------------|-------|
| pgvector 0.9 | Existing Postgres stack | < 2-3M vectors | HNSW added in 0.5; ~5-15K QPS on single instance; "adequate" not fastest |
| LanceDB | Embedded, disk-based, batch updates | 1M+ vectors, larger-than-RAM | Lance columnar format; strong for analytics joins with parquet data |
| Qdrant | Rich metadata pre-filtering | Any scale self-hosted | Applies filters BEFORE vector search (faster + more accurate); good for multi-sport routing |
| Chroma | Prototyping, small corpora | < 1M vectors | Simplest API; in-process; not production-hardened at scale |
| Pinecone | Fully managed, no ops overhead | Any | 5-10x more expensive than self-hosted; not worth it solo project |
| Milvus | Extreme scale | 100B+ vectors | Overkill for this project |

**Key insight from benchmarks:** At the scale of this project (hundreds of thousands of vault notes + game intel chunks), pgvector or LanceDB are both more than sufficient. The retrieval pipeline quality (contextual embeddings, hybrid, reranking) dominates DB choice.

### 9. Evaluation framework (RAGAS)
- **Metrics:** Faithfulness (does the answer match the retrieved context?), Answer Relevancy, Context Precision, Context Recall.
- **Target baselines from 2026 production systems:** Faithfulness ~0.92, Answer Relevancy ~0.88, Context Precision ~0.85, Context Recall ~0.79.
- **For this project:** The analog to "retrieval failure rate" is: given a query about player X's foul tendency in Q4, does the correct vault intel node get retrieved in the top-5?

---

## How THIS project should use it

This project already has a rich structured Obsidian vault (660 player notes, 30 team notes, scheme intel, edge maps) plus structured parquet data (box scores, PBP, signals). The RAG opportunity is specifically the unstructured + semi-structured intel layer.

**1. Build a contextual embeddings index over the vault.**
The Obsidian markdown notes are perfect RAG documents. Run Anthropic Contextual Retrieval at ingestion time over `vault/_Organized/` (player notes, team notes, scheme docs, edge maps). One-time cost, prompt-cached. This gives the LLM synthesizer the right intel node when asked "what does our data say about Wemby in foul trouble late in games?"

**2. Use LanceDB (embedded, no server) as the vector store.**
LanceDB reads/writes Lance files alongside your existing parquets. No separate process to manage. Supports hybrid search natively in recent versions. Natural fit for a solo project that already has a parquet-heavy data layer. pgvector is also fine if you ever add a Postgres instance for structured data.

**3. Implement the full pipeline: contextual embed -> BM25 hybrid -> rerank.**
Use `rank_bm25` for the keyword leg. Merge with RRF (80/20 weights). For production queries (the LLM synthesizer calls in `market_intelligence.py`), rerank top-50 with `bge-reranker-large` (self-hosted, free, no API cost) before passing to Claude. This is the pattern that gives 47% fewer retrieval failures -- directly improving LLM synthesis quality.

**4. Agentic routing is the right architecture for in-game queries.**
The in-game query "given Q3 score=89-84, Brunson on 4 fouls, what is our projected win probability and what does our intel say about his foul behavior in this situation?" requires:
  - Structured PBP state: SQL / parquet lookup (not RAG)
  - Calibrated model output: existing sim call (not RAG)
  - Vault intel: vector retrieval on player foul-tendency and Q4 usage notes
  - News freshness: optional web search tool
An agentic tool-use loop in Claude (tool_use in the messages API) that routes these sub-queries to the right retrieval function is cleaner and more accurate than trying to embed everything together.

**5. Use GraphRAG only for the scheme/playstyle layer, not box scores.**
The scheme intel docs, coaching philosophy notes, and archetype clusters are narrative and relational -- the exact GraphRAG sweet spot. Extract entities (team scheme, coach tendencies, matchup clusters) and relationships, build a lightweight Neo4j or NetworkX graph over them. For the box-score / signal / PBP data, stay with SQL + Parquet.

**6. Separate structured from unstructured retrieval cleanly.**
- Structured (signals, PBP, box scores, model outputs): SQL / Parquet / direct Python -- NO embedding search needed.
- Semi-structured (vault notes, atlas markdown): Contextual embeddings + hybrid search.
- External (news, injury reports): Agentic web-search tool at query time, not pre-indexed.

**7. Calibration discipline applies to the LLM synthesis layer too.**
If the RAG system surfaces an intel node ("Brunson shoots 38% when fatigued in Q4"), the LLM must treat it as a soft prior -- not override the calibrated model probability. The retrieval layer feeds the scouting synthesis, not the betting number. Keep that boundary explicit in the system prompt.

**8. Embedding model recommendation for this project.**
Voyage AI `voyage-2` (what the Anthropic cookbook uses) or OpenAI `text-embedding-3-large` (1536-dim, strong performance, cheap). For sports-domain text (player names, stat jargon, team names), neither is fine-tuned but both handle it adequately. Avoid models < 768-dim for nuanced scouting text.

---

## Gotchas / limits

- **Contextual retrieval costs tokens at ingestion.** With the full vault (660+ player notes), budget the Claude API call carefully. Use `haiku-3` for context generation (fastest/cheapest); the context description does NOT need a powerful model.
- **Reranking adds 100-200ms latency.** Fine for async pregame synthesis; too slow for a sub-100ms live overlay tick. Separate the latency budget: pre-compute contextual embeddings once; retrieve+rerank only for explicit queries (not every websocket tick).
- **GraphRAG is expensive to build.** Microsoft's pipeline makes many LLM calls per document for entity extraction. For the vault's 660+ notes, this could be 5-10K Claude API calls. Run only over the highest-value narrative docs (scheme notes, coaching files). Not worth it over structured data.
- **Hybrid BM25 + vector requires two indexes to keep in sync.** When you add a new game or update a vault note, you must update BOTH the vector index AND the BM25 index. Build a single ingestion pipeline that writes both atomically.
- **Embedding drift.** If you change the embedding model later, all stored vectors become stale. Pin the model version and re-embed on model changes.
- **RAG does NOT improve calibration of numeric predictions.** It improves the quality of the LLM's reasoning over unstructured intel. The calibrated probability (Brier, log-loss) is still owned by the statistical model + walk-forward gating pipeline. RAG is a signal-enrichment layer for qualitative synthesis, not a numerical predictor.
- **Sports-specific chunk boundary problem.** A player game log in tabular form embeds poorly as a blob. Prefer row-level chunks with rich metadata (player_id, game_date, opponent, stat_type) stored as filter fields, and use metadata pre-filtering (Qdrant's strength) to narrow the vector search before scoring. Do not try to embed a 5000-row parquet as a RAG document.
- **Agentic retrieval loops can hallucinate "sufficient evidence."** The LLM agent may decide it has enough context when it does not. Add an explicit evidence-grounding check in the system prompt: require the model to cite the vault note or data source for any claim.

---

## Sources

- [Enhancing RAG with Contextual Retrieval - Anthropic Claude Cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide)
- [RAG Is Not Dead: Advanced Retrieval Patterns That Actually Work in 2026 - DEV Community](https://dev.to/young_gao/rag-is-not-dead-advanced-retrieval-patterns-that-actually-work-in-2026-2gbo)
- [Vector Database Comparison 2026: ChromaDB vs Qdrant vs pgvector vs Pinecone vs LanceDB - 4xxi](https://4xxi.com/articles/vector-database-comparison/)
- [Vector Database Benchmarks 2026: pgvector 0.9, Qdrant, Weaviate, Milvus, LanceDB - CallSphere Blog](https://callsphere.ai/blog/vector-database-benchmarks-2026-pgvector-qdrant-weaviate-milvus-lancedb)
- [Project GraphRAG - Microsoft Research](https://www.microsoft.com/en-us/research/project/graphrag/)
- [GraphRAG GitHub - microsoft/graphrag](https://github.com/microsoft/graphrag)
- [A Hybrid Retrieval and Reranking Framework for Evidence-Grounded RAG - arXiv 2605.01664](https://arxiv.org/abs/2605.01664)
- [Optimizing RAG with Hybrid Search and Reranking - Superlinked VectorHub](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [Contextual Retrieval Summary - Medium / Seahorse Technologies](https://medium.com/@seahorse.technologies.sl/contextual-retrieval-summary-495b2ce91234)
- [Agentic RAG Explained - Machine Learning Mastery](https://machinelearningmastery.com/agentic-rag-explained-in-3-levels-of-difficulty/)
- [Survey on Reasoning Agentic RAG - ACL Anthology / IJCNLP 2025](https://aclanthology.org/2025.findings-ijcnlp.122.pdf)
- [Graphiti: Knowledge Graph Memory for Agentic World - Neo4j Blog](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
