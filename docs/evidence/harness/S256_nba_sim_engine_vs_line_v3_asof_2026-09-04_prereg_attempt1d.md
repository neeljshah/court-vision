# S256 attempt 1d preregistration: local construct trial

## Scope and machine

This is a local construct measurement in `C:/Users/neelj/nba-track-a18` on the
memory-limited laptop. Nothing from this attempt may reach the pod before an
ACCEPT verdict. The successor, only after this row lands and is accepted, is the
355-cluster S256 run on the pod.

This trial is uncharged: it does not read or write any ledger, register, K, or
feature flag. It writes no `data/` files and opens no legacy `team_system` rate
store.

## Frozen inputs and selection

Inputs are the S92 archive
`data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` and the three
S255 artifacts in
`docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/`:
`cluster_qualification.csv`, `player_rate_snapshots.parquet`, and
`team_rate_snapshots.parquet`.

Qualification is recomputed as both `player_snapshot_date < game_date` and
`team_snapshot_date < game_date`. The expected qualification denominator is
355 of 661 clusters. Seed `2561001`, NumPy `default_rng`, chooses without
replacement from lexically sorted qualifying game IDs; the selected IDs are
lexically sorted before scoring:

`401809798,401810022,401810042,401810056,401810130,401810156,401810179,401810183,401810233,401810249,401810253,401810255,401810386,401810388,401810398,401810410,401810533,401810539,401810541,401810549,401810570,401810628,401810663,401810771,401810811,401810831,401810930,401810966,401810972,401836800`

The unit is a whole game cluster: exactly 30 selected clusters, never an
arbitrary tick slice. The archive is streamed in CSV chunks and filtered to
those game IDs before a tick grid, state, or simulator input is built. Snapshot
parquets are predicate-read only for the selected games' strict snapshot dates;
the parquet schemas contain `entity_id` and `as_of_date`, not `game_id`, so the
date predicates are the reconstructible game-to-snapshot join. All selected
games must join both snapshots or the result is CLOSED AT LIMIT.

## Frozen scored comparison

The grid is six equally spaced elapsed-second targets per game:
`[120, 600, 1080, 1560, 2040, 2520]`. For each target, the retained S92 row is
the nearest archive tick, breaking ties by ascending `ts` and then original
stream row order. Thus the intended denominator is 180 unique game-target
states, subject only to a named CLOSED AT LIMIT condition.

The three arms are `market_prob` (market), `p_null` (recal_null incumbent), and
the snapshot-only simulator callback. The callback receives and emits one
probability for every retained state through the shared `cpcv_evaluate` route.
It uses only the selected S255 snapshot rows; fields unavailable in those rows
are filled from the league mean for that same snapshot date, with every field
and fill archived.

The evaluator is frozen to 8 chronological groups, 1 test group per split,
strict test-view redaction, a symmetric 3-calendar-day embargo, the shared
48-hour same-team purge, and the shared 3-day same-matchup purge. The expected
one-test-group design produces one callback probability for each retained tick.

The metrics are tick-weighted Brier and 10-bin ECE for all three arms. The
comparison is simulator improvement over recal_null, defined as mean
`loss_recal_null - loss_simulator`; the game-clustered 95 percent CI is
recomputed from the archived 30-game paired-loss series. The immutable bar is
`+0.004`. SCREEN NULL or BEHIND is a valid successful construct outcome.

## Memory and identity rails

The module prints process RSS immediately before scoring and immediately after
scoring. If RSS exceeds 600 MB at either guard, it prints `MEMORY LIMIT`, names
the offending allocation when known, performs no further scoring, and the memo
closes CLOSED AT LIMIT. It must never call the full-set path.

Before and after the attempted scoring route it records SHA-256 for each S255
artifact and the S92 archive, and asserts and prints one aggregate SHA-256 over
every tracked file under `src/`. Any change is an assertion failure.

## Planned evidence and test

New construct-only outputs are
`docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04_construct.md`,
`docs/evidence/harness/S256_nba_sim_engine_vs_line_v3_asof_2026-09-04_construct/S256_summary_construct.json`,
`S256_selected_tick_series_construct.csv`, and
`S256_per_game_paired_loss_series_construct.csv`. Each will remain below 50 MB.
The Q9 series will include game cluster ID, timestamp, tick count, both paired
losses, and their difference. The sole S256 test will recompute one game loss
from the tick archive and assert the 30-cluster denominator under 200 MB.

Seal SHA-256: 1be7b77791e8b422f1e1a1c4711ef6dec3720090199c28cd34235e8e6f003acf
