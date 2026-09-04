# S294: full-source S86-block CPCV STATIC conformal coverage

## Result

ACCEPT. This is an uncharged NBA in-game calibration measurement on the full
source. The pod scratch replay loaded, scored, and archived 465249 ticks from
1593 game clusters, with no named exclusions. The route held each of the six
fixed S86 tick-balanced blocks once, using the shared game-disjoint purge and
symmetric one-day embargo. Every reported cell exceeds the fixed 400-tick
minimum; there are no `ABSENT_BECAUSE` cells.

The sealed preregistration is
`docs/evidence/harness/S294_preregistration_incumbent_conformal_full_s86_blocks_2026-09-04.md`.
Its file-normalized and `git show HEAD:<path>` seal is
`0591642749e4dbf7bf71207b094e34759fe0c91fa9441f3296a1b79066503b90`.

## Frozen S86 blocks and denominators

| Block | First game_date | Last game_date | Ticks | Games |
| ---: | --- | --- | ---: | ---: |
| 0 | 2024-10-22 | 2024-12-08 | 78255 | 248 |
| 1 | 2024-12-09 | 2025-01-27 | 80259 | 289 |
| 2 | 2025-01-28 | 2025-11-05 | 75563 | 238 |
| 3 | 2025-11-06 | 2026-01-02 | 77853 | 277 |
| 4 | 2026-01-03 | 2026-02-26 | 75904 | 264 |
| 5 | 2026-03-01 | 2026-06-13 | 77415 | 277 |

The game_id-only stream census and scored set both are 465249 ticks / 1593
games. The block table is the direct output of
`s94_nba_early_shrinkage.fold_dates` on the frozen grid.

## STATIC grouped coverage and mean half-width

| Nominal | Cell | Ticks | Groups | Coverage | Mean half-width |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0.90 | P1 | 44428 | 50 | 0.920000000 | 0.078334559 |
| 0.90 | P2 | 68825 | 50 | 0.900000000 | 0.062730609 |
| 0.90 | P3 | 52645 | 50 | 0.940000000 | 0.049578907 |
| 0.90 | P4 | 284586 | 50 | 0.900000000 | 0.011354054 |
| 0.90 | OT | 14765 | 36 | 0.888888889 | 0.056699695 |
| 0.90 | ALL | 465249 | 50 | 1.000000000 | 0.031114796 |
| 0.80 | P1 | 44428 | 50 | 0.840000000 | 0.062073008 |
| 0.80 | P2 | 68825 | 50 | 0.780000000 | 0.046818263 |
| 0.80 | P3 | 52645 | 50 | 0.880000000 | 0.036991346 |
| 0.80 | P4 | 284586 | 50 | 0.800000000 | 0.003384456 |
| 0.80 | OT | 14765 | 36 | 0.777777778 | 0.026552681 |
| 0.80 | ALL | 465249 | 50 | 1.000000000 | 0.019952038 |

The full-source worst coverage is OT at nominal 0.80, 0.777777778, compared
with S265's worst coverage of 0.833333333. The full-source widest mean
half-width is P1 at nominal 0.90, 0.078334559, compared with S265's P2 at
nominal 0.90, 0.207218181. This is a full-source versus sample-scale
calibration comparison only.

## S101 regression, inputs, and reproduction

The retained S101 24-cell STATIC regression is exact: maximum absolute
coverage difference is 0.0, within the fixed 1e-9 tolerance. The local
reference used for this regression is
`data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz`; the pod
used its supplied scratch copy at
`/workspace/wt/a17/inputs/s101_aci_coverage_2026-09-03_ticks.csv.gz`.
Both are 18426107 bytes with MD5
`2dd8f53f9ec629cb5764e6201dad539a`. The source checkpoint input is
`data/cache/inplay_odds/nba_checkpoints_full.parquet`.

Peak pod RSS was 2110668800 bytes. The archive summary is
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_2026-09-04.json`;
the recomputable paired-loss and grouped-coverage archive is
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_paired_loss_2026-09-04.csv.gz`.
The pod output tail is
`docs/evidence/harness/S294_incumbent_conformal_full_s86_blocks_pod_log_tail_2026-09-04.txt`.

## S276 preservation and contract self-check

The prior S276 dated JSON and memo were restored byte-for-byte. Their
correction is recorded only in
`docs/evidence/harness/S276_incumbent_conformal_band_full_pod_2026-09-04_erratum_2026-09-04.md`.

- Q1: the sealed preregistration predates the full-source scoring.
- Q2: no ledger or register action occurred.
- Q3: the fixed S86 block design and S101 constants are unchanged.
- Q4: every held block runs through `cpcv_evaluate` with the shared purge and
  symmetric embargo; the archive preserves the per-state paired series and
  grouped units.
- Q6: this memo reports calibration only.
- Q7: the full source contains 1593 game clusters.
- Q8: the stream premise was remeasured before dispatch.
- Q9: the focused archive-only test recomputes P1 at nominal 0.90.

## NOT VERIFIED

- Pod process history outside the recorded scratch command was not audited.
- A duplicate scratch-only process caused by the local wrapper retry completed
  with the same calibration cells and is not an independent result.
