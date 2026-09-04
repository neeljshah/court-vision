# S262 boxscore q50 source census

## Scope and premise

This memo implements `docs/evidence/tracking/specs/S262_spec.md` and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. Machine:
local worktree `C:/Users/neelj/nba-track-a17`, because the named stores are
local read-only inputs and this row does not authorize a pod action.

Before the census, one read-only metadata open reconfirmed the binding premise:

| Path | Bytes | Rows | Required q50 fields absent |
|---|---:|---:|---|
| data/intelligence/matchup_grid.parquet | 141940 | 4900 | q50_minutes, q50_pts, q50_reb, q50_ast, team_q50_pts, team_q50_reb, team_q50_ast |

The exact before-condition output was:

```text
PATH data/intelligence/matchup_grid.parquet
BYTES 141940
ROWS 4900
MISSING_Q50 q50_minutes,q50_pts,q50_reb,q50_ast,team_q50_pts,team_q50_reb,team_q50_ast
PREMISE HOLDS
```

Filename-only selection searched `data/cache/`, `data/intelligence/`, and
`data/domains/` for a statistic marker (`pts`, `points`, `reb`, `rebounds`,
`ast`, or `assists`) plus a shape marker (`q10`, `q50`, `q90`, `quantile`,
`sample`, or `distribution`). It found five paths under `data/cache/`, zero
under `data/intelligence/`, and two source-control-hook false positives under
`data/domains/`. No store was read during that selection.

## Column-level candidate census

Each tabular candidate below is below 300 MB and was inspected separately.
Only a matching shape-named column was opened at a time. `NOT-A-STORE` paths
were not opened as tabular data.

| Path | Bytes | Rows | Columns | Column-level result and exclusion |
|---|---:|---:|---|---|
| data/cache/pts_q50_oof_int95.parquet | 869923 | 101765 | player_id, date, target_pts, base_q50_pred | `base_q50_pred` opened as double. Point prediction only; missing minutes q50, reb/ast q50, team targets, and distributional samples. |
| data/cache/ast_q50_oof_int95.parquet | 846879 | 101765 | player_id, date, target_ast, base_q50_pred | `base_q50_pred` opened as double. Point prediction only; missing minutes q50, pts/reb q50, team targets, and distributional samples. |
| data/cache/reb_q50_oof_int95.parquet | 842533 | 101765 | player_id, date, target_reb, base_q50_pred | `base_q50_pred` opened as double. Point prediction only; missing minutes q50, pts/ast q50, team targets, and distributional samples. |
| data/cache/statcast/statcast__2022_sample.parquet | 1855678 | 158702 | game_pk, game_date, inning, inning_topbot, at_bat_number, pitch_number, pitcher, batter, events, release_speed, release_spin_rate, estimated_woba_using_speedangle, pitch_type, balls, strikes, outs_when_up, home_team, away_team | No quantile/sample column. Baseball pitch store, not per-player NBA PTS/REB/AST data. |
| data/cache/statcast/statcast__2023_sample.parquet | 1817526 | 154552 | game_pk, game_date, inning, inning_topbot, at_bat_number, pitch_number, pitcher, batter, events, release_speed, release_spin_rate, estimated_woba_using_speedangle, pitch_type, balls, strikes, outs_when_up, home_team, away_team | No quantile/sample column. Baseball pitch store, not per-player NBA PTS/REB/AST data. |
| data/domains/tennis/_raw/sackmann_pbp_repos/tennis_MatchChartingProject/.git/hooks/pre-rebase.sample | 4898 | NOT-A-STORE | NOT-A-STORE | Source-control hook example selected only by filename; no tabular columns or rows. |
| data/domains/tennis/_raw/sackmann_pbp_repos/tennis_slam_pointbypoint/.git/hooks/pre-rebase.sample | 4898 | NOT-A-STORE | NOT-A-STORE | Source-control hook example selected only by filename; no tabular columns or rows. |

The three q50-named NBA files are separately stored point predictions; they do
not form one source with usable per-player PTS/REB/AST distributions and named
team q50 targets. A point prediction is excluded rather than treated as a
distributional match.

## Verdict

**CLOSED AT LIMIT.** No candidate is a usable producer of per-player NBA
PTS/REB/AST quantiles or samples with the minutes and team-q50 fields required
by `scripts/platformkit/boxscore_dist_coherence.py`. Therefore no real-row
30-case matrix exists, no comparison was scored, and `n = 0`.

The missing producer is platform-wide across the exact three searched roots:
`data/cache/`, `data/intelligence/`, and `data/domains/`.

## Reproduction and verifier self-check

- Census logic test: `python -m pytest scripts/platformkit/test_boxscore_q50_census.py -q -p no:cacheprovider` -> `1 passed in 0.99s`.
- B1: PASS. No comparison rows were scored or silently excluded; every candidate and exclusion is named.
- B2: PASS. This landing adds a standalone filename selector and evidence only; no schema or reader changes.
- B3-B6: PASS. No gate, claim lifecycle, deployment, module move, or retirement changed.
- B7-B9: PASS. No sampled visual, fitted, or denominator-based result is claimed.
- B10: PASS. The 240 plus 5 times overtime minutes budget and the existing verdict thresholds were not changed.
- Q1-Q5 and Q9: NOT APPLICABLE. No comparison, charged trial, OOS evaluation, comparative claim, or paired-loss series was produced.
- Q6: PASS. This memo uses calibration-only language and contains no performance claim.
- Q7: PASS. `n = 0` is the specified CLOSED AT LIMIT result, not a sampled or scored metric.
- Q8: PASS. The exact 4900-row and seven-absent-field premise was remeasured before the census.
- A7: PASS. The evidence path and both new source paths are committed with this landing. The user rule prohibits register and ledger writes, so neither was changed.
