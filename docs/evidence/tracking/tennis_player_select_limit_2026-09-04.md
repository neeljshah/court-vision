# G26 tennis player-selection limit measurement (2026-09-04)

## Contract and premise

This is final attempt 2 for G26 and follows
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. The attempt-1 memo at
`tennis_player_select_2026-09-02.md` reproduces its premise: the stipulated
x=[-6,84], y=[-4,40] ft prior changed the three pass fractions from 5/5, 1/5,
4/5 to 1/5, 0/5, 1/5 while recording oob 0.0000 in every one of the 15 ranges.
Its solver-coverage values were unchanged. This memo measures the geometric
limit before choosing any replacement envelope.

The pod measurement uses the same committed ranges: five 300-decoded-frame
ranges per match, seed 20260901. It does not change a harness threshold, the
court solver, camera lock, or `domains/tennis/tracking/court_lines.py`.

## Step-0 remeasurement: FALSIFIED

The current isolated process reimplemented only the unmerged attempt-1
selector in memory. It used the stipulated rectangle and the frozen 15
committed ranges. The generated raw artifacts are intentionally not used to fit
an envelope: the premise check below failed, so the specified stopping rule
applies.

| match | attempt-1 pass fraction | remeasured pass fraction | remeasured oob | solver coverage: attempt-1 -> remeasured |
|---|---:|---:|---|---|
| nyYk 720p | 1/5 | 0/5 | 0.0000 in all 5 | 0.6100, 0.9900, 0.9967, 0.5733, 0.5600 -> 0.6000, 0.9933, 1.0000, 0.5733, 0.5300 |
| tennis 09 | 0/5 | 0/5 | 0.0000 in all 5 | 0.7067, 1.0000, 0.5933, 1.0000, 1.0000 -> 0.7067, 0.9967, 0.5933, 1.0000, 1.0000 |
| tennis 10 | 1/5 | 1/5 | 0.0000 in all 5 | 0.3967, 0.4600, 0.6767, 0.8433, 0.6533 -> 0.3933, 0.4600, 0.6767, 0.8433, 0.6533 |

The requested premise was 1/5, 0/5, 1/5 with solver coverage identical to the
attempt-1 table. The actual result is 0/5, 0/5, 1/5, and coverage differs in
seven ranges. In particular, all five nyYk ranges now fail `coverage` despite
the selected range set being unchanged. This is not a valid foundation for a
new p01/p99 envelope, and no distribution, attribution, or role exclusion was
used to make a geometry rule appear to work.

The raw pod output did contain 33,632 pre-selection candidate rows and 30
evenly placed renders (two positions in every range), but they are not
attributed or used because step 1 is prohibited after a false step-0 premise.
The render set therefore does not claim to satisfy the eight-render acceptance
check; that check is inapplicable to this FALSIFIED stop.

## NOT VERIFIED

- The real-player foot-point distribution and a p01/p99 envelope; neither was
  calculated after the step-0 failure.
- Whether geometry can recover the before fractions on a reproducible current
  solver/camera-lock baseline.
- Role identity or production-daemon behavior. No module was copied to or
  deployed on the pod; the selector existed only in the measurement process.
