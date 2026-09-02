# Basketball producer fix: image_px now means source-image pixels

Lane T3b-BASKETBALL-PRODUCER, pod `213.192.2.83:40048`, repo
`/workspace/nba-ai-system`, 2026-09-01. Artifacts in
`docs/evidence/tracking/basketball_producer_fix_2026-09-01/`. Pod access was
read-only apart from two `nohup setsid` jobs of my own writing to `/tmp`;
nothing was killed and `/workspace/track_daemon.pid` was not touched.

## 0. Premise check

Re-ran T3's shipped check locally before touching anything:
`python -m pytest scripts/platformkit/tracking/test_image_px_containment.py -q`
-> **5 passed**. Re-measured on the pod corpus rather than trusting the number:
every one of the 8 games with footage still FAILS containment, and my per-game
`before` figures below are measured this session, not copied.

## 1. The producer, traced

The chain that turns a source-plane foot point into a minimap-canvas pixel and
then declares it `image_px`:

| step | file:line | what happens |
|---|---|---|
| 1 | `src/tracking/advanced_tracker.py:1425-1431` | `kpt = [head_x, foot_y, 1]` is the SOURCE-frame foot point (ankle keypoints, else bbox bottom). `homo = M1 @ (M @ kpt)` warps it frame -> panorama -> `map_2d`; the detection is dropped unless it lands inside `map_2d.shape`. `head_x, foot_y` are never stored. |
| 2 | `src/tracking/advanced_tracker.py:626-640` | `new_pos = (det["homo"][0], det["homo"][1])`, then `p.positions[timestamp] = new_pos`. Same warp-and-drop at `:1306-1311`, `:1649-1654`, `:1693-1698`. |
| 3 | `src/pipeline/unified_pipeline.py:2013, 2031` | `x2d, y2d = p.positions[frame_idx]` -> `track["x2d"]`. |
| 4 | `src/pipeline/unified_pipeline.py:2697-2698` | `"x_position": x2d, "y_position": y2d`. `map_w/map_h` here are `self.map_2d.shape[1]/[0]` (`:786`, `:1368`) -- the rectified court canvas built at `:1097`, default 940x500. |
| 5 | `scripts/run_clip.py:586-595` | stamps the finished table `coordinate_space=image_px`. |
| 6 | `scripts/platformkit/basketball_relabel_image_px.py` (old `_image_pixel_rows`) | copied `x_position -> x`, `y_position -> y`. |

`scripts/platformkit/track_daemon.py:116` is the daemon entry that runs step 5
(`scripts/run_clip.py --video ... --frames 3000 --data-dir ...`).

**Proof of which field is written**, measured on the pod over all 11 basketball
files (`t3b_result.json`, field `x_equals_x_position`): the shipped
`tracking_data.csv` `x`/`y` are element-wise **identical to the `.pre_relabel`
`x_position`/`y_position` on every row of every file** -- 103,009 of 103,009.
Combined with step 4 that is a closed chain: the declared `image_px` values are
the `map_2d` canvas. No local 1-frame `run_clip` was executed; there is no
basketball footage on this 15 GB box and the identity above is stronger evidence
than a synthetic re-run would be. Stated as not-verified, not as done.

## 2. The fix

The producer is `src/**`, human-gated. Its diff is written up and **not applied**
in `docs/research/organization-sprint/PROPOSED_basketball_producer_2026-09-01.md`.

Applied instead, as clearly-labelled post-processing in
`scripts/platformkit/basketball_relabel_image_px.py::_image_pixel_rows`:

- `x`/`y` are the **bbox foot point** `((bbox_x1 + bbox_x2) / 2, bbox_y2)` -- the
  bottom-edge midpoint, in decoded-frame pixels. `bbox_x1..bbox_y2` are the only
  source-plane values the pipeline persists.
- the minimap canvas keeps its own explicit names `map2d_x`/`map2d_y`; it never
  again rides under `x`/`y` with an `image_px` declaration.
- the producer now writes `frame_width`/`frame_height`, read from the video.
- rows with no bbox are dropped, not filled. Row counts were unchanged on all 8
  games, so no row was actually lost.

This recovers the bbox foot point, not the ankle-keypoint foot point the tracker
warped; where ankles were confident those differ by a few pixels. Removing that
approximation needs the gated producer change.

## 3. The gate

`scripts/platformkit/tracking_schema.py::_validate_image_px_containment`, called
from `normalize_tracking_frame` -- the harness intake path. Rows declaring
`image_px` must have **>= 0.95** of their points inside `[0, w) x [0, h)` of the
frame the producer declared, or the file is rejected with
`coordinate_contract: image_px_containment: ...`. A NaN or non-positive declared
dimension counts as outside: a point that cannot be checked has not been shown to
be in the image plane.

`IMAGE_PX_CONTAINMENT_MIN = 0.95`. **No existing threshold moved** --
`image_px_containment.INSIDE_SHARE_MIN` stays at 0.99 for the standalone check,
and every harness sport config is untouched.

The gate only ever *adds* a rejection. A table with no declared dimensions keeps
the old declaration rejection unchanged, which is why no other sport's rung
changed (`test_a_table_without_declared_dimensions_keeps_the_old_rejection`), and
an `image_px` table that clears containment is still rejected as unscorable
(`test_in_frame_rows_clear_the_gate_and_still_fail_on_the_declaration`).

**The gate is not tautological.** Nothing filters rows by the gate's own
criterion; 4 of 8 re-emitted games fail it.

## 4. Rerun on the pod

`/tmp/t3b_run.py`, log `/tmp/t3b_reemit_2026-09-01.log`, raw
`t3b_result.json`. Output written to a NEW dir `/tmp/t3b_reemit/<game>/` --
no daemon output was overwritten. Containment scored against the resolution read
from the video itself.

| game | decoded | points | containment before | after | rung after |
|---|---|---:|---:|---:|---|
| wnba_01 | 1280x720 | 4,855 | 0.4363 | 0.9151 | image_px_containment |
| wnba_02 | 1280x720 | 5,342 | 0.0180 | 0.9672 | declared image_px (corpus lane) |
| wnba_04 | 1280x720 | 4,906 | 0.0000 | 0.9576 | declared image_px (corpus lane) |
| wnba_05 | 1280x720 | 2,230 | 0.0000 | 0.9493 | image_px_containment |
| ncaa IB-_u4gW3ds | 640x360 | 3,061 | 0.0000 | 0.9533 | declared image_px (corpus lane) |
| ncaa sRtHQbywiTE | 1280x720 | 2,234 | 0.8098 | 0.9749 | declared image_px (corpus lane) |
| ncaa tiUvyvWOCxo | 1280x720 | 4,424 | 0.2080 | 0.9424 | image_px_containment |
| ncaa zqBCKovJCQU | 1920x1080 | 5,303 | 0.4848 | 0.9370 | image_px_containment |

Per-rung counts over the 8 games, frozen judge
(`scripts/platformkit/tracking_harness.evaluate`, config `2026-09-01-v1`):

| rung | before | after |
|---|---:|---:|
| no court calibration sidecar | 0 | 0 |
| rows omit `coordinate_space` | 0 | 0 |
| declared `image_px` (corpus lane) | 8 | 4 |
| **`image_px_containment` (new)** | 0 | 4 |
| reached the metric gates | 0 | 0 |
| PASS | 0 | 0 |

**The fix buys zero passes and was never going to.** `image_px` is corpus-only by
contract; what changed is that the corpus is now honest about what its pixels
are, and that four games are visibly rejected for the defect instead of passing
through it unseen.

Resolution: the two games with a second copy on disk (`wnba_01_1080p`,
`IB-_u4gW3ds_1080p`) are separate `game_id`s under
`track_daemon.parse_name`, so the tracked game came from the base file. Scored
against the 1080p copy anyway for completeness: wnba_01 0.9061 -> 0.9489,
IB-_u4gW3ds 0.0947 -> 0.9827 (`t3b_result.json`, `per_video`).

Denominators are decoded frames: `n_points` equals the shipped row count on
every game, and each row is one detection in one decoded frame.

## 5. Render-and-look

`/tmp/t3b_render.py`, log `/tmp/t3b_render_2026-09-01.log`, summary
`t3b_render.json`. Green = the new source-plane `x/y`; red = the old `map2d`
point where it happens to fall inside the frame. Same six frames T3 rendered.

| frame | resolution | points | in-frame before (T3) | in-frame after | on players? |
|---|---|---:|---:|---:|---|
| `wnba_01_f000300` | 1280x720 | 5 | 3 | 4 | yes -- 4 on feet, 1 in the crowd |
| `wnba_01_f001500` | 1280x720 | 6 | 3 | 6 | yes -- all six on players' feet |
| `wnba_04_f000600` | 1280x720 | 5 | 0 | 4 | **no** -- on bench and crowd people |
| `wnba_04_f001800` | 1280x720 | 5 | 0 | 5 | **no** -- near, but off the players |
| `ncaa_zqBCKovJCQU_f000300` | 1920x1080 | 7 | 4 | 7 | partly -- 4 on feet, 1 on the scoreboard graphic, 2 in the crowd |
| `ncaa_zqBCKovJCQU_f001500` | 1920x1080 | 6 | 3 | 6 | partly -- 3 on feet, 3 in the press row |

13/34 -> 28/34 inside the frame. I looked at all six. The honest verdict is that
the points are now in the source image plane, and on the right people in four of
the six frames; the two `wnba_04` frames are tight zoomed shots where the
tracker itself latched onto bench and crowd, and the ncaa misses are false
detections on the scoreboard and press row. **That is tracker-quality, not
coordinate space** -- but it means "points sit on players" is only true where the
detector was right, and I am not claiming more.

## 6. Residual, and why it was not filtered away

The ~4% of points still outside the frame are **Kalman-coasted boxes**:
`src/tracking/advanced_tracker.py:1165` sets `previous_bb = self._kf_pred[slot]`
for a lost track, and the prediction walks off the frame while `confidence`
decays 0.800 -> 0.733 -> 0.667 (= `1 - lost_age/15`). Measured on wnba_01: 412 of
4,855 rows out of frame, across 322 of 999 emitted frames, `max_x` 5,531 px on a
1,280 px frame.

Dropping them would lift every game over 0.95 in one line. It was deliberately
NOT done: filtering rows by the gate's own criterion is exactly the tautological
gate this program has already been burned by
(`tautological_gates_2026_09_01`). A provenance filter -- drop rows whose bbox is
a Kalman prediction rather than a detection -- is an independent criterion and is
the right next producer change; it is listed in the PROPOSED doc, not applied.

## 7. Daemon restart PENDING -- do NOT assume it happened

The daemon keeps running the old code. It was **not** restarted and nothing was
killed. Its live command line, read from
`/proc/$(cat /workspace/track_daemon.pid)/cmdline` (pid 2201564, cwd
`/workspace/nba-ai-system`):

```
python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
```

Restart command, for a human, after stopping the keepalive
(`/workspace/keep_track_daemon.sh`) so it does not race the restart:

```
cd /workspace/nba-ai-system && nohup setsid python -u -m scripts.platformkit.track_daemon \
  --workers 10 --forever --interval 15 > /workspace/track_daemon.log 2>&1 < /dev/null &
echo $! > /workspace/track_daemon.pid
```

Note that restarting the daemon alone does **not** fix new tracking: the daemon
runs `run_clip.py`, whose producer is the gated `src/**` code above. Until the
PROPOSED change lands, a re-track re-emits `map_2d`-as-`image_px` and the new
gate cannot see it, because `run_clip.py` writes no `frame_width`/`frame_height`.
The post-processing emitter is what makes a basketball table checkable today.

## 8. Not verified

- 3 of 11 games (`wnba_03`, `wnba_kangps_g1`, `wnba_kangps_g2`, 70,654 rows) have
  no footage on the pod; their containment is unmeasured, before and after. The
  8 measured games cover 32,355 of 103,009 corpus rows.
- No local or pod `run_clip` re-run. The producer identity is proved by the
  row-for-row `x == x_position` match plus the code trace, not by re-executing
  the pipeline.
- The bbox foot point is an approximation of the ankle foot point the tracker
  actually warped. Unquantified: the ankle values are not persisted.
- `pytest` is not installed on the pod, so the per-file tests ran locally only;
  the pod ran the changed modules end-to-end on real data instead.
- The re-emitted tables are on the pod at `/tmp/t3b_reemit/` and are not promoted
  into `data/tracking/`. Nothing in the corpus was modified.
- Whether the four games that now clear 0.95 would still clear it after the
  Kalman-provenance filter is unmeasured.

## Commands

```
python -m pytest scripts/platformkit/tracking/test_image_px_containment.py -q          # 5 passed
python -m pytest scripts/platformkit/test_tracking_schema_image_px_containment.py -q   # 7 passed
python -m pytest scripts/platformkit/test_basketball_relabel_image_px.py -q            # 1 passed
python -m pytest scripts/platformkit/test_tracking_harness.py -q                       # 17 passed
python -m pytest scripts/platformkit/test_tracking_schema_coordinate_space.py -q       # 3 passed
```
