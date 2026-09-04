# S243 boxscore coherence check

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q.
Machine: local `C:/Users/neelj/nba-track-a16` CPU worktree. All stores were
read-only; no data write, ledger, register, deployment, or flag change occurred.

## Verdict

NOT VALIDATED for a real distributional input. The required additive checker is
implemented and exercised on a 30-game construction, but no S241 q50 minutes
output exists and no named team q50 target exists for all of pts, reb, and ast.
Therefore no real game was scored and no distributional deviation is claimed.

LIMIT result: the existing module does not already perform the full
distributional check, so the premise is not falsified and the CHANGE step was
required.

## Inputs opened

All source inputs have no image or video resolution.

| Opened path | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `C:/Users/neelj/nba-track-a16/scripts/platformkit/boxscore_crosscheck.py` | 6829 | `52918152d85a0d60dd78076dc0635003a2ff7a90e0021d075a7af950cd5442f5` | none |
| `C:/Users/neelj/nba-track-a16/scripts/platformkit/test_boxscore_crosscheck.py` | 2669 | `9e614bfe6a44be18eadb2127422c82ef37d970881feab9c2cb88b8c6d8c89780` | none |
| `C:/Users/neelj/nba-track-a16/docs/evidence/harness/S241_nba_minutes_distribution_2026-09-04.md` | 5024 | `cbf19e9d83bed4a4724a28bbe135b09b839bf44ac494e46ef1fcc48b83a40252` | none |
| `C:/Users/neelj/nba-track-a16/data/intelligence/matchup_grid.parquet` | 141940 | `f22c8fc84747fa942411e3ff99b1a7dba8d3d60109e7834ab616f908462fe19d` | none |
| `C:/Users/neelj/nba-track-a16/src/prediction/team_total_normalizer.py` | 4557 | `b5f404cc53bfd9a26c5e5ff44da0b7935878e3cecaf70136240d8c0090638151` | none |
| `C:/Users/neelj/nba-track-a16/src/sim/game_simulator.py` | 20235 | `9f30385e1c3f5fd1ec541f24f7753ae8cd9ceb76da7a72e9baed6c00c36e1051` | none |

The read-only `matchup_grid.parquet` resolved through the worktree link to
`C:/Users/neelj/nba-ai-system/data/intelligence/matchup_grid.parquet`. No file
outside this worktree was written. Its 4900 rows have these columns:
`game_id`, `season`, `game_date`, `team_id`, `opp_team_id`, `is_home`,
offense and defense z columns, `data_density`, offense/defense window counts,
and two matchup interaction columns. It has no pts, reb, or ast team-total
target column.

## Binding premise and current check inventory

`boxscore_crosscheck.py` is neither an S241/S242 consumer nor a point-prediction
consumer. It reads a tracking CSV and an official boxscore JSON.

| Inventory item | Current behavior and citation |
|---|---|
| Tracking identity input | Selects jersey, identity, frame, and optional event columns; counts unique frames by tracked identity and maps available jerseys at `boxscore_crosscheck.py:64-95`. |
| Official-player input | Keeps official players with `min > 0`, maps them by jersey, and reports matched, missed, and extra jerseys at `boxscore_crosscheck.py:105-117`. |
| Minutes relation | Forms `(tracked_frame_count, official_minutes)` pairs for matched jerseys and computes Spearman rank association at `boxscore_crosscheck.py:119-120`. It does not sum minutes. |
| Verdict thresholds | Emits `OK` at jersey match >= 0.6 and Spearman >= 0.5; `WEAK` at jersey match >= 0.3 or Spearman >= 0.3; otherwise `FAIL`, at `boxscore_crosscheck.py:121-126`. |
| Optional shots relation | When an event column exists, compares tracking events containing `shot` with sum official FGA and applies `max(1, ceil(FGA * shot_tolerance))` at `boxscore_crosscheck.py:90-94,138-146`. |
| Returned inventory | Returns game id, player and tracking counts, jersey match percentage, minutes Spearman, verdict, jersey sets, pair count, and optional shots detail at `boxscore_crosscheck.py:128-147`. |

The inventory contains no player PTS, REB, or AST sum; no q50 distribution;
no team-total target; no top-five minutes sum; and no S241/S242 source. The
existing test is actually at `scripts/platformkit/test_boxscore_crosscheck.py`,
not the `tests/platformkit/` path named by the spec. The named path was run and
reported `file or directory not found`; the actual tracked test passed with
three cases.

## Additive distributional checker

`scripts/platformkit/boxscore_dist_coherence.py` is 169 lines and has SHA-256
`117f22ec80f554f262302e0726141ff7d786a85f82f7faf845da5bba18cb6976`.
It reads no store. Its input contract requires each player q50 mapping to carry
minutes, pts, reb, and ast (`boxscore_dist_coherence.py:1-12,37-42`).

- It sums the five greatest minutes q50 values, uses the unchanged budget
  `240 + 5 * overtime_periods`, and records both excess and a flag for every
  supplied team-game (`boxscore_dist_coherence.py:97-139`).
- It sums every roster player's pts, reb, and ast q50 values. Each target keeps
  its `source_file` and `source_field`; a nonmissing target without both names
  raises instead of creating an unnamed comparison (`boxscore_dist_coherence.py:45-94`).
- A missing target is `EXCLUDED_MISSING_TARGET`, not a zero deviation. A zero
  target keeps its absolute deviation but is `EXCLUDED_ZERO_TARGET` for the
  percent denominator (`boxscore_dist_coherence.py:66-87`). The summary reports
  valid n and each exclusion count (`boxscore_dist_coherence.py:142-169`).

The only currently named points route is the game engine's
`GameSimResult.home_team_total_samples` and `away_team_total_samples`
(`src/sim/game_simulator.py:163-177`). The normalizer separately derives only
home and away point targets from `predicted_total` and `spread`
(`src/prediction/team_total_normalizer.py:59-86`). Neither source supplies a
team reb or ast q50. S241 also records that existing minutes modules emit no
q10/q50/q90 distribution (`S241_nba_minutes_distribution_2026-09-04.md:32-46`).
These are the named source limits that prevent a real deviation table.

## Construction check inventory

This is one synthetic functional test, not a sampled game score or OOS
comparison. It constructs all 30 stated team-games. `P/R/A` are absolute
deviation followed by percentage deviation. `MISSING` is an explicit target
exclusion, never a zero value.

| Game | Top-5 min q50 | Budget | Excess | PTS | REB | AST |
|---|---:|---:|---:|---|---|---|
| construct-01 | 245.0 | 240.0 | 5.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-02 | 245.0 | 245.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-03 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-04 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-05 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-06 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-07 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-08 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-09 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-10 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-11 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-12 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-13 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-14 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-15 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-16 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-17 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-18 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-19 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-20 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-21 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-22 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-23 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-24 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-25 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-26 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-27 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-28 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-29 | 240.0 | 240.0 | 0.0 | 0.0 / 0.000000 pct | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |
| construct-30 | 240.0 | 240.0 | 0.0 | MISSING | 5.0 / 9.090909 pct | 5.0 / 25.000000 pct |

All 30 constructed games have a minutes result; none was silently excluded.
One regulation game is flagged, while the same 245.0 top-five total is allowed
for the one-overtime game. Mean absolute percentage deviation is PTS 0.000000
with n=29 and one named missing target, REB 9.090909 with n=30, and AST
25.000000 with n=30. This construction validates check inventory only; real
sampled-game n is 0 and is not presented as a calibration result.

## Preregistration and scoring status

Preregistration path: not applicable. Preregistration SHA-256: not applicable.
No scored comparison, OOS evaluator run, paired-loss artifact, or charged trial
occurred. The construction test is a deterministic functional test, not a
model comparison. Thus Q1, Q2, Q4, Q5, and Q9 score requirements do not apply;
the instruction to seal before any scored comparison was not reached.

## Tests and preservation

- `python -m pytest scripts/platformkit/test_boxscore_crosscheck.py -q -p no:cacheprovider` -> `3 passed`.
- `python -m pytest scripts/platformkit/test_boxscore_dist_coherence.py -q -p no:cacheprovider` -> `1 passed`.
- `git diff --exit-code -- scripts/platformkit/boxscore_crosscheck.py scripts/platformkit/test_boxscore_crosscheck.py` was clean. Existing behavior and every existing threshold are byte-identical.

## Verifier self-check

- B1: The construction enumerates all 30 team-games; construct-30's missing PTS target is named, and no real score excludes rows.
- B2: Additive new module and test only; the existing module and test are unchanged, and the new module has no callers.
- B3-B6: No gate, claim lifecycle, deployment, move, retirement, or data write occurred.
- B7-B9: No sampled head slice or fitted residual exists. Every construction row is shown; percentages use named, nonzero team targets and zero targets are explicit exclusions.
- B10: No existing threshold-bearing file changed.
- Q3: The 240 plus 5 times overtime-periods bar is unchanged from the spec.
- Q6: This memo is ASCII and uses calibration language only.
- Q7: The 30-game construction is exhaustive for the check inventory; no sampled or scored result is claimed.
- Q8: The binding module was read in full before the change decision.
- A7: This memo, helper, and test are committed together below; all named evidence paths exist in this worktree at commit time.

## Not verified

No real S241/S242 q50 rows, no team reb/ast q50 source, no real-game deviation
table, no OOS score, and no shared-evaluator run are verified. A future scoring
pass must seal a preregistration before reading metric rows, name every target
source and field, and use the shared evaluator with purge and symmetric,
nonzero embargo.

## Attempt 2 (2026-09-04): CLOSED AT LIMIT

Attempt-2 preregistration was committed before its source inspection:
`docs/evidence/harness/S243_attempt_2_prereg_2026-09-04.md`, commit
`bb97b0ed6e97f6e4d658ccc3422d7d73f0d16f33`. The LF bytes above its seal line
are 1,985 bytes and reproduce from `git show HEAD` with SHA-256
`324f66f755fecffee740f2c7890ec2675c7bdda45c8b6ba594e40731a8b56ba0`.

The one preregistered, read-only source was
`data/intelligence/matchup_grid.parquet` (resolved path
`C:/Users/neelj/nba-ai-system/data/intelligence/matchup_grid.parquet`). It is
141,940 bytes, below the 300 MB rail, and was opened as one store. Its 4,900
rows span `2024-10-22` through `2026-04-12`. Its identifying fields are
`game_id`, `game_date`, and `team_id`; it does not contain the required
`q50_minutes`, `q50_pts`, `q50_reb`, `q50_ast`, `team_q50_pts`,
`team_q50_reb`, or `team_q50_ast` fields. Therefore it cannot provide the
player q50s and named PTS/REB/AST team q50 targets required by this check.

| Required correction | Before attempt 2 | Attempt-2 result |
|---|---|---|
| Named real-data rows | `source_file` was `fixture`; team totals and player values were authored in the test. | CLOSED AT LIMIT: the cited store lacks all seven required q50 fields, so no row, total, table, or summary was fabricated. |
| Distinct exhaustive 30-case matrix | 30 IDs reduced to four input configurations; zero-target and missing-source validation were not reached. | CLOSED AT LIMIT: no source-backed input schema exists from which to replace the construction. The original test is retained unchanged, not presented as an attempt-2 matrix result. |

Attempt-2 matrix summary: 0 source-backed cases, 0 replacement input
signatures, and no new pytest matrix. This is a closure record, not evidence
that the existing 30 constructed IDs satisfy the correction request.

Focused reproduction after the closure decision:

- `python -m pytest scripts/platformkit/test_boxscore_dist_coherence.py -q -p no:cacheprovider` -> `1 passed in 0.70s`.
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> `1 passed in 3.80s`.

### Attempt-2 verifier self-check

- B1: no source row was excluded after scoring; the unavailable field set is
  named before any table or summary was calculated.
- B2-B6: this is an additive memo section only. No source schema, checker,
  test, caller, gate, deployment, or data file changed.
- B7-B9: no sampled or fitted metric is claimed, and no manufactured
  denominator or repeated construction is represented as a real-data result.
- B10 and Q3: the `240 + 5 * overtime_periods` bar is unchanged.
- Q1: the preregistration seal predates the source inspection. No scored
  comparison or charged trial occurred, so Q2, Q4, Q5, and Q9 do not apply.
- Q6: this additive section is ASCII and uses calibration language only.
- Q7: the required 30-case enumeration was not possible without fabricating
  source rows; the result is CLOSED AT LIMIT rather than a rail claim.
- Q8: the real cited store was inspected before attempting a replacement.

### Attempt-2 NOT VERIFIED

- A real player q50 source for minutes, PTS, REB, and AST.
- Named real team q50 targets for PTS, REB, and AST.
- A source-backed team/player coherence table or deviation summary.
- A distinct source-backed 30-case matrix, including zero-target,
  missing-target, and source-validation cases.
- An OOS score, shared-evaluator run, paired-loss artifact, or calibration
  comparison.
