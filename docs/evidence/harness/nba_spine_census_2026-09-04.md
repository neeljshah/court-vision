# S182 NBA Spine Census

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`.

Verdict: NOT VALIDATED IN THIS WORKTREE (ATTEMPT 2).

The games-rooted constructor writes the required default-cache artifact trio. The
default-path rerun reproduced every artifact byte-for-byte. The focused test now
requires that trio, the 18 non-blank FWER rows, and before/after hash identity.

## Premise remeasurement

`games.parquet` has 4,846 outcome-known rows, zero null `home_win` values, dates from 2022-10-18 through 2026-04-12, and this exhaustive denominator:

| Season | Games denominator |
|---|---:|
| 2022-23 | 1,230 |
| 2023-24 | 1,230 |
| 2024-25 | 1,230 |
| 2025-26 | 1,156 |
| Total | 4,846 |

The unchanged legacy corpus has 1,814 distinct event IDs: 0, 0, 1,225, and 589 by the same season order. Its uncovered-games count is 3,032 (62.5671 percent). `_build_nba` starts from `asof_features_ext.parquet`, which confirms the legacy denominator restriction.

## Construction result and default-path reproduction

The default full spine has 4,846 rows and 4,846 distinct event IDs. Its season
counts are 1,230, 1,230, 1,230, and 1,156. The frame carries non-null `y`,
pre-game `p_base` and `p_elo`, the nine as-of fields, and
`is_legacy_gate_subset`; its subset count is 1,814. It preserves exact `y` and
`p_base` equality for all 1,814 legacy event IDs, uses relative source keys,
and supports a portable load when sources are unavailable.

| Metric | Before | Default full spine |
|---|---:|---|
| Rows | 1,814 | 4,846 |
| Coverage | 37.4329 percent | 100.0000 percent |
| 2022-23 | 0 / 1,230 | 1,230 / 1,230 |
| 2023-24 | 0 / 1,230 | 1,230 / 1,230 |
| 2024-25 | 1,225 / 1,230 | 1,230 / 1,230 |
| 2025-26 | 589 / 1,156 | 1,156 / 1,156 |

| Default artifact | Rows | SHA-256 |
|---|---:|---|
| `data/cache/combo/gate_corpus_nba_full.parquet` | 4,846 | `471bf4017e32bcdf076f07b323078894050cca526bcb7cdd402103cf9bec0cf3` |
| `data/cache/combo/gate_corpus_nba_full.sources.json` | 4,846 declared | `bc2b69359aeb06e031965e445d567b1eb28f277c6df5a38f6776ef2a9221461a` |
| `data/cache/combo/gate_corpus_nba_full.census.json` | 44 census rows | `054d3e7a4659c426f2032a27b5c6364ae711267f3cb45927816b1ed2755b4898` |

A second default-path construction reproduced all three hashes exactly.

## Per-column maximum coverage

Every numerator below uses the full games denominator for that season. `OPEN` means the on-disk carrier reaches every game in the season; otherwise the status is `CLOSED AT LIMIT`. The separate JSON copy is `docs/evidence/harness/nba_spine_census_2026-09-04.summary.json`.

| Column | Carrier | 2022-23 | 2023-24 | 2024-25 | 2025-26 | Status |
|---|---|---:|---:|---:|---:|---|
| p_base | games + walk_forward_elo | 1230/1230 | 1230/1230 | 1230/1230 | 1156/1156 | OPEN all seasons |
| p_elo | games + walk_forward_elo | 1230/1230 | 1230/1230 | 1230/1230 | 1156/1156 | OPEN all seasons |
| dreb_diff_asof | asof_box_extra_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| fg3m_diff_asof | asof_box_extra_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| stl_diff_asof | asof_box_extra_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| blk_diff_asof | asof_box_extra_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| pace_diff_asof | asof_features_ext + asof_team_adv fallback | 1214/1230 | 1230/1230 | 1225/1230 | 589/1156 | CLOSED AT LIMIT |
| oreb_pg_diff_asof | asof_features_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| tov_pg_diff_asof | asof_features_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| dreb_x_pace_asof | box_extra + asof_features_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |
| stl_x_fg3m_asof | asof_box_extra_ext | 0/1230 | 0/1230 | 1209/1230 | 589/1156 | CLOSED AT LIMIT |

The alternate carrier measurements are: `asof_team_adv` 3,685 distinct game IDs (1,230/1,230/1,225/0); `asof_quarter_shape` 2,634 rows, 2,386 non-null game IDs and 248 null IDs (0/0/1,230/1,156); and `player_value_features` 7,222 rows with 3,611 distinct IDs (0/1,230/1,225/1,156). They cannot supply the required per-game oreb/tov fields or the four box fields.

## Venue-close attachment

NOT VERIFIED: `data/cache/venue_history/nba_close_corpus.parquet` is absent in this worktree. The specification references a prior 443-outside count (331 in 2022-23, 1 in 2024-25, and 111 in 2025-26) and a prior 289 non-placeholder count outside versus 220 inside; this run does not affirm those figures. With the full spine available, every close whose event ID matches one of the 4,846 games would have a spine row, while an unmatched close would remain explicitly unattached.

## NOT VERIFIED in this worktree

- `data/cache/eval_gate/backtest_fwer.jsonl` is absent, so the focused test's
  required 18-row byte-identity check cannot complete locally. This file was
  not created or modified because it is outside the permitted write scope.
- The venue-close corpus is absent, so the attachment counts cannot be remeasured.

Focused-test result: `PYTHONDONTWRITEBYTECODE=1 python -m pytest
scripts/platformkit/combo/test_nba_spine_census.py -q --basetemp
C:/Users/neelj/AppData/Local/Temp/s182_attempt2` stopped at the required FWER
existence assertion. No sibling test imports this module.

## Verifier self-check

- B1: PASS. Every census denominator is the exhaustive games spine.
- B2: PASS. The legacy schema and builder are untouched; the new schema has no existing readers beyond the new focused test.
- B3: PASS. Missing feature values remain NaN in a retained games-spine row.
- B4 through B10: PASS or not applicable; this is additive construction with no deployment, sampling, fitting, or changed threshold.
- Q1 through Q5 and Q9: not applicable; this is unscored construction.
- Q6: PASS. This memo uses calibration language only.
- Q7: PASS. The temporary construction enumerated all 4,846 outcome-known games, rather than sampling.
- Q8: PASS. The stated games and legacy-corpus premise was remeasured before implementation.
