GAP G376 | sport all (basketball fixtures first) | worktree a12 | log cx_g376_declared_tick_observations

**PRODUCER-AUDIT ROW, SUCCESSOR TO G370 (PARTIAL 2026-09-10 ac008ac6: 32,158 / 45,842 = 0.7014 of DECLARED scheduled evaluated
ticks on the 34 sealed sections and 68,534 / 89,655 = 0.7644 on the 69 replacement fresh sections carry ZERO track observations;
the memo could not say whether this is a producer defect or a scheduling mismatch; derived tick verification resolved only 0.1140
of sealed ticks because 30 of 34 sections report a non-integral decoded_frames / evaluated_frames) and to G368 (CLOSED AT LIMIT:
held runs attributed by file:line; the player table carries no provenance column).** A Claude finisher PREPARES (prereg sealed alone)
and MEASURES on the pod. `src/` (the producer: `src/pipeline/unified_pipeline.py`, `src/tracking/*`) and `scripts/run_clip.py` are
READ and IMPORT only; any producer change is a PROPOSED diff in the evidence dir (sha256 in the memo). Build additively in
`scripts/platformkit/tracking/g376_*.py` (import `g370_ticks`, `g370_schema`, `g368_tick_motion`, `g359_held_position`; copy none).
NEVER write `data/registry/`, never flip a flag, never move a sealed threshold, never touch the register.

**WHERE THIS ROW RUNS:** ON THE POD, `/workspace/wt/a12` (`python3 -m`; CPU only, <= 6 cores, threads = 1); tables READ ONLY from an
IMMUTABLE lane snapshot of the 34 sealed + the G370 replacement 69 (copy once, sha256 each; the live store mutates); ONE controlled
re-run of the deployed `run_clip.py` on ONE scratch copy of a fresh source with `--frames` and stride logging enabled to observe the
schedule directly (scratch only; never the deploy tree's data links).

**PREMISE (step 0, BINDING before-condition):** recompute, from the snapshot, the zero-observation tick share on both sets and the
share of sections with non-integral decoded_frames / evaluated_frames; PRINT them beside G370's 0.7014 / 0.7644 / 30 of 34.
**If the zero-observation share is < 0.10 on both sets, the premise is FALSE: STOP, memo, commit, report.**

METHOD (sealed before any number):
  1. **SCHEDULE RECONSTRUCTION:** from the producer code (cite file:line) derive the exact evaluated-tick rule (stride, phase, frame
     offset, VRAM-flush skips, cut resets) and predict, per section, the set of frame indices the producer SHOULD have evaluated; compare
     with the frame indices that carry >= 1 track row and with the ledger's `evaluated_frames` and the sidecar's `evaluated_frame_count`.
  2. **CLASSIFY every declared tick** into: OBSERVED (>= 1 track row), SCHEDULED_NO_DETECTION (evaluated, detector returned nothing),
     NOT_SCHEDULED (the declaration over-counts: stride/phase mismatch), UNKNOWN; the split is decided by the reconstructed rule and the
     controlled re-run's log, never by the row count alone.
  3. **CONTROLS:** (a) the controlled re-run's own log vs its table = the rule reproduces 100 pct of its ticks; (b) a synthetic table
     with every tick observed -> 0 zero-observation ticks; (c) a synthetic declaration inflated by 2x -> NOT_SCHEDULED = 0.50 exactly.
  4. **CONSEQUENCE:** the corrected denominator for G370's M1 scoring and for G368's motion share; the number of sections whose
     `evaluated_frames` should be restated; a PROPOSED additive sidecar field `evaluated_tick_ids` (list) for the producer.
  5. CHANGE NOTHING ELSE; no src hook; no flag.

ACCEPTANCE RULE:
  metric        = per-set shares OBSERVED / SCHEDULED_NO_DETECTION / NOT_SCHEDULED / UNKNOWN of declared ticks; the reconstructed rule
                  with file:line; the controlled re-run reproduction; the corrected denominators
  before        = G370: 0.7014 / 0.7644 zero-observation shares; 30 of 34 non-integral ratios; tick verification 0.1140
  bar           = >= 0.95 of declared ticks classified (UNKNOWN <= 0.05); controls exact; the re-run reproduces its schedule 100 pct;
                  0 src edits; 0 thresholds moved
  n             = 34 sealed + 69 fresh sections (CONSTRUCT over the two sealed sets) + 1 controlled re-run
  eye check     = REQUIRED: 10 evenly spaced strips (declared ticks vs observed ticks vs reconstructed schedule) <= 200 KB each
  must not move = `src/`, `scripts/run_clip.py`, every sealed threshold, the daemon, `data/`, `data/registry/`, every flag
  verdict       = **DONE** / **PARTIAL** (name the UNKNOWN share or the failed control) / **PREMISE FALSE**
EVIDENCE: `docs/evidence/tracking/g376_declared_tick_observations_2026-09-10.md` (<= 60 lines; VERDICT line 1; NOT VERIFIED; wall
time; SHA-256s) + `.../g376_declared_tick_observations_2026-09-10/{schedule_rule.md,ticks.csv,classification.csv,controls.csv,
consequence.csv,rerun_log.txt,strips/,summary.json,PROPOSED_evaluated_tick_ids.md}`. **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT.**
TEST: `tests/platformkit/test_g376_declared_tick_observations.py` alone (the three controls; a tick outside the reconstructed
schedule is NOT_SCHEDULED; the seal). **NEVER a full pytest.** Every new file <= 300 lines. Vocabulary follows contract Q6; automated
scan required. Prereg sealed as its OWN commit first (`SEAL sha256 <hex>`). ASCII stdout. **NEVER PARK.**

VERSION 2026-09-10
