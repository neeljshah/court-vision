GAP S204 | sport all (pregame) | worktree a18 | log cx_s204_close_reference_calibration
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S05_calibration_report_2026-09-03.md line 148, verbatim: "- No sport is compared to a market close -- no gate
corpus carries one." False on disk: S02 joined the soccer close 16,322/16,322 with "Brier(devigged
close)=0.23946005675766663; Brier(p_base)=0.2627028248079339"; S108 used the close as incumbent on soccer and tennis;
gate_corpus_{nba,mlb}_close.parquet carry p_close. Item 9 of docs/research/model_quality_methods_2026-09-04.md calls
this join BLOCKED; that premise is false too.
PREMISE (step 0): re-measure and print: S05 after-ECEs nba 0.024843 (1,814), mlb 0.008077 (39,162), soccer 0.009302
(25,834), tennis 0.008403 (41,886), FLATTENED 4/4, 0 dropped; close supply measured 2026-09-04 -- nba 563 of 1,814
non-null p_close (343 first_inplay_tick, 220 pregame_last_tick_before_commence), mlb 910 of 39,162, soccer 16,322
joined, tennis vintage SYNTHETIC (S03). If falsified, STOP, memo, commit, FALSIFIED.
LIMIT (step 1): count per sport the rows carrying BOTH a model probability and a PREGAME close (in-play close_source
excluded, its count printed). A sport under 30 clusters of paired rows is NOT SCORABLE with the count; score the
others. Never widen a denominator to reach a bar.
CHANGE (step 2): smallest additive change -- a read-only reporter under scripts/platformkit/eval_gate/ scoring the
EXISTING recalibrated forecaster and the devigged close on the SAME paired rows. No calibrator, fold, bin or builder
touched. Additive only, nothing renamed; helper <= 300 lines within test_loc_rail_scope.py; never write data/; no flag
on; no edits in src/ kernel/ api/ intel/ scripts/team_system/; one store at a time, never > 300 MB; never touch
register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per sport, paired rows only: ECE, Brier, log-loss and the 10-bin reliability table for BOTH model
                  and close, plus the paired Brier delta with a corpus_unit-clustered 95 pct CI and n_eff; denominator
                  = the printed paired-row count
  before        = none exists (S05 line 148); the only close comparisons on record are S02's soccer 0.239460 vs
                  0.262703 and S112's nba +0.025606 (n 351) / mlb +0.007269 (n 276)
  bar           = all four metrics for BOTH sides on identical rows under the ONE S05 bin-edge rule, 0 rows dropped
                  after the pairing step, each sport labelled MATCH / BEHIND / NOT SCORABLE by its own CI. A model
                  BEHIND the close everywhere is the expected valid result; the bar is never lowered
  n             = paired rows per sport; >= 30 clusters for a MATCH/BEHIND label, else NOT SCORABLE
  eye check     = n/a (S-row); reproduction = the verifier recomputes ECE, Brier, log-loss and the CI per sport from
                  the artifact's own paired per-row series
  must not move = the ONE S05 bin-boundary rule and every landed S05 artifact byte-identical (write NEW ones);
                  regime_calibration.py and recalibration.py defaults; every eval_gate threshold; backtest_fwer.jsonl
                  untouched, K unread
NON-TAUTOLOGY: name every excluded row and why (no close, in-play close_source, null price). A gap computed after
dropping the rows where the model is worst is circular -- any other drop reason means REJECT.
EVIDENCE: docs/evidence/harness/S204_close_reference_calibration_2026-09-04.md -- per-sport table, both reliability
tables, exclusion counts, NOT VERIFIED list, summary JSON and paired per-row series under docs/evidence/ (Q9).
TEST: scripts/platformkit/eval_gate/test_s204_close_reference.py -- one new per-file test; run only that file.
REPORT: per-sport table, exclusion counts, test line, SHA. Commit by pathspec, no push. NEVER PARK.
