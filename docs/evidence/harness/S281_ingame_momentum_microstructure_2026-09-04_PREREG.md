# S281 preregistration: NBA in-game momentum microstructure

## Fixed protocol

- Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet`, one parquet
  store, 2,829,826 bytes, 465,249 ticks in 1,593 game clusters. Tabular input:
  resolution is not applicable. The verified schema is `game_id, game_date,
  ts, period, game_clock_s, score_home, score_away, margin, market_prob,
  traded, market_ticker, outcome_home_win, venue`; `event_key` is NOT FOUND.
- Each game is stably ordered by `(ts, source row order)`. `run_120s` is the
  home-minus-away margin change from the earliest to the latest strictly prior
  tick whose timestamp is within the trailing 120 seconds. A tick with no
  prior in-window tick is assigned 0.0. The current tick never contributes to
  its own feature, and the first tick is the named boundary case with 0.0.
- `run_just_ended` is 1 exactly when the prior tick had `abs(run_120s) > 6.0`
  and the current tick's strictly-prior `run_120s` is 0.0; otherwise it is 0.
  The window (120 seconds) and threshold (6.0 points) are fixed before scoring.
- S277 staleness is reproduced unchanged: after the named first tick of each
  game, age is seconds since the most recent `market_prob` change; fresh is
  age <= 600 seconds, stale is age > 7,739 seconds, and all other rows are the
  named middle bin. No bin uses an outcome, a feature loss, or a model loss.
- Arms: frozen `recal_null` from unmodified
  `scripts.platformkit.foundry.ingame_incumbent_nba.apply_incumbent(rows,
  "recal_null")`; and an additive logistic arm fit inside each CPCV training
  path on `[recal_null, run_120s, run_just_ended]`. Each term is independent;
  no interaction term is supplied. Recalibration seed rows without a frozen
  incumbent remain separately counted, never fabricated.
- OOS scorer: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with
  two chronological groups, one test group, shared purge, and a symmetric
  one-day embargo. There is exactly one stable evaluator state per scored tick:
  `game_id|ts|source_row_id`. The candidate model is fit only on the passed
  CPCV training states; both archive losses are computed from its evaluator
  records.
- Metrics: tick-weighted Brier for the frozen incumbent and additive arm in
  fresh, stale, and pooled scored populations. Improvement is recal_null Brier
  minus additive-arm Brier. Game-clustered 95 percent bootstrap intervals use
  2,000 resamples and seed 281; the stale-minus-fresh interaction uses the
  same resampled game-cluster weights. Each scored fresh and stale population
  must contain at least 30 game clusters.
- Acceptance: the pooled frozen bar is +0.004. A pooled improvement interval
  that includes or is below zero is NULL and is reported as a successful
  calibration result regardless of interaction sign. No AHEAD claim is made.
- Differential archive: write the S281 memo, summary JSON, and paired-loss
  CSV. The focused test checks that a planted future row cannot change either
  feature at a fixed earlier tick and reproduces pooled Brier values from CSV.

Seal SHA-256: 10ddf9f7845b2a63cf02ac30247100b82ec06f8a5ad871978d0ab1c5cea1202b
