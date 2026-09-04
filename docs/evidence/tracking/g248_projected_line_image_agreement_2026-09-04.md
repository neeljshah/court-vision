# G248: Projected court-line agreement with image structure

## Verdict

**ACCEPT (measurement-only negative): none of the four pre-registered projected-line/image signals separates the fixed G244 VALID and INVALID classes on the 89-frame G242 denominator.** The explicit overlap counts below, not differences in medians, answer the question. No threshold was fit, no same-frame accuracy is reported, and no production gate is proposed.

Together with G242 (literal acquisition accepts every scene), G244 (retained match diagnostics and cut drops do not separate), and G247 (projected quad shape does not separate), this establishes that **no available hand-built automatic validity signal separates these classes in this one-clip experiment**. The programme needs a trained model or a different instrument rather than another hand-built match- or projection-shape statistic. This does not validate the inherited eye labels, and it does not bear on automatic calibration.

The denominator is 89 in-sample frames from one clip, one seed, one arena, one wide stride, and one G244 labeller: 27 VALID, 28 INVALID, and 34 CANNOT_JUDGE. CANNOT_JUDGE is retained as its own class throughout.

## Lane check, source, disk guard, and inputs

I checked the pod at 2026-09-04 06:04:41 -05:00 and again immediately before the final metric pass at 06:26:36 -05:00. The process check excluded its own numeric PID and did not use substring matching. It found only permanent residents (`keep_track_daemon.sh`, `track_daemon`, `inplay_capture_runner`, and `foundry_runner`); G249 is the permitted other lane and was not interrupted. The final measurement began at 06:26:36 -05:00.

`df` was not used. Before the final worker wrote any artifact, `du -sm /workspace/nba-ai-system/data` was **33084 MB**, then `dd if=/dev/zero of=/workspace/nba-ai-system/g248_disk_probe.bin bs=1M count=1 conv=fsync` passed. Its 1,048,576-byte probe was removed. The final worker retained no video or images, copied its 33,450-byte temporary JSON, then removed its remote temporary directory. Two earlier zero-byte remote temporary directories were removed while repairing sampler mechanics. A 365-byte remote exception trace and its 365-byte copied local diagnostic were also removed. Total transient bytes freed were 1,082,756; no corpus source, G242 artifact, or either `footage_bridge` partial was deleted.

| Input opened | Full path | Bytes | Resolution / role |
|---|---|---:|---|
| Source video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 | 1920x1080, 174,430 frames; read-only pod input |
| Blind labels | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g244_blind_validity_labels_2026-09-04.csv` | 8,114 | Fixed committed 89-row G244 record; SHA-256 `c95071bc687eaff41b30dc46d635f4a835421a3f16e117a7988c6547cfbfdadf` |
| Persisted maps | `C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g247_projected_quad_validity_artifact\g247_measurement.json` | 142,822 | Fixed 89 G247 image-to-court matrices; SHA-256 `05be8b9d4b71c2f865683c4cf6d498b0997ad6108681414ae2e29f88ad37b87b` |

The final artifact is [g248_measurement.json](g248_projected_line_image_agreement_artifact/g248_measurement.json), 39,047 bytes, SHA-256 `82e212b735560916e8890f634f43904ae881968e8047fafdf0a951d557d42beb`. The evidence route is `scripts/platformkit/tracking/g248_projected_line_image_agreement.py`, SHA-256 `814b14105618dd44380cbc6a0b25b12a2e5e23a4c14d19087fd344760b3d85e4`.

## Final decode and fixed line measurement

The scored artifact comes from one sequential `cv2.VideoCapture` decode from frame 0 through 174429. It selected exactly G242's stride-2000 frames 0 through 174000 plus seed frame 19599, for 89 unique frames. It did not seek, rerun G222 matching, alter a homography, retain a decoded frame, or use the 960x540 G242 overlays as pixel input.

The fixed WNBA line model used baselines, sidelines, both lane boundaries, both free-throw lines and circles, both three-point arcs and their corner lines, and the centre circle. It inverse-projected G247's image-to-court matrices and sampled the visible clipped portions at 2-pixel projected arclength. This preserves off-frame geometry in coverage: coverage is in-image clipped projected length divided by all finite projected segment length. Clipping only bounds memory; it does not turn off-frame line length into on-frame evidence.

The four pre-registered signals were computed as follows.

1. **Edge-response contrast:** grayscale Sobel gradient magnitude on curve samples minus controls 3 px (near) and 9 px (far) away, on both perpendicular sides; the four control sets are pooled before subtraction.
2. **Line-detector agreement:** OpenCV `LSD_REFINE_STD`; a sample agrees only if a detector segment is within 4 px and its unoriented tangent differs by at most 15 degrees.
3. **Marking contrast:** grayscale brightness on curve samples minus the same pooled perpendicular controls.
4. **Coverage:** the projected-length fraction described above.

Negative contrast values are measurements, not direction-reversed validity calls. In particular, they are not thresholded or converted to a classification rule.

## Per-class distributions and overlap

P90 uses the standard linear quantile. The 34 CANNOT_JUDGE frames are reported separately and are excluded from every VALID/INVALID overlap count.

| Signal | Class | n | Min | Median | P90 | Max |
|---|---|---:|---:|---:|---:|---:|
| Edge-response contrast | VALID | 27 | -67.888245 | -47.325077 | -34.870512 | -23.571737 |
| Edge-response contrast | INVALID | 28 | -57.526115 | -45.145500 | -33.599431 | -13.773243 |
| Edge-response contrast | CANNOT_JUDGE | 34 | -69.215248 | -30.257095 | -13.603463 | -5.373360 |
| Line-detector agreement | VALID | 27 | 0.010807 | 0.037751 | 0.065375 | 0.141064 |
| Line-detector agreement | INVALID | 28 | 0.000097 | 0.038374 | 0.059436 | 0.078263 |
| Line-detector agreement | CANNOT_JUDGE | 34 | 0.000500 | 0.025977 | 0.059492 | 0.284694 |
| Marking contrast | VALID | 27 | -130.189828 | -99.878700 | -81.576481 | -57.787561 |
| Marking contrast | INVALID | 28 | -121.106930 | -106.921386 | -64.236594 | -45.142235 |
| Marking contrast | CANNOT_JUDGE | 34 | -123.964415 | -84.834722 | -51.033333 | -17.116432 |
| Coverage | VALID | 27 | 0.302965 | 0.308681 | 0.345266 | 0.378616 |
| Coverage | INVALID | 28 | 0.024252 | 0.305943 | 0.402166 | 0.485117 |
| Coverage | CANNOT_JUDGE | 34 | 0.003457 | 0.305618 | 0.444873 | 0.886023 |

The overlap, rather than the medians, is the result:

| Signal | INVALID range | VALID values inside INVALID range | VALID range | INVALID values inside VALID range |
|---|---|---:|---|---:|
| Edge-response contrast | -57.526115 to -13.773243 | 25/27 | -67.888245 to -23.571737 | 26/28 |
| Line-detector agreement | 0.000097 to 0.078263 | 26/27 | 0.010807 to 0.141064 | 23/28 |
| Marking contrast | -121.106930 to -45.142235 | 23/27 | -130.189828 to -57.787561 | 26/28 |
| Coverage | 0.024252 to 0.485117 | 27/27 | 0.302965 to 0.378616 | 21/28 |

There is no clean separation in any signal. CANNOT_JUDGE contains tight crops, graphics, and other frames without enough independently visible geometry; a low signal there is expected and is not evidence about VALID-versus-INVALID separation.

## Multiple comparisons, out of sample, and limitations

This is four pre-registered signals on 89 in-sample points, with only 27 VALID and 28 INVALID labels. One of four signals looking good by chance would be possible; it would not be a discovery. Here none has clean in-sample range separation, so the conditional fresh-sample exercise was not triggered. No out-of-sample labels were created, no threshold was fit, and no same-frame accuracy is reported. Any future clean in-sample separation would require a different-stride, non-overlapping sample, blinded and committed under G244's protocol before its signal is computed; a failure there would be a negative result.

Material limits remain: one clip, one seed, one arena, wide stride samples, and one inherited G244 labeller. Eye-label reliability in this programme has never cleared 80 percent blind agreement on any of four measured criteria, and G246 showed repeatable labels can be uniformly wrong. This row mechanises an eye check; it does not validate that eye check. Nothing here establishes ground truth, another labeller, another clip/arena/camera/sport, dense-frame behavior, automatic calibration, a threshold, or a production gate.

**NOT VERIFIED:** label ground truth or repeatability; image-agreement repeatability; any out-of-sample separation; another seed, clip, arena, camera, or sport; a trained validity model; automatic calibration; and production operation.

## Verification and contract self-check

Focused test run after the final batching change:

```text
python -m pytest scripts/platformkit/tracking/test_g248_projected_line_image_agreement.py -q -p no:cacheprovider
4 passed in 1.99s
```

No full suite ran. A7: every named final evidence path exists. B1: all 89 named rows are retained, with no excluded class or frame. B2-B6: no production schema, lifecycle, deployment, reader field, or moved module changed. B7: the complete stride-2000 G242 decision set is used, not a head slice. B8: this is not a residual against fitted points; it samples independent image structure along the persisted projected line geometry. B9: the denominator is 89 unique source frames, partitioned 27/28/34. B10: no matcher setting, court model, threshold, or gate changed. Q does not apply. A12 does not apply because this landing adds new sub-300-LOC files and does not grow an allowlisted file.
