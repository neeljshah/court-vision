# S212 Regime-Key Clean Rerun

Machine: local `C:/Users/neelj/nba-track-a13` worktree on Windows; this is a
local, evidence-only rerun because all four declared cached corpora are local.

The S200 preregistration is
`docs/evidence/harness/S200_regime_key_oof_prereg_2026-09-04.md`, sealed with
SHA-256 `BCDF43B637B3735078033ED47D9A1A21B1612FBB45BE5C694B72AB64AB4B4AFC`.
The S212 scorer loaded one cached corpus at a time in a fresh Python process.

## Current result

The prior global-key archive is retained as the before row. The clean
date-group, train-only-key result is the current after value. All rows remain
in the denominator; no sport is omitted.

| Sport | Rows scored / input | Before ECE | Clean after ECE | Dropped |
|---|---:|---:|---:|---:|
| nba | 1,814 / 1,814 | 0.024843 | 0.022204500165 | 0 |
| mlb | 39,162 / 39,162 | 0.008077 | 0.009672349829 | 0 |
| soccer | 25,834 / 25,834 | 0.009302 | 0.009192347229 | 0 |
| tennis | 41,886 / 41,886 | 0.008403 | 0.016928256992 | 0 |

The post-correction values reproduce the verifier's prior clean rerun to the
reported precision. Every summary ten-bin reconstruction has maximum absolute
difference 0.0. The paired archives retain every source row with its cluster,
timestamp, outcome, both calibrated predictions, both squared losses, and both
confidence labels; their unique row-index counts are 1,814 / 39,162 / 25,834 /
41,886.

## Inputs and code identity

Every opened tabular source has no raster resolution. Byte sizes below are from
the local files at scoring time.

| Sport | Cached corpus and sidecar | Declared source files | Reference JSON |
|---|---|---|---|
| nba | `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_nba.parquet` (201706 bytes); `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_nba.sources.json` (771 bytes) | `C:/Users/neelj/nba-track-a13/data/domains/basketball_nba/games.parquet` (69063 bytes); `C:/Users/neelj/nba-track-a13/data/domains/basketball_nba/asof_features_ext.parquet` (177603 bytes); `C:/Users/neelj/nba-track-a13/data/domains/basketball_nba/asof_box_extra_ext.parquet` (178350 bytes) | `C:/Users/neelj/nba-track-a13/docs/evidence/calibration/nba_reliability_2026-09-03.json` (6933 bytes) |
| mlb | `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_mlb.parquet` (1645142 bytes); `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_mlb.sources.json` (903 bytes) | `C:/Users/neelj/nba-track-a13/data/domains/mlb/games.parquet` (343723 bytes); `C:/Users/neelj/nba-track-a13/data/domains/mlb/games_current.parquet` (164496 bytes); `C:/Users/neelj/nba-track-a13/data/domains/mlb/asof_park.parquet` (2925 bytes); `C:/Users/neelj/nba-track-a13/data/domains/mlb/asof_features.parquet` (738364 bytes) | `C:/Users/neelj/nba-track-a13/docs/evidence/calibration/mlb_reliability_2026-09-03.json` (6766 bytes) |
| soccer | `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_soccer.parquet` (6053712 bytes); `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_soccer.sources.json` (4326 bytes) | `C:/Users/neelj/nba-track-a13/data/domains/soccer/matches.parquet` (467254 bytes); `C:/Users/neelj/nba-track-a13/data/domains/soccer/asof_features.parquet` (3298632 bytes); `C:/Users/neelj/nba-track-a13/data/domains/soccer/asof_xg_proxy.parquet` (2586822 bytes) | `C:/Users/neelj/nba-track-a13/docs/evidence/calibration/soccer_reliability_2026-09-03.json` (6947 bytes) |
| tennis | `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_tennis.parquet` (2745405 bytes); `C:/Users/neelj/nba-track-a13/data/cache/combo/gate_corpus_tennis.sources.json` (1094 bytes) | `C:/Users/neelj/nba-track-a13/data/domains/tennis/matches.parquet` (1327492 bytes); `C:/Users/neelj/nba-track-a13/data/domains/tennis/asof_hold.parquet` (3219982 bytes); `C:/Users/neelj/nba-track-a13/data/domains/tennis/wta_matches.parquet` (525478 bytes); `C:/Users/neelj/nba-track-a13/data/domains/tennis/asof_hold_wta.parquet` (1102582 bytes); `C:/Users/neelj/nba-track-a13/data/domains/tennis/asof_return.parquet` (3874641 bytes) | `C:/Users/neelj/nba-track-a13/docs/evidence/calibration/tennis_reliability_2026-09-03.json` (7024 bytes) |

Route-file SHA-256 values: `s200_regime_key_oof.py`
`41EAFABE128651FE5B4954621F4296BBB1D34507D10C39CFBC899440D8A42F7C`;
`calibration_report.py`
`B5E41FE9CF344975314A9153EF4645C97520D9E250378E7A9CA620CC0140AACD`;
`calibration_report_helpers.py`
`7E5FD24A816334FFEF3DB8DA5E02175ABA0BE376A8E60EB8035B2E04DCE4F1FF`.

## Corrections and reproduction artifacts

`oof_per_regime` stores an immutable tuple in its global-walk cache and creates
a new list before any arm-specific replacement. The focused test verifies the
clean ECE is invariant to both clean-first and prior-arm-first call orders to
1e-12. `build_sport_summary` now reruns the default report path directly; it
does not construct default rows from a prior paired archive.

- Summary: `docs/evidence/S212_regime_key_clean_rerun_2026-09-04.json`
- Paired records: `docs/evidence/S212_regime_key_clean_rerun_{nba,mlb,soccer,tennis}_paired_2026-09-04.json`
- Focused test: `python -m pytest scripts/platformkit/eval_gate/test_s200_regime_key_oof.py -q -p no:cacheprovider` - 5 passed.
- LOC rail: `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` - 1 passed.

The touched production modules are 277, 114, and 283 physical lines,
respectively, and each is within the 300-line rail. No calibration threshold,
register, ledger, feature flag, or `data/` file was changed.

## NOT VERIFIED

- Fresh-process reproduction of the four clean ECE values was not rerun in this attempt.
- Denominators, zero-drop status, paired archives, and changed-label counts were not re-audited in this attempt.
- No broader test suite or deployment behavior was verified in this attempt.
