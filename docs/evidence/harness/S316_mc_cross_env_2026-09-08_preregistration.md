# S316 MC cross-environment preregistration

Spec: `docs/evidence/tracking/specs/S316_spec.md`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
This file is sealed before the first S316 scored comparison.

## Frozen route and sources

Each arm uses `python -m scripts.platformkit.ingame.s287_sim_full_pod` importing
`scripts/platformkit/ingame/s256_nba_sim_engine_v3.py`, the frozen 30 games
`401809798,401810022,401810042,401810056,401810130,401810156,401810179,401810183,401810233,401810249,401810253,401810255,401810386,401810388,401810398,401810410,401810533,401810539,401810541,401810549,401810570,401810628,401810663,401810771,401810811,401810831,401810930,401810966,401810972,401836800`, and six fixed ticks per game. The shared CPCV evaluator has one state per tick, 8 groups, 1 test group, and its existing 3-day symmetric nonzero embargo.

Opened tabular sources (resolution N/A): `data/cache/eval_gate/s92_nba_lineup_dynamic_2026-09-03_all.csv` (38630145 bytes); `docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04/player_rate_snapshots.parquet` (565095); `team_rate_snapshots.parquet` (22677); `cluster_qualification.csv` (36282); and the comparison target `docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04/S266_selected_tick_series.csv` (53203).

## Ordered comparisons

1. LOCAL premise: run the exact frozen route in `conda basketball_ai` (Python 3.10.20, NumPy 1.26.4, Torch 2.1.2+cu121) and compare its 180 tick records and summary to S266. If any required difference exceeds 1e-9, stop S316 as PREMISE FALSE.
2. Only if the premise holds: LOCAL Torch/OMP threads set to 1, then Torch threads 128 when accepted by the host; compare each to LOCAL premise.
3. Only if the premise holds: alternate local Python 3.10.0, NumPy 2.2.6, Torch 2.2.0+cu121, with threads fixed to 1; compare to local threads-1.
4. Only if the premise holds: pod threads set to 1 with OMP and MKL set to 1; compare to prior POD-1 and local threads-1.

Every pair requires 30 clusters, 180 unique state keys, and reports max absolute `p_simulator` delta, count above 1e-9, simulator Brier and ECE deltas. The paired records archive the evaluator state key, cluster id, timestamp, both squared losses, and baseline-minus-candidate loss delta. Improvement means baseline loss minus candidate loss; positive means the candidate has lower loss.

## Decision table

| Observation | Decision |
|---|---|
| A thread arm moves p_simulator | reduction-order cause; audit the implicated reduction with deterministic algorithms. |
| Version arm moves p_simulator with threads fixed | kernel/library-version cause. |
| Neither moves p_simulator | audit the first floating-point comparison branch that can alter random-draw consumption. |
| Premise misses 1e-9 | PREMISE FALSE; stop without later arms. |

If a cause supports an additive platformkit-only flag, it defaults OFF and must be byte-neutral OFF and reproduce to 1e-9 ON before it is reported. If no fix is found, the proposed bar is within-environment 1e-9 plus reported cross-environment delta. No charged hypothesis trial is created: no ledger is read or written and K is N/A.

## Unchanged constraints

The 180-tick restriction, all S287 values and bars, `src/`, `data/`, feature defaults, pod daemon and guards, register, and ledger do not move. Eye check: NONE. The pod is compute-only through `pod_run` in `/workspace/wt/a2`; no deployed-tree file is written.

SEAL sha256 d03ef82c52efc9d9b5b23e2f227c8e178deaffe9b5a9e3a522770f84ffc56064
