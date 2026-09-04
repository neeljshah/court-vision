# S277 preregistration: NBA in-game market staleness, attempt 2

## Fixed protocol

- Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet`, one parquet
  store, 2,829,826 bytes, 465,249 ticks in 1,593 game clusters. Tabular input:
  resolution is not applicable. The verified schema is `game_id, game_date,
  ts, period, game_clock_s, score_home, score_away, margin, market_prob,
  traded, market_ticker, outcome_home_win, venue`; `state_age_s` and
  `event_key` are NOT FOUND.
- Staleness is recomputed per `game_id` after a stable ascending sort by `ts`
  (source row order breaks timestamp ties). A tick's age is seconds since the
  timestamp of the most recent row at which `market_prob` changed. The first
  tick of every game has no prior price and is the named first-tick exclusion.
- The pre-score distribution has 463,656 ticks in scope after 1,593 named
  first-tick exclusions. The integer timestamps are Unix seconds; its frozen
  p50 is 600 seconds and frozen p90 is 7,739 seconds. Fresh is age <= p50;
  stale is age > p90; all remaining in-scope ticks are the named middle band.
  No tick's bin depends on outcome or either arm's loss.
- Arms: raw `market_prob` and unmodified `recal_null` from
  `scripts.platformkit.foundry.ingame_incumbent_nba.apply_incumbent(rows,
  "recal_null")`. The incumbent route is not edited or refit. The recalibration
  route's named unscorable seed rows, if any, remain separately counted rather
  than assigned a fabricated fitted value.
- OOS scorer: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with
  two chronological groups, one test group, its shared purge, and a symmetric
  one-day calendar embargo. Each scored tick is one state with stable key
  `game_id + tick timestamp`; its probability and feature availability are
  reconstructed from that tick only. The scorer runs once per arm. The two
  evaluator outputs must have identical split, outcome, and stable-key records;
  every archived loss is then derived only from those evaluator records.
- Metrics: tick-weighted Brier for recal_null and market_prob in fresh, stale,
  and pooled scored populations; improvement is market Brier minus recal_null
  Brier. Use a game-clustered 95 percent bootstrap interval with 2,000
  resamples and seed 277. The stale-minus-fresh improvement interaction uses
  the same resampled game-cluster weights and its own 95 percent interval.
- Acceptance: stale improvement is compared against the unchanged +0.004 bar.
  A stale improvement below +0.004, or an interaction interval crossing zero,
  is NULL and is a successful result. Each fresh and stale scored population
  must contain at least 30 game clusters.
- Differential archive: write `S277_ingame_market_staleness_2026-09-04_attempt2.md`,
  `_summary.json`, and `_paired_losses.csv`; the CSV stores per-tick cluster,
  timestamp, arm predictions, and paired losses. Focused test
  `scripts/platformkit/ingame/test_s277_ingame_market_staleness.py` checks a
  first-tick exclusion, a price-move pattern with a timestamp tie, a one-state-
  per-scored-tick fixture, a planted-future-row guard, and one archived-bin
  Brier reconstruction.

Seal SHA-256: 5cb04bba07a94ca0372bc2d5e8d2af65bd759d093c1c446e9eed76da1b90d7df
