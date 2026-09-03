# S180 MLB gate current-era coverage

Date: 2026-09-04
Lane: S180, `track-a14`
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`
Result: ACCEPT candidate; the fixed census coverage bars are met.

## Premise first

Before any implementation, the existing
`data/cache/combo/gate_corpus_mlb.parquet` was read as a full census. It had
39,162 rows and the same nine columns listed in the durable summary. The
premise reproduced exactly:

| corpus_unit | rows | sp_first6_diff_ew | park_factor | sp_ra_diff_asof | y | p_base | p_home_elo |
|---|---:|---:|---:|---:|---:|---:|---:|
| era_2010_2021 | 27,983 | 24,521 | 0 | 26,559 | 27,983 | 27,983 | 27,983 |
| era_2022_2026 | 11,179 | 0 | 0 | 0 | 11,179 | 11,179 | 11,179 |

The on-disk cause also reproduced. `corpus_cache_sources._build_mlb()` loaded
the legacy `asof_park.parquet` and `asof_features.parquet` once, then joined
those same frames to both era legs.

## Current-sibling ceiling

Each store was read separately and was smaller than the 300 MB limit.

| source | source rows | non-null values on 11,179 current-era ids | ceiling |
|---|---:|---:|---:|
| asof_park_current.parquet / park_factor | 10,826 | 10,517 | 94.08 pct |
| asof_features_current.parquet / sp_ra_diff_asof | 10,458 | 9,765 | 87.35 pct |

`build_sp_form_features()` returned 27,983 legacy-era ids and served 0 of the
11,179 current-era ids. Therefore `sp_first6_diff_ew` is CLOSED AT LIMIT for
`era_2022_2026` and is not part of the S180 bar.

## Additive change

The MLB builder now loads each `_current` sibling when it exists, records the
path in `sources`, and uses it only for `era_2022_2026`. Each legacy-joined
column calls `combine_first` with its current sibling, so an existing legacy
value is retained and only an absent value is filled. No output column, field,
status value, threshold, or feature-family definition changed.

The local build called `_build_mlb()` in memory. It did not persist a cache or
sidecar because this lane was explicitly prohibited from writing under
`data/`.

## Before and after full-census counts

| corpus_unit | state | rows | sp_first6_diff_ew | park_factor | sp_ra_diff_asof | y | p_base | p_home_elo |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| era_2010_2021 | before | 27,983 | 24,521 | 0 | 26,559 | 27,983 | 27,983 | 27,983 |
| era_2010_2021 | after | 27,983 | 24,521 | 0 | 26,559 | 27,983 | 27,983 | 27,983 |
| era_2022_2026 | before | 11,179 | 0 | 0 | 0 | 11,179 | 11,179 | 11,179 |
| era_2022_2026 | after | 11,179 | 0 | 10,517 | 9,765 | 11,179 | 11,179 | 11,179 |

The output remains 39,162 rows by nine columns in the same order. `y` and
`p_base` are non-null on 39,162/39,162 rows. The complete rebuilt
`era_2010_2021` frame is `DataFrame.equals`-identical to the archived
pre-change frame, including index, column order, dtypes, and every value.

The fixed family document remains unchanged at five `mlb_gate` features and
45 hypotheses. This lane changes coverage only. It ran no screen and changed
no verdict. The three named corpus columns currently contribute zero
screenable rows on the 910-row close window, leaving 27 of 45 `mlb_gate`
hypotheses unscoreable there; this is not a claim that the entire MLB screen
surface is empty.

## Durable reproduction artifacts

- `docs/evidence/harness/mlb_gate_current_era_2026-09-04_summary.json` contains
  the before and after non-null counts for all nine columns, denominators,
  ceilings, controls, source paths, and artifact paths.
- `docs/evidence/harness/mlb_gate_current_era_2026-09-04_legacy_before.parquet`
  is the complete 27,983-row, nine-column pre-change control slice.
- `docs/evidence/harness/mlb_gate_current_era_2026-09-04_after.parquet` is the
  complete 39,162-row, nine-column in-memory result.

Reproduction: load the two Parquet artifacts; select `era_2010_2021` from the
after artifact and call `reset_index(drop=True).equals(legacy_before)`. Then
group the after artifact by `corpus_unit` and count non-null values for every
column. The results must equal the summary JSON.

## Test

Exactly one new per-file test was run:

`python -m pytest scripts/platformkit/combo/test_corpus_cache_mlb_current_era.py -q -p no:cacheprovider`

Result: 1 passed in 2.73s.

## Verifier self-check

Section B:

- B1: full 39,162-row census; no row excluded.
- B2: additive schema; all nine names and their order are unchanged. The
  builder interface and variable-length source-manifest loop in
  `corpus_cache.py` remain unchanged. Reader search covered the generic corpus
  consumers in `combo/batch_gate.py`, `eval_gate/calibration_report.py`,
  `eval_gate/catalog_rescreen.py`, `eval_gate/close_join.py`,
  `eval_gate/close_join_nba_mlb.py`, `eval_gate/s108_features.py`,
  `foundry/screen_predictor.py`, and `foundry/tiers.py`; all continue to consume
  the same frame and field names.
- B3: missing current siblings preserve the legacy join; absence does not
  quarantine a row.
- B4: no claim or retry state exists in this lane.
- B5: no deployment or remote copy occurred.
- B6: no module moved or retired.
- B7: reproduction is a census, not a head slice.
- B8: no fit or residual metric exists.
- B9: denominators are the two fixed era populations, not recycled ids.
- B10: no threshold, family count, or bar moved.

Section Q:

- Q1: no scored comparison; no preregistration applies.
- Q2: no charged trial and no ledger access.
- Q3: both bars are byte-for-byte those in the S180 spec and were not changed.
- Q4: no OOS model comparison or meta-learner.
- Q5: no AHEAD verdict.
- Q6: calibration language only.
- Q7: `n = 39,162` is the exhaustive census.
- Q8: the premise was remeasured before implementation and matched exactly.
- Q9: no paired-loss comparison; the complete before control and after result
  needed for this coverage metric are archived.

## NOT VERIFIED

- The persisted `data/cache/combo/gate_corpus_mlb.parquet` was not rebuilt or
  modified. The verifier must rebuild it in master, re-read it, and reproduce
  the durable summary counts.
- `data/cache/eval_gate/backtest_fwer.jsonl` is absent in this worktree, so its
  required 18-row byte-identity could not be checked locally. This lane did
  not create, read, or modify it; the verifier must check the master artifact.
- `sp_first6_diff_ew` remains unavailable for the current era and is CLOSED AT
  LIMIT as measured above.
- No downstream screen or verdict was run; coverage alone is not a result.
