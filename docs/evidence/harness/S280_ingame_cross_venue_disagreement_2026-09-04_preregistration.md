# S280 Preregistration

Spec: `docs/evidence/tracking/specs/S280_spec.md`.

This preregistration fixes one comparison before its first metric: an additive
Kalshi-minus-Polymarket home-win-probability disagreement feature versus S123
`recal_null` on the overlapping-tick subset only.

Inputs opened one store at a time:

- `data/cache/inplay_odds/nba_price_series.parquet`
- `data/cache/inplay_odds/nba_checkpoints_full.parquet`

The parse join is exact `(ticker date, away, home)`. It enumerates every 62
Kalshi event keys, reports the full exact intersection, and scores every tick
of each exact-overlap moneyline game. Spread events are reported but excluded
from the probability comparison because they do not encode home-win probability.

The shared evaluator is `cpcv_evaluate` with 8 groups, 2 test groups, purge,
and symmetric nonzero 1-day embargo. Each checkpoint tick is one state keyed
by `(game_id, checkpoint_ts)`; the Kalshi price is the latest available price
at or before that checkpoint tick. The null is logistic recalibration on
market logit. The additive arm adds only venue disagreement. All models fit
only evaluator training states.

Primary metric: augmented Brier minus recal_null Brier. The game-clustered
95 percent interval is a deterministic 10,000-replicate game bootstrap. The
frozen calibration bar is +0.004 improvement, equivalently metric at most
-0.004. No charge, ledger read, registry write, or feature flag action occurs.

SEAL_SHA256: 3bc9893a7373dd47ebeba0c28b2d1cf2ec8250aba446975d2d3cfdd25e2adc09
