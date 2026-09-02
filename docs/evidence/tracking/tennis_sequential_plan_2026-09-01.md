# Tennis sequential camera-lock plan (2026-09-01)

This is G18 evidence from the unmodified tennis adapter, camera lock, and
`scripts/platformkit/tracking_harness.py`. Each run used five deterministic
300-frame contiguous ranges (seed `20260901`). Range anchors used the existing
`court_diagnostics.rejection_gate(frame) == "accepted"`; no new gate or
threshold was added. The decoded-frame denominator is the emitted manifest.

| match | source range | solved coverage | drift-checked reuse | verdict | failing metric |
|---|---:|---:|---:|---|---|
| nyYk 720p | 5715-6014 | 0.6100 | 36 | PASS | none |
| nyYk 720p | 33105-33404 | 0.9900 | 24 | PASS | none |
| nyYk 720p | 33855-34154 | 0.9967 | 26 | PASS | none |
| nyYk 720p | 41985-42284 | 0.5733 | 17 | PASS | none |
| nyYk 720p | 43830-44129 | 0.5600 | 18 | PASS | none |
| tennis 09 | 615-914 | 0.7067 | 4 | FAIL | oob 0.50 > 0.08 |
| tennis 09 | 5070-5369 | 1.0000 | 1 | FAIL | oob 0.51 > 0.08 |
| tennis 09 | 5775-6074 | 0.5933 | 0 | FAIL | oob 0.11 > 0.08 |
| tennis 09 | 6960-7259 | 1.0000 | 0 | PASS | none |
| tennis 09 | 7140-7439 | 1.0000 | 0 | FAIL | oob 0.35 > 0.08 |
| tennis 10 | 150-449 | 0.3967 | 12 | FAIL | oob 0.49 > 0.08 |
| tennis 10 | 3585-3884 | 0.4600 | 14 | PASS | none |
| tennis 10 | 3930-4229 | 0.6767 | 11 | PASS | none |
| tennis 10 | 6345-6644 | 0.8433 | 6 | PASS | none |
| tennis 10 | 6405-6704 | 0.6533 | 5 | PASS | none |

Pass fractions are 5/5 for nyYk 720p, 1/5 for tennis 09, and 4/5 for tennis
10. This verifies that sequential frame spacing removes the linspace-induced
`jump_p95` construction in these sampled ranges: no range failed on jump_p95.
It does not establish universal camera-lock quality. The four tennis 09 and one
tennis 10 failures remain recorded as harness failures, all for out-of-bounds
player coordinates; no selection, adapter, gate, or harness parameter was
tuned after these results. Raw per-video evidence is in the adjacent JSON files.

## Render-and-look (independent verifier, 2026-09-01)

Four ranges were re-run on the pod and rendered with the solved court lines
drawn (`tennis_calib_eval.render_overlays`, unchanged) at three frames each;
overlays are in `tennis_sequential_plan_2026-09-01/overlays/`. Nothing was
tuned; this is a read of the committed run.

| range | verdict | frames viewed | lines on lines? | what the FAIL actually is |
|---|---|---|---|---|
| tennis 09 6960-7259 | PASS | 6960, 7110, 7259 | yes -- baselines, sidelines, service lines and centre line all sit on the painted lines through a camera pan | n/a |
| tennis 09 5070-5369 | FAIL oob 0.51 | 5070, 5220, 5369 | yes -- solve is correct on every frame viewed | NOT a solve error. `detect_players` emitted courtside non-players: at f5070 the two emitted feet are (46, 50) ft = staff by the equipment bags and (34, 41) ft = the ball kid at the umpire chair, while Nadal and Medvedev were not emitted at all. oob y spans 40.7-67.2 ft, i.e. 5-31 ft beyond the doubles sideline -- the courtside furniture lane. |
| tennis 10 6345-6644 | PASS | 6348, 6474, 6600 | yes -- second venue (WTA hard court), lines on lines | n/a |
| tennis 10 150-449 | FAIL oob 0.49 | 255, 315, 375 | yes on the solved frames | Two defects, neither a solve error. (a) The oob track is the chair umpire: every oob row is track 2 at (63-66, 48-50) ft, and at f255 the far player Swiatek is not emitted while the umpire in the chair is. (b) Plan artifact: 181 of 300 frames report `calibration_unavailable` -- the range spans a non-court segment, so only 119 frames emit at all. |

Conclusion of the look: the sequential plan and the camera-lock solve are sound
on all four ranges viewed. The oob failures are a player-selection defect in
`detect_players` (largest / most-continuous box per court half picks the chair
umpire, ball kids and courtside staff when a real player is small or occluded),
not a homography defect. That is a separate, newly localised gap; no threshold,
adapter, gate or harness parameter was changed to produce this note.
