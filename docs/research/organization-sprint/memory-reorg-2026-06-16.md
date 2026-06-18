# Memory Reorg Pass — 2026-06-16

Target dir: `C:/Users/neelj/.claude/projects/C--Users-neelj/memory` (171 memory .md + MEMORY.md).
Conservative pass: no memory file deleted. SAFE fixes applied in place; RISKY merges/deletes are PROPOSALS for the human only.

## Link-graph health
A prior wave (`project-platform-platformkit-rename-2026-06-13`) already normalized the slug graph to kebab-case
and repaired ~214 dead links. The graph is healthy: every real `[[wikilink]]` resolves to an existing note
(by `name:` slug or filename stem). The only "unresolved" links are TEMPLATE/EXAMPLE placeholders inside
documentation, NOT broken references:
`[[<TEAM>]]`, `[[GamePlans/X]]`, `[[Matchups/X]]`, `[[Teams/X]]`, `[[Wikilinks]]`, `[[links]]` —
these are illustrative (e.g. "repointed `[[GamePlans/X]]`->`[[Teams/X]]`") and should be LEFT AS-IS.

## SAFE fixes APPLIED in place (this pass)
1. `project_unified_ingame_shadow.md` — had NO frontmatter block at all. Added full canonical frontmatter
   (name: project-unified-ingame-shadow, metadata.node_type, metadata.type: project) + a **Why:** and
   **How to apply:** block + `[[links]]` to related notes. Fact untouched.
2. `feedback_platform_engineer_protocols.md` — flat `type: feedback` -> nested `metadata:\n  node_type: memory\n  type: feedback`.
3. `project_nba_data_vision.md` — flat `type: project` -> nested `metadata` block + node_type.
4. `project_tracker_extraction_roadmap.md` — flat `type: project` -> nested `metadata` block + node_type.
5. `project_llm_scheme_prior_layer_2026-06-10.md` — broken placeholder `[[feedback_... ]]` de-linked to
   plain text "the CV_AGENT_DEF_SUPP gating pattern" (no real target existed; it was an authoring placeholder).
6. `feedback-north-star-best-predictions-not-no-edge.md` — body wikilinks normalized from underscore form
   `[[feedback_accuracy_is_not_edge]]` / `[[feedback_pregame_edge_is_market_follow_artifact]]` to canonical
   hyphen form `[[feedback-accuracy-is-not-edge]]` / `[[feedback-pregame-edge-is-market-follow-artifact]]`.

## Stale dates
No genuinely-ambiguous standalone relative dates found. Every "today/tomorrow/this season" hit is either
generic prose ("on today's data", "0 PRA quotes today") or anchored by an absolute date in the same
sentence (wave logs like "WAVE 17e (2026-06-05) ... 0 rows today"). No conversions needed. MEMORY.md
header date is 2026-06-15; today is 2026-06-16 (refresh on next index rewrite).

## MEMORY.md index links
All markdown-style links `(file.md)` in MEMORY.md resolve to existing files. The index mixes hyphen-slug
and underscore-filename wikilink forms; both resolve, so this is cosmetic. A future rewrite should
standardize on one form.

## RISKY — PROPOSALS for human review (NOT applied)
### Merge / supersede
- KEEP `feedback-consistency-cv-orthogonal-interval-signal.md`; consider folding the original 2026-05-30
  "consistency-CV is a genuine orthogonal interval signal" claim — it is now self-corrected/overturned by
  the 2026-06-01 correction block in the SAME file. No second file to merge; the file already carries both
  the claim and its overturn. NO ACTION needed beyond awareness; listed for completeness, do not delete.
- `project_session_handoff_2026-05-30.md` — a transient session handoff whose "NEXT ACTION"
  (confidence-sizing backtest) was completed and whose key finding (consistency-CV) was later OVERTURNED.
  Mostly superseded by `project-quarter-intel-atlases-2026-05-30` +
  `feedback-consistency-cv-orthogonal-interval-signal`. Candidate to retire OR demote, but retains archival
  value documenting the descriptive->integration phase transition. Human call.

### Possible archival cluster (chronological wave logs — keep, but could be index-collapsed)
The 2026-06-12/13 platform-wave files (`project-platform-kernel-promotion`, `-harness-promotion`,
`-loc-discipline`, `-platformkit-rename`, `project_platform_build_session`) are each a distinct fact (a
distinct wave). NOT duplicates — DO NOT merge. They could be collapsed under one index sub-bullet in
MEMORY.md to shorten the index without touching the files.

## Notes on feedback Why/How-to-apply labels
These feedback notes carry the reasoning + application guidance in their bodies but lack the literal
**Why:** / **How to apply:** label tokens: `feedback_train_inference_parity`, `feedback_iter57_filter_loses_bet_policy`,
`feedback_consistency_cv_orthogonal_interval_signal`, `feedback-graph-playstyles-not-people`,
`feedback-north-star-best-predictions-not-no-edge`. Content is substantively complete; adding the literal
labels is optional polish (NOT applied this pass to avoid editing dense bodies that already explain why/how).
