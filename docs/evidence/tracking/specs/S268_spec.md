GAP S268 | sport mlb | worktree a17 | log cx_s268_distributional_evaluator_route
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S260 (CLOSED AT LIMIT 3493e217c) and S244 (CLOSED AT LIMIT 4f9206946). Verified: walkforward.py
  def walk_forward:122, "raise ValueError(...out of [0,1])":149; cpcv_engine.py def cpcv_evaluate:93,
  "raise ValueError(...out of [0,1])":126 -- both routes accept only a scalar Predictor and reject a sample vector.
  scripts/platformkit/mlb_batter_pitcher_line_dist.py already present in this repo (no recovery needed);
  score_naive_clusters:95-138 owns its own date-cutoff loop, calling neither evaluator. Archived naive figures
  (S260_mlb_batter_pitcher_line_q4_2026-09-04.md, informational reproduction table): CRPS 0.5098297809224259,
  pinball q10 0.08655308369594088, q50 0.37323931073931077, q90 0.2013804110232682, on 777 date clusters/3,000 rows.
PREMISE (step 0, INFORMATIONAL): confirm score_naive_clusters:95-138 still calls neither evaluator; confirm both
  evaluators still validate `0.0 <= p <= 1.0` and would reject a returned sample sequence.
CHANGE (step 1): additive only, <= 300 LOC, one new function beside cpcv_evaluate importing cpcv_splits and the
  purge/embargo helpers unchanged: accepts a predictor returning an empirical forecast (sample sequence) instead of
  a scalar, applies the IDENTICAL cpcv_splits fold construction + purge + symmetric embargo (same PURGE_HOURS=48 /
  EMBARGO_DAYS=3 constants, untouched), then calls a supplied score_fn(forecast, settled_outcome) -> named
  quantities dict per row (CRPS, pinball q10/q50/q90) appended to the record; existing cpcv_evaluate is not edited,
  byte-identical, asserted by SHA-256. Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes
  above the seal line via git show :<path>, verified with git show HEAD:<path>) fixing: a seeded >= 30-state
  synthetic fixture the test builds itself, with ONE planted leak (a train-eligible row whose feature encodes the
  test row's own outcome, purged only when embargo/purge run); and the 777-cluster/3,000-row MLB re-score plan.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (a) new-route Brier on the fixture (degenerate point-mass forecast) vs cpcv_evaluate's own Brier
                  on the identical fixture; (b) Brier delta between purge-ON and a purge-OFF debug-only rerun of the
                  SAME fixture (never used for real scoring); (c) S244 naive CRPS/pinball q10/q50/q90 via the new
                  route on all 777 clusters/3,000 rows vs the archived figures above
  before        = no distributional route exists; both public evaluators reject a vector return (S260 memo)
  bar           = (a) <= 1e-9; (b) != 0.0 (purge/embargo demonstrably changes the score, proving it is exercised);
                  cpcv_engine.py and walkforward.py SHA-256 byte-identical to master; (c) reproduces to <= 1e-9 OR
                  the exact per-quantity discrepancy is printed and the row reports CLOSED AT LIMIT (a valid result)
  n             = fixture: >= 30 states, self-built (CONSTRUCT); MLB re-score: 777 clusters / 3,000 rows (n >= 30)
  eye check     = n/a (S-row); reproduction = verifier reruns the fixture test and the MLB re-score, diffs (a)-(c)
  must not move = cpcv_evaluate + cpcv_splits + walkforward.py byte-identical; PURGE_HOURS/EMBARGO_DAYS; the
                  archived S244/S260 figures above; the existing S244/S260 evidence files (new dated filenames only)
NON-TAUTOLOGY: the leaky rerun must actually score better than the honest one on the planted metric alone, or the
  fixture proves nothing about purge; report that comparison explicitly, not just that the deltas differ.
EVIDENCE: docs/evidence/harness/S268_distributional_evaluator_route_2026-09-04.md + fixture JSON + the MLB
  per-cluster paired-loss CSV (Q9) if the re-score runs.
TEST: one new per-file test building the fixture in-file, asserting the Brier match + the leak/no-leak delta only.
REPORT: fixture match, leak delta + honest-vs-leaky comparison, byte-identity, S244 reproduction table or named
  discrepancy, SHA. No push. NEVER PARK.
