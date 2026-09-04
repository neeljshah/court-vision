# S265 attempt 1b: incumbent conformal band sample

## Result

ACCEPT, SAMPLE-SCALE only. This local STATIC conformal calibration measurement
for the S123 `ladder_base` incumbent used the sealed whole-game sample with
seed 258104: 79919 ticks / 269 games. The binding streaming `game_id` premise
was 465249 ticks / 1593 games. Peak RSS was 449515520 bytes, below 600 MB.

The sealed preregistration is
`docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md`.
Its `git show HEAD:<path>` LF-byte seal is
`17aa1f6cdee9207aa83fd8addcefb58931ade103fb464b72d5068a6a74f451f8`.

## STATIC coverage and mean half-width

Coverage is empirical grouped coverage against the stated nominal. The grouped
cells are P1, P2, P3, P4, OT, and ALL. Every reported cell exceeds the fixed
400-tick minimum; there are no `ABSENT_BECAUSE` cells.

| Nominal | Cell | Ticks | Groups | Coverage | Mean half-width |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0.90 | P1 | 6028 | 15 | 1.000000000 | 0.201177648 |
| 0.90 | P2 | 9543 | 23 | 1.000000000 | 0.207218181 |
| 0.90 | P3 | 7160 | 17 | 1.000000000 | 0.114159443 |
| 0.90 | P4 | 38727 | 50 | 1.000000000 | 0.137909089 |
| 0.90 | OT | 2711 | 6 | 0.833333333 | 0.096824213 |
| 0.90 | ALL | 64169 | 50 | 1.000000000 | 0.149771680 |
| 0.80 | P1 | 6028 | 15 | 1.000000000 | 0.181682661 |
| 0.80 | P2 | 9543 | 23 | 0.956521739 | 0.184737047 |
| 0.80 | P3 | 7160 | 17 | 1.000000000 | 0.101631631 |
| 0.80 | P4 | 38727 | 50 | 1.000000000 | 0.045685435 |
| 0.80 | OT | 2711 | 6 | 0.833333333 | 0.033841366 |
| 0.80 | ALL | 64169 | 50 | 1.000000000 | 0.084881664 |

The worst-covered cells are OT at both nominal levels, each 0.833333333. The
widest mean half-width is P2 at nominal 0.90, 0.207218181.

## Retained S101 STATIC regression

The scorer replayed
`data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz` through
`s101.score` and compared its 24 market/model, nominal, and grouped-cell
STATIC coverages against the committed
`data/cache/eval_gate/s101_aci_coverage_2026-09-03.json`. The result is
`max_abs_coverage_diff = 0.0`, within the fixed `1e-9` tolerance.

## Reproduction and bounds

The scorer is
`scripts/platformkit/eval_gate/s265_incumbent_conformal_band_sample.py` (238
lines). It streams the source for complete-game selection, loads only the
sealed selected games, uses S101 `run_fold` and `score` callbacks, and asserts
game-disjoint purge plus a symmetric one-day embargo in every scored fold.
RSS was 155791360 bytes before scoring and 251244544 bytes after scoring.

`docs/evidence/harness/S265_incumbent_conformal_band_sample_2026-09-04_retry2.json`
stores the summary and all 24 S101 comparisons. Its paired-loss and grouped
coverage archive is
`docs/evidence/harness/S265_incumbent_conformal_band_sample_paired_loss_2026-09-04_retry2.csv`.
The per-file archive-only recomputation passed:

`python -m pytest tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py -q`

Sample coverage is not full-source coverage. The only route to a claim about
the 465249-tick / 1593-game source is the successor stage-2 pod row after this
sample-scale acceptance; no module or evidence was copied to a pod here.

## Contract self-check

- Q1: the preregistration was its own committed, LF-sealed commit before scoring.
- Q2: this local calibration measurement has no charged-trial ledger action.
- Q3: the S86 fold design and S101 grouped constants are unchanged.
- Q4: all coverage values are produced by the shared S101 callbacks with purge
  and symmetric embargo assertions.
- Q7: the sealed sample has 269 complete game clusters, above the 30-cluster rail.
- Q8: the row premise was remeasured by the binding streaming scan before scoring.
- Q9: the CSV preserves game membership, per-game paired losses, and grouped
  coverage units; the focused test recomputes P4 at nominal 0.80 from it.
