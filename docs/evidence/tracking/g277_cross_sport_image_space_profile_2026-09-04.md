# G277: Cross-sport image-space profile -- schema and cadence stop

## Verdict

**CLOSED AT LIMIT / FALSIFIED PREMISE (measurement only): the WNBA clip cannot be called typical or an outlier, because all three WNBA footage runs lack `cls`, `track_id`, `x`, and `y`; their normalized same-ID speeds, track lengths, ranks, and percentiles are therefore undefined among the 42 footage runs.**

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. The intended 42-run footage census was measured: 15 named detector/hash variants were excluded, leaving 42 footage runs across seven sports. Only 34 runs across five sports are schema- and row-complete for the stated calculation. They have zero source-consecutive same-ID steps, so no speed quantile exists even for those 34 runs. No detector, tracker, video, map, production code, corpus source, or bridge partial was changed.

**Central limitation:** image displacement conflates player motion, camera motion, and tracking error; without a map they cannot be separated. Camera regimes differ greatly by sport. A larger tail in one sport would not be evidence of worse tracking there. This is not a quality ranking of sports. Here, there is no WNBA tail to compare at all.

The denominator is detector-box observations, not authenticated players. `cls=player`, where present, is the detector label, not a verified identity. `wnba_01` here is a separate landed run, not G267's retained 3,801-frame record set; they were not merged or compared row-for-row.

## Method and measured stop

The specified calculation was implemented without a raw-pixel comparison:

```text
speed = sqrt(dx^2 + dy^2) / source_height * source_fps
```

It applies only to consecutive-source-frame, same-`track_id` steps. Track length is the count of observed detector-box rows per `track_id`; seconds are rows divided by the run's constant `source_fps`. Quantiles would be linear-interpolated median, p90, p99, p99.9, and maximum in frame-heights per second.

Raw per-frame pixels were never compared across runs. The 34 otherwise complete runs yielded `step_count=0` under the required consecutive-source-frame condition, hence every speed quantile below is `N/A`. The WNBA rows additionally have no valid `track_id`/`x`/`y`/`cls` schema, so even their track-length statistics are unavailable. No field aliases were substituted.

## Run split

The 42 footage runs are listed in the per-run table below. Eight are explicitly retained as footage but not numerically comparable: NCAA and all WNBA rows have the legacy `player_id`/`x_position`/`y_position` schema and no `cls`; three tennis rows have blank required-coordinate rows and `cls` values `ball,player`; `tennis_smoke` lacks source timebase/height/duration and also has `ball,player`.

Excluded non-footage variants (15):

| Run(s) | Reason |
|---|---|
| `g172_cv2_environment_gap_20260903_a5` | g172 detector/hash variant on the same footage |
| `g225_yolov8m_r1_1788509783`, `g225_yolov8m_r2_1788509903`, `g225_yolov8m_r3_1788510023` | g225 YOLOv8m detector variants |
| `g225_yolov8n_r1_1788509139`, `g225_yolov8n_r2_1788509240`, `g225_yolov8n_r3_1788509342` | g225 YOLOv8n detector variants |
| `g225_yolov8s_r1_1788509445`, `g225_yolov8s_r2_1788509558`, `g225_yolov8s_r3_1788509670` | g225 YOLOv8s detector variants |
| `g226c_basketball_20260904T0558Z` | g226c detector/hash variant |
| `g239_basketball_20260904T0729Z` | g239 detector/hash variant |
| `g240_basketball_hash_20260904T084304Z_r1`, `g240_basketball_hash_20260904T084304Z_r2`, `g240_basketball_hash_20260904T084304Z_r3` | g240 detector/hash variants |

## Full per-run table

`N/A` means no valid statistic, not a zero value. Speed columns are frame-heights per second. The committed [CSV table](g277_cross_sport_image_space_profile_artifact/g277_per_run_summary.csv) is the machine-readable version; the [JSON summary](g277_cross_sport_image_space_profile_artifact/g277_per_run_summary.json) retains each opened input's full `data/tracking/<run>/tracking_data.csv` path, byte size, CSV mtime, source-metadata value sets, provenance-file metadata, and route hash.

| Run | Sport | Status | Rows | Steps | Speed med/p90/p99/p99.9/max | Tracks | Length med/p90 frames | <5 frames | Length med/p90 sec | cls | observation |
|---|---|---|---:|---:|---|---:|---|---:|---|---|---|
| football_Z8Ezd95NnjM | football | comparable | 136911 | 0 | N/A | 29 | 1072/14836.6 | 0.138 | 35.769/495.048 | player | observed |
| football_wHZt1eY3A9s | football | comparable | 258248 | 0 | N/A | 37 | 2666/20801.6 | 0.027 | 88.956/694.080 | player | observed |
| football_yahhMkUWd7c | football | comparable | 147019 | 0 | N/A | 33 | 1015/14231.2 | 0.121 | 33.867/474.848 | player | observed |
| kbo_01 | kbo | comparable | 63497 | 0 | N/A | 4381 | 9/35 | 0.330 | 0.150/0.584 | player | observed |
| kbo_02 | kbo | comparable | 39744 | 0 | N/A | 3020 | 8/31 | 0.362 | 0.133/0.517 | player | observed |
| kbo_03 | kbo | comparable | 39254 | 0 | N/A | 2959 | 8/31 | 0.357 | 0.133/0.517 | player | observed |
| kbo_04 | kbo | comparable | 54914 | 0 | N/A | 3835 | 9/36 | 0.342 | 0.150/0.601 | player | observed |
| kbo_05 | kbo | comparable | 53295 | 0 | N/A | 3876 | 7/35 | 0.402 | 0.117/0.584 | player | observed |
| kbo_06 | kbo | comparable | 47317 | 0 | N/A | 3323 | 9/37 | 0.362 | 0.150/0.617 | player | observed |
| kbo_07 | kbo | comparable | 49366 | 0 | N/A | 3151 | 9/38 | 0.336 | 0.150/0.634 | player | observed |
| kbo_08 | kbo | comparable | 76995 | 0 | N/A | 5052 | 10/36 | 0.307 | 0.167/0.601 | player | observed |
| kbo_09 | kbo | comparable | 86881 | 0 | N/A | 5469 | 9/40 | 0.371 | 0.150/0.667 | player | observed |
| kbo_10 | kbo | comparable | 58895 | 0 | N/A | 4173 | 8/34.8 | 0.353 | 0.133/0.581 | player | observed |
| mlb_2026-08-30_03d78bee | mlb | comparable | 39998 | 0 | N/A | 3173 | 8/30 | 0.364 | 0.133/0.501 | player | observed |
| mlb_2026-08-30_08b16ce9 | mlb | comparable | 49132 | 0 | N/A | 3727 | 9/32 | 0.341 | 0.150/0.534 | player | observed |
| mlb_2026-08-30_0f36e8cc | mlb | comparable | 54537 | 0 | N/A | 4773 | 7/28 | 0.401 | 0.117/0.467 | player | observed |
| mlb_2026-08-30_10893dca | mlb | comparable | 32380 | 0 | N/A | 2584 | 8/29 | 0.339 | 0.133/0.484 | player | observed |
| mlb_2026-08-30_1c6706c6 | mlb | comparable | 42691 | 0 | N/A | 2728 | 10/36 | 0.310 | 0.167/0.601 | player | observed |
| mlb_2026-08-30_2143de43 | mlb | comparable | 46570 | 0 | N/A | 3721 | 8/30 | 0.371 | 0.133/0.501 | player | observed |
| mlb_2026-08-30_2b814fad | mlb | comparable | 46490 | 0 | N/A | 2989 | 11/35.2 | 0.285 | 0.184/0.587 | player | observed |
| mlb_2026-08-30_3a02d9b3 | mlb | comparable | 35882 | 0 | N/A | 2306 | 11/35 | 0.286 | 0.184/0.584 | player | observed |
| mlb_2026-08-30_7e8080e5 | mlb | comparable | 48816 | 0 | N/A | 3935 | 8/28 | 0.372 | 0.133/0.467 | player | observed |
| mlb_2026-08-30_f8812b72 | mlb | comparable | 60952 | 0 | N/A | 4158 | 9/36 | 0.337 | 0.150/0.601 | player | observed |
| mlb_A5AkcaXA2fk | mlb | comparable | 79013 | 0 | N/A | 985 | 8/152 | 0.402 | 0.267/5.067 | player | observed |
| mlb_gDv5xF2AA2E | mlb | comparable | 183929 | 0 | N/A | 8251 | 15/54 | 0.225 | 0.250/0.901 | player | observed |
| mlb_nLoG6gvC-Nk | mlb | comparable | 118535 | 0 | N/A | 3811 | 10/56 | 0.320 | 0.333/1.867 | player | observed |
| ncaa_basketball_IB-_u4gW3ds | ncaa_basketball | schema incompatible: cls,track_id,x,y absent | 271 | N/A | N/A | N/A | N/A | N/A | N/A | FIELD ABSENT | observed |
| npb_01 | npb | comparable | 140965 | 0 | N/A | 5995 | 15/57 | 0.230 | 0.500/1.900 | player | observed |
| npb_02 | npb | comparable | 154016 | 0 | N/A | 7318 | 11/52 | 0.281 | 0.367/1.733 | player | observed |
| npb_03 | npb | comparable | 139970 | 0 | N/A | 6673 | 12/50 | 0.293 | 0.400/1.667 | player | observed |
| npb_04 | npb | comparable | 119498 | 0 | N/A | 5364 | 13/57 | 0.260 | 0.433/1.900 | player | observed |
| soccer_Z6NTDyxcODs | soccer | comparable | 240661 | 0 | N/A | 2384 | 77/205 | 0.027 | 2.567/6.833 | player | observed |
| soccer_c1mzmBGHQr4 | soccer | comparable | 182403 | 0 | N/A | 2470 | 45/176 | 0.109 | 1.500/5.867 | player | observed |
| soccer_dnR5C6WLJI4 | soccer | comparable | 237203 | 0 | N/A | 2451 | 67/218 | 0.038 | 2.233/7.267 | player | observed |
| soccer_kSgNjoaqCpI | soccer | comparable | 230794 | 0 | N/A | 2407 | 53/242 | 0.083 | 1.767/8.067 | player | observed |
| tennis_01 | tennis | incomplete: 2153 required numeric rows blank | 19437 | N/A | N/A | N/A | N/A | N/A | N/A | ball,player | observed |
| tennis_02 | tennis | incomplete: 104 required numeric rows blank | 1637 | N/A | N/A | N/A | N/A | N/A | N/A | ball,player | observed |
| tennis_ref01 | tennis | incomplete: 136 required numeric rows blank | 1861 | N/A | N/A | N/A | N/A | N/A | N/A | ball,player | observed |
| tennis_smoke | tennis | schema incompatible: source_duration,source_fps,source_height absent | 1861 | N/A | N/A | N/A | N/A | N/A | N/A | ball,player | observed |
| wnba_01 | wnba | schema incompatible: cls,track_id,x,y absent | 3377 | N/A | N/A | N/A | N/A | N/A | N/A | FIELD ABSENT | observed |
| wnba_02 | wnba | schema incompatible: cls,track_id,x,y absent | 4171 | N/A | N/A | N/A | N/A | N/A | N/A | FIELD ABSENT | observed |
| wnba_03 | wnba | schema incompatible: cls,track_id,x,y absent | 4534 | N/A | N/A | N/A | N/A | N/A | N/A | FIELD ABSENT | observed |

All comparable rows had only `cls=player` and `observation=observed`; no comparable-run exception appeared. The table names every exception: `cls` is absent in NCAA and WNBA, while tennis includes `ball`; all inspected runs with an `observation` column had only `observed`.

## Sport aggregation and WNBA placement

Aggregation is the median of the available run-level values, not pooled rows and not a sport-quality ranking. It is limited to football (3), KBO (10), MLB (13), NPB (4), and soccer (4). Their speed columns are all N/A because every run has zero qualifying steps; the track summaries remain descriptive only.

| Sport | Runs | Median tracks | Median length frames | p90 length frames | Median length seconds | p90 length seconds | Median <5-frame fraction |
|---|---:|---:|---:|---:|---:|---:|---:|
| football | 3 | 33 | 1072 | 14836.6 | 35.769 | 495.048 | 0.121 |
| kbo | 10 | 3855.5 | 9 | 35.5 | 0.150 | 0.592 | 0.355 |
| mlb | 13 | 3721 | 9 | 35 | 0.150 | 0.584 | 0.339 |
| npb | 4 | 6334 | 12.5 | 54.5 | 0.417 | 1.817 | 0.270 |
| soccer | 4 | 2429 | 60 | 211.5 | 2.000 | 7.050 | 0.061 |

For each WNBA run and every requested statistic -- step count, five speed quantiles, track count, both track-length quantiles in frames and seconds, and short-track fraction -- rank and percentile are **N/A**. There is no valid WNBA value to place in the 42-run footage census or the 34-run schema-complete subset.

## Provenance and disk guard

Each run directory was inspected for manifest/config/timestamp evidence; the JSON summary records every candidate path, byte size, and mtime. Football and soccer carry `harness_verdict.json` and `tracking_capability.json`; KBO, MLB, and NPB additionally carry `teacher_meta.json`; NCAA and WNBA carry `harness_verdict.json`, `resolver_debug.json`, `team_colors.json`, and `tracking_capability.json`; tennis has the listed harness/capability artifacts. The bounded JSON inspection found no tracker-version, detector-version, pipeline-version, model-version, commit, or route-SHA scalar in those candidate files. Run names and mtimes differ (for example WNBA candidates span 2026-09-03 through 2026-09-04, while MLB includes dated and ID-named runs). Tracker provenance is therefore unknown and may be mixed; any cross-run difference would be confounded by pipeline/version as well as footage. A common pipeline must not be assumed.

The final pod measurement used `/workspace/wt/a6` because the landed records reside on the pod. Before scoring, the active other-Python lane-worktree set was `{ /workspace/wt/a17 }`; the two-PID-per-lane rule was applied by CWD, and no process was interrupted. The pod-side guard measured `du -sm /workspace` as 39,003 MB before and after a successful 1,048,576-byte `dd conv=fsync` probe; that probe was removed. The launcher preflight was 39,003 MB. The final pass replaced 105,879 bytes of prior scratch summaries and fetched 99,715-byte JSON plus 6,164-byte CSV summaries only. No corpus source or bridge partial was deleted. Known bytes freed: 1,154,455 bytes (the final probe plus replaced scratch summaries).

Route SHA-256: `7e8940d16f0ef605a7583aa313386cf05c8fe7e44f1013c1486549b024ca775e` for [the 298-line read-only harness](../../../scripts/platformkit/tracking/g277_cross_sport_image_space_profile.py). Source videos were not opened, decoded, rendered, or measured; the opened inputs were only the per-run `tracking_data.csv` files and bounded JSON provenance records named in the committed JSON inventory.

```text
python -m pytest scripts/platformkit/tracking/test_g277_cross_sport_image_space_profile.py -q -p no:cacheprovider
4 passed
```

Contract self-check: A7 paths below exist; A9 input inventory is retained in the JSON summary; A11 records the exercised harness SHA. B1 names all 42 footage and 15 variant runs and never filters rows to improve a metric. B2--B6 make no schema, lifecycle, deployment, production, or relocation change. B7/A3 do not apply: no render or head slice was used. B8 has no fitted residual. B9 names detector-box and run denominators. B10 moves no bar. Q does not apply.

## NOT VERIFIED

- A WNBA normalized-speed or track-length profile, WNBA rank, percentile, typicality, or outlier status.
- Whether non-unit source-frame gaps reflect a frame stride, export convention, or tracker behavior.
- A common tracker version, detector version, pipeline revision, or comparable provenance across runs.
- Person precision/recall, authenticated identity, on-court status, or a quality ranking of any sport.
- Court-space accuracy, calibration, camera-motion separation, causal source of image displacement, or a production change.
