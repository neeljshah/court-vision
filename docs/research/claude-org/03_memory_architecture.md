# Long-Lived Agent Memory Architecture

Research date: 2026-06-17. Goal: architect agent memory + knowledge bases so they stay
SMALL, RELEVANT, and COMPOUNDING (not bloated). ASCII-only.

This doc captures cross-source patterns and ends with a concrete recommended architecture
for a memory directory that is currently OVER its 24.4KB index limit (~80 files).

---

## 1. The core problem: memory is cumulative, so errors compound

Unlike static RAG, an evolving memory system carries errors forward. Mistakes are
cumulative and persistent across three stages: ingestion -> consolidation -> retrieval.
Three named failure modes:

- Semantic drift: repeated summarization gradually distorts facts.
- Procedural drift: suboptimal workflows get reinforced because they are "remembered".
- Hallucination internalization: a wrong fact gets stored and later treated as ground truth.
- Memory staleness: an accurate-but-outdated fact becomes "confidently wrong"
  (e.g. old employer, retired model). Recency must be a ranking signal, not just a store.

Implication: the index/master file is the highest-leverage and highest-risk surface.
Keep it short, keep it true, and have an explicit lifecycle for every entry.

Sources: arxiv 2603.11768 (SSGM governance), mem0.ai state-of-2026.

---

## 2. Tiering: HOT / WARM / COLD (the OS memory-hierarchy analogy)

The dominant production pattern is a three-tier hierarchy mirroring RAM / disk / cold storage.
Agents actively manage their own tiers via function calls (decide what to retain, summarize,
archive) -- they are NOT passive recipients of injected context (MemGPT/Letta lineage).

| Tier | Analogy | Contents | Loaded? | Size budget | Lifecycle |
|------|---------|----------|---------|-------------|-----------|
| HOT  | RAM     | active task state, open questions, immediate action items | always in context | <500 tokens target, hard trigger at 800 | pruned aggressively the instant a task completes |
| WARM | disk    | stable facts: preferences, conventions, invariants, tool/config, recurring interests | retrieved on demand | 1,000-3,000 tokens | never arbitrarily deleted; dedup + supersede; demote to COLD only when historical |
| COLD | archive | completed milestones, historical decisions, lessons learned, old session logs | NOT in active retrieval | bounded by summarization | detail progressively replaced by summary; a 5-day project -> one paragraph |

Promotion / demotion rules (from the HOT/WARM/COLD source):
- -> HOT: anything needed within the next 2-3 interaction turns.
- -> WARM: a newly discovered STABLE user/system fact.
- -> COLD: a completed project's high-level summary.
- -> DELETE: granular detail already captured in a summary; expired temporary data.

Reported production effect: active context dropping from 8k-15k tokens to 1.5k-3k tokens,
per-session cost to ~0.25-0.35x baseline, while preserving continuity.

Sources: clawrxiv 2603.00037 (HOT/WARM/COLD), arxiv 2603.07670 (mechanisms survey),
atlan.com agent-memory-architectures, apxml multi-agent course.

---

## 3. File organization: atomic notes + a thin index (Zettelkasten for agents)

A-Mem (NeurIPS 2025) is the reference: organize memories as interconnected atomic notes
following Zettelkasten, with dynamic indexing and linking, and adjust memory strength over
time via an Ebbinghaus forgetting-curve weighting (time + significance).

Concrete Zettelkasten rules that transfer directly to an agent memory dir:

- ONE fact / idea / concept per note file. Atomic = concise, focused, linkable.
- The INDEX is a navigation layer, not a content store. It points; it does not contain.
- Link only when the connection is MEANINGFUL, and state WHY (link context).
  A note with ~50 links almost certainly has too many.
- Frontmatter (YAML) carries metadata: tags, status, timestamps, links. This gives
  structure WITHOUT a rigid hierarchy, so the graph can grow organically.
- Growth that lives in the note graph (not the index) is what prevents index bloat.

Claude Code's native auto-memory model matches this exactly:
- `MEMORY.md` is an INDEX, loaded every session, capped at first 200 lines OR 25KB
  (whichever comes first). Content beyond the cap is silently NOT loaded.
- Topic files (`debugging.md`, `api-conventions.md`, ...) are NOT loaded at startup;
  Claude reads them on demand. This is exactly the WARM/COLD lazy-load tier.
- Keep `MEMORY.md` concise by moving detail into topic files.

Sources: arxiv 2502.12110 (A-Mem), zettelkasten.de atomicity guide, adobe/getrecall
zettelkasten, code.claude.com/docs/en/memory.

---

## 4. What to put in the index vs. files (Claude Code official guidance)

From the Claude Code docs and community best-practice:

- The root index should stay SMALL and STABLE. Anything deep, topic-specific,
  path-specific, or only-sometimes-relevant goes into a separate file / rule / skill.
- Target under 200 lines per CLAUDE.md-style file; longer files reduce ADHERENCE,
  not just cost. Practical high-signal range cited: 80-120 lines.
- Specific beats vague: "Use 2-space indentation" > "format code properly".
  Personality/think-step-by-step filler wastes the instruction budget and prevents
  no specific mistakes. Models reliably track ~150-200 distinct instructions total;
  the harness already spends ~50, so the index effectively has ~100-150 usable slots.
- Only write down what the agent would get WRONG without it (mistake-driven capture):
  add an entry when the agent repeats a mistake, a review catches a known thing, or
  you re-type the same correction.
- Imports (`@path`) help ORGANIZATION but do NOT save context -- imported files expand
  inline at launch. Lazy-loaded topic files (read on demand) are what actually save tokens.
- Use block-level HTML comments for human-maintainer notes; they are stripped before
  injection (zero token cost).

Sources: code.claude.com/docs/en/memory, medium (Bijit Ghosh CLAUDE.md guide),
orchestrator.dev agent-memory-2026.

---

## 5. Dedup, consolidation, and conflict resolution (the Mem0 ADD/UPDATE/DELETE/NOOP loop)

Mem0's two-phase pipeline is the cleanest dedup/consolidation pattern:

1. EXTRACT: pull salient facts from the new turn + relevant history.
2. UPDATE: for each candidate fact, retrieve semantically-similar existing memories
   (vector similarity), then have the LLM choose ONE operation:
   - ADD    -> genuinely new info (no semantic equivalent exists).
   - UPDATE -> augment/refine an existing memory with newer/finer detail.
   - DELETE -> remove a memory the new fact CONTRADICTS.
   - NOOP   -> fact already present or irrelevant; do nothing.

This four-way decision is the mechanism that keeps the store from growing on every
interaction. Apply it whenever a new "remember this" arrives: search first, then decide.

Conflict handling refinement (Mem0g graph variant): on contradiction, MARK the old
relationship invalid rather than hard-deleting it, preserving temporal reasoning
("X was true until date D"). Useful when historical truth still matters.

Retrieval/recall design that keeps context minimal:
- Multi-signal fused retrieval: semantic (vectors) + keyword (BM25) + entity match,
  scored in parallel, surface only top matches. Beats single-signal retrieval and keeps
  the loaded context tiny (cited: ~7k tokens/query vs ~26k for full-context, similar quality).
- Temporal weighting: recency as a ranking signal so stale facts sink without deletion.
- Metadata filtering: inclusion/exclusion prompts + depth to exclude whole data classes.
- Treat agent-generated facts as first-class alongside user statements in a SINGLE
  extraction pass, so the same fact isn't captured twice from two perspectives.

Sources: arxiv 2504.19413 (Mem0), docs.mem0.ai memory-operations/update, memo.d.foundation
mem0 breakdown, mem0.ai state-of-2026.

---

## 6. When to summarize / archive / delete vs. keep

Decision rule by tier (synthesizes sections 2, 5):

- KEEP verbatim: HOT task state (until task done); WARM stable invariants/preferences.
- SUMMARIZE: a COLD item where the OUTCOME matters but the steps don't. Preserve
  what happened, why, what was decided; discard granular detail. Compress completed
  projects to a paragraph.
- ARCHIVE (move to COLD, drop from active retrieval): completed milestones, old session
  logs. Retain for audit/debug/periodic distillation, not for routine recall.
- DELETE: granular detail already captured in a summary; expired temporary data;
  memories CONTRADICTED by newer facts (Mem0 DELETE); confirmed duplicates (post-dedup).

Guard against compounding (section 1): never summarize a summary repeatedly without
re-grounding against a source -- that is exactly the semantic-drift loop. Keep a pointer
from each COLD summary back to its source artifact (file path / commit) so it can be
re-derived rather than re-summarized.

Sources: clawrxiv 2603.00037, arxiv 2603.11768.

---

## 7. Knowledge debt: docs/memory rot and the review cadence

"Knowledge debt" / documentation debt: memory drifts from reality, nobody notices because
each gap is individually small and accumulative, so it never gets prioritized -- until
trust in the memory collapses. LLM-KB staleness specifically = indexed docs/metadata no
longer match current reality.

Fixes that apply to an agent memory dir:

- OWNERSHIP + cadence: a scheduled review rhythm with update triggers tied to events
  (here: after each big build wave / milestone), so memory doesn't silently rot.
- A debt ledger: track known-stale/superseded entries explicitly (the project already has
  a "Knowledge Debt sync" habit -- formalize it as a section, not scattered).
- Staleness scoring: flag entries by last-verified date; oldest unverified bubble up
  for review or demotion.

Sources: dtales.tech documentation-debt, reworked.co information-debt, atlan.com
llm-knowledge-base-staleness, getdx.com code-rot.

---

## 8. Naming conventions

- Stable, descriptive, kebab-case, ONE topic per filename: `debugging.md`,
  `api-conventions.md`, `feedback-clv-over-roi.md`. (Project already standardized on
  uniform kebab-case slugs -- keep it; it killed 214 dead links once before.)
- Prefix by family so related notes cluster and dedup is visible:
  `project-*`, `feedback-*`, `reference-*`, `gotcha-*`, `project-atlas-player-*`.
- Date-suffix only when the note is a point-in-time snapshot (`*-2026-06-16.md`);
  evergreen notes get NO date so they can be updated in place.
- Filename == the link target == the index slug (no aliasing) -> renames are cheap,
  links don't rot.

Sources: code.claude.com/docs/en/memory (one-topic-per-file, descriptive names),
zettelkasten linking guidance.

---

## 9. RECOMMENDED ARCHITECTURE (for a dir OVER 24.4KB with ~80 files)

The current MEMORY.md is the index AND it is over budget; the loader silently truncates
past 200 lines / 25KB, so the tail entries are NOT being seen. This is the bloat failure.

### 9a. Index design -- make MEMORY.md a thin router, hard-capped

- Hard budget: <= 180 lines / <= 20KB (leave headroom under the 200-line / 25KB cap so
  the WHOLE index always loads; never ride the limit).
- Each index entry = ONE line: `[slug](slug.md) -- <=120-char gist`. Strip the long
  trailing detail that currently pushes entries to ~200 chars; the gist points, the file holds.
- Replace the flat one-line-per-file list (~80 lines of links alone) with a two-level index:
  TOPIC HUBS, not individual files. The root index lists ~12-15 hub files; each hub file
  lists its member notes. This removes the 80-link wall from the always-loaded surface.
  Example hubs: `hub-edge-discipline.md`, `hub-platform-kernel.md`, `hub-nba-engine.md`,
  `hub-ingame.md`, `hub-intelligence-vault.md`, `hub-ops-loop.md`, `hub-atlases.md`.
- Keep a single always-loaded BINDING INVARIANTS + GOTCHAS block (it is the HOT tier of
  rules) -- but trim it to the ones the agent would actually violate; move the rest to a
  `reference-invariants.md` that the index points to.
- "START HERE" stays: 5-7 lines of current-state + north-star + the invariants block.

### 9b. Tiering applied to this dir

- HOT  = the START HERE block + invariants/gotchas (always in MEMORY.md, <500 tokens).
- WARM = the ~12-15 hub files + the durable `feedback-*` discipline notes (loaded on
  demand when the topic is in play).
- COLD = dated snapshot waves (`project-*-2026-06-1x.md`) and superseded experiment logs;
  collapse each completed wave to a one-paragraph summary in its hub, archive the full
  note under `archive/` (still on disk, NOT linked from the root index).

### 9c. Archive policy

- After each milestone/wave: run the ADD/UPDATE/DELETE/NOOP pass over new learnings;
  fold the wave's detail into a one-paragraph hub summary; move the verbose note to
  `memory/archive/`. Keep a back-pointer to the source (commit / file path) so it can be
  re-derived, never re-summarized from the summary.
- DELETE outright: confirmed duplicates (the memory already flags 2 redundant atlas pairs
  at r=0.98/0.95 -- merge them), expired temporary state, and entries contradicted by a
  newer note.
- Never delete a `feedback-*` discipline note (those are hard-won invariants); demote, don't delete.

### 9d. Size-budget enforcement (make it mechanical, not vibes)

- A pre-load / lint check: fail loud if `MEMORY.md` > 180 lines OR > 20KB, or if any
  single index line > 120 chars, or if the root index links > 20 files directly.
- A staleness pass: sort notes by last-modified; anything unverified for N waves gets
  surfaced for re-verify / demote / delete (knowledge-debt cadence from section 7).
- A dedup pass: embed note titles+gists, flag pairs above a similarity threshold for
  manual merge (the atlas-redundancy method, generalized).
- This is the same discipline already enforced elsewhere (<=300 LOC/file); apply the
  identical "hard cap + lint" model to memory.

### 9e. Compounding loop (how it gets BETTER, not just smaller)

1. Capture: only mistake-driven, atomic, one-fact notes; search-before-add (NOOP often).
2. Consolidate: per wave, ADD/UPDATE/DELETE into hubs; summarize completed work to COLD.
3. Curate: enforce the index budget + staleness + dedup passes on a cadence.
4. Recall: hubs + on-demand topic files keep the always-loaded surface tiny while the
   full graph keeps growing on disk. The index size stays flat as knowledge compounds.

Net: index stays under a HARD budget forever; depth lives in lazy-loaded hubs/notes;
every entry has a tier and a lifecycle; dedup + staleness + summarization run on a cadence.

Sources (all of the above): clawrxiv 2603.00037; arxiv 2502.12110, 2504.19413,
2603.07670, 2603.11768; mem0.ai state-of-2026; docs.mem0.ai; code.claude.com/docs/en/memory;
zettelkasten.de; atlan.com; dtales.tech; getdx.com.
