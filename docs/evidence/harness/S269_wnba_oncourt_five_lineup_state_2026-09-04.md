# S269 WNBA on-court five lineup state, 2026-09-04

Verdict: FALSIFIED. No calibration comparison was scored and no operational change was made.

## Binding premise

S269 requires the direct set overlap of `stamps.csv game_id` with
`wnba_checkpoints_full.parquet game_id` to be 85 of 85 before any join or
scoring. The exact binding command was run locally in this worktree before any
scored comparison. Its output was:

```text
PREMISE_S253_STAMPS_ROWS=5647
PREMISE_S253_STAMPS_GAME_IDS=167
PREMISE_S206_JOINED_TICKS=18650
PREMISE_S206_JOINED_CLUSTERS=85
PREMISE_S206_SCORED_TICKS=16571
PREMISE_S206_SCORED_CLUSTERS=75
PREMISE_S253_CHECKPOINT_OVERLAP=0_OF_85
PREMISE_CHECKPOINTS_OUTSIDE_S253=85
PREMISE_S253_OUTSIDE_CHECKPOINTS=167
PREMISE FALSIFIED
```

The first six count fields match the stated before-condition, but the required
keyed overlap is zero rather than 85. The requested backward as-of join has no
rows, so attempting a feature comparison would violate the fixed joined-tick
denominator and would be circular. This attempt stops here under the explicit
premise rule and verifier contract Q8.

## Inputs opened

Each data store was opened separately. No raw CDN store was read.

| Path | Bytes | SHA-256 | Use |
| --- | ---: | --- | --- |
| `docs/evidence/harness/S253_nba_oncourt_five_from_cdn_subs_2026-09-04/stamps.csv` | 929213 | `cdf4d679bea1452e2da17f0e24e5e86a33e95d5bc5ae0639e35ea7a275eb240a` | Direct `game_id` set and required S253 row/game counts. |
| `data/cache/inplay_odds/wnba_checkpoints_full.parquet` | 167408 | `a97392703bb6c710b0713f8421db860236dcb0c1b9dcc6623ca1d4d5e57a76dc` | Direct `game_id` set and S206 joined-tick denominator. |
| `data/cache/inplay_odds/wnba_price_series.parquet` | 3270899 | `3ce89dee6471a04745bcf1e32c6c183fac4238ab781df7dcea53a994e472b8f3` | Existing S206 orientation loading needed to bind its scored tick/cluster count. |

## Non-actions and contract self-check

- No preregistration was written or sealed because Q1 applies to a scored comparison and the premise stopped work before one existed.
- No Brier, ECE, interval, feature coefficient, paired-loss artifact, or test result was produced.
- No files under `data/`, no register, no ledger, and no S253 or S206 artifact were changed.
- Nothing was copied to a pod.
- The required scored comparison, per-cell table, RSS score measurement, and paired-loss test are inapplicable after this falsified prerequisite; this is not a NULL result.

The result applies only to the committed inputs named above. It does not assess whether a lineup-state feature could be evaluated after a future, separately specified reconciliation of the incompatible `game_id` sets.

## NOT VERIFIED

- No calibration result is verified because the required game-ID overlap is zero.
