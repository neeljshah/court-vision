# G243c: Verified-Point Amateur Seed Attempt

**FRAME-SELECTION RESULT: NO ELIGIBLE SEED FRAME.** The clip survey did not yield four court features that are both individually identifiable and unoccluded by players, coaches, or officials in one frame. Per G243c step 10, I stopped before labelling, fitting, either model gate, G222 propagation, detector projection, in-court calculation, or labels-per-hour arithmetic.

**VERDICT: CLOSED AT LIMIT.** Denominator: 1 clip, 0 eligible seed frames, 0 fitted labels, and 0 model gates. This is the third specified full-success outcome, not a substitute calibration result.

This measurement-only row follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changed no production module, threshold, coordinate contract, matcher, existing label file, daemon, keeper, corpus source, `src/`, or `domains/` file.

## Lane hold, source premise, and disk guard

I began on 2026-09-04 at 05:31 -05:00 in `C:\Users\neelj\nba-track-a6`, branch `track-a6`. Immediately beforehand, an executable-and-argument process inspection excluding this session found the live measurement lane as `pythonw.exe` PID 17012, tag `g247_projected_quad_validity`, cwd `C:/Users/neelj/nba-track-a5`. It was not interrupted. No permanent resident was touched.

Before survey or fitting, I re-measured the remote source:

| Field | Measured value |
|---|---|
| Exact source path | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Byte size | 24,523,745 |
| SHA-256 | `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` |
| ffprobe identity | 1280x720; 30/1 fps; 120.100000 s; 3,601 decoded video frames |

`df` was not used. The required pod probe `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g243c_disk_probe.bin bs=1M count=1 conv=fsync status=none` passed, wrote 1,048,576 bytes, and was removed. `du -sm /workspace/nba-ai-system/data` was 33,049 MB. The two abandoned partials were observed and not changed: `baseball__npb_05.mp4.part` at 2,490,710,544 bytes and `football__football_m8UWuQoflJo.mp4.part` at 4,999,500,276 bytes.

## Survey and pre-fit identity decision

The committed [whole-clip contact sheet](g243c_amateur_seed_verified_points_2026-09-04_artifact/whole_clip_survey_stride_60.jpg) contains 61 decoded frames at zero-based indices 0 through 3,600, one per two seconds. Its frame labels are produced by the row-local helper, which streams the remote source through `ffmpeg -vf select=not(mod(n\,60))` without input-side seek. I then frame-exactly re-decoded the candidates below with `ffmpeg -vf select=eq(n\,N) -vsync 0 -frames:v 1 -f rawvideo -pix_fmt bgr24 pipe:1`, also with no input-side `-ss`.

| Frame | Exact decode | Pre-fit identity outcome |
|---:|---|---|
| 660 | [frame](g243c_amateur_seed_verified_points_2026-09-04_artifact/candidate_frames/frame_660.jpg) | The right free-throw/lane geometry is closer than G243b frame 2760, but player bodies stand on the remaining lane/free-throw intersections; fewer than four identity-safe correspondences remain. |
| 840 | [frame](g243c_amateur_seed_verified_points_2026-09-04_artifact/candidate_frames/frame_840.jpg) | The centre-circle contour is visible, but its visible circumference alone does not identify four world-coordinate points. The painted lane intersections needed to complement it are player-occluded. |
| 3300 | [frame](g243c_amateur_seed_verified_points_2026-09-04_artifact/candidate_frames/frame_3300.jpg) | A late free-throw sequence makes the near painted end large, but players occupy the line intersections; it is not a four-point identity frame. |
| 3525 | [frame](g243c_amateur_seed_verified_points_2026-09-04_artifact/candidate_frames/frame_3525.jpg) | The same free-throw formation still obscures the usable key intersections. No point was promoted to a label. |

I did not create identity crops because there is no intended fitted point: a crop can establish only a feature that is visibly present. Calling an unmarked centre-circle circumference location a particular world-coordinate extremum, or calling an occupied key location a paint corner, would repeat G243b's exact error. The candidate-frame review is therefore pre-fit evidence of non-selection, not fitted input evidence.

G246 is controlling here: **LABEL REPEATABILITY IS NOT LABEL CORRECTNESS.** Repeating an incorrect point within 11.39 px can be repeatable without identifying the intended feature. Thus no three-label spread is reported: inventing three repeatable placements for an occluded or non-identifiable feature would not satisfy the row.

## Court models and the unrun gates

`court_points_for_sport` was read, not modified. It accepts exactly these keys:

| Key | Ordered returned points, ft | Assumption |
|---|---|---|
| `ncaa_basketball` | `(19,0) (31,0) (19,19) (31,19)` | 94x50 ft, 12-ft lane, 19-ft paint depth |
| `wnba` | `(17,0) (33,0) (17,19) (33,19)` | 94x50 ft, 16-ft lane, 19-ft paint depth |

Had an identity-safe seed existed, the preregistered models would have been (a) G243b's row-local high-school 84x50-ft model with 12-ft lane and 19-ft paint depth, and (b) the existing `ncaa_basketball` 94x50-ft / 12-ft-lane / 19-ft-paint-depth model. No new sport key was added. The footage is qualitatively consistent with high-school markings, but this oblique camera cannot measure 84 versus 94 ft or the physical lane width; the model would be assumed, not verified.

No rendered model receives a PASS or FAIL because the hard stop occurred before any fit. RMS is deliberately absent: with four fitted points it would be identically zero and uninformative, while there are zero fitted points here.

## Required downstream hard stops and G233d comparison

No G222 direct-to-seed call ran. The 3,601-frame bound, matches, inliers, inlier ratio, propagation horizon, detector projection, and in-court fraction against either named extent are all NOT RUN. There is consequently no in-court fraction to report, including no non-deterministic detector draw.

This stop preserves the controlling result from G242 and G244: G222 acceptance, matches, inliers, ratio, and RMS do not distinguish valid maps from close-ups, graphics, replays, or the wrong hoop end. Only independent-geometry renders could establish a hold, and none exists without a verified seed.

| Quantity | G233d WNBA broadcast | G243c amateur attempt |
|---|---:|---:|
| Resolution | 1920x1080 | 1280x720 |
| Seed gate | PASS | Not run: no identity-safe seed |
| Direct horizon | 1,200 tested frames | Not run |
| Direct inliers | 421-1,848 | Not run |

The lower 720p resolution has fewer pixels per foot than G233d's 1080p source, so a same-size pixel error would imply a larger real-world error here. This comparison does not rank amateur footage generally: it is one 120.1-second clip, one camera, and one labeller.

## Artifacts, cleanup, and verifier self-check

The retained artifact directory is [g243c_amateur_seed_verified_points_2026-09-04_artifact](g243c_amateur_seed_verified_points_2026-09-04_artifact/) (2,950,153 bytes). The row-local remote decoder and survey helper have SHA-256 `ef7df5526c6e44016d76266fc975de4d6dc0d0c4b5fedb3f481109226f9c4155`; its focused test has SHA-256 `ab664ab06a2073007975b9eb6c7ab43e3309afc7e4a65b67a02a5def95602073`. Focused test: `python -m pytest scripts/platformkit/tracking/test_g243c_amateur_seed_verified_points.py -q -p no:cacheprovider` -> `3 passed`. The helper is 101 lines and no allowlisted shared file grew, so A12 does not apply.

After retaining those five artifacts, I removed the local temporary survey, exact candidate decodes, and inspection crops, freeing 6,352,990 bytes. No corpus source or bridge partial was deleted.

Contract self-check: A7 paths named above exist in this commit. B1 has no derived metric or excluded denominator; B2-B6 change no schema, lifecycle, deployment, production code, or module location; B7 uses whole-clip evenly spaced survey frames plus pre-fit candidate frames, not a head slice; B8 has no fitted inputs or residual; B9 recycles no denominator; B10 changes no bar, threshold, matcher, coordinate contract, or court-model key. Q does not apply to this tracking measurement row.

## NOT VERIFIED

- A four-point seed, any point-label repeatability, either court-model gate, automatic calibration (still 0/17), or any propagation.
- Physical court dimensions, camera-model adequacy, detector coordinates, detector repeatability, or an in-court fraction.
- Whether another clip, camera, time interval, or labeller contains an identity-safe seed.
- The suitability finding from G245 beyond its stated one-labeller visual scope. Plausibility is necessary, never sufficient.
