# S227 preregistration: NBA in-game final-margin CRPS

Status: SEALED BEFORE SCORING
Spec: `docs/evidence/tracking/specs/S227_spec.md`
Verifier: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q

## Sealing rule

`seal_sha256_payload` is the SHA-256 of this file with the value on that line
set to `PENDING`. This lets the embedded seal be reproduced without a
self-referential hash.

seal_sha256_payload: 53915e8b77ccd7336a088b71052c325956bc4c62c0bda60679d5954c9c0b0eb7

## Fixed inputs

- `C:\Users\neelj\nba-track-a17\data\cache\inplay_odds\nba_checkpoints_full.parquet`, 2,829,826 bytes, parquet table (no raster resolution); 465,249 rows and 1,593 game ids measured in the premise pass.
- `C:\Users\neelj\nba-track-a17\data\intelligence\garbage_time_segments.parquet`, 4,851,899 bytes, parquet table (no raster resolution); its `game_id` and `is_garbage_time` fields supply an optional descriptive blowout label only.

No register or results-ledger file will be read or written. No file under `data/` will be written.

## Frozen scoring design

- Unit: all 465,249 checkpoint ticks clustered into 1,593 games. The observed target for every tick is the score-home minus score-away value at that game's chronologically last checkpoint. A game is never excluded; any unavailable join is reported with its count and uses the fixed-sigma arm only.
- Frozen ladder: `(5, 10, 15, 20, 25, 30)`. Every point is reported even when the observed event count is zero.
- Distribution: for a tick with current margin `m`, its game's first traded `market_prob` recorded in the checkpoint corpus as fixed as-of prior `p0_asof`, remaining regulation fraction `r`, and sigma `s`, score `Normal(m + s * Phi^-1(p0_asof) * r, s * sqrt(r))`. At `r = 0`, use a point mass at `m` and CRPS is absolute error. This is the distributional form of the fixed-sigma repricer. The premise pass measured a non-null first traded probability for all 1,593 games.
- BEFORE arm: fixed `s = 13.5` throughout. The existing repricer is not edited.
- FITTED arm: per phase cell `period_bucket|margin_bucket|rem_bucket`, where `period_bucket` is P1, P2, P3, or P4 (P4 includes overtime); `margin_bucket` is `abs_margin_le5`, `abs_margin_6_12`, or `abs_margin_ge13`; and `rem_bucket` is `rem_gt12`, `rem_6_12`, or `rem_le6`, using regulation-equivalent minutes remaining. Select from frozen grid `3.0` through `60.0` inclusive in 0.5 increments by minimum train-only mean Gaussian CRPS. A cell with fewer than 200 train ticks uses 13.5. The target is never used in its own fitted value.
- OOS partitions: `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`, five chronological timestamp groups, one test group per path, `embargo_days=1`. The imported evaluator supplies its symmetric nonzero calendar embargo and same-team/matchup purge. The test callback receives redacted test states and returns a constant valid probability only to certify the shared split; the frozen fitting and CRPS scoring use only that evaluator's recorded train/test game memberships.
- Primary statistic: tick CRPS, first averaged within game, then averaged across game clusters. The fitted-minus-fixed difference is reported as fixed minus fitted, so a positive value means lower fitted CRPS. The 95 percent interval is a 10,000-resample game-cluster bootstrap with seed 227.
- Tail calibration at each frozen ladder point: `nominal_tail_rate` is the mean predicted `P(abs(final_margin) >= ladder_point)`; `empirical_tail_rate` is the observed game-clustered tick rate; `coverage_gap` is empirical minus nominal; `event_count` is the unfiltered observed count. These are descriptive calibration quantities, not selection criteria.
- Differential archive: one committed per-game row containing both arm CRPS values, their difference, the game id, game timestamp, tick count, all six observed and nominal tail rates, and the optional garbage-time label.

## Required checks

- The premise has already established non-null margin/outcome/score fields and exact final-tick margin recovery for all 1,593 games before this seal.
- The run asserts each scored game appears once as a test game, no train/test game overlap, and every train-game/test-game date separation has absolute distance greater than the one-day symmetric embargo.
- The run prints the reason and count for every unavailable prior join; the acceptance report must show zero dropped games or state FALSIFIED/REJECT.
- The focused test fixes the Gaussian CRPS value for a known draw and asserts the frozen ladder exactly.

## Claim boundary

This is a calibration measurement only. A fitted sigma no better than 13.5 is a valid result. No monetary performance claim is permitted.
