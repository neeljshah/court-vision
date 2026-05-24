# cycle 96b (loop 5) -- T1-B foul-rate v3 (post-93a daemon)

## Context

Cycle 92d was REJECTED with 0% PF coverage in 2025-26 holdout (boxscore cache
covered only Oct 2024). Cycle 93a's background daemon was supposed to extend
boxscore coverage into 2025-26. This cycle re-aggregates PF and re-probes.

## Aggregation refresh

```
python scripts/aggregate_player_pf_from_boxscores.py
[pf] game_date lookup: 6078 entries
[pf] reading 245 traditional boxscore files
[pf] 6774 player-game rows; skipped 0 games w/o date, 0 files w/o players
[pf] unique games: 245
[pf] unique players: 615
[pf] date range: 2024-10-22 -> 2026-01-19
[pf] wrote data/player_pf.parquet

python scripts/aggregate_pf_per_36.py
[pf36] read 6774 PF rows; unique players: 615
[pf36] computed 6774 rows; 4308 with prior history (rest are first-game NaNs)
[pf36] wrote data/player_pf_per36.parquet
```

PF data now extends from 2024-10-22 to **2026-01-19** (was Oct 2024 only).

## Coverage in holdout (build_pergame_dataset)

| Metric | v2 (cycle 92d) | v3 (cycle 96b) | Gate (>=70%) |
|---|---|---|---|
| Total holdout rows | 19,964 | 19,964 | - |
| Rows with `pf` | 0 (0.0%) | 2,650 (13.3%) | FAIL |
| Rows with `season_pf_per_36` | 0 (0.0%) | 1,997 (10.0%) | FAIL |
| Holdout date range | 2025-10-31 -> 2026-04-12 | 2025-10-31 -> 2026-04-12 | - |

Coverage jumped from 0% to 13.3% (PF) / 10.0% (season_pf_per_36) -- big
improvement vs v2 but still far below the 70% ship gate.

## Root cause

The 93a daemon successfully extended boxscore cache from Oct 2024 to
**2026-01-19**, but the prop holdout extends to **2026-04-12**. The daemon
covered only ~52% of the holdout window (calendar-wise), and within the
covered window, not every player-game has a boxscore file (only 245 unique
games in cache vs the full 2025-26 schedule of ~600+ games played by
2026-01-19).

Net: cache covered ~3 months of the ~5.5-month holdout, AND is sparse
within that coverage window. 13.3% row coverage is the realistic ceiling
until the daemon finishes the remaining ~10 weeks (Jan 19 -> Apr 12) AND
backfills missed games in the Oct 2025 - Jan 2026 window.

## Verdict

**REJECT (coverage)** -- 13.3% holdout PF coverage is below the >=70% ship
gate. Did NOT run the actual probe (`probe_foul_rate_shrink_v2.py`) because
the coverage prerequisite failed. Any MAE delta measured on 13.3% of rows
would be dominated by the no-op fallback on the other 86.7% and the result
would be a noisy near-zero, indistinguishable from v2's 0% no-op.

## Suggested follow-up

1. Extend the 93a daemon's date window: re-run with end_date=`2026-04-12`
   to cover the full 2025-26 holdout.
2. Backfill missed games within the Oct 2025 - Jan 2026 window (only 245
   unique games cached vs the ~600+ played).
3. Once holdout PF coverage >= 70%, re-run cycle 96b as v4 with the actual
   probe + ship gate.

## What did NOT happen this cycle

- Did NOT wire PF feature into production (no probe result -> no ship).
- Did NOT conflict with cycles 96a / 96c / 96d / 96e.
- Did NOT alter feature engineering or model code.

Only changes: refreshed two parquets via aggregation scripts (idempotent
re-runs that pick up the daemon's expanded boxscore cache).
