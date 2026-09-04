# G254: Refine the published WNBA seed against detected edges, then measure its basin

## Verdict

**ACCEPT (measurement-only warning): on one G233d gate-passed seed, the fixed G252 reporting metric changes from pooled found-candidate median/p90 5/18 px to 4/17 px after edge-based matrix refinement, but the refined court FAILS the independent hard eye gate. The fixed basin is narrow: 13/43 starts return to the same detector-fit answer, and zero non-identity joint translate/rotate/scale starts do.** The apparent numerical reduction therefore does not establish a better calibration. It is an edge-detector fit, and the painted-end/arc render is the gate.

**Hard eye gate (n=1 refined court, 1 frame, 1 seed, 1 clip, 1 arena): FAIL -- the refined end baseline/free-throw-area geometry is visibly displaced above the painted end markings, and the three-point arc is no longer a clean independent painted-line match.** See the [refined overlay](g254_projection_refinement_and_basin_artifact/refined_overlay.jpg).

This follows the [verifier contract](VERIFIER_CONTRACT.md). It changes no production code, label, threshold, court model, coordinate contract, daemon, keeper, corpus source, `src/`, or `domains/` file.

## Lane check, disk guard, and exact inputs

This ran on the pod because the full-resolution source is readable there and was kept read-only. Immediately before final launch on 2026-09-04 at about 07:10 -05:00, the executable-and-complete-argument process check excluded its own `python3` checker PID 3007766 and parent PID 3007763. Its only non-checker match was permanent `scripts.platformkit.track_daemon` PID 33064; no G253 or other measurement worker was active or interrupted. The durable timing bracket is the pre-score protocol timestamp 07:09:20 -05:00 and final render timestamp 07:11:24 -05:00.

`df` was not used. A preflight `dd conv=fsync` probe first recorded `du -sm /workspace/nba-ai-system/data` = 33112 MB and removed its 1,048,576-byte probe. The route repeated the required probe immediately before its worker wrote output: 33117 MB and another 1,048,576-byte probe removed. The worker stream-decoded the one frame, retained 94,103-byte JSON plus a 657,464-byte render only in `/tmp/g254_refine_*`, copied both committed artifacts, and removed that directory: 751,567 bytes. Known temporary bytes freed are **2,848,719**. No corpus source or `footage_bridge` partial was deleted.

| Input opened | Full path | Bytes | Role |
|---|---|---:|---|
| Source video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080, frame 19599, read-only |
| Published seed | `docs/evidence/tracking/g233d_seed_gate_validated_frame_artifact/g233d_measurement.json` | 4,472,890 | SHA-256 `89b4fa628f380d8a065ba374f60683a5146ce0996fe8b23d742433e2f8fbbd34`; G233d's published image-to-court matrix only |
| G252 machinery | `scripts/platformkit/tracking/g252_projection_accuracy_in_pixels.py` | 13,989 | SHA-256 `0f1ea9e2b7d6ac9636bdcde50fc2c5cd139f1a734eaa083939d91f0c78d968af`; geometry and reporting constants reused |

The streamed native-BGR frame SHA-256 is `686c94a7738c3e1ede2b39ea98cb09f096eead96826ff543baf4585d4c8f4270`, matching G233d's published decode. Decode was `ffmpeg -i VIDEO -vf select=eq(n,19599) -vsync 0 -frames:v 1 -f rawvideo -pix_fmt bgr24 pipe:1`; there was no input-side seek and no full decode written to disk.

## Frozen method, before outcomes

The [pre-score protocol](g254_projection_refinement_and_basin_artifact/g254_protocol.md) (1,956 bytes, SHA-256 `369b14ec393db7cdce8b982f6c47429c470b591197d319628cdb483b8eea546e`) was written at 07:09:20 -05:00, before the final render/measurement. It froze the objective, detector settings, convergence rule, equality rule, and all 43 starts; none changed after the gate.

The matrix, not the four G233d labels, was refined. I inverse-projected G252's fixed WNBA curves from the published G233d image-to-court matrix and left-multiplied its forward court-to-image map by a four-parameter image-space similarity `(tx px, ty px, degrees, log-scale)`. The objective is the mean, equally weighted across visible line types, of squared `min(Canny distance-transform distance at a projected 4-px sample, 24 px)`. It uses fixed Canny low/high 50/150, 3x3 aperture, and L2 gradient. A deterministic coordinate pattern search started at `(8, 8, 0.75, 0.005)`, tried signed coordinate steps in fixed order, halved a failed sweep, and converged when steps reached `(0.0625, 0.0625, 0.005859375, 0.0000390625)` (absolute bounds 192 px, 192 px, 12 degrees, and 0.20; maximum 240 iterations).

The resulting correction is `(-2.0 px, -23.75 px, +0.1875 degrees, -0.0009375 log-scale)`, after 114 objective evaluations and 16 iterations; the final fitted objective is 176.710160 squared-pixel units. This fitted objective and its residual are not correctness evidence. Canny edges can be wrong, absent, or belong to crowd rails, bench lines, floor logos, or other non-court structure. That is why the independent arc, sidelines, and painted-end eye gate above controls the result.

For reporting only, before and after use **G252's exact normal-search method**: 4-px visible projected samples; integer normal offsets -24 through +24 px; minimum absolute Canny-edge offset. `Found` is conditional on a candidate; `No candidate` is retained and is never read as a small offset. A found 24 px is right-censored; offsets larger than the 24-px search cannot be distinguished.

## G252-compatible offsets, one G233d seed frame

| Line type | Before samples | Before found | Before no candidate | Before median | Before p90 | Before max | After samples | After found | After no candidate | After median | After p90 | After max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sideline | 13018 | 50 | 12968 | 7.5 | 18.1 | 23.0 | 13008 | 57 | 12951 | 5.0 | 18.4 | 24.0 |
| baseline | 725 | 459 | 266 | 3.0 | 11.0 | 24.0 | 724 | 456 | 268 | 3.0 | 10.0 | 23.0 |
| lane boundary | 324 | 214 | 110 | 5.0 | 17.7 | 24.0 | 324 | 216 | 108 | 4.0 | 14.0 | 24.0 |
| free-throw line | 650 | 351 | 299 | 6.0 | 22.0 | 24.0 | 650 | 421 | 229 | 3.0 | 17.0 | 24.0 |
| arc | 932 | 701 | 231 | 5.0 | 18.0 | 24.0 | 925 | 664 | 261 | 7.0 | 20.0 | 24.0 |
| centre circle | 0 | 0 | 0 | - | - | - | 0 | 0 | 0 | - | - | - |
| pooled | 15649 | 1775 | 13874 | 5.0 | 18.0 | 24.0 | 15631 | 1814 | 13817 | 4.0 | 17.0 | 24.0 |

The pooled found-candidate summary improves by one pixel at median and p90, and the free-throw/lane buckets improve, but arc median/p90 worsen from 5/18 to 7/20 px. More importantly, the hard gate FAILS. It would be wrong to call this an improved court merely because the detector objective or pooled conditional offset moved.

## Basin of convergence

Before outcomes, `same answer` was fixed as p95 <= 2 px on all reference-refined in-image points of a 5-ft court grid. The reference had 68 such points. This is a projected-court discrepancy, not a fitted residual: it compares the unperturbed refined forward matrix with the separately refined trial matrix at the fixed grid. Two pixels is much tighter than the 24-px reporting search but allows subpixel/raster variation.

The full frozen table follows. Translation is the stated pixel offset of the projected court; scale is about the 1920x1080 image centre. Every row reran the same refinement, not an evaluation of its start.

| Start | Family | tx | ty | degrees | scale | grid points | p95 px | Same answer |
|---|---|---:|---:|---:|---:|---:|---:|---|
| identity | identity | 0 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_-1_8 | translation | -8 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_-1_16 | translation | -16 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_-1_32 | translation | -32 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_-1_64 | translation | -64 | 0 | 0.0 | 1.000 | 68 | 72.994 | NO |
| translate_x_+1_8 | translation | 8 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_+1_16 | translation | 16 | 0 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_x_+1_32 | translation | 32 | 0 | 0.0 | 1.000 | 68 | 41.578 | NO |
| translate_x_+1_64 | translation | 64 | 0 | 0.0 | 1.000 | 68 | 70.920 | NO |
| translate_y_-1_8 | translation | 0 | -8 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_y_-1_16 | translation | 0 | -16 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_y_-1_32 | translation | 0 | -32 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_y_-1_64 | translation | 0 | -64 | 0.0 | 1.000 | 68 | 81.927 | NO |
| translate_y_+1_8 | translation | 0 | 8 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_y_+1_16 | translation | 0 | 16 | 0.0 | 1.000 | 68 | 0.000 | YES |
| translate_y_+1_32 | translation | 0 | 32 | 0.0 | 1.000 | 68 | 138.064 | NO |
| translate_y_+1_64 | translation | 0 | 64 | 0.0 | 1.000 | 68 | 98.344 | NO |
| rotation_-8.0 | rotation | 0 | 0 | -8.0 | 1.000 | 68 | 136.070 | NO |
| rotation_-4.0 | rotation | 0 | 0 | -4.0 | 1.000 | 68 | 140.661 | NO |
| rotation_-2.0 | rotation | 0 | 0 | -2.0 | 1.000 | 68 | 1.871 | YES |
| rotation_-1.0 | rotation | 0 | 0 | -1.0 | 1.000 | 68 | 3.885 | NO |
| rotation_-0.5 | rotation | 0 | 0 | -0.5 | 1.000 | 68 | 1.871 | YES |
| rotation_+0.5 | rotation | 0 | 0 | 0.5 | 1.000 | 68 | 3.885 | NO |
| rotation_+1.0 | rotation | 0 | 0 | 1.0 | 1.000 | 68 | 16.972 | NO |
| rotation_+2.0 | rotation | 0 | 0 | 2.0 | 1.000 | 68 | 18.581 | NO |
| rotation_+4.0 | rotation | 0 | 0 | 4.0 | 1.000 | 68 | 97.266 | NO |
| rotation_+8.0 | rotation | 0 | 0 | 8.0 | 1.000 | 68 | 191.957 | NO |
| scale_0.900 | scale | 0 | 0 | 0.0 | 0.900 | 68 | 79.286 | NO |
| scale_0.950 | scale | 0 | 0 | 0.0 | 0.950 | 68 | 60.904 | NO |
| scale_0.975 | scale | 0 | 0 | 0.0 | 0.975 | 68 | 41.709 | NO |
| scale_1.025 | scale | 0 | 0 | 0.0 | 1.025 | 68 | 28.700 | NO |
| scale_1.050 | scale | 0 | 0 | 0.0 | 1.050 | 68 | 35.558 | NO |
| scale_1.100 | scale | 0 | 0 | 0.0 | 1.100 | 68 | 109.563 | NO |
| joint_-1_8 | joint | -8 | -8 | -0.5 | 0.990 | 68 | 13.959 | NO |
| joint_-1_16 | joint | -16 | -16 | -1.0 | 0.980 | 68 | 8.297 | NO |
| joint_-1_32 | joint | -32 | -32 | -2.0 | 0.960 | 68 | 148.803 | NO |
| joint_-1_64 | joint | -64 | -64 | -4.0 | 0.920 | 68 | 185.228 | NO |
| joint_-1_96 | joint | -96 | -96 | -6.0 | 0.880 | 68 | 234.143 | NO |
| joint_+1_8 | joint | 8 | 8 | 0.5 | 1.010 | 68 | 3.866 | NO |
| joint_+1_16 | joint | 16 | 16 | 1.0 | 1.020 | 68 | 36.523 | NO |
| joint_+1_32 | joint | 32 | 32 | 2.0 | 1.040 | 68 | 91.138 | NO |
| joint_+1_64 | joint | 64 | 64 | 4.0 | 1.080 | 68 | 226.799 | NO |
| joint_+1_96 | joint | 96 | 96 | 6.0 | 1.120 | 68 | 232.737 | NO |

The largest successful individual translations are 32 px in the negative x and negative y directions; positive x/y each stop at 16 px. The largest successful rotation is -2 degrees, but the nonmonotonic -1/-0.5 outcomes show there is no single rotational radius. No tested scale perturbation returns to the same answer. Most importantly, the largest successful member of the precommitted joint ladder is **identity only**: even 8 px x/y, 0.5 degrees, and 1 percent scale does not return within 2 px. This is a narrow, irregular local basin, not a wide approximate-start result.

## Narrow automatic-calibration implication

On this one frame only, an automatic starting homography would need to be much closer than the smallest tested joint perturbation: it cannot be assumed to recover a simultaneous 8-px x/y translation, 0.5-degree rotation, and 1-percent scale change under this frozen objective. Isolated translations sometimes return from 16-32 px, but even 2.5-percent isolated scale changes and every nonidentity joint start fail the 2-px rule. The implication is narrow and negative: refinement cannot presently be treated as a rescue for a rough automatic guess on this frame. This does **not** demonstrate automatic calibration; it remains 0/17.

This is one frame, one hand-labelled seed, one clip, and one arena. A basin on one frame is not a property of the method or footage class. The same caveats apply to the Canny edge detector: it can select non-court structures or miss paint, and the 24-px search censors larger offsets. Eye-label reliability has not cleared 80 percent blind agreement on any of the programme's four measured criteria, and G246 showed repeatable labels can be uniformly wrong.

## Verification, cleanup, and NOT VERIFIED

The final [measurement artifact](g254_projection_refinement_and_basin_artifact/g254_measurement.json) is 99,549 bytes, SHA-256 `4c2e1de5598d09030f04348f265b114b82852af79ad05d9ea0d3117115c47762`; it retains the seed/refined matrices, raw normal-search values and summaries, all 43 starts, final parameters, objective convergence information, code hashes, and disk guard. The [refined overlay](g254_projection_refinement_and_basin_artifact/refined_overlay.jpg) is 657,464 bytes, SHA-256 `d07fa9a5b7b7a5ccf1b3056038432b9bb374a387e180b4431f88c3a16a6ee82b`. The evidence route is `scripts/platformkit/tracking/g254_projection_refinement_and_basin.py`, 16,108 bytes, SHA-256 `f70623bfffcb34d7631da6a9c3298ec6e362ba4bf1320aa5f38c125276486bc5`.

Focused test (no full suite):

```text
python -m pytest scripts/platformkit/tracking/test_g254_projection_refinement_and_basin.py -q -p no:cacheprovider
3 passed; one non-measurement invalid-escape warning from compiled worker source
```

Self-check: A7 final evidence paths exist. B1 retains every in-image projected sample and names every no-candidate count; no row is excluded. B2-B6 change no schema, lifecycle, deployment, production module, or moved module. B7 does not head-slice: n=1 is the complete stipulated one-frame decision set and its sole gate render is retained. B8 is explicit: the fit residual/objective is not independent evidence; the independent render failed. B9 names the one-frame, per-line sample, 43-start, and 68-grid-point denominators. B10 moves no inherited threshold, model, matcher, or gate. B11: this is a one-run, environment-stamped measurement, not a system property. Q does not apply to this tracking measurement row. A12 does not apply: the new non-test route is 177 lines, below the 300-line rail.

**NOT VERIFIED:** a valid refined calibration; whether any detected edge is paint; offsets beyond 24 px; another seed/frame/clip/arena/camera/sport; a different detector or optimiser; repeatability of the one eye gate; a smooth or global basin; automatic calibration; label ground truth; a validity signal; and any production change.
