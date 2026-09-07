# S283 preregistration attempt 2: NBA time-score blend

Date: 2026-09-04

This sealed attempt replaces the prior unscored preregistration after its seal
check failed under CRLF normalization. No metric was produced before this file.
It concerns one additive, offline calibration measurement arm; no production
route changes.

## Inputs and scope

- Input: `data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2,829,826 bytes,
  tick resolution, loaded only through
  `scripts.platformkit.eval_gate.s86_nba_every_tick.load_ticks`.
- Baseline: `scripts.platformkit.foundry.ingame_incumbent_nba.apply_incumbent`
  with `kind="recal_null"`, fit only in the evaluator train membership.
- Candidate: a strictly-prior empirical outcome table keyed by
  `period_bucket`, `margin_bucket`, and `rem_bucket`. A cell with fewer than
  200 train rows uses its named parent `period_bucket` table. No test row is
  removed for sparsity.

## Frozen scoring plan

- Use `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with
  `n_groups=5`, `n_test_groups=1`, and `embargo_days=1`. Its symmetric purge
  and embargo are the only split route.
- Supply one evaluator state per scored tick, with the stable key
  `game_id|ts|period|game_clock_s`. The evaluator callback emits both the
  recalibrated-null and candidate probability for every archived tick.
- Fit the table and select `k` afresh inside each callback train membership.
  Select `k` by train Brier from exactly `(0.5, 1.0, 2.0, 4.0)`; record the
  chosen value and all train-grid Briers for each split.
- Candidate probability is `(1 - rem_fraction ** k) * table_prob +
  (rem_fraction ** k) * market_prob`, with `rem_fraction=rem/48` clipped to
  `[0, 1]`.
- Archive only evaluator records: a paired per-tick CSV, summary JSON, and
  memo. Calculate every reported loss from the paired CSV.
- Headline metric is mean game-cluster Brier(recal_null) minus mean
  game-cluster Brier(blended arm), with a deterministic game-clustered 95 pct
  bootstrap CI. The frozen bar is `+0.004`; positive means lower candidate
  Brier. At least 30 game clusters are required.

## Planned files

- `scripts/platformkit/ingame/s283_bayes_timescore_blend.py`
- `tests/platformkit/ingame/test_s283_bayes_timescore_blend.py`
- `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04.md`
- `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_summary.json`
- `docs/evidence/harness/S283_bayes_timescore_blend_2026-09-04_paired_loss.csv`

Seal SHA-256: e60457016bc5cb8ba10ed8d460a4593334456bed9a55ea2aedca3bfcd97cf224
