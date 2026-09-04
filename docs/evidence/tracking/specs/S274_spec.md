GAP S274 | sport mlb | worktree a15 | log cx_s274_mlb_distribution_evaluator_route
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S244 re-issue. S244 (SUCCESS: NOT SCORABLE) landed the naive-only MLB batter/pitcher baseline via its OWN
  date-cutoff loop, calling neither shared evaluator: CRPS 0.5098297809224259, pinball q10 0.08655308369594088,
  q50 0.37323931073931077, q90 0.2013804110232682, on 777 date clusters / 3,000 rows, module
  scripts/platformkit/mlb_batter_pitcher_line_dist.py (present; score_naive_clusters:95-138). S268 (ACCEPT, verify
  37b16ade0, attempt2 86669f618 in worktree a17 branch track-a17) added the sibling scripts/platformkit/eval_gate/
  cpcv_distribution.py (cpcv_evaluate_distributional; 65 lines, SHA-256
  0e006243171a92c2102c7a6a6cb52d1eee456be60d68fef85819695333311be8) importing cpcv_engine.cpcv_splits/
  _blocked_indices/_redact/assert_vintage read-only, and reproduced these same four quantities to delta 0.0 as ITS
  OWN construct evidence -- not a landed S244-successor row. `stat` it first; if absent (lands within the hour),
  recover via `git show 86669f618:scripts/platformkit/eval_gate/cpcv_distribution.py > <path>` from a17.
PREMISE (step 0, INFORMATIONAL): confirm cpcv_distribution.py presence (stat or recover); re-run the S244 streaming
  census for non-null market_prob rows over the 777-cluster/3,000-row corpus and print the count (S244 found 0).
CHANGE (step 1): additive only, <= 300 LOC, one new adapter module beside mlb_batter_pitcher_line_dist.py: turns
  each CorpusRow into a cpcv_evaluate_distributional state dict (state_ts=score_date, game_id, outcome=
  realized_stat), a predictor returning the player's own earlier realized_stat samples (same empirical-forecast
  rule as score_naive_clusters, cold-start point mass at 0.0), and a score_fn emitting CRPS + pinball q10/q50/q90.
  Only if the premise count is nonzero: add a second, market-conditioned predictor arm scored the same way, with a
  game-clustered bootstrap CI. Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above
  the seal line via git show :<path>, verified with git show HEAD:<path>). cpcv_distribution.py and
  mlb_batter_pitcher_line_dist.py stay byte-identical (SHA-256 asserted); score only through
  cpcv_evaluate_distributional with its existing symmetric embargo_days purge, unchanged.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = CRPS + pinball q10/q50/q90 via cpcv_evaluate_distributional vs the archived S244 naive figures;
                  market-conditioned arm CRPS + pinball with a game-clustered CI, only if premise count > 0
  before        = the S244 naive figures above, scored outside the shared evaluator route (no CI, no purge assert)
  bar           = all four naive quantities reproduce to <= 1e-9 through the shared route on all 777/3,000; a
                  market arm (if any) reports a game-clustered CI; premise count = 0 means NULL is a success
  n             = 777 date clusters / 3,000 rows (n >= 30)
  eye check     = n/a (S-row); reproduction = verifier reruns the adapter and diffs all four naive quantities plus
                  the premise market-row count
  must not move = cpcv_distribution.py, mlb_batter_pitcher_line_dist.py byte-identical; embargo_days=3; the
                  archived S244 figures; every existing artifact (new dated filenames only)
NON-TAUTOLOGY: covers all 777 clusters/3,000 rows, none excluded; a zero-row market arm is measured price coverage,
  not an excluded set -- state the count plainly.
EVIDENCE: docs/evidence/harness/S274_mlb_distribution_evaluator_route_2026-09-04.md + JSON + paired-loss CSV (Q9).
TEST: one per-file test -- exact CRPS/pinball on a seeded fixture it builds; structural properties only (row/
  cluster counts, embargo assertion) on the real 777/3,000 corpus.
REPORT: premise count, 4-quantity reproduction table, market-arm CI or NULL, RSS, test line, SHA. No push. NEVER PARK.
