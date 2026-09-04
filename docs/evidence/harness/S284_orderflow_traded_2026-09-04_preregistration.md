# S284 Preregistration: Native Kalshi Trade Occurrence

Spec: `docs/evidence/tracking/specs/S284_spec.md`.

This preregistration fixes the only scored comparison before its first metric.
The premise census found 40 exact game clusters for the `away_home` ordering
and zero for `home_away`; `away_home` is therefore the disclosed join-quality
ordering. The frozen checkpoint `traded` flag was true on all 465249 rows, so
it is not an arm input. No prior arm used a non-degenerate traded flag.

Inputs, opened separately: `data/cache/inplay_odds/nba_price_series.parquet`
(25140428 bytes, parquet) and `data/cache/inplay_odds/nba_checkpoints_full.parquet`
(2829826 bytes, parquet). Native Kalshi keys must match
`KXNBAGAME-YYMONDD<away><home>` and checkpoint keys must match
`nba-<away>-<home>-YYYY-MM-DD`. The joined subset is every checkpoint tick of
the 40 exact-overlap game-moneyline clusters with a native Kalshi event tick
strictly earlier than the checkpoint timestamp and no more than 60 seconds old.

At each checkpoint state, the candidate inputs are the latest prior Kalshi
event-level `traded_any` flag and the count of all native Kalshi tick rows with
`traded == true` in `(checkpoint_ts - 60 seconds, checkpoint_ts)`. Ties at a
Kalshi timestamp are collapsed with `traded_any = any(flag)` and the rolling
count retains all true tick rows. The baseline is the OOF `p_e4` emitted by
`scripts.platformkit.foundry.ingame_incumbent_nba.apply_incumbent` with
`kind="recal_null"` on the joined subset. A candidate logistic recalibration
uses only the baseline logit plus these two inputs and only CPCV training states.

Each stable evaluator state is one `(game_id, checkpoint_ts)` tick. Both arms
run through `cpcv_evaluate` with 8 groups, 2 test groups, its symmetric purge,
and a symmetric nonzero one-day embargo. The primary metric is recal_null
Brier minus candidate Brier, positive when the candidate has lower loss. A
deterministic 10000-resample game-cluster bootstrap (seed 284) supplies the
95 percent interval from evaluator-derived paired losses. The frozen bar is
+0.004 calibration improvement. No ledger is opened, charged, or written; no
registry or feature flag action occurs.

SEAL_SHA256: 9ea40e19826a36bc5f8de3d651403f64fcd1b78ab7c821ddd06a6ada03ea8932
