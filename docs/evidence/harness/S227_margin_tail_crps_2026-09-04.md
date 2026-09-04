# S227 NBA in-game final-margin CRPS and tail calibration

## NOT VERIFIED

This lane memo records the attempt-2 correction and fresh regeneration. It is
not an independent verification decision. The existing fixed 13.5 sigma
repricer remains unchanged, and this additive measurement makes no deployment
or monetary claim.

## ATTEMPT 2: target-alignment correction

The verifier rejected attempt 1 because fitted-cell training used the first
`len(cell)` values from the full training target array. The correction removes
that full-train array and supplies
`sub["final_margin"].to_numpy(float)` to each cell's Gaussian CRPS call. The
CPCV memberships, purge, symmetric one-day embargo, fixed sigma, frozen
ladder, grid, minimum training count, bootstrap seed, and uncharged screen
status are unchanged.

| Quantity | Attempt 1 | Attempt 2 corrected |
|---|---:|---:|
| Fixed arm mean game CRPS | 2.831221751521 | 2.831221751521 |
| Fitted arm mean game CRPS | 3.156220895132 | 2.827759236496 |
| Fixed minus fitted CRPS | -0.324999143612 | 0.003462515025 |
| Game-clustered 95 percent interval | [-0.347001407359, -0.303568411729] | [0.000419169197, 0.006640873627] |

The fixed arm and empirical tail-coverage row reproduce unchanged. Corrected
fitted nominal tail coverage is shown in the results table.

## Preregistration and inputs

The preregistration was sealed before the final scored run: `docs/evidence/harness/S227_margin_tail_crps_prereg_2026-09-04.md`. Its canonical payload SHA-256 is `53915e8b77ccd7336a088b71052c325956bc4c62c0bda60679d5954c9c0b0eb7`. Canonicalization replaces the embedded seal value with `PENDING` before hashing.

Inputs opened one store at a time:

- `C:\Users\neelj\nba-track-a17\data\cache\inplay_odds\nba_checkpoints_full.parquet`, 2,829,826 bytes, parquet table, no raster resolution.
- `C:\Users\neelj\nba-track-a17\data\intelligence\garbage_time_segments.parquet`, 4,851,899 bytes, parquet table, no raster resolution.

The premise reproduced 465,249 ticks and 1,593 games. Margin, outcome, and both scores were non-null throughout. The score-home minus score-away value at each game final checkpoint matched its recorded margin for all 1,593 games. The first traded checkpoint probability was available for every game. Zero games and zero ticks were dropped. The optional garbage-time join had zero true labels; this label is descriptive only and never changes scoring.

## OOS design

The run used `scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` with five chronological groups, one test group per path, and a symmetric one-day embargo. The imported evaluator also applies its purge. The callback records only evaluator train/test memberships; each game is test-scored once. Fitted sigmas use only the corresponding train memberships. The fixed ladder was `5, 10, 15, 20, 25, 30`; every point is retained below.

The fixed arm uses sigma 13.5. The fitted arm selects a train-only CRPS minimum per frozen phase cell from 3.0 through 60.0 in 0.5 increments, with a 200-tick minimum and fixed-sigma fallback. The game-clustered interval uses 10,000 bootstrap resamples with seed 227.

## Results

| Arm | Mean game CRPS | n_eff games |
|---|---:|---:|
| Fixed sigma 13.5 | 2.831222 | 1,593 |
| Train-fitted cell sigma | 2.827759 | 1,593 |

Fixed minus fitted CRPS is `0.003463`, with a game-clustered 95 percent interval of `[0.000419, 0.006641]`.

| Margin threshold | Empirical tail rate | Fixed nominal | Fixed gap | Fitted nominal | Fitted gap | Observed tick count |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 0.790333 | 0.778041 | 0.012291 | 0.774986 | 0.015347 | 366023 |
| 10 | 0.549906 | 0.551948 | -0.002043 | 0.551268 | -0.001362 | 251442 |
| 15 | 0.341494 | 0.357671 | -0.016177 | 0.358404 | -0.016910 | 155780 |
| 20 | 0.206529 | 0.220738 | -0.014210 | 0.221516 | -0.014988 | 92132 |
| 25 | 0.124922 | 0.132238 | -0.007317 | 0.132313 | -0.007391 | 55841 |
| 30 | 0.069052 | 0.072651 | -0.003599 | 0.072351 | -0.003299 | 30473 |

## Differential archive and reproduction

The paired per-game archive is `docs/evidence/harness/S227_margin_tail_crps_2026-09-04_per_game.csv`: 1,593 rows, 583,437 bytes, SHA-256 `19c00fd5184be92f6448a7d4a58c4b73ce39e231fc06ea9c133055f11e2798ad`. It contains both game CRPS values, their difference, game id, timestamp, tick count, six observed tail rates, both nominal tail rates, and the descriptive label. The machine summary is `docs/evidence/harness/S227_margin_tail_crps_2026-09-04_summary.json`, 3,635 bytes, SHA-256 `308e0525a9127401a8a5eca3eac0f9a47708f06df1700b8c1fdbc4739bef11be`.

A separate fresh process read the archive and recomputed fixed CRPS `2.831221751521`, fitted CRPS `2.827759236496`, fixed-minus-fitted difference `0.003462515025`, all six empirical rates, and all corrected fitted nominal rates to less than 1e-12 from the machine summary.

Route identities:

- `scripts/platformkit/s227_margin_tail_crps.py`: SHA-256 `d77756f6776b43870352a5f9f299a19486d39adc4d03cbe3ae6c8437e6c648fb`, 231 LOC.
- `scripts/platformkit/eval_gate/cpcv_engine.py`: SHA-256 `6f622dc107b432df0bdc1f4700e44d900de5c5adaad9657e15a22c579269c6e6`.

Focused test: `python -m pytest tests/platformkit/test_s227_margin_tail_crps.py -q -p no:cacheprovider` passed: `3 passed`.

## Contract self-check

- B1/B3: all corpus games remain in the denominator; unavailable evidence does not exclude a game.
- B2/B6/B10: this is additive; no existing field, route, threshold, or schema changed.
- B8: each fitted cell sigma uses only the matching cell targets from its OOS train rows.
- Q1: the sealed preregistration path and canonical SHA are above.
- Q2: this is an uncharged calibration screen; no register or ledger was read or written.
- Q4: OOS memberships come from the shared evaluator with purge and symmetric nonzero embargo.
- Q5: no cross-corpus superiority designation is made.
- Q6: calibration language only.
- Q9: the paired per-game archive above is sufficient to recompute the headline differential.
