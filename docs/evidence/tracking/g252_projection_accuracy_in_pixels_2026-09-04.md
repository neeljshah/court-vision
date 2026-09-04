# G252: Pixel offset of eye-valid projected court markings

## Verdict

**ACCEPT (measurement only): the eye-valid-but-not-pixel-accurate hypothesis is SUPPORTED on this restricted measurement.** On the 27 inherited G244 VALID frames, the nearest detected strong-edge candidate is a median **5 px** from the projected marking, with p90 **19 px**, within a 24-px normal search. Those offsets are not near zero. An eye check at overlay scale can therefore tolerate pixel error that a pixel-precise image statistic cannot see.

This is a magnitude measurement, not a validity signal. It does not reopen G242/G244/G247/G248's closed separation question, fit a threshold, propose a gate, or alter production behavior. The 24-px bound censors every true offset beyond it, and a no-candidate result can mean either no strong edge or an offset beyond the bound. It must never be read as a small offset.

## Lane check, source, and disk guard

This ran on the pod because the named full-resolution source video is present there read-only. At **2026-09-04 06:49:19 -05:00**, I checked processes by executable and complete argument, explicitly excluding the checker process and its parent. There was no active measurement row: the seven matched processes were permanent residents (the trading auto loop and paper runners, `inplay_capture_runner`, `ingame_paper_settle`, and `foundry_runner`). Nothing was interrupted.

`df` was not used. Before the worker wrote its temporary JSON, `du -sm /workspace/nba-ai-system/data` was **33101 MB**. The required command `dd if=/dev/zero of=/workspace/nba-ai-system/g252_disk_probe.bin bs=1M count=1 conv=fsync status=none` passed; its 1,048,576-byte probe was then removed. The stdin worker created one 2,296,145-byte temporary JSON, which was copied into this committed artifact and removed from the pod. Total temporary bytes freed were **3,344,721**. No corpus source, G242 artifact, or either abandoned `footage_bridge` partial was deleted.

| Input opened | Full path | Bytes | Resolution / role |
|---|---|---:|---|
| Source video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080, 174,430 declared frames; read-only full-resolution pixel input |
| Blind labels | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g244_blind_validity_labels_2026-09-04.csv` | 8,114 | Fixed 89-row G244 labels; SHA-256 `c95071bc687eaff41b30dc46d635f4a835421a3f16e117a7988c6547cfbfdadf` |
| Persisted maps | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g247_projected_quad_validity_artifact\g247_measurement.json` | 142,822 | Fixed 89 G247 image-to-court matrices; SHA-256 `05be8b9d4b71c2f865683c4cf6d498b0997ad6108681414ae2e29f88ad37b87b` |

The G242 960x540 overlays were not image input. The [measurement artifact](g252_projection_accuracy_in_pixels_artifact/g252_measurement.json) is 2,432,356 bytes, SHA-256 `31a33f64308ef67d1bb249908ee7adfdd80c2f4b616dc4425d57a11422c997b2`; it retains all per-frame, per-line-type found distances and no-candidate counts. The local route was [g252_projection_accuracy_in_pixels.py](../../../scripts/platformkit/tracking/g252_projection_accuracy_in_pixels.py), SHA-256 `0f1ea9e2b7d6ac9636bdcde50fc2c5cd139f1a734eaa083939d91f0c78d968af`; it was transmitted as stdin code only, not deployed or copied to the pod.

## Decode and fixed measurement definition

One `cv2.VideoCapture` pass decoded frames 0 through 174429 sequentially. It selected G242's stride-2000 frames 0 through 174000 plus explicit seed 19599: **89 unique source frames**, partitioned by the inherited committed labels into 27 VALID, 28 INVALID, and 34 CANNOT_JUDGE. It did not seek, rerun matching, modify a homography, retain a decoded image, or relabel a frame.

The fixed WNBA model inverse-projects baselines, sidelines, four lane boundaries, both free-throw straight markings and circles, both three-point curves plus their corner legs, and the centre circle. `free_throw_line` below includes both straight free-throw markings and circles; `arc` includes three-point curves and corner legs. Visible projected segments were sampled every 4 px. For each sample, I searched along its local normal at integer offsets -24 through +24 px for a Canny strong-edge pixel (`low=50`, `high=150`, 3x3 aperture, L2 gradient) and retained the minimum absolute offset.

The search radius is **24 px**. A sample with no candidate is retained and counted; it is not imputed as zero or otherwise dropped. A found distance of 24 px is right-censored at the bound, so the reported maximum 24 px is not a true maximum; any actual offset beyond 24 px is censored. A Canny edge is a detector output, not semantic proof that the candidate is painted court ink. Conversely, an absent candidate does not prove a good projection.

## Offset distributions

`Samples` is every in-image projected 4-px sample. `Found` is the subset with a Canny edge along the normal within 24 px. Distances are conditional on `Found`; `No candidate` is the named complementary count. A dash means that the centre circle had no in-image projected samples on this hoop-end view, not zero offset.

| Class | Line type | Samples | Found | No candidate | Median px | P90 px | Max px |
|---|---|---:|---:|---:|---:|---:|---:|
| VALID | sideline | 494432 | 1832 | 492600 | 7.0 | 19.0 | 24.0 |
| VALID | baseline | 19616 | 9003 | 10613 | 5.0 | 19.0 | 24.0 |
| VALID | lane boundary | 8757 | 4790 | 3967 | 5.0 | 19.0 | 24.0 |
| VALID | free-throw line | 17565 | 10668 | 6897 | 7.0 | 21.0 | 24.0 |
| VALID | arc | 25140 | 17237 | 7903 | 5.0 | 17.0 | 24.0 |
| VALID | centre circle | 0 | 0 | 0 | - | - | - |
| VALID | pooled | 565510 | 43530 | 521980 | 5.0 | 19.0 | 24.0 |
| INVALID | sideline | 455283 | 3686 | 451597 | 5.0 | 19.0 | 24.0 |
| INVALID | baseline | 20233 | 9761 | 10472 | 6.0 | 19.0 | 24.0 |
| INVALID | lane boundary | 77186 | 5637 | 71549 | 5.0 | 19.0 | 24.0 |
| INVALID | free-throw line | 18202 | 9052 | 9150 | 8.0 | 22.0 | 24.0 |
| INVALID | arc | 16656574 | 17366 | 16639208 | 5.0 | 18.0 | 24.0 |
| INVALID | centre circle | 0 | 0 | 0 | - | - | - |
| INVALID | pooled | 17227478 | 45502 | 17181976 | 6.0 | 19.0 | 24.0 |
| CANNOT_JUDGE | sideline | 433346 | 2571 | 430775 | 7.0 | 20.0 | 24.0 |
| CANNOT_JUDGE | baseline | 24414 | 6072 | 18342 | 6.0 | 20.0 | 24.0 |
| CANNOT_JUDGE | lane boundary | 74561 | 5024 | 69537 | 7.0 | 20.0 | 24.0 |
| CANNOT_JUDGE | free-throw line | 2327280 | 8741 | 2318539 | 9.0 | 22.0 | 24.0 |
| CANNOT_JUDGE | arc | 6412324 | 16297 | 6396027 | 5.0 | 19.0 | 24.0 |
| CANNOT_JUDGE | centre circle | 0 | 0 | 0 | - | - | - |
| CANNOT_JUDGE | pooled | 9271925 | 38705 | 9233220 | 6.0 | 20.0 | 24.0 |

The extremely large projected sample totals for INVALID and CANNOT_JUDGE arc/free-throw geometry are retained rather than normalized away: a bad projective map can repeatedly traverse the image near a projective discontinuity. They are context only, not a classifier comparison. No VALID/INVALID separation, overlap calculation, threshold, or gate is reported.

## Error budget and interpretation

G140's p90 label repeatability is **11.39 px** at the same 1920x1080 resolution, and G233d's seed used four hand labels. The VALID median of 5 px is within that known p90 repeatability scale, but the VALID p90 of 19 px is larger than 11.39 px. Thus the measured upper tail is not consistent with G140's stated p90 label repeatability alone, while the central offsets could be. This is not a causal decomposition: G140 measured hand-label repeatability at seed points, while G252 measures nearest Canny-edge distance across projected curves; four fitted labels may propagate their uncertainty non-uniformly.

Plainly: the hypothesis is **SUPPORTED**, not refuted. The detected-edge subset of eye-VALID projections is several pixels off at the median and has a censored 19-px p90. That is enough to show that render-scale eye validity can coexist with a miss of thin image structure. The large no-candidate count and the detector/censoring limits mean it is not an accuracy claim for every projected line or for calibration generally.

## Verification and limitations

Focused test run:

```text
python -m pytest scripts/platformkit/tracking/test_g252_projection_accuracy_in_pixels.py -q -p no:cacheprovider
4 passed in 1.01s
```

I independently reloaded the artifact: 89 records and 89 unique source frames; the 27/28/34 class partition reproduced; and, for every class/line bucket, `found + no_candidate == sample_points`. No full suite ran. A7 paths named above exist. B1 retains every sample including all no-candidate results. B2-B6 introduce no production schema, lifecycle, deployment, or moved module. B7 uses the complete stride-2000 decision set, not a head slice; no renders are required because this is a distance measurement. B8 uses independent image-edge candidates, never residuals against the four fitted seed points. B9 names both the 89 unique-frame denominator and every sampled-point denominator. B10 changes no matcher, seed, court model, production threshold, or gate; Canny settings are the fixed measurement definition only. Q does not apply.

**NOT VERIFIED:** whether a Canny candidate is a painted court line; uncensored offsets beyond 24 px; line visibility when no candidate is found; ground truth or repeatability of G244's inherited single-labeller labels; a second labeller; another seed, clip, arena, camera, sport, or dense temporal sample; automatic calibration (still 0/17); a validity signal; and any production change.
