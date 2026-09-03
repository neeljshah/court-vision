GAP S205 | sport all (pregame) | worktree a18 | log cx_s205_calib_bakeoff
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S05_calibration_report_2026-09-03.md section 2, verbatim: "On nba, soccer and tennis per-regime isotonic buys
a large calibration gain and pays for it in resolution every time (nba -0.0026823, soccer -0.0005781, tennis
-0.0006802)"; on mlb "recalibration made BOTH ECE and reliability WORSE." No sport reaches IMPROVES. Items 3, 2 and 1
(ranks 2, 3, 6) of docs/research/model_quality_methods_2026-09-04.md name the untried fix -- the CALIBRATOR family,
not more features (Guo 2017; Kull 2017; Zadrozny and Elkan 2002).
PREMISE (step 0): re-measure and print the S05 headline: nba 1,814 ECE 0.053328 -> 0.024843, RES 0.0398911 ->
0.0372088; mlb 39,162 ECE 0.005918 -> 0.008077, RES 0.0040466 -> 0.0039913; soccer 25,834 ECE 0.106927 -> 0.009302,
RES 0.0028144 -> 0.0022363; tennis 41,886 ECE 0.038691 -> 0.008403, RES 0.0317161 -> 0.0310359; FLATTENED 4/4, 0
dropped, reproduction_max_abs_diff 0.0. If falsified, STOP, memo, commit, report FALSIFIED.
LIMIT (step 1): the sealed rule is IMPROVES only when ECE falls AND Murphy reliability falls AND resolution does not
fall. Print the resolution BUDGET the isotonic arm spent before fitting. If no calibrator can spend less without
losing the ECE gain, the result is a resolution-tax table with 0/4 IMPROVES -- report it, do not tune.
CHANGE (step 2): smallest additive change -- two extra calibrator arms (single-scalar temperature on the logit; the
3-parameter beta map) fitted on EXACTLY the folds, regime keys and bins the isotonic arm uses, so arms differ ONLY by
the calibrator; isotonic default byte-identical. Additive only, nothing renamed; helper <= 300 lines within
test_loc_rail_scope.py; never write data/; no flag on; no edits in src/ kernel/ api/ intel/ scripts/team_system/; one
store at a time, never > 300 MB; never touch register or ledger.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per sport per calibrator: ECE, Murphy reliability, Murphy resolution, sharpness and log-loss over
                  denominators 1,814 / 39,162 / 25,834 / 41,886 rows, with the sealed S05 verdict applied unchanged
  before        = the isotonic arm above (ECE after 0.024843 / 0.008077 / 0.009302 / 0.008403; resolution deltas
                  -0.0026823 / -0.0000553 / -0.0005781 / -0.0006802), FLATTENED on 4 of 4
  bar           = 12 cells scored (4 sports x 3 calibrators), 0 rows dropped, the isotonic column reproducing the four
                  published after-ECEs at max abs diff exactly 0.0, every cell carrying the sealed verdict. 0/8 new
                  cells reaching IMPROVES is the expected valid result; the sealed rule is never relaxed
  n             = 1,814 / 39,162 / 25,834 / 41,886 scored rows per sport (sampled metric, >= 30 satisfied)
  eye check     = n/a (S-row); reproduction = the verifier refits all three arms and recomputes ECE, both Murphy terms
                  and log-loss per cell from the artifact's own bins and per-row predictions
  must not move = the sealed S05 IMPROVES rule and its ONE bin-boundary rule; every landed S05 artifact byte-identical
                  (write NEW ones); the isotonic default path; every eval_gate threshold; backtest_fwer.jsonl
                  untouched, K unread
NON-TAUTOLOGY: all four corpora keep every scored row in every arm; no bucket, regime or sport is dropped for a
calibrator that fails there. A resolution-tax table computed only where the new arm wins is circular -- REJECT.
EVIDENCE: docs/evidence/harness/S205_calib_bakeoff_2026-09-04.md -- the 12-cell table, per-sport bin tables per arm,
the resolution-tax column, NOT VERIFIED list, summary JSON and per-row predictions under docs/evidence/ (Q9).
TEST: scripts/platformkit/eval_gate/test_s205_calib_bakeoff.py -- one new per-file test; run only that file.
REPORT: the 12-cell table, the isotonic reproduction diff, test line, SHA. Commit by pathspec, no push. NEVER PARK.
