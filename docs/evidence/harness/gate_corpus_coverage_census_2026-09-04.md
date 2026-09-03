# S183 Gate Corpus Coverage Census

## Result

The fresh read-only census enumerates 52 feature columns and 220
`(column, corpus_unit)` cells across the four live gate corpora. All 52 columns
and all 220 cells are present in `freshness_report`. Six cells have a zero
non-null count and are recorded by name below. The four spine columns
`event_id`, `corpus_unit`, `event_date`, and `y` are excluded.

A zero cell is recorded and named; it does not raise. In particular,
`park_factor` is zero for both MLB units. Refusing that recorded state would
turn a coverage finding into an MLB build interruption, whereas the named list
is the instrument for callers and review.

Rates are non-null count divided by the shown row count. The JSON coverage
extract next to this memo records the four `freshness_report` census results;
the tables below make the complete enumeration readable.

## NBA: 11 columns, 22 cells, 1,814 rows

| Feature | Global | 2024-25 | 2025-26 |
| --- | --- | --- | --- |
| p_base | 1814/1814 (1.000000) | 1225/1225 (1.000000) | 589/589 (1.000000) |
| p_elo | 1814/1814 (1.000000) | 1225/1225 (1.000000) | 589/589 (1.000000) |
| dreb_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| fg3m_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| stl_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| blk_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| pace_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| oreb_pg_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| tov_pg_diff_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| dreb_x_pace_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |
| stl_x_fg3m_asof | 1798/1814 (0.991180) | 1209/1225 (0.986939) | 589/589 (1.000000) |

## MLB: 5 columns, 10 cells, 39,162 rows

| Feature | Global | era_2010_2021 | era_2022_2026 |
| --- | --- | --- | --- |
| p_base | 39162/39162 (1.000000) | 27983/27983 (1.000000) | 11179/11179 (1.000000) |
| p_home_elo | 39162/39162 (1.000000) | 27983/27983 (1.000000) | 11179/11179 (1.000000) |
| sp_first6_diff_ew | 24521/39162 (0.626143) | 24521/27983 (0.876282) | 0/11179 (0.000000) |
| park_factor | 0/39162 (0.000000) | 0/27983 (0.000000) | 0/11179 (0.000000) |
| sp_ra_diff_asof | 26559/39162 (0.678183) | 26559/27983 (0.949112) | 0/11179 (0.000000) |

## Soccer: 29 columns, 174 cells, 25,834 rows

Unit rows are D1/E0/E1/F1/I1/SP1. Their denominators are
3366/4180/6072/3856/4180/4180, respectively.

| Features | Global | D1/E0/E1/F1/I1/SP1 counts (rates) |
| --- | --- | --- |
| p_base, p_over25, home_n_prior, away_n_prior | 25834/25834 (1.000000) | 3366/4180/6072/3856/4180/4180 (all 1.000000) |
| home_sot_for_l10, home_sot_ratio_for_asof, home_sot_for_asof, home_sot_against_asof, home_shots_for_asof, home_shots_against_asof, home_xg_for_asof, home_xg_against_asof, home_xg_supremacy_asof | 25752/25834 (0.996826) | 3354/4170/6055/3842/4166/4165 (0.996435/0.997608/0.997200/0.996369/0.996651/0.996411) |
| away_sot_for_l10, away_sot_ratio_for_asof, away_sot_for_asof, away_sot_against_asof, away_shots_for_asof, away_shots_against_asof, away_xg_for_asof, away_xg_against_asof, away_xg_supremacy_asof | 25729/25834 (0.995936) | 3348/4170/6051/3837/4159/4164 (0.994652/0.997608/0.996542/0.995073/0.994976/0.996172) |
| diff_sot_for_asof, diff_sot_against_asof, diff_shots_for_asof, diff_shots_against_asof, diff_xg_for_asof, diff_xg_against_asof, diff_xg_supremacy_asof | 25708/25834 (0.995123) | 3345/4170/6046/3833/4155/4159 (0.993761/0.997608/0.995718/0.994035/0.994019/0.994976) |

The JSON count/row pairs retain the unrounded ratios used by the report.

## Tennis: 7 columns, 14 cells, 41,886 rows

| Feature | Global | ATP | WTA |
| --- | --- | --- | --- |
| p_base | 41886/41886 (1.000000) | 30616/30616 (1.000000) | 11270/11270 (1.000000) |
| p_elo | 41886/41886 (1.000000) | 30616/30616 (1.000000) | 11270/11270 (1.000000) |
| surface | 41886/41886 (1.000000) | 30616/30616 (1.000000) | 11270/11270 (1.000000) |
| p1_hold_pct_asof | 40753/41886 (0.972950) | 30024/30616 (0.980664) | 10729/11270 (0.951996) |
| p2_hold_pct_asof | 39756/41886 (0.949148) | 29443/30616 (0.961687) | 10313/11270 (0.915084) |
| diff_return_won_asof | 29179/41886 (0.696629) | 29179/30616 (0.953064) | 0/11270 (0.000000) |
| diff_break_pct_asof | 29181/41886 (0.696677) | 29181/30616 (0.953129) | 0/11270 (0.000000) |

## Zero coverage cells

1. `mlb: sp_first6_diff_ew, era_2022_2026`
2. `mlb: park_factor, era_2010_2021`
3. `mlb: park_factor, era_2022_2026`
4. `mlb: sp_ra_diff_asof, era_2022_2026`
5. `tennis: diff_return_won_asof, WTA`
6. `tennis: diff_break_pct_asof, WTA`

## Reproduction and preservation

`freshness_report(sport)` reads each cached parquet and recomputes counts and
rates from `df.groupby('corpus_unit')[column].notna().sum()` and `.mean()`.
The test uses only a temporary cache directory. The live parquet SHA-256
prefixes remain NBA `716f6f5f3f21`, MLB `ac60c9cb1895`, soccer
`e0d2f13e7a53`, and tennis `22d006f2b4f7`; their existing sidecars are not
written by this lane.

## Verifier self-check

- B1: every feature column and unit is included; no failing row is excluded.
- B2: only additive report and newly built-sidecar keys are added.
- B3-B6: no gate, claim, deployment, or module move is introduced.
- B7-B10: this is an exhaustive construct census with no sampling or bar change.
- Q1-Q6 and Q9: no scored comparison, threshold, preregistration, ledger action,
  or model comparison is involved; language is limited to coverage and calibration.
- Q7: `n = 52 (CONSTRUCT)` and all 220 cells are enumerated. Q8: the premise was
  remeasured before the change and matched.

## NOT VERIFIED

- The census records coverage; it does not determine why a source value is absent.
- `data/cache/eval_gate/backtest_fwer.jsonl` is absent in this worktree, so its
  byte preservation cannot be verified here; it was not created or written.
- No source tables, cached parquets, existing sidecars, register, ledger, flags, or
  deployment targets were written.
