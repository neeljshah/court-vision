# Tennis camera-lock coverage: the vertical-line lever (2026-09-01)

Footage: `data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4` (1280x720, 50 fps,
48048 frames; byte-identical copy of the pod file, 274,423,923 bytes). Harness:
unedited `scripts/platformkit/tracking_harness.py`, SHA-256
`93cf19288bc45e1c3b459337085934d2e14e21a244a0251f739d33f97226dde6`. Measurement
script: unedited `scripts/platformkit/tennis_camera_lock_measure.py`, plan
`--linspace 0 48047 600`, denominator = decoded manifest rows (599).

## Step 0: premise check (the stated symptom was a content artifact)

The stated symptom was "dead sections show 0-1 vertical lines vs the >=2 gate while
~10 horizontals detect". Measured with `scripts/platformkit/tracking/tennis_vertical_probe.py`
(`probe_before2/vertical_probe.json`, contact sheets `*_sheet.png`):

| section (source frames, n) | content (viewed) | prod verticals (median) | first gate |
|---|---|---:|---|
| doc_dead 3816-4565 step 25, n=30 | player close-up + graphic overlay, NOT a court view | 2 | insufficient_oriented_lines 13, vertical_cluster_count 17 |
| dead1 15300-15600 step 10, n=31 | main camera, hard shadow | 15 | vertical_cluster_count 31/31 (4 vertical clusters, 3 horizontal) |
| dead3 29700-30000 step 10, n=31 | main camera, hard shadow | 13 | vertical_cluster_count 31/31 (4 vertical, 1-2 horizontal) |
| dead4 34500-34800, n=31 | player close-up, NOT a court view | 3 | insufficient_oriented_lines / vertical_cluster_count |
| live1/live2/live3 | main camera | 16 | accepted 19-31 of 31 |

So the documented 3816-4565 window is unsolvable by any detector (no court in view);
the >=2 orientation gate is NOT the wall on court views. On court-view dead shots
verticals are abundant; the frame dies at the exactly-five-cluster rule because ONE
length line (the right doubles sideline, lying in the shadow) and one or two
horizontals (near service line, baselines) are missing from the brightness mask.

## Root cause (measured, `probe_before2/*.png`, cluster dump in session log)

`cv2.inRange(frame, 200..255)` never contains a court line inside the hard shadow that
covers half of many main-camera frames: at f15300 the vertical clusters were
[262, 355, 629, 901] (right doubles sideline at ~995 absent), horizontal clusters
[211, 282, 562] (near service line at ~440 absent). Raw LSD on grayscale saw those
lines (cyan in `probe_before2/dead1_f015300.png`). Two compounding solver defects
were also measured on this footage:

1. `len(vertical_clusters) != 5 -> reject`: richer evidence (top-hat, LSD) yields MORE
   clusters, so it accepted 0 of 186 court frames under the old rule (`mask_ab.json`).
2. Ordinal horizontals (`horizontal_clusters[0]` = far baseline): on accepted frames the
   "far baseline" was the scoreboard graphic (row 38) and the "near service line" the
   net; held-out service-T error on the old accepts was median 42.65 ft, p95 43.54 ft,
   n=101 (`evidence_selection_ab.json`, `OLD_bright`). Coverage was coverage of wrong
   homographies, which is why the frozen harness failed on oob (0.213) and jump_p95.

## Fix (root, one module, all callers): `domains/tennis/tracking/court_lines.py`

- Evidence: white top-hat (thin AND brighter than surroundings; kernel 11 px at 720p,
  scaled by height) instead of absolute brightness; the same HoughLinesP parameters.
- Vertical roles: the 5-subset of vertical clusters whose TWO cross ratios match the
  court (567/486 and 486/425.25), tolerance 0.05 unchanged, instead of exactly five.
- Horizontal roles: templates along the centre line by cross ratio, bounded by the
  court's own structure (sidelines end at the baselines; the centre line ends at the
  service lines, one-sided so a player standing on it cannot break it).
- Independent fifth correspondence: the far-right corner predicted by the 4-anchor
  homography must land within 2% of frame width of the observed far/right intersection.
- Evidence cascade: contrast 45 first, then 60; each pass faces the same strict gates.
- Callers: `adapter.detect_court_corners`, `court_diagnostics.rejection_gate` /
  `held_out_service_t_error`, `camera_lock.detected_intersections` (drift evidence).

No harness threshold, gate tolerance, or >=2 orientation rule was loosened.

## Same-frame A/B on the sections above (`evidence_selection_ab_v3.json`)

Pooled court-view sections, n=186 frames (dead1, dead3, live1, live2, live3, dead5):

| detector | accepted | held-out service-T ft median / p95 (n) |
|---|---:|---|
| old (bright mask, exactly-5, ordinal) | 101 | 42.65 / 43.54 (101) |
| new, contrast 45 only | 129 | 0.28 / 0.78 (129) |
| new, contrast 60 only | 74 | 0.34 / 0.73 (73) |
| new, cascade 45 then 60 (shipped) | 161 | 0.30 / 0.80 (161) |

Non-court sections (n=92): old 0 accepts; new 2, both verified by eye to be genuine
court frames at the start of the mixed section (`false_accept_dead2_f017300.png`).

Caveat: the held-out service T is now partly selected by the same projective invariant
that the solver uses, so it is a consistency check, not an independent accuracy number.
The independent checks are the far-right corner gate and the frozen harness below.

## End-to-end, frozen harness, same denominator

See `baseline_local/` (unchanged code, reproduces the pod result exactly: 61/599 =
0.1018, harness FAIL) and `after_local_final/`. Numbers in the table below are copied
verbatim from the two `summary.json` and `frozen_harness.txt` files.

| measure (600-row linspace plan, 599 decoded) | before (`baseline_local`) | after (`after_local_final`) |
|---|---:|---:|
| raw accepts (`detect_court_corners` returned corners) | 60 | 135 |
| fresh solves (`solved` provenance) | 50 | 107 |
| locks formed | 5 | 18 |
| drift-checked reuses (`camera_lock_drift_checked`) | 11 | 12 |
| drift rejects (`unsolved_drift`) | 1 | 2 |
| solved-frame coverage (fresh + drift-checked reuse) / decoded | 61 / 599 = 0.1018 | 119 / 599 = 0.1987 |
| reuse drift residual px p50 / p95 / max (n) | n/a | 0.85 / 4.82 / 11.84 (120) |
| frozen harness exit code | 1 (FAIL) | 1 (FAIL) |
| harness failures | median_track_len 2.00 < 3.00; oob 0.21 > 0.08; jump_p95 10.96 > 8.00; ball_valid 0.06 < 0.20 | oob 0.18 > 0.08; jump_p95 22.29 > 8.00; ball_valid 0.18 < 0.20 |

Harness verdict: still FAIL. median_track_len now passes (3.0), oob improved 0.213 -> 0.176,
ball_valid 0.056 -> 0.176; jump_p95 got WORSE (10.96 -> 22.29). On this plan consecutive
manifest rows are ~80 source frames (1.6 s) apart and the harness has no time base, so a
larger solved run yields more 1.6 s player displacements counted as "jumps"; whether the
jump number is a plan artifact or a geometry defect is measured separately on a
sequential range below, not asserted.

Remaining headroom: `unsolved_after_sheet.png` samples every 8th still-unsolved plan row
(60 of 480). By eye, 6-7 of those 60 are main-camera court views (about 10%); the rest are
close-ups, graphics, crowd and stadium shots that no court solver can register. So the
content ceiling of this plan is roughly 0.28 and the after-fix 0.1987 sits near it;
this is an eyeballed estimate from a 60-tile sample, not a measured label set.

## Sequential range (time-adjacent rows) and the 1080p positive control

Same script, `--range` plans, after-fix code. Verbatim from `summary.json` / `frozen_harness.txt`.

| measure | `after_sequential_15300_15600` (nyYk 720p, the dead1 shot) | `control_1080p_tennis09` (range 5050-5120, the honest doc's 1080p control) |
|---|---:|---:|
| decoded | 301 | 71 |
| raw accepts | 198 | 60 |
| fresh solves | 187 | 56 |
| locks formed | 12 | 9 |
| drift-checked reuses | 83 | 2 |
| drift rejects | 2 | 0 |
| solved-frame coverage | 270 / 301 = 0.8970 | 58 / 71 = 0.8169 (was 5 / 71 = 0.0704) |
| reuse drift px p50 / p95 / max (n) | 1.12 / 4.72 / 6.40 (272) | 4.02 / 8.69 / 12.29 (58) |
| frozen harness | exit 0, `passed: true`, failures [] | exit 0, `passed: true`, failures [] |
| harness metrics | median_track_len 10.0, ball_valid 0.6889, jump_p95 0.78, oob 0.013 | median_track_len 58.0, ball_valid 0.4828, jump_p95 1.08, oob 0.0 |

This shot was 0 / 31 accepts under the old detector (`probe_before2`). With time-adjacent
rows the jump_p95 is 0.78 ft and oob 1.3%, so the 22.29 ft jump on the linspace plan is
the plan's 1.6 s row spacing, not solver geometry. `liveness_verdict` stays UNCALIBRATED
in every run (no source time base is declared); that is unchanged from before.

## Review caveats (cv-code-reviewer, APPROVE-WITH-NITS)

- `camera_lock.detected_intersections` now sees top-hat evidence: on a probed 6 px true
  shift the old mask rejected (n=4, 5.36 px) and the new accepts (n=6, 4.76 px); the
  residual still tracks true drift, but the effective ceiling sits near 6 px rather than
  the nominal 5.0, so part of any reuse-coverage gain is measurement sensitivity.
- `held_out_service_t_error` is now conditioned on frames where the far service line was
  detected (5-line template); it is not comparable to pre-diff held-out numbers.
- The five platformkit probe scripts (`tennis_gate_funnel`, `line_detector_ab`,
  `tennis_threshold_sweep`, `tennis_resolution_anchor_ab`, `tracking/tennis_vertical_probe`)
  re-implement the OLD solver for measurement; their funnel numbers describe dead code.

Overlays (viewed): `overlays_after/*.png` (dead1 f15450, dead3 f29900, live1/2/3, the
mixed-section court frame, and two close-ups correctly rejected as
`insufficient_oriented_lines`), `probe_before2/*.png` (before).
