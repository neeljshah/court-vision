GAP S200 | sport all (harness) | worktree a13 | log cx_s200_regime_key_oof
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/S05_calibration_report_2026-09-03.md:144, verbatim: "- `regime_calibration.buckets`
assigns confidence terciles from a whole-corpus ranking, so the regime KEY is fitted on all rows including the
scored one. Only the isotonic map is out-of-fold; the key is not." Corroborated as SF-5 (:19) and SF-18 (:32) in
docs/evidence/harness/REDTEAM_SIGNAL_FACTORY_2026-09-03.md. Every published four-sport calibration number
rests on a regime key fitted on the row it scores.
PREMISE (step 0): re-measure and print the S05 headline this rests on -- ECE before -> after, 0 dropped:
nba 1,814 rows 0.053328 -> 0.024843; mlb 39,162 rows 0.005918 -> 0.008077; soccer 25,834 rows 0.106927 ->
0.009302; tennis 41,886 rows 0.038691 -> 0.008403; verdict FLATTENED on all four. Read
scripts/platformkit/regime_calibration.py and confirm the global tercile sort (:52-58) still assigns confidence
T1/T2/T3. If any headline is falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): the leak is in the KEY only. Before changing anything, recompute the tercile cut points from the
expanding TRAIN window alone and count, per sport, how many scored rows change confidence label. If 0 rows
change on all four corpora the leak is inert -- report CLOSED AT LIMIT with the four counts and do not fix.
CHANGE (step 2): the smallest additive change -- an opt-in key_source="train" path taking the tercile cut points
from the train window and assigning the scored row by them. Default byte-identical; nothing renamed or
removed; new helper <= 300 lines, inside tests/platformkit/test_loc_rail_scope.py counts; never write data/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-sport ECE after per-regime recalibration under train-only regime keys, denominators
                  1,814 / 39,162 / 25,834 / 41,886 rows, plus the per-sport count of scored rows whose
                  confidence label changes
  before        = the four published after-ECEs: nba 0.024843, mlb 0.008077, soccer 0.009302, tennis 0.008403
  bar           = 4/4 sports re-scored under train-only keys with the label-change count printed; the DEFAULT
                  path reproduces those four after-ECEs at max abs diff exactly 0.0; 0 rows dropped
                  (denominators exactly as above). An ECE that WORSENS under the honest key is the expected,
                  valid result, published as-is; the bar is never lowered
  n             = 4 corpora scored on 1,814 / 39,162 / 25,834 / 41,886 rows (sampled metric, >= 30 satisfied)
  eye check     = n/a (S-row); reproduction = the verifier reruns both paths and recomputes ECE per sport from
                  the new artifact's own bins and per-row predictions
  must not move = the S05 ONE bin-boundary rule; regime_calibration.py default behaviour; every landed
                  docs/evidence/calibration artifact byte-identical (write NEW ones); every eval_gate threshold;
                  data/cache/eval_gate/backtest_fwer.jsonl untouched with K unread
NON-TAUTOLOGY: every scored row of all four corpora stays in the denominator; no row is dropped for changing
label. A train-only ECE computed on a subset (only rows whose label held) is circular -- report REJECT.
EVIDENCE: docs/evidence/harness/S200_regime_key_oof_2026-09-04.md -- the four-sport before/after table, the
label-change counts, the default-path max abs diff, a NOT VERIFIED list, and the per-sport bin tables plus a
summary JSON under docs/evidence/ so every number reproduces from the artifact alone.
TEST: scripts/platformkit/eval_gate/test_s200_regime_key_oof.py -- one new per-file test; run only that file.
REPORT: four deltas, label-change counts, diff stat, test line, SHA. Commit by pathspec, no push. NEVER PARK.
