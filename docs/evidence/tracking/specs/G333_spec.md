GAP G333 | sport all | worktree a1 | log cx_g333_apply_producer_diffs

**PRODUCER ROW -- src/ EDITS AUTHORIZED.** On 2026-09-08 ~10:20 CDT the user authorized applying the PROPOSED
producer diffs without further human input ("do all these, you don't need me for any human input"). This row
applies exactly four landed PROPOSED diffs to `src/`, each behind a test, each additive, each with a
before/after measurement on committed constructs. NEVER write `data/registry/`, never flip a feature flag,
never claim an edge, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` or any threshold.
The route's defaults stay byte-identical except where the diff itself is the change (state each).

**WHERE THIS ROW RUNS:** LOCAL for code, tests and the construct measurements. The pod is READ-ONLY (never
touch `track_daemon` pid 1168432 or the guards 1039858 / 1519254); deployment of these src changes to the
pod is a SEPARATE orchestrator step after landing, not this row. One local 130 s section (<= 40 MB) may be
copied from the pod corpus for the end-to-end smoke of diffs 1 and 2 and deleted afterwards; peak RSS
under 1.5 GB (the local RAM guard kills at 99 pct).

**THE FOUR DIFFS (sources are frozen evidence; apply, do not redesign):**
  1. **G330 -- do not cache the fallback panorama under the per-video path.** Source:
     `nba-track-a1:docs/research/organization-sprint/G330_PROPOSED_pano_cache_key.md` (local-only; sha256
     in the G330 attempt-2 memo). Track a `used_fallback` flag through the substitution at
     `src/pipeline/unified_pipeline.py` (~:969-985) and skip the `cv2.imwrite` to the per-video cache path
     (~:987-988) when set, so a later run retries the stitch instead of inheriting a foreign panorama.
     Additive: a run that legitimately stitched still caches. Test: a builder stub that returns the
     fallback must leave no per-video cache file; a stub that returns a stitched panorama must cache it.
  2. **G325 -- drop wholly off-frame Kalman coasts at write.** Source (committed):
     `docs/evidence/tracking/PROPOSED_g325_drop_wholly_offframe_2026-09-07.md`. The unclamped Kalman
     prediction (`src/tracking/advanced_tracker.py` ~:132-137) is written for up to MAX_LOST=90 frames even
     when the box lies wholly outside the decoded frame (23,408 of 480,158 observations, G325). Apply the
     drop-at-write guard exactly as proposed (a box with no overlap with the frame rectangle is not
     emitted; the track keeps coasting internally). Test: a synthetic track that leaves the frame emits no
     wholly-off-frame rows, partially-off-frame rows still emit, and the id survives re-entry.
  3. **G320 -- write the inferred flag only when a coordinate exists.** Source:
     `nba-track-a1:docs/research/organization-sprint/G320_PROPOSED_ball_inferred_coord.md`. Replace the
     one line at `unified_pipeline.py` ~:1991 with the proposed form gating `ball_inferred` on
     `ball_pos is not None`. Test: a row dict built with `last_2d_pos=None` and `ball_inferred=True` writes
     `inferred=0`; with a coordinate it writes `inferred=1`.
  4. **G331 -- record the real evaluated-frame count.** Source:
     `nba-track-a6:docs/research/organization-sprint/G331_PROPOSED_evaluated_frames.md` (4 lines across
     `unified_pipeline.py` ~:3049 and `scripts/run_clip.py` ~:505). Expose the post-run `gameplay_frames`
     (the detector-gated count at ~:2069) so `evaluated_frame_count.json` carries the number instead of
     null, with the `reason` field retained when the count is unavailable. Additive: existing sidecar keys
     keep names and meanings. Test: a stub route with 7 gameplay frames yields `evaluated_frames: 7`.

**PREMISE (step 0, BINDING before-condition):** for each diff, reproduce the defect on a construct BEFORE
editing and PRINT it (fallback cached under the per-video path; a wholly-off-frame row emitted; inferred=1
with no coordinate; evaluated_frames null). A diff whose defect does not reproduce is reported CLOSED
ALREADY and skipped.

METHOD:
  1. Apply the four diffs as minimal edits (each a handful of lines; cite `file:line` before and after);
     keep every touched src file within its existing LOC allowlist (they are legacy-exempt at their current
     sizes -- do not grow `unified_pipeline.py` by more than 12 lines total; `test_loc_rail_scope.py`
     must stay green).
  2. Tests: one per-file test module `tests/platformkit/test_g333_producer_diffs.py` covering the four
     constructs above, plus the existing test file of every touched module (find them; run each alone).
  3. BEFORE/AFTER on committed evidence: (a) G325 -- re-run the G325 census reader over the committed
     ledger snapshot / census CSVs is not possible post-hoc (the producer must run), so run the tracker on
     the local section before and after and report wholly-off-frame rows / total rows for both (n);
     (b) G330 -- after the change, run the route's panorama step on the same section and show no
     per-video cache file is written when the fallback is used (print the cache dir listing before/after);
     (c) G320 -- unit construct only; (d) G331 -- unit construct plus the sidecar from the section run
     showing a non-null count. Every number with its n.
  4. CHANGE NOTHING ELSE. No threshold, no default beyond the four diffs, no register edit.

**HONEST LIMITATIONS to state, not discover:** these diffs remove known-bad rows and a foreign-panorama
cache; they do not make registration work (G330 held-out inliers stay ~1 pct until a real court
calibration exists -- that is a separate row); the section smoke is one clip, a screening not a census.

ACCEPTANCE RULE:
  metric        = four premise prints; the four diffs with `file:line`; the test module + existing tests
                  green; the before/after table for the section smoke with n
  before        = the four defects reproduce on constructs
  bar           = each applied diff has a construct test that fails on the old code and passes on the new;
                  `unified_pipeline.py` grows <= 12 lines; every existing test file of a touched module
                  stays green; 0 register edits
  n             = the four diffs (exhaustive); the section smoke (1 clip, labelled screening)
  eye check     = NONE. Say that.
  must not move = `data/`, `data/registry/`, every feature flag, every threshold, the pod (read-only), the
                  daemon and guards, every committed artifact and hash,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if all four apply with passing tests; **PARTIAL** listing the diffs that could
                  not be applied and why.
EVIDENCE: `docs/evidence/tracking/g333_apply_producer_diffs_2026-09-08.md` (<= 60 lines) with VERDICT on
line 1, the premise prints, the diff table, the before/after table, a **NOT VERIFIED** list, wall time and
the SHA-256s. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append, LF). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g333_producer_diffs.py` plus the existing test file of every touched module,
each alone. **NEVER a full pytest.**
COMMIT: explicit pathspec only (src/ paths named explicitly). ASCII stdout. Prereg sealed as its OWN commit
first (embed the seal: last line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
