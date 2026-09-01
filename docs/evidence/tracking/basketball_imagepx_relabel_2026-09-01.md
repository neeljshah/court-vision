# Basketball image_px relabel: premise falsified, and the label is wrong anyway

Lane T3-BASKETBALL, pod `213.192.2.83:40048`, repo `/workspace/nba-ai-system`,
2026-09-01. Pod access was read-only apart from three `nohup setsid` jobs of my
own writing to `/tmp`. Artifacts in
`docs/evidence/tracking/basketball_imagepx_relabel_2026-09-01/`.

## 1. Premise check: there was nothing left to relabel

The assigned premise was that basketball rows carry `court_feet` without an
accepted homography. Measured on the pod:

| question | measured |
|---|---|
| basketball dirs under `data/tracking/` | 15 (10 wnba + 5 ncaa) of 182 total |
| with a `tracking_data.csv` | 11 (wnba_06/07/08 and ncaa_WFl3V7ZY4ss are empty) |
| basketball rows in `track_daemon_ledger.jsonl` | 40 rows / 10 unique games (26 timeout, 7 thin, 7 tracked) |
| rows declaring `court_feet` | **0** |
| rows already declaring `image_px` | **103,009 of 103,009 (11 of 11 files)** |

The relabel already ran, in commit `b29369580`, and its memo is
`docs/research/organization-sprint/BASKETBALL-POD-RELABEL-IMAGE-PX-2026-09-01.md`.
The pre-relabel sources (`tracking_data.csv.pre_relabel`, all 11 present)
declared `image_px` on 29,294 rows and declared nothing at all on 73,715. None
declared `court_feet`, so no row ever carried the failure the lane was sent to
fix.

The assigned selector `homography_accepted == false` would also have been the
wrong criterion. `homography_valid` is 1 on 98,278 rows and 0 on 4,731, but
`scripts/run_clip.py` states in its own comment that the per-clip homography is
solved in memory and discarded and that `ft_x/ft_y` are an affine rescale of
`x_norm`. No row of the corpus has a persisted transform, so the honest
selector is "no calibration sidecar" -- which is what the shipped relabel used.

**No second relabel tool was built.** It would have rewritten zero rows under
the correct selector and 98,278 rows wrongly under the assigned one.

## 2. Per-rung harness counts, before -> after (11 games)

Frozen judge, thresholds untouched (`scripts/platformkit/tracking_harness.evaluate`,
config `2026-09-01-v1`), scored this session on the pod: `before` =
`tracking_data.csv.pre_relabel`, `after` = current `tracking_data.csv`. Raw
output: `t3_bb_harness_result.json`, pod log `/tmp/t3_bb_harness_2026-09-01.log`.

| rung | before | after |
|---|---:|---:|
| no court calibration sidecar | 11 | 0 |
| declared `image_px` (corpus lane, unscorable by design) | 0 | 11 |
| rows omit `coordinate_space` | 0 | 0 |
| reached the metric gates | 0 | 0 |
| PASS | 0 | 0 |

Row and emitted-frame counts are byte-identical before and after (103,009 rows,
19,531 emitted frames). The six files whose raw rows had no `coordinate_space`
column still scored at the sidecar rung, not the undeclared rung, because the
schema router sends NBA-production-column tables down the sidecar branch before
any declaration is read.

Both facts stated plainly: an `image_px` row **can** pass the `image_px` rung --
it is a correctly declared preserved corpus and that is the honest place for it
to sit. An `image_px` row **can never** pass `court_feet`; the contract rejects
it on the declaration alone, regardless of magnitude. The relabel moved 11 games
from "claims court coordinates it cannot support" to "declares what it is". It
bought zero passes and was never going to.

Denominators: emitted frames equal decoded frames here. `wnba_01` emits frame
ids 0..2997 with 999 unique values over a 100.0 s window at 30 fps, i.e. a
stride-3 decode of the first 2,998 source frames -- 999 of 1,000 sampled
positions produced rows. The clips are 100 s windows of much longer videos
(`wnba_01.mp4` is 28,861 frames); no decode manifest exists on the pod for any
basketball game, so the stride was reconstructed from frame ids and timestamps.

## 3. Render-and-look: the `image_px` label does not describe these pixels

Six frames rendered from three games with detections drawn: red circles at the
declared `image_px` `x/y`, green boxes at the source-plane `bbox_x1..bbox_y2`
from the wide backup. Pod log `/tmp/t3_bb_render_2026-09-01.log`.

The green boxes land on real people. The red points do not -- they sit on crowd,
on empty floor, on the scoreboard, or off the frame entirely. In
`wnba_04_f000600.png` all five points are outside the image and only appear
because the renderer clamps them to the border.

| frame | source | image_px points | inside the frame |
|---|---|---:|---:|
| wnba_01_f000300 | 1280x720 | 5 | 3 |
| wnba_01_f001500 | 1280x720 | 6 | 3 |
| wnba_04_f000600 | 1280x720 | 5 | 0 |
| wnba_04_f001800 | 1280x720 | 5 | 0 |
| ncaa_zqBCKovJCQU_f000300 | 1920x1080 | 7 | 4 |
| ncaa_zqBCKovJCQU_f001500 | 1920x1080 | 6 | 3 |

Corpus-wide, over the 8 games whose footage still exists
(`t3_bb_containment_result.json`, pod log `/tmp/t3_bb_containment_2026-09-01.log`):

**7,514 of 32,355 declared `image_px` points lie inside their own decoded frame
-- 23.22%. Eight of eight games FAIL; two score 0.0000.** `x` reaches 3,396 px on
a 640x360 clip; `y` reaches 1,710 px on a 720p clip.

These are the pipeline's `map_2d` minimap-canvas pixels. The frozen harness
already says so in its rejection text; `run_clip.py` stamps that canvas
`image_px`. The declaration gate is magnitude-independent by design, so nothing
in the contract can see the difference between the image plane and a derived
canvas -- the relabel was correct that these are not court coordinates, and
wrong that they are image pixels.

Shipped check: `scripts/platformkit/tracking/image_px_containment.py` scores
only `image_px` rows against the resolution read from the video itself and
fails below a 0.99 inside share. `test_image_px_containment.py` -- 5 passed.
The shared/gated fix is written up, not applied, in
`docs/research/organization-sprint/PROPOSED_basketball_shared_2026-09-01.md`.

Basketball anchors were used as validators only. The FT circle (6.00 ft), the
arc (22.146 ft) and midcourt (x=47 ft) appear nowhere in this work; the only
reference used is the source resolution read from the decoded video.

## 4. Not verified

- 3 of 11 games (`wnba_03`, `wnba_kangps_g1`, `wnba_kangps_g2`) have no footage
  on the pod, so their containment is unmeasured. The 23.22% covers 32,355 of
  103,009 corpus rows.
- `ncaa_basketball_IB-_u4gW3ds` has both a 640x360 and a `_1080p` copy; the
  sweep scored the 360p one. Its `max_x` of 3,396 px overflows either, so the
  FAIL stands, but its 0.0000 share is resolution-ambiguous.
- The `map_2d` reading is inferred from the harness text, `run_clip.py`'s
  comment, and the geometry (values exceed frame dimensions; correlation with
  bbox centre x is 0.065). The producing code path was not traced to the canvas
  it writes.
- The 30 games the lane asked for do not exist: the whole basketball corpus is
  11 tracked games. Nothing was extrapolated to a larger n.
- The relabel is offline post-processing. The daemon keeps running the old code;
  no daemon change was made or proposed here, so a re-track of any basketball
  game will re-emit the same `map_2d`-as-`image_px` rows. **Daemon change
  pending.**
