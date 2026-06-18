# Memory Reorg Plan (04) -- Claude memory dir audit

Scope: `C:\Users\neelj\.claude\projects\C--Users-neelj\memory\`
Mode: READ-ONLY audit. This is a plan only; no files were edited or deleted.
Date: 2026-06-17. ASCII only.

## 1. Current state (measured)

- Files on disk: 178 `.md` (177 memories + `MEMORY.md` index).
- Total bytes: 1,058,007 (~1.03 MB).
- `MEMORY.md` index: 33,510 bytes = OVER the 24,400-byte (24.4KB) limit by ~9.1KB (+37%).
- Linked files in index: 133 distinct, plus 44 atlas files summarized as 2 cluster lines = all 177 accounted for.
- Broken `[[links]]` / broken `(file.md)` links: NONE found. (Link hygiene is fine.)
- Orphan files (on disk, not covered by index): NONE (atlases intentionally rolled up).

### Largest memory files (top 8)
```
166280  project-platform-intelligence-robustness-wave-2026-06-13.md
127891  project_monte_carlo_engine_2026-06-06.md
 59340  project_pregame_model_ceiling_2026-06-04.md
 36002  project_self_improving_loop.md
 22971  project-best-predictions-loop-2026-06-15.md
 21382  project_loop7_status.md
 18338  project_courtvision_live_night_wiring.md
 17645  project_hardening_campaign_2026-06-02.md
```
These are large but are topic files (not the index) -- they cost retrieval tokens, not index budget. Trimming them is optional; the binding problem is the index.

## 2. Root-cause of the 24.4KB breach

The index is NOT over budget because of too many entries -- it is over because **94 of ~133 entries exceed the ~200-char one-line rule** (line 29 invariants block = 596 chars; line 157 atlas cluster = 582; line 205 paths = 384; ~90 entry lines in the 200-344 range). Fixing the breach is primarily a REWRITE-TO-SPEC job (tighten every line to <=160 chars), secondarily a small prune. Both are below.

## 3. Problems found

### (a) Index-line bloat (PRIMARY)
94 lines over 200 chars. Worst offenders: lines 18-29 (START HERE block), 157/159 (atlas clusters), 205 (paths). Tightening all entries to <=160 chars alone recovers ~10-12KB.

### (b) Stale / superseded files (prune candidates)
- `project_session_handoff_2026-05-30.md` -- self-flagged "MOSTLY SUPERSEDED", points to a retired MEMORY-REORG-PROPOSAL; a one-off interrupted-handoff snapshot from 2+ weeks ago. ARCHIVE.
- `planning-corpus-audit.md` -- 2026-05-21 one-off audit (STATE.md fixed, CANONICAL_VALUES.md created); historical, low recall value. ARCHIVE.
- `project-scoreboard-c6-stale-c7-shipped-2026-06-17.md` -- micro-status (1752b); its content folds into the org-sprint / best-predictions line. MERGE into START-HERE note, then ARCHIVE the file.
- `project_courtvision_game7_live_readiness.md` and `project_courtvision_live_page_fixes_2026-06-03.md` -- both are dated point-in-time "readiness during G1/G7" snapshots, superseded by `project_courtvision_live_night_wiring.md` (the one-command go-live). MERGE key residuals into the wiring note, ARCHIVE the two snapshots.

### (c) Overlapping clusters that should merge
- **Platform build-session chain** (5 dated files): `project_platform_h0_built_2026-06-11`, `project_platform_build_session_2026-06-12`, `project-platform-kernel-built-2026-06-12`, `project-platform-kernel-promotion-2026-06-13`, `project-platform-harness-promotion-2026-06-13`. These are sequential build logs of one effort. MERGE into a single `project-platform-build-log-2026-06.md` (keep dated section headers).
- **Platform proof-of-domain chain** (2 files): `project-platform-soccer-third-domain-2026-06-12`, `project-platform-mlb-fourth-domain-2026-06-12`. MERGE into `project-platform-domains-proven-2026-06-12.md`.
- **CV per-bug notes** (5 small files, ~13KB total): `project_bug26_enricher_origin`, `project_bug33_eventdetector_root_cause`, `project_bug39_10slot_ceiling`, `project_int56_player_id_zero_bug`, `project_tracking_q1_period_nan_bug`. MERGE into one `project-cv-bug-register.md` (each as a section). Keep `project_cv_bug_magnitudes.md` as the summary that points into it.
- **CV signal-quality micro-notes** (3 files): `project_blk_cv_strong_signal`, `project_xast_potential_assists_inverted`, `project_shot_quality_suspend_recommendation`. MERGE into `project-cv-signal-quality.md`.
- **2026-06-01 intel/integration campaign** (slight overlap): `project_intel_campaign_2026-06-01`, `project_outcome_impact_campaign_2026-06-01`, `project_prediction_integration_2026-06-01` overlap on "intel built -> betting REJECTs." Keep separate (each is substantive) but cross-link; do NOT merge.
- **PTS/REB ceiling pair**: `project_pregame_model_ceiling_2026-06-04` (59KB) and `project_pts_reb_at_data_ceiling.md` say the same thing at two sizes. Keep the short one as the index entry; demote the 59KB one to an archived deep-log referenced from it.

### (d) Atlas cluster
44 atlas files (~26KB total) are correctly rolled into 2 cluster lines (player x28, team x16). KEEP as-is -- do not individually index. Trim the two cluster lines (currently 582 + 368 chars) by dropping the inline name lists and pointing to a generated manifest.

## 4. Concrete actions

### (a) MERGE (exact filenames -> target)
1. `project_platform_h0_built_2026-06-11.md` + `project_platform_build_session_2026-06-12.md` + `project-platform-kernel-built-2026-06-12.md` + `project-platform-kernel-promotion-2026-06-13.md` + `project-platform-harness-promotion-2026-06-13.md` -> **`project-platform-build-log-2026-06.md`**
2. `project-platform-soccer-third-domain-2026-06-12.md` + `project-platform-mlb-fourth-domain-2026-06-12.md` -> **`project-platform-domains-proven-2026-06-12.md`**
3. `project_bug26_enricher_origin.md` + `project_bug33_eventdetector_root_cause.md` + `project_bug39_10slot_ceiling.md` + `project_int56_player_id_zero_bug.md` + `project_tracking_q1_period_nan_bug.md` -> **`project-cv-bug-register.md`**
4. `project_blk_cv_strong_signal.md` + `project_xast_potential_assists_inverted.md` + `project_shot_quality_suspend_recommendation.md` -> **`project-cv-signal-quality.md`**
5. `project_courtvision_game7_live_readiness.md` + `project_courtvision_live_page_fixes_2026-06-03.md` -> fold residuals into **`project_courtvision_live_night_wiring.md`**, then archive the two.
6. `project-scoreboard-c6-stale-c7-shipped-2026-06-17.md` -> fold into **`project-org-sprint-2026-06-16.md`** START-HERE note, then archive.

Net: 13 source files collapse into 4 new + 2 existing = removes ~9 index-eligible files.

### (b) ARCHIVE / DELETE (move to `_archive/` subfolder, reason)
- `project_session_handoff_2026-05-30.md` -- self-flagged MOSTLY SUPERSEDED one-off handoff. ARCHIVE.
- `planning-corpus-audit.md` -- 2026-05-21 completed one-off audit. ARCHIVE.
- The 13 merged sources above (after content is folded) -- ARCHIVE (do not hard-delete; keep recoverable).
- `project_pregame_model_ceiling_2026-06-04.md` (59KB) -- ARCHIVE the deep-log body; keep `project_pts_reb_at_data_ceiling.md` as the live index entry that links to the archived deep version.
Recommendation: ARCHIVE (move to `_archive/`), not DELETE -- these are git-tracked lessons; archiving preserves recall while clearing the index.

### (c) Rewritten MEMORY.md index design (fits under 24.4KB)

Rules for the rewrite:
- Every entry line <=160 chars (hard cap; not the soft ~200).
- Slug + " -- " + <=140-char gist. No restating the date inside the line when the slug already carries it.
- Invariants/gotchas block (line 29) and paths block (line 205): move the FULL text to a dedicated `reference-invariants-and-paths.md` file; leave a single <=160-char pointer line in the index for each.
- Atlas clusters: drop the inline name lists; replace with one <=120-char line each pointing to the auto-built manifest.

Proposed section structure (8 groups, unchanged grouping logic, tightened):
```
H1 title + 1-line "index only" note + Today date
SECTION 1  START HERE -- current state + north star   (~8 entries)
SECTION 2  Load-bearing discipline (accuracy!=edge / CLV / leak-free)  (~22 entries)
SECTION 3  Platform & multi-sport kernel              (~10 entries, post-merge)
SECTION 4  NBA engine, ratings & pregame prediction    (~20 entries)
SECTION 5  In-game (live) layer                         (~5 entries)
SECTION 6  Edge / betting market-efficiency proofs      (~4 entries)
SECTION 7  Autonomous loop & ops protocols              (~17 entries)
SECTION 8  Intelligence vault & auto-atlases            (~4 entries + 2 cluster lines)
SECTION 9  CV / tracking moat                           (~10 entries, post-merge)
SECTION 10 Products & job search                        (~6 entries, post-merge)
SECTION 11 References, data & paths                     (~3 entries + 2 pointer lines)
```

Sample tightened entries (showing the <=160-char target form):
```
- [project-org-sprint-2026-06-16] -- 06-16 org sprint: eval-gate keystone + funnel levers + RAG + sellable + build-loop, 8 LOCAL commits; HUMAN-CONFIRM list pending
- [feedback-accuracy-is-not-edge] -- minimizing MAE pulls predictions toward the line (=market) and KILLS edge; calibrate per-stat ONLY where you lose to Vegas
- [project-platform-build-log-2026-06] -- H0->kernel->NBA-adapter->kernel/harness promotions, one merged build log (was 5 dated files); tasks_done~101
- [project-cv-bug-register] -- merged per-bug register: Bug26 pbp-fill origin, Bug33 ghosts, Bug39 10-slot, INT56 id=0, Q1 period-NaN
- [reference-invariants-and-paths] -- BINDING INVARIANTS + GOTCHAS + codebase/vault/env paths (moved out of the index; read this first each session)
```

Budget math: ~115 entry lines x ~130 chars avg ~= 15KB + ~11 section headers + title/notes ~= 2KB = **~17KB**, comfortably under 24.4KB with headroom for growth.

### (d) Size-budget enforcement rule

Add to the index header and to a CI/loop check:
1. HARD CAP: `MEMORY.md` must stay <= 24,400 bytes. A pre-commit/loop check fails if `wc -c MEMORY.md` exceeds it.
2. PER-LINE CAP: no index entry line > 160 chars (the previous ~200 soft rule was the leak; tighten and enforce).
3. ADD-ONE-PRUNE-ONE: when a new dated project note is indexed, the author must either (a) keep the line <=160 chars AND (b) check whether it supersedes an older dated note in the same cluster; if so, archive the older one same-commit.
4. NO FULL PROSE BLOCKS in the index: invariants/gotchas/paths live in `reference-invariants-and-paths.md`, referenced by a single line.
5. ATLAS RULE: never index atlas files individually; one cluster line each, names in the auto-built manifest.
Suggested check (loop or pre-commit):
```
bytes=$(wc -c < MEMORY.md); [ "$bytes" -le 24400 ] || { echo "MEMORY.md $bytes > 24400"; exit 1; }
awk 'NR>1 && /^- \[/ && length>160{print NR": "length; bad=1} END{exit bad}' MEMORY.md
```

## 5. Expected result
- Index: 33.5KB -> ~17KB (under the 24.4KB cap, ~30% headroom).
- File count: 177 -> ~162 memories (13 merged + 2 archived from index; bodies preserved in `_archive/`).
- Recall quality preserved: no lessons deleted; only consolidated and de-bloated.
