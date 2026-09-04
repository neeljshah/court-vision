# S272 preregistration: NBA in-game pooled-tail recalibration

## Fixed protocol

- Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet`, one parquet
  store, 2,829,826 bytes, 465,249 ticks in 1,593 game clusters. Tabular input:
  resolution is not applicable.
- Population: every tick is retained for all-ticks Brier. The fixed tail is
  exactly `market_prob <= 0.10 or market_prob >= 0.90`; tail-only Brier and
  ECE use that same named population.
- Incumbent: `recal_null`, logistic recalibration on logit(market probability),
  fit only on strict-prior training games. Candidate: independent isotonic maps
  for the low and high tail, each fit only on that side's strict-prior tail
  ticks. Outside the fixed tail, the candidate equals `recal_null`.
- OOS route: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with
  two chronological groups, one test group, its shared team/matchup purge, and
  a symmetric one-day calendar embargo. The predictor additionally admits to a
  fit only game-first-dates strictly before the scored game's first date. The
  first season has no prior season and therefore both arms fall back to market.
- Season folds: 2024-25 and 2025-26 from the NBA July-to-June convention. The
  trainable 2025-26 fold fits on 2024-25 only; no later game enters a fit.
- Metrics: tick-weighted Brier for all ticks and tail ticks, plus 10-bin tail
  ECE. Report each arm and a game-clustered 95 percent bootstrap interval for
  each metric (2,000 resamples, seed 272). Store per-game all-tick paired loss
  sums and per-tail-tick paired rows for reconstruction.
- Acceptance: unchanged all-ticks Brier improvement bar `+0.004` versus
  `recal_null`; tail ECE is diagnostic. A nonpositive all-ticks improvement is
  BEHIND even if tail ECE declines. Each reported denominator must have at
  least 30 game clusters.
- Artifacts: `S272_ingame_tail_recal_screen_2026-09-04.md`,
  `_summary.json`, and `_paired_losses.csv`; focused test
  `scripts/platformkit/ingame/test_s272_ingame_tail_recal.py` recomputes one
  season fold's tail ECE and all-ticks Brier from the archived CSV.

Seal SHA-256: bd33af6d49a43150916e7d4d6a0dd6e15a520165aab9a2834159042b39ed006d
