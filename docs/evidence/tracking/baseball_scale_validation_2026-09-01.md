# Baseball scale validation -- lane T5c: the rubber is the independent anchor, and 25 pct of segments survive

Date: 2026-09-01. Lane: T5c-BASEBALL-SCALE.
Verdict: **the px/ft can now be checked, and most of it does not pass.** A second,
independent landmark (the pitching rubber, 24 in) was added and differenced
against the mound chord at the same image row. Across the four T5b clips,
**9 of 36 pitch segments (25.0 pct)** and **73 of 332 pitch-view frames (22.0 pct)**
carry a scale two references agree on within 10 pct. Everything else is now
labelled `scale_status: unvalidated` and is still emitted unchanged. No existing
gate was loosened; no threshold was moved; this adds a column.

## 1. The design correction: the plate cannot be the 10 pct partner

The lane brief proposed comparing the mound-diameter scale against a
batter's-box width near the plate. Measured on the corpus, that comparison is
not like-with-like and would have been wrong:

* On a centre-field broadcast the mound images **below** home plate and ~60.5 ft
  **nearer** the camera, so its px/ft is legitimately larger. Measured on
  `mlb_2iosUkpL0Bc` frame 180: mound 43.4, plate 35.3 px/ft -- a real 1.23x
  depth ratio, not an error. A naive 10 pct gate on that pair would reject
  correct detections and would have to be widened until it gated nothing.
* The brief's "white pentagon at the bottom-centre" is the wrong location for
  this camera. In the centre-field view the plate is at the TOP of the pitch
  view, small (17 in ~ 50 px), and routinely occluded by catcher, umpire and
  batter.
* The batter's-box chalk is scuffed and asymmetric: on the frames inspected the
  left outer line survives and the right side does not, so a 10.42 ft
  box-to-box span is not measurable on real footage.

**The pitching rubber solves this.** It is 24 in wide, white against dirt, and it
sits ON the mound, so its px/ft is a horizontal scale at the SAME image row as
the chord. Two horizontal references at one depth compare like with like, and a
10 pct gate on them is a physical statement rather than a tuned one. Measured on
frame 180: chord 782 px -> 43.4 px/ft, rubber 86 px -> 43.0 px/ft, 0.9 pct apart.

The plate is still detected and still reported (`plate_px_per_ft`,
`perspective_ratio = mound/plate`), but it is **diagnostic only and never
vetoes**. An earlier revision let a ratio band veto; on real frames it rejected
frames whose rubber had already agreed, because the plate is the noisier of the
two detections. Letting the weaker detector overturn the stronger one was wrong,
and it is removed.

## 2. What was built

| file | role |
|---|---|
| `domains/baseball/tracking/plate_landmark.py` | landmark detection + the two-reference gate (282 LOC) |
| `domains/baseball/tracking/test_plate_landmark.py` | 7 synthetic-frame tests |
| `domains/baseball/tracking/adapter.py` | **additive**: per-frame and per-segment validation columns |
| `scripts/platformkit/tracking/teacher_emit.py` | **additive**: `scale_status` passes into `teacher_meta.json` |
| `scripts/platformkit/tracking/baseball_scale_probe.py` | the measurement + overlay renderer |

Emitted per frame: `plate_center_px`, `plate_width_px`, `plate_confidence`,
`rubber_px`, `rubber_width_px`, `rubber_confidence`, `box_corners`. Emitted per
frame and per segment: `scale_status`, `scale_reference_px_per_ft`,
`scale_disagreement`, `plate_px_per_ft`, `perspective_ratio`,
`scale_status_reason`. A segment is `validated` if ANY of its frames validated.

**Non-tautology.** The rubber search band bounds WHERE to look (inside the chord,
near the mound row, within 15 pct of the chord centre) and the shape filter
bounds flatness. Neither bounds how wide an accepted rubber may be. A width prior
would have guaranteed the agreement the gate exists to test -- the same defect
recorded in the `tautological_gates_2026_09_01` memory.

## 3. Measured on the four real clips (one local process, <= 600 frames each)

Window A: 600 processed frames at stride 3 = the first 1,800 source frames.

| clip | pitch-view frames | plate rate | rubber rate | frame agreement | segments | validated segments | segment agreement |
|---|---|---|---|---|---|---|---|
| `mlb_2iosUkpL0Bc` | 255 | **0.910** | **0.831** | 0.259 | 19 | 7 | **0.368** |
| `mlb_ARtRmUHC7dw` | 67 | 0.239 | 0.269 | 0.104 | 11 | 2 | **0.182** |
| `mlb_gMm3EODDb6w` | 0 | n/a | n/a | n/a | 0 | 0 | n/a |
| `mlb_3Oc4S_1np98` | 0 | n/a | n/a | n/a | 0 | 0 | n/a |

Window B, the two night games only, 600 processed frames at stride 20 = 12,000
source frames, to reach past the sampling problem rather than assume it away:

| clip | pitch-view frames | plate rate | rubber rate | segments | validated segments |
|---|---|---|---|---|---|
| `mlb_gMm3EODDb6w` | 1 | 0.000 | 0.000 | 1 | 0 |
| `mlb_3Oc4S_1np98` | 9 | 0.333 | 1.000 | 5 | 0 |

**Totals across both windows: 9 / 36 segments (25.0 pct) and 73 / 332 pitch-view
frames (22.0 pct) validated.** This confirms and quantifies the T5b warning: the
`METRIC_LOCAL` rung is reached on segments whose px/ft mostly cannot be
corroborated.

### Scale before vs after validation

| clip | median (all) | range (all) | median (validated) | range (validated) | median mound/plate ratio |
|---|---|---|---|---|---|
| `mlb_2iosUkpL0Bc` | 41.8 | 14.3 - 64.1 | **43.4** | **23.7 - 44.1** | 1.30 |
| `mlb_ARtRmUHC7dw` | 32.2 | 14.2 - 61.7 | **15.6** | **14.6 - 32.7** | 0.66 |
| `mlb_gMm3EODDb6w` (B) | 19.0 | 19.0 | none | none | n/a |
| `mlb_3Oc4S_1np98` (B) | 19.6 | 17.9 - 40.8 | none | none | 2.11 |

On `mlb_2iosUkpL0Bc` validation tightens a 4.5x spread (14.3-64.1) to 1.9x
(23.7-44.1) and moves the median onto the value the frame-180 hand-measurement
confirms. On `mlb_ARtRmUHC7dw` it does the opposite to the median (32.2 -> 15.6),
because that clip's camera is a wide third-base-side angle where a genuinely
small mound gives a genuinely small px/ft -- see frame 1176 below. Part of the
spread T5b flagged is real framing variation, not detector error, and the gate
now separates the two instead of assuming either.

## 4. Render-and-look: 11 overlays, all viewed

`docs/evidence/tracking/baseball_scale_validation_2026-09-01/` (red = mound
chord, yellow = rubber, cyan = plate, magenta = chalk/box corners; the verdict
and both scales are burned into each frame).

| overlay | verdict | what the eye confirms |
|---|---|---|
| `mlb_2iosUkpL0Bc_f000144_validated` | VALIDATED | chord on the true mound, yellow box on the true rubber; 43.4 vs 39.5 px/ft |
| `mlb_2iosUkpL0Bc_f000135_validated` | VALIDATED | same view, 43.4 vs 41.0 px/ft; the plate read (16.2) is poor and correctly does not veto |
| `mlb_2iosUkpL0Bc_f000765_validated` | VALIDATED | chord and rubber both correct; 44.0 vs 43.5 px/ft |
| `mlb_2iosUkpL0Bc_f000138_unvalidated` | **false negative** | chord IS on the true mound, but the pitcher's foot clips the rubber to 71 px -> 18.3 pct disagreement |
| `mlb_2iosUkpL0Bc_f000438_unvalidated` | correct reject | wide right-field view; the 880 px "chord" is the outfield dirt band, not the mound; 62.2 pct disagreement |
| `mlb_ARtRmUHC7dw_f000165_unvalidated` | correct reject | the 936 px "chord" is the second-base dirt band; 73.1 pct disagreement |
| `mlb_ARtRmUHC7dw_f000465_unvalidated` | correct reject | the 970 px "chord" is the infield dirt band; there is no mound in frame at all and no rubber found |
| `mlb_ARtRmUHC7dw_f001071_validated` | VALIDATED | chord on the true mound of a wide angle; 32.7 vs 31.5 px/ft |
| `mlb_ARtRmUHC7dw_f001176_validated_lowest` | VALIDATED | the 14.6 px/ft case: chord IS on a genuinely small, distant mound; rubber 16.0, agrees 9.6 pct |
| `night_stride20/mlb_3Oc4S_1np98_f003780_unvalidated` | correct reject | the 418 px "chord" is the home-plate dirt cut-out; 50.5 pct disagreement |
| `night_stride20/mlb_gMm3EODDb6w_f002160_unvalidated` | correct reject | night right-field view; the 342 px "chord" is the foul-line dirt strip; no rubber found |

Five distinct false-mound classes are rejected on frames rendered here --
outfield dirt band, second-base band, infield band with no mound in frame,
home-plate cut-out, and foul-line strip -- which covers the failure class the
T5b overlay flagged. Five correct accepts were confirmed by eye. The one
observed false negative is occlusion of the rubber by the pitcher, which fails
closed.

## 5. Honest limits -- what is NOT established

* **75 pct of segments are not corroborated, not refuted.** `unvalidated` means
  "no independent reference agreed", which mixes a wrong chord with a rubber
  that was occluded, out of frame, or unlit. `mlb_2iosUkpL0Bc` frame 138 is a
  measured example of the benign case. The rate of each is NOT measured.
* **Night games remain unusable.** Across 12,000 source frames each,
  `mlb_gMm3EODDb6w` yielded 1 pitch-view frame and `mlb_3Oc4S_1np98` yielded 9,
  none validated. This is the green-gate stadium-lighting failure T5b recorded,
  upstream of this lane; it is confirmed, not fixed.
* **The batter's box is not a working reference.** `box_corners` are emitted as
  chalk evidence only. No box-width scale is computed, because a full 4 ft box
  edge was not measurable on any frame inspected.
* **`detect_pitch_geometry` still accepts non-pitch views.**
  `mlb_ARtRmUHC7dw` frame 1176 is a live play, not a pitch. That is an upstream
  classification issue this lane did not touch.
* **No harness claim.** These clips still fail intake on `coordinate_contract`
  by design; nothing here changes the rung, the coordinate space, or any
  threshold. A `validated` scale is a corroborated pixel measurement, not a
  calibrated ground plane and not a homography.
* **Pod metadata is stale.** The 87 pod `teacher_meta.json` files predate the
  column and will read `scale_status: null` (the writer carries an absent value
  through as unknown rather than inventing one). **Daemon restart pending** --
  `domains/baseball/tracking/adapter.py` is shared with the running
  `track_daemon`, which will keep emitting the old shape until it is restarted.
  The change is additive, so the old shape stays valid meanwhile.
* Player counts in the wiring check used a stub detector; no YOLO ran.

## Reproduce

```
python -m pytest domains/baseball/tracking/test_plate_landmark.py -q
python -m scripts.platformkit.tracking.baseball_scale_probe \
  data/videos/bridge/mlb_2iosUkpL0Bc.mp4 data/videos/bridge/mlb_ARtRmUHC7dw.mp4 \
  --out-dir docs/evidence/tracking/baseball_scale_validation_2026-09-01 \
  --max-frames 600 --stride 3 --overlays 4
python -m scripts.platformkit.tracking.baseball_scale_probe \
  data/videos/bridge/mlb_gMm3EODDb6w.mp4 data/videos/bridge/mlb_3Oc4S_1np98.mp4 \
  --out-dir docs/evidence/tracking/baseball_scale_validation_2026-09-01/night_stride20 \
  --max-frames 600 --stride 20
```

Related: `docs/evidence/tracking/baseball_footage_acq_2026-09-01.md` (the corpus
and the untrustworthy-scale finding this lane acted on).
