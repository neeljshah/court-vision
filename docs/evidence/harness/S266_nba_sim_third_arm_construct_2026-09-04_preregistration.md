# S266 preregistration: NBA simulator third-arm construct acceptance

Spec: `docs/evidence/tracking/specs/S266_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

## Scope and machine

This local Windows worktree measurement runs at
`C:/Users/neelj/nba-track-a17` on the memory-limited laptop. It is construct
scale only. It must not call the full 355-cluster route, copy any file to a
pod, read or write a ledger or register, read K, flip a feature flag, or write
under `data/`. The only route to a 355-cluster result is the successor stage-2
pod row after an ACCEPT decision on this row.

## Named read-only inputs

| path | bytes | resolution | role |
|---|---:|---|---|
| `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` | 38,630,145 | tabular CSV, 79,554 ticks / 661 clusters | frozen tick archive |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv` | 36,282 | tabular CSV, 661 clusters | strict qualifying-cluster mapping |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet` | 565,095 | tabular Parquet, 76,820 rows | prior-dated player rates |
| `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet` | 22,677 | tabular Parquet, 1,434 rows | prior-dated team rates |

The binding premise is already reproduced from these paths: 355 of 661 strict
qualifying clusters, 79,554 ticks, market Brier 0.142876712852, and
recalibrated-null Brier 0.144293050901. SHA-256 is recorded before and after
the route for each S255 artifact and S92 archive. Every tracked `src/` byte is
also aggregated and asserted byte-identical before and after.

## Frozen whole-game construction

The selection is NumPy `default_rng(2561001).choice` without replacement from
lexically sorted strict qualifying game IDs, then lexically sorted before
scoring. Its 30 whole-game clusters are:

`401809798, 401810022, 401810042, 401810056, 401810130, 401810156, 401810179, 401810183, 401810233, 401810249, 401810253, 401810255, 401810386, 401810388, 401810398, 401810410, 401810533, 401810539, 401810541, 401810549, 401810570, 401810628, 401810663, 401810771, 401810811, 401810831, 401810930, 401810966, 401810972, 401836800`.

The frozen elapsed-second grid is `[120, 600, 1080, 1560, 2040, 2520]`. One
nearest S92 tick is retained per target using ascending absolute elapsed
distance, then timestamp, then streaming source order. The sealed denominator
is 30 whole-game clusters and 180 unique game-target ticks. Archive reading is
streamed in 5,000-row chunks and filtered to those clusters before state
construction. Snapshot Parquet reads are predicate-limited to the selected
strict snapshot dates, and every absent fast-simulator field is filled from
that date's `ft_rate_q50` league mean with the field, date, transform, and game
named in the summary.

## Frozen comparison and evaluator

The three probability arms are `market_prob` (market), `p_null`
(recalibrated-null incumbent), and the snapshot-only fast simulator. The
callback emits every simulator probability via shared
`scripts/platformkit/eval_gate/cpcv_engine.py:cpcv_evaluate` with 8
chronological groups, one test group per split, strict test-view redaction, the
shared 48-hour same-team purge, shared 3-day same-matchup purge, and a
symmetric nonzero 3-calendar-day embargo. There are 32 seeded CPU simulator
draws per retained state. The callback's state seed is game ID plus frozen grid
target; it is not a full-set call.

For every sealed tick, including the simulator's weakest periods, archive
tick-weighted Brier and 10-bin ECE for all arms. Define improvement as mean
`loss_recal_null - loss_simulator`; recompute its game-clustered 95 percent CI
from the archived per-game paired-loss series. The immutable calibration bar is
`+0.004`. `SCREEN_NULL` or `BEHIND` is a valid successful construct result.

## Compatibility, memory, and outputs

The additive module keeps new callables `select_games`, `price`, and `score`,
and exposes legacy aliases `select_sample`, `price_snapshot_only`, and
`evaluate`. Summary `status` aliases `verdict`; valid legacy and new status
values remain `SCREEN_NULL` and `BEHIND`. Primary S266 output names are
`S266_summary.json`, `S266_selected_tick_series.csv`, and
`S266_per_game_paired_loss_series.csv`; compatibility copies with the S256
construct output names are written beside them.

Print RSS immediately before and after scoring and guard every callback. Above
600 MB, print `MEMORY LIMIT`, name the location, stop further scoring, and
report CLOSED AT LIMIT. The sole focused test recomputes one selected game's
paired loss from the archived series, asserts the sealed denominator and all
legacy aliases, and stays under 200 MB.

Seal SHA-256: 9b52164a6f2d8f2d501573c4e35fdd91bd8c1c269c61c674f35f250e3a6bbd55
