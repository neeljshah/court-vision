GAP S281 | sport nba (in-game) | worktree a17 | log cx_s281_ingame_momentum_microstructure
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: hypothesis: within-game momentum (a recent scoring run, a run just ending) is priced late by the
  venue, so it improves recal_null more on stale ticks (S277's staleness definition). Verified via a one-column
  parquet read of nba_checkpoints_full.parquet (465,249 ticks/1,593 games): columns are game_id, game_date, ts,
  period, game_clock_s, score_home, score_away, margin, market_prob, traded, market_ticker, outcome_home_win,
  venue. `event_key` is NOT FOUND on this store (present only on the separate nba_price_series.parquet, a
  different schema); this row derives its features from score_home/score_away/ts/period/game_clock_s alone, as
  the task allows, and does not read event_key.
PREMISE (step 0, INFORMATIONAL): reprint the verified column list and the event_key NOT FOUND finding; print 5
  distinct rows of period/game_clock_s/score_home/score_away ordered by (game_id, ts) to confirm ticks are
  monotonic per game and margin = score_home - score_away as documented.
CHANGE (step 1): additive; per tick, using strictly prior ticks of the SAME game only (assert in test via a
  planted future row that must not affect the computed value): a `run_120s` feature = the home-minus-away scoring
  swing over the trailing 120 wall-clock seconds by ts; a `run_just_ended` flag = 1 when a run_120s magnitude
  above a fixed, printed threshold was present at the prior tick and has since gone to zero. Add both as
  independent additive terms to the S123 recal_null incumbent, scored through
  scripts/platformkit/eval_gate/cpcv_engine.cpcv_evaluate with purge and a symmetric nonzero embargo on the full
  465,249-tick grid, plus the same S277 fresh/stale interaction (recal_null-plus-momentum improvement, stale
  bin minus fresh bin, with CI). Never touches S123/S224/S272/S277 artifacts; never flips a flag.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (recal_null + run_120s + run_just_ended) minus recal_null Brier, pooled and per S277
                  fresh/stale bin, game-clustered 95 pct CI, plus the stale-minus-fresh interaction with CI
  before        = recal_null Brier on the full archive (no momentum feature has ever been scored here)
  bar           = the frozen +0.004 bar pooled; NULL (CI includes or is below zero) is a success and reported as
                  such regardless of the interaction's sign
  n             = >= 30 game clusters pooled and in each of the fresh/stale bins, printed separately
  eye check     = n/a (S-row); reproduction = verifier reruns the feature build and scorer with the planted
                  future-row test and diffs every number
  must not move = nba_checkpoints_full.parquet, S123's market default, S277's staleness definition, the +0.004
                  bar; backtest_fwer.jsonl untouched, K unread, nothing charged
NON-TAUTOLOGY: the run_120s window and the run_just_ended threshold are fixed and printed before scoring, never
  tuned against the outcome; every one of the 465,249 ticks is assigned a feature value, none dropped for a
  missing 120s window (a game's first 120 seconds use whatever prior ticks exist, named as a boundary case).
EVIDENCE: docs/evidence/harness/S281_ingame_momentum_microstructure_2026-09-04.md + summary JSON + paired-loss
  CSV.
TEST: one per-file test asserting a planted future row (ts after the scored tick) does not change run_120s or
  run_just_ended for a fixed fixture tick, plus one reproduced Brier delta from the archived CSV.
REPORT: pooled and fresh/stale table, interaction CI, RSS, test line, SHA. No push. NEVER PARK.
