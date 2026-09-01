# SynthCal Wave 7 tennis verdict -- 2026-09-01

## VERDICT: FAIL

The Wave 7 refine did not converge and never produced a checkpoint. Its own
pre-registered save gate (`/tmp/synthcal_wave7_refine.py` line 83:
`if pck>.90: torch.save(...)`) was not met: `steps=20000, converged=false,
synthetic_val_pck_at_7px=0.129821` (`/tmp/synthcal_refine_run.log`, finished
23:09 UTC; summary copied here as `synthcal_w7_verdict_2026-09-01/synthcal_wave7_refine.json`).
`data/models/synthcal_tennis_wave7.pt` does not exist on the pod. The only
weights on disk are v1, `data/models/synthcal_tennis.pt`
(mtime 2026-09-01 18:55:16 UTC, 1,886,325 bytes), trained BEFORE Wave 7.

Failure mode: NON-CONVERGENCE ON ITS OWN SYNTHETIC DISTRIBUTION. A 0.13 PCK@7px
on the model's own rendered validation set means the W7 recipe (decoy lines,
non-court background plates, hue/lighting jitter, narrow behind-baseline prior,
465k-param heatmap net, batch 10) could not even fit synthetic frames; the
real-frame appearance gap diagnosed in the earlier render-and-look was never
reached. No real-frame number can be attributed to Wave 7.

## Calibration anchor (required before any verdict) -- REPRODUCED

`scripts/platformkit/tennis_resolution_anchor_ab.py <video> --variant endpoint --seconds 180`
(held-out right service T at (60,18) ft, 0.1 s samples), run on two machines:

| arm | machine | median ft | p95 ft | n | target |
|---|---|---:|---:|---:|---|
| classical endpoint, nyYk 720p | pod (script copied to /tmp/synthcal_judge2, TENNIS_MEASURE_PROJECT_ROOT set) | 5.280 | 21.847 | 259 | 5.28 +/- 0.15 |
| classical endpoint, nyYk 720p | local, committed HEAD | 5.280 | 21.847 | 259 | 5.28 +/- 0.15 |
| classical endpoint, tennis_07 | pod | 17.867 | 27.840 | 28 | (not the anchor; n<30, provisional) |

The instrument reproduces the anchor exactly, so a verdict is permitted.
The pod's `/tmp/tennis_720_endpoint.json` (median 395 ft, n=2) is the
discredited 0.8-second run and is not evidence.

## Four-number contract -- measured on v1 (the only checkpoint that exists)

Emitter run with the CORRECT flags (`--frames-per-video 60 --device cuda`,
`--confidence 0.0`), 60 decoded frames per video (linspace over the whole
video), judge `tennis_calib_eval --min-overlays 10`. Reports:
`synthcal_w7_verdict_2026-09-01/report_v1_*.json`.

| video | decoded | rows | frames_valid | (a) PCK@7px 1280x720 | (b) depth-band median ft: near / mid / far | (c) court scale max abs pct (gate <= 3) | judge |
|---|---:|---:|---:|---|---|---|---|
| nyYk2nPZAwY_720p | 60 | 59 | 57 | 0.4035 (n=570) | 28.87 (n=171) / none (n=0) / 29.39 (n=171); p95 278.5 / - / 487.1 | length 51,423.8 (median -1.68); singles width 148,719.1 (median +82.3) -> FAIL | REJECT |
| tennis_07 | 60 | 59 | 59 | 0.3949 (n=590) | 34.21 (n=177) / none (n=0) / 29.10 (n=177); p95 584.7 / - / 291.7 | length 3,668.4 (median -5.93); singles width 15,287.2 (median +134.6) -> FAIL | REJECT |

Reading (a) honestly: the judge's PCK numerator includes the four doubles-corner
SOLVE landmarks, which reproduce themselves through the 4-point homography at
0 px. 4 of 10 landmarks per frame = a 0.40 floor; the held-out six contribute
about 2 of 230 hits on nyYk. Held-out PCK@7px is effectively 0.

(b) v1 depth-band error is ~29-34 ft median against the classical 5.28 ft:
5.5x-6.5x WORSE than the ceiling it was meant to beat.

(d) Render-and-look: 6 overlay frames viewed with the Read tool, in
`synthcal_w7_verdict_2026-09-01/`:

| frame | content | lines on lines? |
|---|---|---|
| v1_nyYk_f00000_wide.jpg | wide court, near+far visible | NO -- court rectangle drawn across the far stands/backdrop, keypoints in the scoreboard |
| v1_nyYk_f00814_wide_high.jpg | high wide angle | NO -- rendered court displaced onto the far half and stands, wrong scale |
| v1_nyYk_f03257_graphic_noncourt.jpg | full-screen stats graphic | NO -- confident tiny court on a graphic; no court/no-court discrimination |
| v1_t07_f00000_near_closeup.jpg | near-court close-up of a player | NO -- court drawn over the back wall and scoreboard |
| v1_t07_f00255_wide.jpg | wide court, near+far visible | NO -- degenerate pencil of lines converging above the far baseline |
| v1_t07_f00639_near_closeup.jpg | near-court close-up | NO -- court drawn over the crowd and the ROLEX board |

Lines are on lines in 0 of 6 frames. Same class as the Wave 7 pre-training
diagnosis (A -- appearance gap): maxima attach to broadcast graphics, stands,
and players, not to court geometry.

## Consequence (per .planning/NOW.md T0 contract)

- Classical 5.28 ft median / 21.85 ft p95 (n=259) STANDS as the tennis
  registration ceiling.
- Soccer and basketball synthcal training are NOT queued.
- Per-sport pivot to teacher / image_px lanes (T1 vertical-line lever for
  tennis; T2/T3 as already sequenced behind T0).

## Landmines recorded

- Watcher defect: `/tmp/synthcal_autoJudge.sh` wrote `/tmp/synthcal_verdict/COMPLETE`
  after BOTH stages failed (emitter: `unrecognized arguments: --max-frames 900 --stride 15`;
  judge: `FileNotFoundError` on the missing jsonl), and it hard-coded the v1
  weights path rather than the W7 output path. There is no repo copy of the
  watcher; the repo consumer `scripts/platformkit/ops_healthcheck.py` now
  reports `complete` only when `COMPLETE` AND at least one `*_report.json`
  exist (`SYNTH_VERDICT_REPORTS`), with a per-file test.
- `tennis_calib_eval` PCK@7px counts solve landmarks; with 10 landmarks and a
  4-point solve it has a 0.40 floor. Read depth-band and scale, not PCK, until
  the judge excludes `solve_landmarks` from `pixel_convention` (harness change,
  not made here).
- Pod checkout lags local HEAD: `domains/tennis/tracking/adapter.py` on the pod
  predates the camera-lock commit, and `tennis_resolution_anchor_ab.py` is
  absent there. The anchor helpers it uses were unchanged, and the pod and local
  runs agree to the last digit.

## Not verified

- Wave 7 network real-frame behaviour: cannot be measured, no weights were saved.
- tennis_07 classical arm is n=28 (< 30): provisional, informational only.
- No mid-band landmarks exist in the judge's 10-landmark set (mid n=0 is
  structural, not a detection failure).

Pod jobs used: `/tmp/synthcal_judge2/` only; nothing killed; daemon pid file untouched.
