# Vault Knowledge / Retrieval Layer (sports intel RAG)

_Design doc, 2026-06-16. For: roadmap L3 prep (LLM-as-orchestrator + wordalisation) and item 7 (LLM intelligence layer); feeds X1 (freshness pipeline) and L3 board narration. Build location: scripts/platformkit/knowledge/ + domains/<sport> hooks; MCP server under scripts/mcp_server/. No src/ kernel/ api/ edits._

## Goal + done-criteria

A Claude agent must answer "what do we know about X" and assemble a pregame scouting-context bundle WITHOUT the human or agent loading the whole vault into context. The vault today = 4113 person-free concept notes under vault/_Organized/{NBA,MLB,Soccer,Tennis}/ (avg ~1.8KB, ~7.4MB total) plus the _Index/ digests and (local) edge maps + wave notes. This layer indexes them and exposes hybrid + reranked retrieval as (a) a Python library, (b) an MCP tool surface.

HARD BOUNDARY (binding): this layer informs SYNTHESIS and NARRATION only. It never touches a probability. The calibrated number is owned by the sim / walk-forward pipeline. Any retrieved intel that reaches the prediction chain may only become a BOUNDED, leak-flagged multiplier on an existing sim knob (per invariant 7), and only via the human-gated scheme-prior path -- the retrieval layer itself emits text + citations, nothing numeric that enters a Brier-scored output.

Done = "shipped + validated" means, measurably:
1. Index build over all 4 sports completes from cold in < 10 min on the local box; incremental refresh of changed notes in < 30s.
2. Retrieval quality: on a git-tracked golden set of >= 120 (query -> correct note) pairs (>= 30/sport), the correct note is in top-5 for >= 90% of queries (recall@5), measured leak-free (queries written without seeing the index). This mirrors the contextual-retrieval Pass@k target (baseline ~87% -> contextual+hybrid+rerank ~95%).
3. Pregame context assembly: given (sport, home_id, away_id, optional question), returns a citation-grounded bundle (<= 2K tokens) in < 30s (multi-hop pregame budget) with every claim carrying a [[note]] citation.
4. Live single-hop path returns from a pre-warmed per-game cache in < 200ms (no rerank, no LLM in the hot loop).
5. A passing per-file test for each module; an MCP server that `claude mcp list` shows healthy and that answers `vault_search` + `assemble_pregame_context`.
6. An honest-reject answer is first-class: when nothing clears a relevance floor, the tool returns "no relevant intel found" rather than fabricating.

## Design

### Corpus model -- one chunk per node (no sub-chunking)
The vault notes are already atomic concept nodes at ~1.8KB. Do NOT fixed-size-split them; the natural unit IS the chunk (parent-child collapses to parent-only here). Each note -> one record:

```
NoteChunk:
  note_id        # stable: sport + relpath, e.g. "NBA/AdaptabilityVersatility/adaptive_pace_role_flexibility"
  sport          # NBA|MLB|Soccer|Tennis (from path)
  category       # folder name, e.g. "AdaptabilityVersatility"
  title          # H1
  tags           # YAML frontmatter tags[]
  body           # full markdown minus frontmatter
  related        # [[wikilink]] targets parsed from ## Related -> graph edges
  contextual     # LLM-generated 1-2 sentence situating prefix (Anthropic Contextual Retrieval)
  embed_text     # contextual + "\n" + title + "\n" + body  (what gets embedded + BM25-indexed)
  mtime, content_sha256, embedded_with (model+version)
```

_Index/ digests (_Brain, _Cohesive_Index, _Cross_Sport_Transfer, etc.) are indexed too, tagged category="_Index", so "what do we know about NBA pace overall" routes to the digest, not 200 leaf nodes.

### Contextual prefix (the single biggest documented lift)
For each note, one Haiku call: prompt = the note body + its category + sport, ask for a 1-2 sentence situating sentence ("This NBA concept node defines pace-role flexibility; it belongs to the AdaptabilityVersatility cluster and relates to lineup morphing and scheme-agnostic fit."). Prepend to embed_text before embedding AND before BM25 indexing. Notes are tiny so no per-doc prompt cache is needed across chunks; batch via the Message Batches API (50% off) for the one-time build. Store the prefix so refresh only regenerates it when content_sha256 changes.

### Vector store choice -- LanceDB (embedded)
Decision: **LanceDB**. Rationale against the brief's trade-off table:
- pgvector: requires a running Postgres instance; this project has none and the data layer is parquet-first. Adds an ops surface for ~4K vectors -- not worth it.
- Chroma: fine at this scale but in-process state is fragile and it is "not production-hardened"; weaker for the analytics-join story.
- Qdrant: best metadata pre-filter, but needs a server; overkill for 4K vectors.
- **LanceDB**: embedded, no server, writes Lance/columnar files that sit next to the existing parquets, native hybrid search + reranker hooks in recent versions, larger-than-RAM ready if the vault grows 10x. Matches a solo, parquet-heavy, no-server stack exactly (brief recommendation #2).

Scale note: 4113 vectors is tiny; DB choice is ~5-10% of quality (brief). LanceDB chosen for zero-ops, not speed.

### Retrieval pipeline -- hybrid -> RRF -> rerank
```
query
  -> dense: embed(query) -> LanceDB top-100 (cosine), metadata pre-filter on sport (+ optional category)
  -> sparse: rank_bm25 over embed_text -> top-100
  -> RRF merge (k=60, 80% dense / 20% sparse weight; lean BM25 higher when query has exact title/category tokens)
  -> rerank top-50 with BAAI/bge-reranker-v2-m3 (self-hosted, free, ~100-200ms) -> top-k (default 6)
  -> relevance floor: drop reranker scores below tau (calibrate tau on the golden set); if none survive -> honest-reject
```
The reranker model is downloaded once to data/models/rerankers/ (gitignored) and loaded lazily; CPU is fine at this volume.

### Two query paths
- **Pregame (multi-hop, 10-30s budget):** agentic. A Claude tool-use loop may: (1) vault_search on the matchup theme, (2) follow `related` graph edges one hop to pull adjacent concepts, (3) optionally vault_search a second sub-question (Self-Ask decomposition), (4) assemble a cited bundle. Multi-hop + graph-follow is allowed because pregame is async.
- **Live (single-hop, pre-warmed):** at game load, assemble_pregame_context is run once and the resulting bundle + the top intel nodes for both teams are cached to a per-game JSON (data/cache/intel_warm/<game_id>.json, gitignored). The live tick reads that cache only -- NO embedding, NO rerank, NO LLM in the hot loop (keeps the sub-200ms / sub-100ms-overlay budget from the rag brief gotcha).

### Directory layout (all under ALLOWED paths)
```
scripts/platformkit/knowledge/
  __init__.py
  config.py            # paths, model ids, weights, tau, top_k  (<=80 LOC)
  ingest.py            # walk vault -> NoteChunk records (parse frontmatter, H1, Related)  (<=200)
  contextual.py        # Haiku contextual-prefix generation (Batches API)  (<=180)
  index.py             # build/refresh LanceDB table + bm25 pickle; sha-based incremental  (<=220)
  retrieve.py          # hybrid + RRF + rerank + relevance floor -> List[Hit]  (<=240)
  assemble.py          # pregame context assembly (agentic multi-hop, graph follow)  (<=240)
  warm.py              # pre-warm per-game live cache  (<=120)
  tests/
    test_ingest.py  test_retrieve_rrf.py  test_assemble.py  test_warm.py   # per-file only
scripts/mcp_server/
  vault_knowledge.py   # stdio MCP server exposing the tools below  (<=260)
data/index/vault/      # LanceDB table + bm25.pkl + manifest.json   (GITIGNORED)
data/cache/intel_warm/ # per-game warmed bundles  (GITIGNORED)
```

### MCP framing (ties to the mcp-server blueprint)
A local **stdio** MCP server (no auth, least-privilege, points only at data/index + vault read-only). Primitives:
- Tool `vault_search(sport, query, category?, top_k=6)` -> ranked hits {note_id, title, score, snippet, citation}.
- Tool `assemble_pregame_context(sport, home_id, away_id, question?)` -> {bundle_markdown, citations[], reject:bool}.
- Tool `related_nodes(note_id, hops=1)` -> graph neighbors (uses parsed wikilinks).
- Resource `vault://index/manifest` -> build stats (note count, model, last refresh) so any agent sees freshness.
- Resource `vault://note/{note_id}` -> raw note text on demand (read-only).

This is exactly the "wrap the vault as a queryable tool" piece; it composes with the predictor MCP server from the sibling blueprint -- both run as stdio entries in .claude/settings.json mcpServers. **Adding the mcpServers block to .claude/settings.json is the only shared-config touch -> mark human-confirm before applying** (the active branch may also edit settings.json). Ship the server module + a copy-paste settings snippet; do not edit settings.json in this build.

### What it feeds
- **X1 freshness pipeline:** assemble_pregame_context is the "agentic RAG for pre-game context assembly" the freshness brief calls for -- it gathers the relevant concept nodes (e.g. vacated-load, usage-role, rest/b2b splits) that the structured injury extractor then maps onto specific players. Retrieval supplies the qualitative frame; the extractor + vacated-load model supply the numbers.
- **L3 wordalisation on the board:** the cited bundle is the raw material for the one-paragraph scouting narrative. The sim computes feature contributions; retrieval supplies the language and the [[note]] grounding so the narrative is auditable, not hallucinated.

## Implementation sketch

config.py
```python
SPORTS = ("NBA", "MLB", "Soccer", "Tennis")
VAULT = "vault/_Organized"
INDEX_DIR = "data/index/vault"
EMBED_MODEL = "voyage-3"          # or text-embedding-3-large; pin version in manifest
CTX_MODEL = "claude-haiku-4-5"    # cheap contextual prefixes
RERANKER = "BAAI/bge-reranker-v2-m3"
RRF_K = 60; DENSE_W = 0.8; SPARSE_W = 0.2
TOP_K = 6; RERANK_POOL = 50; RELEVANCE_TAU = 0.15   # calibrate on golden set
```

ingest.py (core)
```python
def parse_note(path: Path, sport: str) -> NoteChunk:
    raw = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(raw)            # YAML between leading ---
    title = first_h1(body)
    related = re.findall(r"\[\[([^|\]]+)", section(body, "Related"))
    return NoteChunk(
        note_id=f"{sport}/{path.relative_to(Path(VAULT)/sport).with_suffix('')}".replace("\\","/"),
        sport=sport, category=path.parent.name, title=title,
        tags=fm.get("tags", []), body=body, related=related,
        content_sha256=sha256(raw), mtime=path.stat().st_mtime)
```

retrieve.py (the pipeline)
```python
def retrieve(sport, query, category=None, top_k=TOP_K) -> list[Hit]:
    qv = embed([query])[0]
    flt = f"sport == '{sport}'" + (f" AND category == '{category}'" if category else "")
    dense = table.search(qv).where(flt).limit(100).to_list()
    sparse = bm25_topk(query, sport_filter=sport, n=100)
    fused = rrf(dense, sparse, k=RRF_K, w=(DENSE_W, SPARSE_W))
    pool = fused[:RERANK_POOL]
    scored = reranker.compute_score([(query, h.embed_text) for h in pool])
    ranked = sorted(zip(pool, scored), key=lambda x: -x[1])
    hits = [Hit(note_id=h.note_id, title=h.title, score=s, snippet=h.summary)
            for h, s in ranked if s >= RELEVANCE_TAU][:top_k]
    return hits   # empty list -> caller emits honest-reject
```

assemble.py (pregame, agentic, multi-hop)
```python
SYSTEM = ("You assemble SCOUTING CONTEXT from retrieved vault notes. "
          "Every claim MUST cite a [[note_id]]. You do NOT output probabilities, "
          "odds, or numeric edges. If retrieval returns nothing relevant, say "
          "'No relevant intel found.' Markets are efficient; calibration is the goal; "
          "claim no edge.")
def assemble_pregame_context(sport, home_id, away_id, question=None) -> Bundle:
    # tool-use loop: model calls vault_search / related_nodes up to N_HOPS times
    # seed queries from team identity + question; follow graph edges 1 hop
    # then write a <=2K-token cited bundle. Sim/number tools are NOT exposed here.
    ...
```

MCP server (stdio, Python SDK)
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("vault-knowledge")

@mcp.tool()
def vault_search(sport: str, query: str, category: str | None = None, top_k: int = 6) -> list[dict]:
    return [h.__dict__ for h in retrieve(sport, query, category, top_k)]

@mcp.tool()
def assemble_pregame_context(sport: str, home_id: str, away_id: str, question: str = "") -> dict:
    b = assemble(sport, home_id, away_id, question or None)
    return {"bundle": b.markdown, "citations": b.citations, "reject": b.reject}

if __name__ == "__main__":
    mcp.run()   # stdio
```

settings.json snippet (HUMAN-CONFIRM before applying -- do not auto-edit)
```json
{ "mcpServers": {
    "vault-knowledge": {
      "command": "python",
      "args": ["scripts/mcp_server/vault_knowledge.py"],
      "env": {"PYTHONPATH": "."}
    } } }
```

Incremental refresh (CronCreate / headless -p, runs after vault rebuilds):
```
python -m scripts.platformkit.knowledge.index --refresh   # sha-diff -> re-embed only changed notes, rebuild bm25
```

## Validation plan

This layer produces NO probability, so the leak-free walk-forward Brier machinery does not apply to its OUTPUT. It is validated as a RETRIEVAL system; the boundary itself is also a tested invariant.

1. **Retrieval quality (recall@k), >= 2 corpora.** Golden set tests/fixtures/intel_golden.jsonl: >= 120 (sport, query, expected_note_id) rows, >= 30 each for NBA, MLB, Soccer, Tennis (the >= 2 corpora rule -> here >= 4). Queries authored WITHOUT looking at the index (avoid query-leak). Metric: recall@5 and MRR. Threshold: recall@5 >= 0.90 overall AND >= 0.85 on every sport (no sport silently broken). Report a 95% CI via bootstrap over queries; clustering not needed (independent queries). Ablation table (baseline dense-only -> +BM25 -> +contextual -> +rerank) to confirm each stage helps, matching the brief's documented ladder.
2. **Reranker floor calibration.** Sweep RELEVANCE_TAU on a held-out half of the golden set; pick tau maximizing F1 of (relevant vs irrelevant) so honest-reject fires correctly. Validate on the other half (held-out, not the tuning half).
3. **Latency SLOs.** Assert pregame assemble p50 < 30s, p95 < 45s over the golden queries; live warm-cache read p95 < 200ms. Measured on the local box (RTX 4060), CPU reranker.
4. **Boundary test (the invariant as a test).** test_boundary.py: assert the MCP tool registry exposes NO numeric/predict tool; assert assemble() system prompt forbids probabilities; feed an adversarial query ("what's the win probability and give me a bet") and assert the bundle contains no probability/odds/ROI token and includes the no-edge disclaimer. This is the leak guard for the LLM layer (roadmap risk row "LLM number leaks into the chain").
5. **Faithfulness (RAGAS-style, sampled).** On 30 sampled bundles, an LLM-judge (different model, adversarial) checks every claim is supported by a cited note; target faithfulness >= 0.92. Honest-reject cases must NOT fabricate.
6. **Refresh correctness.** Touch one note, run --refresh, assert only that note re-embedded (manifest sha diff), bm25 rebuilt, recall unchanged elsewhere.

No DM test / Shin-devig here -- those belong to the prediction pipeline this layer never enters. Stating that explicitly is part of the honest discipline.

## Effort + sequencing

Rough total ~6-8 days solo-with-Claude.
1. (1d) ingest.py + tests; parse all 4113 notes, confirm frontmatter/H1/Related parse clean (17/17 sampled had frontmatter; handle the minority without gracefully).
2. (1.5d) index.py + LanceDB table + bm25; embed without contextual prefix first (baseline). Build the golden set in parallel (Claude drafts candidate queries from note titles; human spot-checks for leak).
3. (1d) retrieve.py: hybrid + RRF + rerank; run the ablation; calibrate tau. -> gives validation items 1-2.
4. (1d) contextual.py: Haiku prefixes via Batches API; re-embed; confirm the +contextual lift on the golden set.
5. (1.5d) assemble.py agentic multi-hop + boundary tests + faithfulness sample.
6. (1d) warm.py + MCP server + settings snippet (human-confirm to wire).

Dependencies: nothing blocks step 1. Contextual prefix (step 4) depends on index (2) for re-embed but the pipeline (3) can validate baseline first -- do contextual AFTER you have a baseline number to beat (so the lift is measured, not assumed). MCP wrap (6) depends on retrieve+assemble. This is L3 PREP, so it can land before the L3 orchestrator/wordalisation work; X1 (freshness) consumes assemble() once it exists.

Avoid collision with the active fullsend branch: all new files live under scripts/platformkit/knowledge/ and scripts/mcp_server/ (new dirs) -- no overlap with in-game/pregame src edits. The ONLY shared file is .claude/settings.json (mcpServers) -> deliver as a snippet, human applies.

## Gotchas + how the honest discipline applies

- **The boundary is the whole point.** Retrieval feeds synthesis/narration, NEVER the probability (invariant). If an intel node ever needs to influence the number, it goes through the human-gated scheme_prior path as a bounded, leak-flagged multiplier on an existing sim knob -- not through this layer. test_boundary.py enforces it.
- **Person-free vault.** Notes are concept/archetype nodes, not player dossiers (by design, per [[feedback-graph-playstyles-not-people]]). "What do we know about Wemby" must be answered as "which playstyle/archetype concepts apply" -- the agent maps a player to archetypes, then retrieves concepts. Do not reintroduce person-keyed notes.
- **Two indexes must stay in sync** (brief gotcha): index.py writes the LanceDB vectors AND the bm25 pickle atomically in one --refresh pass; never update one without the other or hybrid silently rots.
- **Embedding drift:** pin EMBED_MODEL + version in manifest.json; on model change, full re-embed (it's only 4K notes, < 5 min). A stale-model mismatch between query and stored vectors is a silent recall killer.
- **No concurrent index rebuilds** (matches the no-concurrent-brain-rebuilds memory): serialize --refresh; never run it while the brain pipeline is rmtree-ing _Organized. Take a simple lockfile in data/index/vault/.lock.
- **Live latency:** rerank + LLM are async-only; the live path reads the pre-warmed JSON. Putting the agentic loop in the websocket tick would blow the budget (rag brief gotcha) -- warm.py exists precisely to prevent that.
- **Honest-reject is a feature, not a bug:** empty retrieval -> "no relevant intel found", surfaced as a first-class UI state (mirrors roadmap section 4 move #2). The agent must not pad with generic basketball truisms; the faithfulness check + boundary test catch fabrication.
- **Cost discipline:** contextual prefixes use Haiku via Batches API (50% off), one-time; per-query cost is local-only (self-hosted reranker, local LanceDB) so there is no per-query API spend in the hot loop.
- **cwd flakiness:** prefix every bash invocation with `cd /c/Users/neelj/nba-ai-system &&`; the MCP server sets PYTHONPATH=. and is launched from repo root.
- **ASCII only** in all generated notes/prefixes (cp1252 stdout); no unicode arrows in stored text.
