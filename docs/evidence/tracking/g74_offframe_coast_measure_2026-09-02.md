# G74 geometric off-frame/coast measurement - 2026-09-02

This result is scoped to one tracking table, `test720_4MoMewm2j-o`, and its one source clip only. It does not generalize to basketball, other clips, or `wnba_04`. The table's `run.log` identifies the input as `test720_4MoMewm2j-o.mp4` (the render is BKN versus NYK), not `wnba_04`; the claimed `wnba_04` bench/crowd latch therefore remains unmeasured.

## Read-only input and definition

- Source table: `/workspace/nba-ai-system/data/tracking/test720_4MoMewm2j-o/tracking_data.csv`.
- Table SHA-256: `93935e4140b863276c1627d05f160c23ca72dca62d1e7584ab98249c62b2158d`.
- Actual count read: 29,830 rows, all geometrically evaluable. The live schema has 67 columns, including `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2`, and `player_id` as its track field. The older 69-column description is not used as a denominator.
- Frame bounds: 1280 x 720. `run.log` records `/root/nba_videos/test720_4MoMewm2j-o.mp4`, which is unavailable after pod reallocation. Bounds and read-only renders came from the same-named archived copy at `/workspace/nba-ai-system/data/videos/full_games/test720_4MoMewm2j-o.mp4`, opened with `cv2.VideoCapture`.
- Geometric definition: a row is off-frame when the bbox minimum x or y is below zero, or its maximum x exceeds 1280 or maximum y exceeds 720. This uses only bbox coordinates and frame bounds, never the tracker's coast rule.

The table has no `is_coast`, matched-detection, predicted-only, tracker-state, or equivalent field. A pure-coast count is therefore **not evaluable** from this table and was not inferred from the geometric flag.

## Results

The pooled geometric off-frame rate is **7,596 / 29,830 = 25.46 percent** (Wilson 95 percent CI 24.97 to 25.96 percent). This does not reproduce the unmeasured approximate 4 percent assertion, but it is a geometric bbox result, not a Kalman-coast rate.

| track (`player_id`) | off-frame / rows | fraction | Wilson 95 percent CI |
|---:|---:|---:|---:|
| 1 | 715 / 3,004 | 23.80% | 22.31% to 25.36% |
| 2 | 644 / 2,974 | 21.65% | 20.21% to 23.17% |
| 3 | 609 / 2,971 | 20.50% | 19.09% to 21.99% |
| 4 | 616 / 2,773 | 22.21% | 20.71% to 23.80% |
| 5 | 283 / 1,086 | 26.06% | 23.54% to 28.75% |
| 6 | 937 / 3,327 | 28.16% | 26.66% to 29.72% |
| 7 | 952 / 3,385 | 28.12% | 26.63% to 29.66% |
| 8 | 860 / 3,351 | 25.66% | 24.21% to 27.17% |
| 9 | 983 / 3,503 | 28.06% | 26.60% to 29.57% |
| 10 | 997 / 3,456 | 28.85% | 27.36% to 30.38% |

The rate is present on every track (20.50 to 28.85 percent), rather than being concentrated in one pathological track. It does not establish a single cause.

## Mandatory eye check

I rendered and inspected the 12 midpoint-spaced rows in the complete ordered 7,596-row flagged set: no head slice was used. Every image draws the clipped bbox where it intersects the image, or a red edge marker plus the raw bbox when the complete bbox is outside the image.

| source row | finding from render |
|---:|---|
| 1,149 | Studio/warm-up shot; the wholly right-of-frame box has no corresponding player. |
| 2,687 | Bench/huddle personnel, not an in-play player. |
| 4,149 | Studio commentator, not an in-play player. |
| 7,078 | Right-baseline bench/crowd region, not an in-play player. |
| 10,936 | Real player; bbox extends 13 px above the frame while the player remains visible, consistent with bbox overrun rather than an exit. |
| 13,716 | Real player cropped at the right edge. |
| 16,031 | Wholly above-frame box at the scoreboard/top-right area; no player. |
| 18,856 | Real player entering/cropped at the top edge. |
| 20,136 | Real player at the right edge. |
| 22,227 | Official/bench-side person behind the play, not an in-play player. |
| 25,510 | Real player; bbox extends 15 px above the frame, a small top-boundary overrun. |
| 28,287 | Real player cropped at the right edge. |

Thus six of 12 reviewed flags are studio, bench, official, crowd, or graphic latches with no active player; four are real players at a frame edge; two are real-player boxes with a small top-boundary overrun. The looked-at evidence is not a uniform population of genuine player exits. It also cannot establish a pure Kalman-coast rate because the required matched-versus-predicted signal was not emitted.

Durable inputs for recomputation and review are:

- [all 29,830 per-row flags](g74_offframe/per_row_flags.csv)
- [summary and Wilson intervals](g74_offframe/summary.json)
- [the selection and render manifest](g74_offframe/render_selection.json)
- [the 12 rendered rows](g74_offframe/renders/)

## Proposed diff only - not applied

`src/tracking/advanced_tracker.py` is human-gated and was not edited. A future human-approved change should emit an additive per-row association-source field (for example `matched_detection` versus `predicted_only`) and preserve frame dimensions with every re-emitted table. That would make a coast rate observable without defining it from the geometric result. This measurement does not claim that change repairs the non-player/studio latches.

## Verifier self-check

| Contract item | Result |
|---|---|
| A7 | PASS. Every linked CSV, JSON, render directory, and the 12 files named by `render_selection.json` exists before this memo is reported. |
| B1 | PASS. The numerator is evaluated over every one of the 29,830 table rows; no rows were excluded and coast is not inferred from the off-frame flag. |
| B2 | PASS. No production schema or reader changed; evidence-only columns are in a new artifact. |
| B3 | PASS. No gate or absent-evidence behavior changed. |
| B4 | PASS. No claim loop or runtime failure path changed. |
| B5 | PASS. The pod was read-only: inline processes streamed table-derived JSON and JPEG bytes to the worktree; no file was copied or deployed to the pod. |
| B6 | PASS. No module was moved or retired. |
| B7 | PASS. Twelve midpoint-spaced rows cover the ordered 7,596-row decision set from source row 1,149 through 28,287; none is a head-slice-only sample. |
| B8 | PASS. No fitted residual or self-fit is reported. |
| B9 | PASS. Pooled denominator is 29,830 unique table rows; per-track denominators partition those same rows by `player_id`. |
| B10 | PASS. No tracker, harness threshold, verdict, flag, or deployment changed. |

## NOT VERIFIED

- `wnba_04` was not this table or clip, so its asserted bench/crowd latch is unmeasured.
- The original `/root/nba_videos` input is unavailable after reallocation. The same-named archived copy was used for bounds and rendering, but byte identity to the original path was not testable.
- The table does not expose detection association or prediction/coast status; no pure-coast fraction can be claimed.
- Twelve renders are an evenly spread visual sample, not a manual label census of all 7,596 flags. They are one observer's inspection.
- No re-track, tracker modification, threshold change, or pod deployment was performed.

Verdict: **ACCEPT** as a durable, read-only, single-table geometric measurement; the separate `wnba_04` and pure-coast claims remain unmeasured.
