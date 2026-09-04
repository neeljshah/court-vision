# S280 NBA In-Game Cross-Venue Disagreement

Spec: `docs/evidence/tracking/specs/S280_spec.md`.
Contract checked: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

Verdict: NULL. The comparison was scored because the comparable parsed overlap is
40 game clusters. Its calibration improvement is below the frozen +0.004 bar.
No feature flag or default changed.

## Premise first

The binding column-only parquet census was rerun before the scorer. Exact
columns used were price-series `venue`, `game_date`, `ticker_or_slug`, and
`event_key`; checkpoint `venue`, `game_date`, `market_ticker`, and `game_id`.

| Store | Bytes | Resolution | Measured result |
| --- | ---: | --- | --- |
| `data/cache/inplay_odds/nba_price_series.parquet` | 25,140,428 | parquet | kalshi 657,145 rows; polymarket 7,742,487 rows; Kalshi date range 2026-04-27 through 2026-06-14; 62 Kalshi event keys |
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2,829,826 | parquet | polymarket 465,249 rows; date range 2024-10-22 through 2026-06-13; 1,593 game IDs |

First three parsed Kalshi identifiers were `(2026-04-26, BOS, PHI)`,
`(2026-04-26, LAL, HOU)`, and `(2026-04-27, DET, ORL)`. First three parsed
checkpoint identifiers were `(2024-10-22, NYK, BOS)`, `(2024-10-22, MIN,
LAL)`, and `(2024-10-23, IND, DET)`.

The ticker-date plus away/home parse enumerated every 62 Kalshi event keys.
Its exact checkpoint intersection is 49 events: 40 moneyline events and 9
spread events. The scored set is every tick from the 40 moneyline games only;
the 9 spread events are named in the overlap table but are not home-win
probabilities. There are 8,828 scored checkpoint ticks, each with an as-of
Kalshi price, and no pre-price exclusions.

## Sealed comparison

Preregistration: `docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04_preregistration.md`.
Its LF-byte seal is `3bc9893a7373dd47ebeba0c28b2d1cf2ec8250aba446975d2d3cfdd25e2adc09`.
It was committed before the first metric in `de1b4a73b8365023933308fbf937a161a57fdb47`.
The post-commit `git show HEAD:docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04_preregistration.md | head -n 30 | sha256sum`
verification reproduced that seal.

Each stable evaluator state is one `(game_id, checkpoint_ts)` tick. The shared
`cpcv_evaluate` route used 8 groups, 2 test groups, its purge, and a symmetric
nonzero 1-day embargo. The null was a training-only logistic recalibration of
market logit. The only additive candidate input was the latest available
Kalshi-home probability minus the checkpoint Polymarket probability. The
candidate never used a future Kalshi price. The 61,796 evaluator records are
seven CPCV records for each of the 8,828 states.

| Quantity | Value |
| --- | ---: |
| recal_null Brier | 0.12960918202643246 |
| augmented Brier | 0.12891112151862477 |
| augmented minus recal_null Brier | -0.0006980605078076834 |
| calibration improvement | 0.0006980605078076834 |
| game-clustered 95 percent interval for metric | [-0.0019271681112867855, 0.0002133248411028257] |
| frozen bar | +0.004 |

The observed improvement is below the bar, so this is NULL. It is not an
ahead claim and no second-corpus condition is invoked.

## Artifacts and reproduction

- `docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04.json`
  records inputs, byte sizes, SHA-256 values, premise counts, code SHA-256,
  evaluator-record count, and summary.
- `docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04_overlap.csv`
  is the exhaustive 62-event parse enumeration.
- `docs/evidence/harness/S280_ingame_cross_venue_disagreement_2026-09-04_ticks.csv`
  is the evaluator-derived per-state paired-loss archive. It names cluster,
  state timestamp, both source timestamps, outcome, both OOF probabilities,
  both losses, differential, and evaluator-record multiplicity. The interval
  recomputes from its per-state differential and game ID alone.

The final route hash is `8d32563c23104ff19eea2c83db665647807e5432504492a738d3bbc6e7b2578a`.
The initial pod attempt stopped before a metric because its linked pod data tree
did not contain `nba_price_series.parquet`; no deployed tree was written. The
streamed local run was used only after that input preflight and had an observed
RSS working set of 379,531,264 bytes (362.0 MB), below the 500 MB pod threshold.

Reproduction command:

    python -m scripts.platformkit.eval_gate.s280_cross_venue --output-dir docs/evidence/harness

## Contract self-check

| Clause | Result |
| --- | --- |
| B1, Q7, Q9 | All 8,828 comparable ticks are included; no selected subset. Per-state losses and clusters are archived. |
| B2-B4, B6 | Additive new module only; no reader, default, archive, or claim state changed. |
| B5 | Pod stopped before scoring; the local streamed run did not deploy or alter data. |
| B7-B10 | No renders, self-fit claim, recycled denominator, or moved threshold. |
| Q1 | Preregistration was sealed and committed before the first metric. |
| Q2 | No charge, ledger read, or ledger write. |
| Q3-Q6 | The +0.004 bar is unchanged; CPCV uses purge and symmetric embargo; no ahead claim; calibration language only. |
| Q8 | The store census and exhaustive parse join were rerun first. |

## Test

`python -m pytest scripts/platformkit/eval_gate/test_s280_cross_venue.py -q -p no:cacheprovider`
returned `1 passed in 4.67s`.

## NOT VERIFIED

- Historical failed-pod deployment state was not independently observed.
