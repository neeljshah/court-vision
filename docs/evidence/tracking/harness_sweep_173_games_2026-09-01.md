# Frozen-harness sweep of all 173 pod tracked games (2026-09-01)

Every `data/tracking/*/tracking_data.csv` on the pod was scored with the frozen
judge (`scripts/platformkit/tracking_harness.evaluate`, thresholds untouched),
sport inferred from the directory prefix (kbo/npb/mlb -> baseball, wnba/ncaa ->
basketball). Command preserved in the session transcript; run on the pod at
`nice -n 15`.

## Result: 0 passes / 173 games

| sport | games | verdict |
|---|---|---|
| baseball | 86 | all fail |
| football | 41 | all fail |
| soccer | 24 | all fail |
| basketball | 11 | all fail |
| tennis | 11 | all fail |

## Where they die

| stage | games | reading |
|---|---|---|
| declared `image_px` (contract-correct, unscorable by design) | 105 | honest producers; these can never pass and are the declared-corpus lane |
| rows OMIT coordinate_space (producer bug or legacy) | 50 | a writer is (or was) emitting undeclared rows; under audit |
| basketball: no court calibration sidecar | 11 | CSVs claim court coords without a solve artifact |
| empty CSV | 2 | |
| reached the metric gates | 4 | ALL TENNIS -- the only games in the program judged on quality |

## The four metric-reaching games (all tennis)

Recorded failures: `oob 0.23 > 0.08`, `oob 0.09 > 0.08`, `jump_p95 31.31 > 8.00`,
`jump_p95 36.53 > 8.00`. No coverage failure was recorded, which is SUSPICIOUS
against the measured 1.67% fresh-solve rate: if the producer emits only solved
frames, coverage is inflated by a suppressed denominator (the harness
denominator is emitted frames). Denominator audit dispatched twice
independently (Codex a1 wave 8 + a Claude audit agent) before any fix ships.

## What this changes

The binding wall is CALIBRATION, not detection or tracking: 97.7% of games are
rejected before a single quality metric is computed. Classical registration is
exhausted (tennis line-correspondence homography failed its pre-registered
< 2 ft gate; 5.28 ft median stands). The licence-clean path under test is a
self-trained synthetic-render keypoint model (no external weights or datasets).
Baseball's S4-via-measured-impossibility packet is the nearest bankable S4.
