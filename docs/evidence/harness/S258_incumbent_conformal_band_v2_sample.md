# S258 attempt 1d: incumbent conformal band local sample

## Result

This is a local SAMPLE-SCALE STATIC conformal calibration SCREEN for the S123
NBA incumbents. It uses the sealed deterministic full-source sample with seed
258104: 79919 ticks / 269 complete games. The complete S86 source denominator
used to form that sample is 465249 ticks / 1593 games. The local scorer peak
working set was 335458304 bytes, below 600 MB.

The committed preregistration is
`docs/evidence/harness/S258_preregistration_incumbent_conformal_band_v2_sample.md`.
Its committed LF-byte seal, verified from `git show HEAD:<path>` by the focused
test, is `3c36c78bc78e5e372c87170831d388af87bd2eb1fad734ddf7ca69868c89f87a`.

## Inputs and local execution

| Input | Path | Bytes | Resolution | SHA-256 |
| --- | --- | ---: | --- | --- |
| Full source for deterministic selection | `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2829826 | Parquet tabular input; no pixel resolution | `5ea6498d88bf7548395c700c7239641dcbd1d641bdaddb5a6b63fcf0ea8909e5` |
| Materialized complete-game sample | `docs/evidence/harness/S258_incumbent_conformal_band_v2_source_sample.parquet` | 817494 | Parquet tabular input; no pixel resolution | `3bd1e4bf61458f7fe0738abde5e20592986849b08b7d2d603f0eeeaa9da67f4c` |
| Paired-loss and grouped-cell archive | `docs/evidence/harness/S258_incumbent_conformal_band_v2_sample_paired_loss.csv` | 158577 | CSV tabular input; no pixel resolution | `31acaeee493186f3d37e5373c1708cbd2b7dba0e50da70d8385a219bee416191` |

Machine: local `C:\Users\neelj\nba-track-a15`, Python 3.10. The deterministic
sample source was materialized locally through `s86.load_ticks(s86.CHECKPOINTS)`
before scoring; the bounded scorer loaded that sample through `s86.load_ticks`.
No module, preregistration, sample, or result was copied to a pod. The prior
pod-derived S258 files are superseded and excluded from evidence for this row.

The scorer retains the S86/S101 five-fold game-disjoint purge and symmetric
one-day embargo. `COVERAGE_MIN_GROUP=400`, `COVERAGE_MAX_GROUPS=50`, the two
minimum-group requirement, and nominal 0.90/0.80 are unchanged. Scored counts
can be below the sample denominator because the train-only seed and S123 as-of
anchor availability are not scored replacements for the input denominator.

## STATIC coverage and mean interval half-width

Coverage is empirical grouped coverage versus its stated nominal. There are no
ABSENT_BECAUSE cells: every listed phase and ALL cell has enough scored ticks
for the unchanged shared grouped evaluator.

| Arm | Nominal | Cell | Ticks | Groups | Coverage | Mean half-width |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| e4 | 0.90 | P1 | 6279 | 15 | 0.733333333 | 0.081443911 |
| e4 | 0.90 | P2 | 9929 | 24 | 0.666666667 | 0.076949988 |
| e4 | 0.90 | P3 | 7438 | 18 | 0.833333333 | 0.049636886 |
| e4 | 0.90 | P4 | 40231 | 50 | 0.920000000 | 0.011636362 |
| e4 | 0.90 | OT | 2711 | 6 | 1.000000000 | 0.022916582 |
| e4 | 0.90 | ALL | 66588 | 50 | 0.920000000 | 0.032661804 |
| e4 | 0.80 | P1 | 6279 | 15 | 0.533333333 | 0.063642231 |
| e4 | 0.80 | P2 | 9929 | 24 | 0.500000000 | 0.061340962 |
| e4 | 0.80 | P3 | 7438 | 18 | 0.722222222 | 0.042868032 |
| e4 | 0.80 | P4 | 40231 | 50 | 0.860000000 | 0.004443470 |
| e4 | 0.80 | OT | 2711 | 6 | 1.000000000 | 0.011735356 |
| e4 | 0.80 | ALL | 66588 | 50 | 0.880000000 | 0.023098556 |
| ladder_base | 0.90 | P1 | 6028 | 15 | 1.000000000 | 0.244008960 |
| ladder_base | 0.90 | P2 | 9543 | 23 | 1.000000000 | 0.239943616 |
| ladder_base | 0.90 | P3 | 7160 | 17 | 1.000000000 | 0.166155946 |
| ladder_base | 0.90 | P4 | 38727 | 50 | 1.000000000 | 0.138987892 |
| ladder_base | 0.90 | OT | 2711 | 6 | 0.833333333 | 0.148714479 |
| ladder_base | 0.90 | ALL | 64169 | 50 | 1.000000000 | 0.167312476 |
| ladder_base | 0.80 | P1 | 6028 | 15 | 0.933333333 | 0.166409873 |
| ladder_base | 0.80 | P2 | 9543 | 23 | 0.956521739 | 0.159691066 |
| ladder_base | 0.80 | P3 | 7160 | 17 | 1.000000000 | 0.113917578 |
| ladder_base | 0.80 | P4 | 38727 | 50 | 0.580000000 | 0.074027186 |
| ladder_base | 0.80 | OT | 2711 | 6 | 0.833333333 | 0.066430147 |
| ladder_base | 0.80 | ALL | 64169 | 50 | 0.760000000 | 0.099577270 |

The worst-covered cell is e4, nominal 0.80, P2: 0.500000000 coverage. The
widest mean interval is ladder_base, nominal 0.90, P1: 0.244008960 half-width.

## S101 sample STATIC regression

On the same 79919-tick / 269-game sample, the S101 market/model STATIC route
and its direct grouped replay agree over 24 arm/nominal/cell values:
`max_abs_coverage_diff = 0.0 <= 1e-9`. The JSON records each comparison.

| Route file | SHA-256 used by scorer |
| --- | --- |
| S258 sample evaluator | `8e28c05c9de06111df1ac17064784b5ff3791512b61b0d43e2681fe574a0022a` |
| S86 loader | `2e197d14cce6d86ed80db6482cf37b08201c61944b930197cbf6317a1140fa68` |
| S101 evaluator | `4dbadc319b76a0e9c6e4ea53e3c683f242176774290917bebee894344c2cf93f` |
| S123 incumbent | `476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed` |
| ACI support | `17dbb28395158d0366cafddf9e309152722076960783fb8d30d53e14db12136c` |

## Contract self-check and NOT VERIFIED

- Q1: the sample preregistration was committed and sealed before scoring.
- Q3: fixed nominal, fold, embargo, and grouped-cell constants are retained.
- Q4: each fold asserts purge and symmetric embargo; the S101 sample STATIC
  route regression is 0.0.
- Q5/Q6: this is one-window calibration SCREEN language only.
- Q7: all result cells retain their counts and grouped archive records.
- Q8: the full-source premise was remeasured locally: 465249 / 1593.
- Q9: the CSV preserves every sample-game denominator, per-game paired Brier
  losses, and every grouped coverage unit required to recompute a cell.

NOT VERIFIED:

- An independent verifier has not rerun this landed local archive.
- This sample-scale result is not a full-source measurement.
- No second independent corpus is supplied.
- No deployment, feature-flag action, register, ledger, or pod execution is in scope.

SUCCESSOR: a full-source pod run (465249 / 1593) is a separate row after this
one lands; contract B5 prohibits transferring its module bytes before ACCEPT.
