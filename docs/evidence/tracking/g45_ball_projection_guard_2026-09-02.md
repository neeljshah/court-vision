# G45: tennis ball ground-projection guard

Date: 2026-09-02. Gap: G45. Code change: `domains/tennis/tracking/ball_projection_guard.py`, called by `ball_rows`. No harness file was edited, no threshold or `passed` field changed, no deploy or pod copy occurred.

## Relationship to G44 and G65

G39 established that the tennis ball detections are largely not balls: all 12 rendered candidates were not the ball. G65 is producing the label set needed to measure that properly. This G45 row is independent: the projection is unsound even if its input is a real ball. Both detection validity and plane validity must hold before any ball-derived quantity is trusted.

## Premise reproduced before the change

Read-only recomputation over `/workspace/nba-ai-system/data/tracking/<clip>/tracking_data.csv`, `cls == ball`, reproduced the G39 premise. The old table has no input pixel or homography, so this is a coordinate distribution replay, not a re-track.

| clip | all ball rows | x < -1000 ft | x > 1000 ft | abs(x) > 10000 ft | raw x min..max ft |
|---|---:|---:|---:|---:|---|
| tennis_02 | 1,831 | 60 | 119 | 21 | -113,676.5 .. 226,046.5 |
| tennis_03 | 2,630 | 34 | 80 | 19 | -126,835.5 .. 106,853.7 |
| tennis_04 | 2,946 | 64 | 101 | 11 | -34,542.6 .. 168,015.5 |
| tennis_05 | 2,395 | 70 | 129 | 21 | -85,003.7 .. 395,650.8 |

The totals below -1,000 ft are therefore 60/34/64/70, as G45 required. The maximum raw value is 395,650.8 ft; G45's cited 106,853.7 ft is the tennis_03 maximum. G39's two controls, whose vanishing rows were off-screen at -239.6 and -109.4 pixels, reached only 184.7 and 200.8 ft.

## Guard rule

For each current-frame homography, normalize its third row to obtain the image-space vanishing line, back-project the court centre through that same homography to establish the valid ground-side sign, reject a pixel on or beyond that line, and otherwise reject its ground projection unless it lies in the stated generous physical envelope `x in [-6, 84] ft`, `y in [-4, 40] ft`.

This is homography-derived, not a per-clip image-row constant. `projection_status` and `projection_rejection_reason` are additive fields. Rejected ball rows remain rows, retain their raw pre-guard projection in `raw_projected_x_ft` and `raw_projected_y_ft`, retain declared `court_feet` provenance, and expose `x`/`y` as missing rather than laundering an invalid ground coordinate. Existing fields retain their meaning. Player coordinate values are unchanged.

## Underlying distribution and row-count effect

To make the row drop auditable rather than circular, the raw distribution above is retained. The following independent read-only replay applies the stated physical envelope to every historical ball row. It is not used as a new quality metric and does not change `ball_in_bounds_pct`, its non-gating G43 adjudication, any harness threshold, player projection, solver, or camera lock.

| clip | before rows | usable x/y rows after envelope | rejected rows, retained with reason in new schema | usable fraction | post x min..max ft | post y min..max ft |
|---|---:|---:|---:|---:|---|---|
| tennis_02 | 1,831 | 449 | 1,382 | 24.52% | -5.916 .. 83.918 | -3.843 .. 39.849 |
| tennis_03 | 2,630 | 1,700 | 930 | 64.64% | -5.879 .. 83.949 | -3.720 .. 39.913 |
| tennis_04 | 2,946 | 1,572 | 1,374 | 53.36% | -5.588 .. 83.927 | -2.161 .. 39.996 |
| tennis_05 | 2,395 | 845 | 1,550 | 35.28% | -5.964 .. 83.432 | -3.921 .. 39.788 |

Thus the replay has zero usable rows below -1,000 ft and zero above the stated 84 ft x upper bound; the raw values remain named and retained for audit. The drop is expected containment, not evidence of better ball detection. The deployed code, unlike the legacy table, assigns each rejected row either `on_vanishing_line`, `beyond_vanishing_line`, or `outside_physical_envelope`; it never silently drops it.

## Eye check: eight evenly spaced newly covered candidates

The premise videos are deleted, so the eye check uses the preserved same-adapter sibling-run frames from G39, selected evenly over its 12 offending candidates (indices 0, 2, 4, 6, 7, 8, 10, 11; not a head slice). Each has raw x above 84 ft and is therefore newly rejected by the guard's envelope branch. The renders are committed under [`g45_renders/`](g45_renders/).

| frame | raw x ft | render | visual finding |
|---:|---:|---|---|
| 5501 | 161.4 | `f005501_outside_physical_envelope.jpg` | Scoreboard/speed-display graphic; not a ball. |
| 5644 | 115.5 | `f005644_outside_physical_envelope.jpg` | Far player's head/racket; not a ball. |
| 5687 | 100.5 | `f005687_outside_physical_envelope.jpg` | Far player's legs; real yellow ball is visible lower on court. |
| 5727 | 113.3 | `f005727_outside_physical_envelope.jpg` | Far player's head/racket; real ball is visible lower on court. |
| 5767 | 112.1 | `f005767_outside_physical_envelope.jpg` | Far player's head/racket; not a ball. |
| 5794 | 115.4 | `f005794_outside_physical_envelope.jpg` | Far player's head; real ball is visible at right. |
| 5870 | 111.1 | `f005870_outside_physical_envelope.jpg` | Staff/crowd-side motion beside speed display; not a ball. |
| 5902 | 115.8 | `f005902_outside_physical_envelope.jpg` | Far player's torso/head/racket; not a ball. |

Tally: 0/8 are the tennis ball; 7/8 are far-player body/head/racket and 1/8 is staff/crowd-side motion. This is a G44/G65 detection-label finding, not a claim that G45 has corrected ball court coordinates.

## Honest framing

A tennis ball is genuinely off the ground plane most of the time. Treating even a true ball pixel as a floor point is wrong. This guard does not make ball court coordinates correct; it stops them from being absurd and makes the rejected projection visible rather than silent.

## Test

Exactly one new per-file test was added to `domains/tennis/tracking/test_ball.py`:

```text
python -m pytest domains/tennis/tracking/test_ball.py -q
4 passed in 2.13s
```

## Verifier-contract self-check before report

| item | result |
|---|---|
| A7 | PASS: this memo and all eight named files in `g45_renders/` existed before commit. |
| B1 | PASS: the named raw distribution is reported before the envelope replay; rejected rows remain named. |
| B2 | PASS: only additive fields were introduced; ball producer, adapter, schema assertion, and rally consumer were inspected. |
| B3 | PASS: absent detections still follow the existing no-row path; a present rejected detection is retained and labelled. |
| B4 | PASS: rejection is terminal for that projection and is emitted as an explicit row status. |
| B5 | PASS: no code or artifact was copied to the pod; pod access was read-only CSV measurement. |
| B6 | PASS: this adds a directly imported module and retires nothing. |
| B7 | PASS: the eight render indices are evenly spaced across all 12 preserved offending candidates, not a head slice. |
| B8 | PASS: no fit or residual claim is made. |
| B9 | PASS: denominators are unique emitted ball rows per named clip. |
| B10 | PASS: no threshold or harness file changed. |

## NOT VERIFIED

- No post-change code was copied to or executed on the pod, per G45. The historical four clip tables do not contain input pixels or per-frame homographies, so the stored-coordinate replay cannot reconstruct the code's split between `beyond_vanishing_line` and `outside_physical_envelope` for each historical rejected row.
- The four premise videos are absent; the mandatory visual check uses preserved renders from the same current adapter on a sibling clip. It does not establish image-space classification for tennis_02 through tennis_05.
- This is a containment guard, not a ball detector, 3D trajectory estimator, or ground-plane-correct ball localization method.
- The verifier must re-run the single test and land this commit before it can validate the post-change runtime output on the pod.
