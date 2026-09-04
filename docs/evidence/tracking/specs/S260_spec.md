GAP S260 | sport mlb | worktree a13 | log cx_s260_mlb_batter_pitcher_line_q4
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S244 REJECT (e1bd3c1b0, docs/evidence/harness/S244_VERIFY_2026-09-04.md:23,31). Q4 FAIL: OOS scoring in
  scripts/platformkit/mlb_batter_pitcher_line_dist.py:95-138 is a custom fold loop, not walk_forward/cpcv_evaluate.
  Verifier CORRECTION (line 31): replace that fold construction with a contract route and regenerate both CSVs
  plus memo; if no compatible route exists, close at the limit naming the missing capability. Apply that diff.
PREMISE (step 0, INFORMATIONAL): re-run mlb_batter_pitcher_line_dist.py; confirm lines 95-138 still build folds
  without calling walk_forward or cpcv_evaluate; reproduce the archived naive CRPS 0.5098297809224259 and pinball
  q10/q50/q90 0.08655308369594088/0.37323931073931077/0.2013804110232682 over all 777 clusters / 3,000 rows from
  S244_attempt_2_naive_row_series_2026-09-04.csv and S244_attempt_2_naive_cluster_losses_2026-09-04.csv.
CHANGE (step 1): route the same past-only purge / 3-day symmetric embargo fold construction through
  scripts/platformkit/eval_gate/'s walk_forward or cpcv_evaluate, callback producing every scored quantity.
  Regenerate the row and cluster CSVs plus the memo under NEW filenames (additive; 0 rows dropped, 48 cold-start
  rows at point mass 0.0 kept and named). If the shared callback signature cannot accept this continuous-
  distribution scorer (S244 memo:157-159 names this exact limit), STOP and report CLOSED AT LIMIT naming the
  incompatibility. Seal a prereg FIRST (own commit; seal = SHA-256 of the committed bytes above the seal line,
  LF, verified via git show HEAD). Never write docs/research/ or data/; no src/ kernel/ api/ intel/ edits.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = naive CRPS and pinball q10/q50/q90 over all 777 date clusters, scored via the contract route
  before        = CRPS 0.5098297809224259; pinball 0.08655308369594088/0.37323931073931077/0.2013804110232682
                  (custom loop, S244 attempt 2)
  bar           = the contract route reproduces all four numbers at max abs diff <= 1e-9 on the same 777
                  clusters / 3,000 rows, 0 rows dropped; OR CLOSED AT LIMIT naming the exact incompatibility
  n             = 777 clusters / 3,000 rows (all scored; exceeds the 30 rail)
  eye check     = n/a (S-row); reproduction = verifier reruns the contract route and diffs all four numbers
  must not move = the 30-cluster bar; prop_history_corpus_mlb.jsonl (read-only); the 48 cold-start point-mass rule
NON-TAUTOLOGY: all 777 clusters / 3,000 rows stay in the denominator; no cluster or row is dropped to make the
  reproduction clean.
EVIDENCE: docs/evidence/harness/S260_mlb_batter_pitcher_line_q4_2026-09-04.md plus new CSVs (new filenames only).
  ASCII only; calibration language only; evidence files under 50 MB.
TEST: one new per-file test (contract-route CRPS/pinball match the custom-loop archive to 1e-9), run only that
  file.
REPORT: four before/after pairs, seal hashes, evaluator assertion, test line, SHA. Commit by pathspec, no push.
  NEVER PARK.
