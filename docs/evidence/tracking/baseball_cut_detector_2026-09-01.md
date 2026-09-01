# Baseball cut detector -- lane T5-BASEBALL: premise FALSIFIED, no code change

Date: 2026-09-01. Lane: T5-BASEBALL. Verdict: **REJECT the stated premise.**
The baseball cut detector does not over-trigger, and no cut-detector change can
move the intake pass count. No code was changed. All numbers below were measured
this session on the pod (`213.192.2.83:40048`, `/workspace/nba-ai-system`).

## Verdict table

| Claim under test | Verdict | Evidence |
|---|---|---|
| 0/37 teacher games pass intake | CONFIRMED (and worse: 0/87) | 37 local + 87 pod reports, `passed=true` count 0 |
| Median track length 14 frames | PARTLY reproduced | corpus-wide median is 28.0 over 62 `image_px` CSVs; 14 is the exact value for `npb_kqPv-_WwWLk` with the cut gate ON |
| Churn 71 | NOT reproduced | corpus-wide median `churn_ratio` 34.45 (min 4.9, max 100.2) |
| Cut detector over-triggers | **FALSE** | cut rate 0.37-2.75 pct of processed frames across 24 clips; histogram-correlation p05 0.87-0.98 against a 0.60 threshold |
| Over-triggering costs pitch-view frames | **FALSE** | `geo_frames_lost_to_cut_gate` = 0, 0, 0, 0 and 1-of-26 across five 3000-frame runs |
| Fixing the cut detector raises the pass count | **IMPOSSIBLE** | current harness rejects 86/87 baseball CSVs on `coordinate_contract` before any tracking metric is computed |

## Step 0 -- premise check (before any edit)

Stored reports, `data/tracking_reports/baseball/`:

* local (37 files): 0 passed. Failure heads: `jump_p95` 33, `ball_valid` 33, `oob` 32, `coverage` 23, `empty` 4. Median of `median_track_len` = 335.0 (min 0, max 4591). **No report fails on `median_track_len`.**
* pod (87 files): 0 passed. Failure heads: `coordinate_contract:` 60, `oob` 24, `jump_p95` 24, `ball_valid` 24, `coverage` 16, `empty` 3.

Re-running the CURRENT harness over all 87 pod CSVs
(`scripts/platformkit/tracking_harness.evaluate`, `sport="baseball"`,
thresholds untouched):

```
{"csvs": 87, "passed": 0, "failure_heads": {"coordinate_contract:": 86, "empty": 1},
 "median_of_median_track_len": 0.0}
```

86 of 87 games now fail on ONE thing: the coordinate contract. Track length,
churn, `oob`, `jump_p95` and `ball_valid` are unreachable code paths for
baseball today.

`scripts/platformkit/tracking_quality_scan.scan` over the 62 `image_px` CSVs:
median `median_track_frames` 28.0, median `churn_ratio` 34.45, median
`singleton_share` 0.1042, median `tracks_per_frame` 3.31.

## Why intake can never pass, and why that is correct

`BaseballAdapter` emits `coordinate_space="image_px"` because there is no
validated ground-plane homography (`domains/baseball/tracking/adapter.py` module
docstring; S4 packet). `SPORT_COORDINATE_SPACES["baseball"]` accepts only
`court_feet` (`scripts/platformkit/coordinate_provenance.py:16-21`), so
`_validate_coordinate_space` fails closed. `scripts/platformkit/adapter_run.py:41-45`
states the intent outright: image rows "are REJECTED by the harness with
coordinate_contract -- they are a preserved corpus for training, never a passing game."

This is a declaration-level rejection, not a quality-level one. No tracking
improvement of any kind changes it. The only levers are a validated baseball
homography (measured out of frame -- S4 packet) or loosening the contract, which
this lane is forbidden to do and which would re-open the exact pixels-as-feet
laundering the contract exists to prevent.

## Direct measurement of the cut detector

`domains/baseball/tracking/segmenter.detect_cut`: 64x36 grayscale histogram
correlation, cut when correlation < 0.60. Adapter stride is `round(fps * 0.1)` = 3
at 30 fps, so compared frames are 0.1 s apart.

3000 processed frames per clip (9000 source frames, 5 minutes of video):

| clip | cuts | cut rate | corr p50 | corr p05 | pitch-view frames (gate off) | lost to cut gate |
|---|---|---|---|---|---|---|
| `kbo_2ZtgAvs67so` | 11 | 0.0037 | 0.9939 | 0.9796 | 0 | 0 |
| `mlb_5IA4jaKNOYg` | 33 | 0.0110 | 0.9896 | 0.9314 | 12 | 0 |
| `npb_01_720p` | 50 | 0.0167 | 0.9870 | 0.8743 | 0 | 0 |
| `mlb_QqHhEShXAX0` | 50 | 0.0167 | 0.9957 | 0.9463 | 0 | 0 |
| `kbo_FDSWjM_OaTs` | 20 | 0.0067 | 0.9586 | 0.9097 | 26 | 1 |

The 5th percentile of the correlation signal is 0.87-0.98. The trigger threshold
is 0.60. The detector spends essentially no time near its own threshold. One cut
per 6-27 seconds is the true edit rate of these broadcasts.

The decisive column is the last one: across five runs the cut gate suppressed
**one** pitch-view frame in total (1 of 26, on the only clip with meaningful
pitch views). The cut detector is not what is costing pitch views.

## Render-and-look: classifying the triggers

All 20 triggers on the one real game broadcast in the set (`kbo_FDSWjM_OaTs`)
were dumped as before/after pairs and viewed as four contact sheets.

* 16-17 are unambiguous hard shot transitions (wide field to batter close-up, dugout to mound, field to studio).
* 3-4 are borderline, and every one of them is either a SECOND trigger inside a single long cross-dissolve (triggers 11/12, 15/16/17/18) or a studio graphic wipe with the camera unchanged (triggers 13, 17).
* **Zero** false triggers on pitch-view content.

The borderline class -- repeat triggers inside one dissolve -- is the only thing
hysteresis or a minimum scene length would fix. It occurs on studio and graphic
content, costs zero pitch-view frames, and cannot change the intake verdict.
Building it now would be work with a measured benefit of zero.

## Corpus finding (this is the real blocker for the teacher path)

Green-field / mound-chord / infield-band census, 400 processed frames per clip,
24 staged baseball clips:

* **16 of 24 clips have `green_rate` = 0.0** -- no live grass at all in the sampled window.
* Only 3 of 24 produce any pitch view: `kbo_FDSWjM_OaTs` 6.5 pct, `npb_kqPv-_WwWLk` 6.25 pct, `npb_V3FrwLVwCpA` 2.5 pct.
* The mound-chord to infield-band step then drops everything on three more: `kbo_ahHGpSJWcIU` 11 chords to 0 pitch views, `mlb_5IA4jaKNOYg` 26 to 0, `mlb_QqHhEShXAX0` 9 to 0.

Viewing frames confirms why: `kbo_2ZtgAvs67so` is a KBO studio talk show and a
fantasy-app promo; `mlb_QqHhEShXAX0` is a podcast screen-share of a stats app.
Neither is game footage. This extends the S4 packet's void-source finding
(`mlb_x6YpMlNYbrU`, `kbo_lrK_Hv6BEE0`) to a much larger share of the corpus.

Consequence for the framing prereg: across all 87 games there is exactly **one**
`teacher_meta.json`, and it reads `pitch_view_frames: 0`, `pitch_segments: 0`,
`segments: []`. Zero confident targets.
`scripts/platformkit/teacher_feature_gate.py` therefore holds baseball at rung
`IMAGE_PX_DECLARED`; `METRIC_LOCAL` needs one segment carrying `scale_px_per_ft`,
and `HARNESS_PASS_10` needs 10 harness passes, which the coordinate contract
makes unreachable.

## Cut-gate A/B (same detections, identity reset on vs off)

3000 processed frames, identical YOLO boxes fed to two `BaseballIdentityTracker`
instances differing only in whether `cut=True` is passed:

| clip | cuts | tracks ON to OFF | median track ON to OFF | churn ON to OFF | singleton ON to OFF |
|---|---|---|---|---|---|
| `kbo_FDSWjM_OaTs` | 20 | 259 to 143 | 10 to 22 | 15.24 to 8.41 | 0.166 to 0.021 |
| `npb_kqPv-_WwWLk` | 64 | 444 to 235 | 14 to 22 | 24.67 to 13.06 | 0.083 to 0.017 |

The cut gate does roughly double the track count -- because each of 20 or 64
verified cuts retires every active identity, and about 6 people are on screen.
That is the arithmetic, and it is the CORRECT behaviour: carrying a centre-field
identity across a real camera change is identity laundering, not continuity.
Turning the gate off buys median 22 instead of 10-14, which is still nowhere near
"persists across the pitch", and it buys it by fabricating identity links across
verified shot boundaries. It also changes no intake verdict.

## Not verified / not claimed

* Frames were classified visually for one game (20 triggers) plus 6 pairs across two non-game clips; no labelled ground-truth cut corpus exists for baseball, so the true/false split is my eye, not an annotation.
* The census sampled the first 400 processed frames (1200 source frames) per clip. A clip whose game action starts later would read `green_rate` 0.0 here; the 16-of-24 figure is a lower bound on usable footage, not a proven count of void sources.
* TransNetV2 (`domains/baseball/tracking/transnet.py`, MIT) was NOT run. It was not needed: the histogram detector is not the failing component, so swapping in a stronger one has no measured target.
* No claim is made about framing, calibration, prediction quality, or any edge.

## Artifacts

Pod: `/tmp/t5_cutprobe.log`, `/tmp/t5_geo.log`, `/tmp/t5_cutab.log`,
`/tmp/t5_reintake.log`, `/tmp/t5_geocensus.json`, `/tmp/t5_reintake.json`,
`/tmp/t5_cutab.json`, frame dumps `/tmp/t5_dump_kbo`, `/tmp/t5_dump_kbo2`,
`/tmp/t5_dump_mlb2`. Probe sources: `/tmp/t5_cutprobe.py`,
`/tmp/t5_geocensus.py`, `/tmp/t5_cutab.py`.
