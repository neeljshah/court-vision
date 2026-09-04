# S245 NBA in-game live box score update - 2026-09-04

## Attempt 2 (current)

### Verdict

BEHIND, retained as the valid calibration result. The state-conditioned
remaining-game distribution has higher CRPS than the naive unconditional
remaining distribution at end Q1, end Q2, and end Q3. No checkpoint was
dropped. This attempt supersedes the attempt-1 data-limit conclusion below.

Preregistration: `docs/evidence/harness/S245_attempt2_prereg_2026-09-04.md`.
The committed LF-prefix seal is
`cc75e0f963502c71825359598cd619c0c2667883e5c9fe6dedb110692d4536d5`, verified
from `git show 6620cf5e0c587cdeacbb573105569179beeacde3` before scoring.

### Protocol and inputs

Every paired loss is produced by the callback of
`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate`: 8 date groups, 1
test group, shared 48-hour same-team purge, 3-day matchup purge, and symmetric
nonzero 1-calendar-day embargo. There is no custom fold loop.

Inputs were opened locally in this worktree, one store at a time; no file under
`data/` was written.

| Full path | Bytes | Use |
| --- | ---: | --- |
| `data/domains/basketball_nba/espn_nba_game_bridge.parquet` | 46,002 | exact bridge |
| `data/cache/quarter_box/` | 7,659 JSON files, each 5,241-12,868 | q1-q4 PTS/REB/AST |
| `data/cache/ingame/possession_states_2024_25.parquet` | 249,491 | state |
| `data/cache/ingame/possession_states_2025_26.parquet` | 247,926 | state |
| `data/intelligence/garbage_time_segments.parquet` | 4,851,899 | partition |

The 1,299-row bridge yields 1,231 unique games with q1-q4 player statistics.
The lineup-clock census remains `LINEUP_CLOCK_MATCH_COUNT=0`; this is
game-state conditioned, not lineup conditioned.

### Before / after

| Item | Attempt 1 | Attempt 2 |
| --- | --- | --- |
| Partial observations | Claimed absent | 1,231 exact-bridged games |
| OOS route | None | shared CPCV with purge and embargo |
| CRPS and game CI | not computed | measured and archived |
| Differential archive | absent | 208,887 player-stat rows, gzip CSV |

### Measured CRPS table

Difference is state-conditioned minus naive CRPS; lower is better. CI is a
seeded game-clustered 95 percent bootstrap interval. `garbage-unavailable` is
separate, never merged into non-garbage. Observed `garbage-time` has n=0 at all
three fixed checkpoints and has no score.

| Checkpoint | Partition | n | State CRPS | Naive CRPS | Difference | 95 percent CI |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| End Q1 | all scored | 1,231 | 3.076241 | 2.165269 | 0.910973 | [0.885711, 0.936214] |
| End Q1 | non-garbage | 43 | 3.074158 | 2.188765 | 0.885393 | [0.746357, 1.022419] |
| End Q1 | garbage-time | 0 | n/a | n/a | n/a | n/a |
| End Q1 | garbage-unavailable | 1,188 | 3.076317 | 2.164418 | 0.911899 | [0.885710, 0.937206] |
| End Q2 | all scored | 1,231 | 1.722859 | 1.610471 | 0.112388 | [0.097237, 0.127564] |
| End Q2 | non-garbage | 43 | 1.720474 | 1.645011 | 0.075463 | [-0.005205, 0.157943] |
| End Q2 | garbage-time | 0 | n/a | n/a | n/a | n/a |
| End Q2 | garbage-unavailable | 1,188 | 1.722946 | 1.609221 | 0.113724 | [0.098674, 0.128696] |
| End Q3 | all scored | 1,231 | 1.054839 | 1.002705 | 0.052133 | [0.042724, 0.061527] |
| End Q3 | non-garbage | 43 | 1.057755 | 1.036345 | 0.021410 | [-0.034156, 0.078211] |
| End Q3 | garbage-time | 0 | n/a | n/a | n/a | n/a |
| End Q3 | garbage-unavailable | 1,188 | 1.054733 | 1.001488 | 0.053245 | [0.043788, 0.062733] |

Artifacts: `docs/evidence/harness/S245_attempt2_summary_2026-09-04.json` and
`docs/evidence/harness/S245_attempt2_paired_losses_2026-09-04.csv.gz`.
Archive SHA-256: `fdfaf0e16482eb7f3810fe6860a4b21e59b0d841a547c310498007e55bc8d853`.
Route SHA-256: `f246749bd9d3e40291e33f202a23e4c5de0d1f6b0c2ef6ce4168891bea77bc81`.

### Contract self-check

- B1: all 1,231 complete-quarter exact-bridge games are retained; availability is named.
- B2-B6: additive module, tests, and evidence only; no schema, gate, deployment, register, or ledger change.
- B7-B9 and Q4: OOS CPCV provides purge plus symmetric embargo; game clusters supply the CI.
- B10/Q3: fixed checkpoints and the n >= 30 rail are unchanged. Q1 seal predates scoring; Q5 has no AHEAD claim; Q6 uses calibration language only.
- Q9: the archive retains player id, target, parameters, both losses, game id, checkpoint, and timestamp for direct replay.

Focused tests, run one file at a time:

```text
python -m pytest tests/platformkit/test_ingame_boxscore_update.py -q -p no:cacheprovider
1 passed in 3.19s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed in 1.59s
```

### Not verified

- flag-to-partition routing (garbage-time flag -> partition) is untested; NEW GAP
- Period-level garbage labels are absent for 1,188 game/checkpoint records; observed garbage-time n is zero.
- Exact-bridge matching was not independently re-adjudicated.
- Overtime completeness is not established; this is a regulation-quarter remaining target.
- S241/S242 do not supply independently validated quantile distributions here; this state arm is time-scaled observed rate plus train-only residuals.

## Attempt-1 text (superseded)

# S245 NBA in-game live box score update - 2026-09-04

## Verdict

CLOSED AT LIMIT. No archived NBA partial player box score is available as-of a
mid-game checkpoint. The required CRPS comparison was not computed, and no
partial values were synthesized.

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including
sections B and Q. It was run locally in
`C:\Users\neelj\nba-track-a17` because the required read-only state and raw
payload inputs are local to this worktree.

## Inputs and bounded reads

Each input was opened independently and released before the next input. No
input file opened was over 300 MiB. All inputs are structured data, so raster
resolution is not applicable.

| Full path | Bytes | Resolution / scan unit | Observed fact |
| --- | ---: | --- | --- |
| `data/cache/ingame/possession_states_2024_25.parquet` | 249491 | Parquet schema and metadata | 30383 rows; `seconds_remaining`, `pace_so_far`, and `run_diff` present |
| `data/cache/ingame/possession_states_2025_26.parquet` | 247926 | Parquet schema and metadata | 30199 rows; `seconds_remaining`, `pace_so_far`, and `run_diff` present |
| `data/intelligence/garbage_time_segments.parquet` | 4851899 | Parquet schema and metadata | 1226606 rows; `period`, `game_clock_sec`, and `is_garbage_time` present |
| `data/intelligence/**/*.parquet` and `data/cache/**/*.parquet` | 2937 files; maximum 59588606 bytes per file | one Parquet schema at a time | lineup and partial-box schema censuses below |
| `data/cache/nba_pbp_wallclock_raw/scoreboard/*.json` | 398 files; 40942864 aggregate bytes; 348171 maximum file bytes | one JSON payload at a time | 1903 NBA event records |
| `data/cache/nba_pbp_wallclock_raw/summary/*.json` | 1610 files; 736578812 aggregate bytes; 684690 maximum file bytes | one JSON payload at a time | 1610 unique NBA games and 3220 player-stat groups |
| `scripts/platformkit/ingame/ingame_prop_repricer.py` | 10513 | Python source | checked against the binding before-condition |

No files under `data/` were written. No register or ledger write occurred.

## Premise re-measurement

The required schema scan covered every Parquet below `data/intelligence/` and
`data/cache/`, one file at a time. It searched for either `on_floor` or
`lineup_id` together with a clock-bearing field or `period`.

```text
files=2937
LINEUP_CLOCK_MATCH_COUNT=0
```

The state-store metadata re-measurement was:

```text
data/cache/ingame/possession_states_2024_25.parquet 30383 ['game_id', 'asof_idx', 'date', 'seconds_remaining', 'frac_elapsed', 'state_diff', 'home_margin', 'possessions_elapsed', 'pace_so_far', 'run_diff', 'poss_since_lead_change', 'home_final', 'away_final', 'outcome', 'n_plays_seen']
data/cache/ingame/possession_states_2025_26.parquet 30199 ['game_id', 'asof_idx', 'date', 'seconds_remaining', 'frac_elapsed', 'state_diff', 'home_margin', 'possessions_elapsed', 'pace_so_far', 'run_diff', 'poss_since_lead_change', 'home_final', 'away_final', 'outcome', 'n_plays_seen']
data/intelligence/garbage_time_segments.parquet 1226606 ['game_id', 'period', 'game_clock_sec', 'clock_rem', 'score_home', 'score_away', 'margin_abs', 'leading_team', 'is_garbage_time', 'gt_entry_clock_sec', 'gt_exit_clock_sec', 'build_date', 'n_games', 'gt_definition_version']
```

## Binding before-condition and LIMIT check

The before-condition was re-run rather than assumed. The previously landed
generic re-pricer was checked because its name suggested a possible existing
implementation. Its exact binding output was:

```text
REPRICER_PUBLIC_API=reprice_prop,reprice_from_dist
REPRICER_NBA_PTS_REB_AST_ADDITIVE=False
REPRICER_OUTPUT_TYPE=NoneType
REPRICER_HISTORICAL_CHECKPOINT_STORE=False
```

It therefore does not provide an NBA PTS/REB/AST quantile distribution at an
archived checkpoint. It exposes a scalar over-line re-price only, and cannot
produce one for the `PTS` fixture without a supplied fallback callable.

The full Parquet schema census for a historical partial player box required a
game key, player key, all three of PTS/REB/AST (or their expanded names), and a
clock, period, or as-of field. Its exact output was:

```text
HISTORICAL_PARTIAL_BOX_SCHEMA_MATCH_COUNT=0
```

The raw NBA archive was then scanned one JSON payload at a time. It did not
contain an in-progress capture usable as a partial player box:

```text
RAW_FILE_SIZE_CHECK files=2008 max_bytes=684690 over_300_mib=0
SUMMARY_SCAN files=1610 unique_games=1610 status_counts={'STATUS_FINAL': 1606, 'STATUS_POSTPONED': 4} player_stat_groups=3220 midgame_status_records=4
SCOREBOARD_SCAN files=398 events=1903 status_counts={'STATUS_FINAL': 1894, 'STATUS_POSTPONED': 9} midgame_status_records=9
```

All four summary records and all nine scoreboard records counted outside
`STATUS_FINAL` were postponed, not in-progress. Thus the scan has zero
mid-game NBA observations, not a head-slice conclusion.

The binding before-condition remains true: there are zero remaining-game NBA
box-score distributions at any archived mid-game checkpoint. Step 1 therefore
closes this row at the named data limit before Step 2.

## Fixed checkpoint table

The checkpoint set is fixed by the spec. No CRPS, confidence interval, or
comparison was computed because there are zero eligible game clusters. The
garbage-time partition remains explicit and is not merged with non-garbage
rows.

| Checkpoint | Partition | Eligible game clusters | State-conditioned CRPS | Naive CRPS | Game-clustered CI |
| --- | --- | ---: | --- | --- | --- |
| End Q1 | non-garbage | 0 | not computed | not computed | not computed |
| End Q1 | garbage-time | 0 | not computed | not computed | not computed |
| Half | non-garbage | 0 | not computed | not computed | not computed |
| Half | garbage-time | 0 | not computed | not computed | not computed |
| End Q3 | non-garbage | 0 | not computed | not computed | not computed |
| End Q3 | garbage-time | 0 | not computed | not computed | not computed |

## Test and contract self-check

Binding-route test, run one file at a time:

```text
python -m pytest scripts/platformkit/ingame/test_ingame_prop_repricer.py -q -p no:cacheprovider
18 passed in 0.78s
```

The new S245 synthetic test is not applicable: Step 1 stopped before any S245
module or scoring route could be added.

- B1: no metric was computed and no rows were excluded from a metric.
- B2-B6: no schema, gate, deployment, import, or caller changed.
- B7-B9: the relevant archive and schema censuses cover their full sets; no
  fitted or recycled metric denominator exists.
- B10 and Q3: no threshold or bar changed.
- Q1, Q2, Q4, Q5, and Q9: no scored comparison, charge, OOS evaluation, ahead
  claim, or paired-loss archive exists because the row stopped at the limit.
- Q6: this memo makes calibration-language-only statements.
- Q7: the `n >= 30` rail is not met because no scored sample exists.
- Q8: the premise was re-measured before the limit verdict.

## Required acquisition

The named gap is an archived NBA player box-score snapshot with game id, player
id, PTS, REB, AST, and an as-of period/clock at the fixed checkpoints. At least
30 game clusters per checkpoint are required before the fixed CRPS comparison
can be preregistered and scored.
