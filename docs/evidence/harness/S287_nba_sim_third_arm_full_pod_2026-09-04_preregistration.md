# S287 full-scale simulator preregistration

Spec: `docs/evidence/tracking/specs/S287_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

This preregistration was sealed before any S287 scored comparison. The binding
before-condition printed `qualifying=355/661`; S266 is the archived construct
comparison of 30 clusters and 180 ticks with simulator improvement
`-0.077387998354` versus recalibrated-null.

## Frozen design

The compute-only measurement will run on the pod scratch directory through:

```text
/c/Users/neelj/bin/pod_run a13 --ship docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04 --fetch docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04 --fetch docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04_pod.log -- python -m scripts.platformkit.ingame.s287_sim_full_pod
```

The entrypoint will import the landed S256 simulator module without changing it,
select all and only the 355 S255-qualified game clusters, and choose the six
frozen elapsed-second targets `[120, 600, 1080, 1560, 2040, 2520]` per game.
The scored denominator is therefore 355 clusters x 6 targets = 2,130 unique
game-target state keys. There is one shared `cpcv_evaluate` state for every
scored tick. The evaluator uses strict redaction, its shared purge, and a
symmetric nonzero three-calendar-day embargo.

Inputs are read one store at a time: `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv`,
`docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/cluster_qualification.csv`,
`docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet`,
and `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/team_rate_snapshots.parquet`.
The S92 archive and both parquet snapshots were statted on the pod before
dispatch; all exist there. Every opened input, the unchanged S256 module, and
the new entrypoint will be SHA-256 identified. The run will record MD5 parity
for every shipped S255 input on both sides.

The primary metric is tick-weighted Brier improvement, defined as
recalibrated-null loss minus simulator loss. Positive values mean the simulator
has lower loss (candidate better); negative values mean the simulator is behind.
The frozen calibration bar is `+0.004`. The game-clustered 95 percent interval
is computed from the archived per-game paired-loss series. The verdict is
`AHEAD` only when the interval clears the bar; otherwise `SCREEN_NULL` for a
nonnegative estimate and `BEHIND` for a negative estimate. Any AHEAD would
require a second corpus, so it will instead be labelled `SINGLE-WINDOW` and not
treated as an acceptance claim.

The fetched Q9 artifacts will include a per-tick series (state key, cluster,
timestamp, outcome, all three probabilities and losses) and a per-game paired
loss series from evaluator records only. The entrypoint will also be restricted
to S266's sealed 30 game identifiers, and its artifacts will be compared to the
archived S266 values with maximum absolute difference no greater than `1e-9`.
No ledger, register, K value, feature flag, `data/` file, deployed pod file, or
charged trial is involved.

## Seal

SHA-256 of every LF byte above this seal line, staged before the first score: 9dc03d9ef0418c4f3a2e025a06354fd420a84d6ee217b84384463314879ddc64
