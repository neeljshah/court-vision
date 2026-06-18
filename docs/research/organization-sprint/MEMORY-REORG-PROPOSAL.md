---
name: memory-reorg-proposal
description: RISKY merge/delete proposals for human review -- NOT auto-applied. Lists files that are candidates for merging or deletion with reasoning.
metadata:
  type: reference
  created: 2026-06-16
---

# MEMORY REORG PROPOSAL -- Human Review Required

These changes were NOT auto-applied. Every file in memory/  remains intact. Review and apply manually.

---

## AUTO-FIXES ALREADY APPLIED (safe, in-place, no files deleted)

1. **Wikilink normalization (51 files):** All `[[old_underscore_slug]]` references updated to `[[kebab-slug]]` to match the `name:` field in each file's frontmatter. No links were deleted; all now resolve to the correct existing file.

2. **Type field corrections (2 files):** `feedback_cv_attribution_vs_eventdetection.md` and `feedback_osnet_ghost_slot_pattern.md` had `type: project` in their frontmatter; corrected to `type: feedback` (they start with `feedback_` and carry feedback-pattern content).

3. **Malformed description repaired (1 file):** `project_bug33_eventdetector_root_cause.md` had a truncated YAML description (`Bug 33 strict ghosts (Strus` -- missing closing quote/content); replaced with a complete one-line description.

4. **Missing Why/How-to-apply added (6 files):** Added required `**Why:**` and/or `**How to apply:**` lines to feedback files that lacked them:
   - `feedback-graph-playstyles-not-people.md` -- added Why
   - `feedback-north-star-best-predictions-not-no-edge.md` -- added Why + How to apply
   - `feedback_consistency_cv_orthogonal_interval_signal.md` -- added Why
   - `feedback_iter57_filter_loses_bet_policy.md` -- added Why
   - `feedback_runpod_fetcher_cookie_perms.md` -- added How to apply
   - `feedback_train_inference_parity.md` -- added Why

5. **MEMORY.md rewritten:** Clean, scannable index (from the ~300-line mixed-prose original); one line per file; grouped under 11 cluster headings matching the task spec. Every linked file was verified to exist. **Trimmed 2026-06-16 from 201 -> 199 lines** (removed one redundant `---` section-separator + blank between the atlas and CV clusters) to satisfy the <=200-line ceiling; no fact removed.

---

## MERGE PROPOSALS (keep <- merge_in + reason)

### M1 -- No action: feedback-consistency-cv-orthogonal-interval-signal.md
**keep:** `feedback-consistency-cv-orthogonal-interval-signal.md`
**merge_in:** (none -- already self-contained)
**Reason:** The original 2026-05-30 claim AND its 2026-06-01 overturn coexist in ONE file, correctly structured as a correction block. The self-correcting structure is correct and valuable -- it preserves the epistemological history (claim, then refutation). No merge needed; just awareness. Do not split this into two files.

### M2 -- Consider: project_prediction_improvement_roadmap.md <- project_nba_data_vision.md
**keep:** `project_prediction_improvement_roadmap.md`
**merge_in:** `project_nba_data_vision.md`
**Reason:** Both are archival-era (pre-platform-pivot, 2026-05-30 era) north-star reference docs. `project_nba_data_vision.md` defines the data collection ambition (CV tracking + NBA API + external factors per game). `project_prediction_improvement_roadmap.md` defines the prediction improvement strategy. Together they form the "what to collect + how to use it" pair from that era. Both are now SUPERSEDED by `project-north-star-deepest-data-best-predictions-per-sport.md` and `project-intelligence-master-plan-2026-06-13.md`. Merging would preserve both facts in one place and cut file count by 1. CONSERVATIVE: propose only, human decides.

### M3 -- Consider: project_market_validation_oddsapi.md <- project_realmoney_triage_2026-06-01.md
**keep:** `project_market_validation_oddsapi.md`
**merge_in:** `project_realmoney_triage_2026-06-01.md`
**Reason:** Both are archival betting-validation documents from 2026-05-30 to 2026-06-01. The triage doc covers uncommitted real-money code edits (bankroll gate, CLV sign, parlay de-vig, corr matrix). The oddsapi doc covers the validated market comparison. Neither has been updated since the platform pivot. Both are superseded by `reference-edge-maps-2026-06-15.md` and `project-season-backtest-2026-06-10.md` as the definitive market-efficiency proofs. The triage facts are historical correctness artifacts worth preserving. CONSERVATIVE: propose only, human decides.

---

## DELETE PROPOSALS

### D1 -- project_session_handoff_2026-05-30.md
**File:** `project_session_handoff_2026-05-30.md`
**Reason:** Transient session-handoff document from 2026-05-30. Its "NEXT ACTION" (confidence-sizing backtest) was subsequently completed (see `project_prediction_integration_2026-06-01.md`). Its headline finding (consistency-CV as an interval signal) was OVERTURNED on 2026-06-01 (see `feedback_consistency_cv_orthogonal_interval_signal.md`). Its descriptive phase-transition summary is superseded by `project-quarter-intel-atlases-2026-05-30.md`. The document retains minor archival value documenting the "descriptive->integration" phase transition posture. CONSERVATIVE: proposed as demote/retire (rename to `_archive_session_handoff_2026-05-30.md` or move to docs/archive/), NOT deleted this pass. Human decides.

### D2 -- planning-corpus-audit.md
**File:** `planning-corpus-audit.md`
**Reason:** This 2026-05-21 document records a one-time planning-corpus reconciliation (STATE.md fixed, phases 39-44 added, CANONICAL_VALUES.md created) and the bot-queue visibility rule. The STATE.md work is long past. The bot-queue visibility rule is more durably captured in `bot-queue-visibility.md`. The only unique content is the 2026-05-21 phase-numbering fix -- purely archival. CONSERVATIVE: propose deletion, human decides. If the bot-queue visibility fact is confirmed to be fully captured in `bot-queue-visibility.md`, this file is deleteable.

### D3 -- project_nyk_sas_team_system_2026-06-06.md (conditional)
**File:** `project_nyk_sas_team_system_2026-06-06.md`
**Reason:** The NYK vs SAS 2026 Finals series is over (archival). The team system it describes (scripts/team_system/) is still used, but the PBP-driven two-team intelligence it built is Finals-specific. The scripts it references remain generally useful. CONDITIONAL: do NOT delete if there are any live references to Finals game IDs in active code. Only delete if confirmed that the Finals PBP artifacts are fully archived and the scripts are documented elsewhere. Very low priority -- propose only.

---

## NOT RISKY -- Explicitly Left as-is

- **All 44 atlas files** (project_atlas_player_*.md + project_atlas_team_*.md): These are auto-generated registry entries with exact parquet/section names. Do not merge or delete; they serve as the definitive spec for each atlas section.
- **All CV bug files** (project_bug26, project_bug33, project_bug39, project_int56, project_tracking_q1_period_nan_bug): Each bug has a unique mechanism and unique recovery path. Do not merge.
- **feedback-no-concurrent-brain-rebuilds.md**: High-stakes operational guardrail; never merge or delete.
- **feedback-north-star-best-predictions-not-no-edge.md**: Binding directive from 2026-06-15; never merge or delete.
