GAP S279 | sport nba (in-game) | worktree a15 | log cx_s279_ingame_signal_stacker
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: a stacked meta-arm over S123's recal_null incumbent plus every archived AS-OF-SAFE per-tick signal
  already on disk. Source: docs/evidence/harness/S223_intel_pool_asof_census_2026-09-04.json, `stores` array,
  `label`=="AS-OF SAFE" -- 49 of 158 present rows (4 atlas + 45 intelligence), e.g.
  data/cache/atlas_player_durability_load.parquet (as_of, 768 rows), data/intelligence/anomaly_log.parquet
  (game_date, 812 rows). SNAPSHOT-ONLY (55) and UNDATED (54) rows are excluded by construction: they cannot be
  joined as-of without a future leak. Incumbent grid: data/cache/inplay_odds/nba_checkpoints_full.parquet
  (465,249 ticks/1,593 games; verified columns game_id, game_date, ts, period, game_clock_s, score_home,
  score_away, margin, market_prob, traded, market_ticker, outcome_home_win, venue).
PREMISE (step 0, INFORMATIONAL): re-read S223's JSON, filter label=="AS-OF SAFE", print the count (expect 49)
  and every path plus its as_of/date column, grouped atlas vs intelligence; re-verify each named path still
  exists and its temporal column name is unchanged (report NOT FOUND per path rather than dropping it silently).
CHANGE (step 1): additive per-tick join of the incumbent grid to each AS-OF-SAFE store on player/team grain and
  the as-of temporal column, keeping only rows strictly before the scored game's date; a walk-forward logistic
  stacker (recal_null's probability plus every joined signal column as inputs) with L2 shrinkage toward the
  recal_null coefficient, shrinkage strength chosen on TRAIN folds only via scripts/platformkit/eval_gate's
  existing CV split, scored through scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate with purge and a
  symmetric nonzero embargo. Missing joins for a given tick are imputed to the recal_null-only prediction, named
  and counted, never dropped silently. Never touches S223's or S123's artifacts (new dated filenames only);
  never flips a flag; never writes data/registry/.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = stacker Brier minus recal_null Brier (positive = improvement), game-clustered 95 pct CI, plus
                  the fitted shrinkage path and final per-signal weight vector
  before        = S123 recal_null incumbent Brier on the full 465,249-tick archive (identity comparison; no
                  stacked arm has ever been scored against this incumbent)
  bar           = the frozen +0.004 bar over recal_null; a NULL (CI includes zero or below) means the archived
                  AS-OF-SAFE signals carry no incremental calibration and is reported as a valid success
  n             = >= 30 game clusters, printed; the AS-OF-SAFE enumeration itself is n = 49 (CONSTRUCT: every
                  present labelled row from S223's JSON, exhaustive by construction)
  eye check     = n/a (S-row); reproduction = verifier reruns the join, refits the stacker on the same folds,
                  and diffs the Brier delta and weight vector
  must not move = S223's JSON, nba_checkpoints_full.parquet, S123's market default, the +0.004 bar;
                  backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: every one of the 465,249 ticks is scored, including ticks whose signal join is imputed; a
  candidate that only scores joined-and-present ticks is circular and self-rejected by the lane.
EVIDENCE: docs/evidence/harness/S279_ingame_signal_stacker_2026-09-04.md + summary JSON + weight/paired-loss CSVs.
TEST: one per-file test fitting the stacker on a small fixture with one signal and asserting the shrinkage
  path collapses to the recal_null-only prediction at maximum shrinkage.
REPORT: Brier delta, CI, weight vector, imputed-tick count, RSS, test line, SHA. No push. NEVER PARK.
