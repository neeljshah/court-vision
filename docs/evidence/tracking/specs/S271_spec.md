GAP S271 | sport nba | worktree a18 | log cx_s271_boxscore_quantile_producer
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: successor to S262 (CLOSED AT LIMIT, box score q50 census). Verified this session (Python parquet read):
  data/cache/{pts,reb,ast}_q50_oof_int95.parquet each has 101,765 rows, columns player_id/date/target_<stat>/
  base_q50_pred, date range 2022-10-18..2026-05-24 -- the nearest existing per-player historical box-score source
  S262 named, but point predictions only (no q10/q90), so S262 closed at n=0 comparisons. matchup_grid.parquet
  (4,900 rows) still lacks all seven required q50_* fields per S262's table.
PREMISE (step 0, INFORMATIONAL): print the three q50_oof parquets' row counts and date ranges (expect 101,765 /
  2022-10-18..2026-05-24 each); print 5 evenly spaced rows per file confirming target_pts/target_reb/target_ast
  are realized box-score values, not predictions.
CHANGE (step 1): additive producer scripts/platformkit/boxscore_quantile_producer.py (<= 300 LOC) that, using the
  three q50_oof parquets' player_id+date+target_<stat> columns as its as-of label source, fits per-stat q10/q50/
  q90 via gradient-boosted pinball-loss regression, with features built only from a player's OWN prior rows
  (game-first-date purge: no feature for a scored row may read a target_<stat> at or after that row's date),
  scored through scripts/platformkit/eval_gate/walkforward.py walk_forward with a symmetric nonzero embargo on a
  held-out season (2025-26, the tail of the date range). Emits a new dated docs/evidence/harness/ filename plus a
  sample parquet under 50 MB. Never touches player_props.py, quantile_props.py, or any existing model artifact
  (all under human-gated src/, untouched).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = q10/q90 empirical coverage vs nominal (80 pct band) and pinball loss at q50, per stat
                  (pts/reb/ast), on the held-out season
  before        = S262: n=0, no per-player q10/q90 producer exists on disk for any of the three stats
  bar           = coverage and pinball reported per stat with a game-clustered 95 pct CI, n >= 30 game clusters;
                  a test asserts 0 rows where any feature's source date is at or after the scored row's date
  n             = the held-out season's scored rows (>= 30 game clusters), denominator printed
  eye check     = n/a (S-row); reproduction = verifier reruns the producer and diffs coverage/pinball per stat
  must not move = the three q50_oof parquets, matchup_grid.parquet, every existing artifact under data/models/
                  and src/prediction/ (untouched, human-gated)
NON-TAUTOLOGY: coverage is reported on every scored row, not only rows where the point q50 was already accurate;
  miscalibrated q10/q90 (NULL) is reported as a success, never filtered out of the denominator.
EVIDENCE: docs/evidence/harness/S271_boxscore_quantile_producer_2026-09-04.md + summary JSON + sample parquet
  (< 50 MB).
TEST: one per-file test asserting the purge invariant (no future target_<stat> in any feature) on a small fixture,
  plus coverage arithmetic on a synthetic 3-row case with known quantiles.
REPORT: coverage/pinball table per stat, purge-assert result, RSS, test line, SHA. No push. NEVER PARK.
