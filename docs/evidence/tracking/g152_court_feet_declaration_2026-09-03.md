# G152 - tennis `court_feet` declaration trace

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A7, B1-B10,
and Q8. Local-only code-reading and premise measurement; no pod, SSH, table,
adapter, solver, harness, coordinate contract, threshold, or verdict changed.

## Verdict

**CLOSED AT LIMIT - premise FALSIFIED (Q8).** The required local reference
directory, `data/videos/reference/`, is absent. `Test-Path` returned `False`;
the local `data/videos/` listing contains only `youtube_cookies.txt`, not a
tennis clip. Therefore this lane has no decoded frames, cannot run the adapter
on the required source, and cannot truthfully produce the requested five
failed-frame renders.

The code trace nevertheless resolves the central mechanism: a tennis output
table's `court_feet` declaration is **not conditional on a court solve, a
rally view, a keypoint count, confidence, or player detection.** It is stamped
unconditionally after `process_video()` finishes. Those geometry conditions
only determine whether projected rows are emitted before the table is stamped.

## Premise measurement and requested rates

| Item | Local result | Interpretation |
|---|---:|---|
| Reference clip directory | absent | `data/videos/reference/` does not exist. |
| Local reference-tennis video files | 0 | No source can be decoded locally. |
| Decoded-frame count | not measurable | There is no clip, so no decoder was run. |
| Declaration rate over all decoded frames | not measurable (`0/0`) | This is deliberately not reported as 0 pct. |
| Declaration rate over rally frames only | not measurable (`0/0`) | There is no rally-frame set to classify. |
| Failed-frame renders | not available | No source frames exist; see [render availability note](g152_declaration/README.md). |

G34's 125/300 rally-share result describes a different retained historical
clip. It is not applied to an absent local clip and cannot supply either G152
rate.

## Complete table-declaration path

This is the exhaustive enumeration of conditions that decide whether the
current tennis adapter returns a table carrying the `court_feet` declaration.
There are no geometry conditions in this list.

| # | Deciding code | Condition | What makes it fail on a real clip |
|---|---|---|---|
| D1 | `domains/tennis/tracking/adapter.py:204-206` - `capture = cv2.VideoCapture(...)` then `if not capture.isOpened(): raise FileNotFoundError(...)` | The input must open. | A missing, unreadable, or unsupported video prevents any output table from being returned. |
| D2 | `domains/tennis/tracking/adapter.py:257-260` - `self.last_output = stamp_court_space_rows(pd.DataFrame(rows, columns=SCHEMA), "tennis")` | `process_video()` must reach its post-loop return path. | An unhandled processing error would prevent a result; an ordinary end-of-stream simply exits the loop and still reaches this call. |
| D3 | `scripts/platformkit/coordinate_provenance.py:57-68` - `spaces = SPORT_COORDINATE_SPACES.get(sport)` and `return _stamp(rows, sorted(spaces)[0], HOMOGRAPHY)`; tennis is mapped to `COURT_FEET` at lines 20-25. | The fixed sport key must be `tennis`. | It cannot fail for the adapter's hard-coded `"tennis"`; an unknown sport key would raise instead. |

The empty-output behavior is explicit rather than an inference: `_stamp()`
adds all provenance columns in its `if result.empty` branch
(`coordinate_provenance.py:32-48`). A local no-geometry probe passed an empty
five-column DataFrame to `stamp_court_space_rows(..., "tennis")` and returned
0 rows with these eight columns:

```text
frame,track_id,cls,x,y,coordinate_space,observation,calibration
```

Thus a readable clip that decodes zero useful frames, detects no court, or
detects no players still returns a declared (possibly header-only) output
table. `write_csv()` then includes the complete provenance extension whenever
the columns are present (`coordinate_provenance.py:71-88`).

## Geometry path, separately: conditions for projected row emission

The following exhaustive path is included because it is what a re-track needs
for *geometry-backed player or ball rows*. It does not control D1-D3 above or
the table declaration.

| Stage | Deciding code | Required condition | Why it can fail on broadcast footage |
|---|---|---|---|
| Frame selection | `adapter.py:215-225` | The frame must satisfy `source_frame % stride == 0`; only evaluated frames call `_calibrated_homography`. | A non-selected frame is recorded as `skipped_stride` and has no solve attempt. |
| Court evidence pass | `court_lines.py:237-250` | At contrast 45 or 60, Hough must return segments; the first accepted contrast wins. | A close-up, replay, graphic, crowd shot, or low-contrast court view can leave no thin bright line segments at both fixed contrasts. |
| Oriented evidence | `court_lines.py:99-109, 138-144` | At least 2 horizontal and 2 vertical segments, then at least 4 horizontal clusters and 5 vertical clusters. | Occlusion, framing, shadow, or fragmented markings can leave too few usable directions or clusters. |
| Width-role geometry | `court_lines.py:63-81, 145-150` | The vertical positions must contain 5 of at most 14 clusters whose cross-ratio deviations are at most 0.05. | Non-court lines, missing sidelines, or perspective positions inconsistent with the court template leave no valid five-line subset. |
| Length-role geometry | `court_lines.py:152-191` | Candidate horizontal crossings must fit one allowed far/service/net/near template and its position windows at the same cross-ratio tolerance. | Baselines or service lines outside frame, clutter, or bad line extent leaves no role assignment. |
| Corner solve | `court_lines.py:198-228` | Four named intersections must exist in depth order; `findHomography` must return; skew, image-bounds, and far-right consistency checks must pass. | Parallel/noisy fitted lines, a non-behind-baseline view, off-image corners, or a predicted far-right corner not supported by the image rejects the solve. |
| Temporal fresh solve | `adapter.py:146-167`; `keypoint_calib.py:175-195` | The four solver corners become four confidence-1.0 detections; RANSAC needs four inliers, a finite homography, mean reprojection error no greater than the tennis calibrator's 8.0 drift threshold, and a current-to-prior probe displacement no greater than 8.0. | A geometrically unstable solve, RANSAC rejection, excessive reprojection error, or camera change beyond the tolerance returns no fresh homography. |
| Lock reuse | `camera_lock.py:13-15, 174-204` | Without a fresh solve, an existing lock needs at least 3 prior fresh solves, at least 2 detected current-frame intersections, and median drift at most 5.0 px scaled to frame height. | After cuts or on a view without two supporting intersections, reuse is unavailable rather than assumed. |
| Player rows | `adapter.py:178-197, 227-235` | A returned homography and one valid detector box in each court half are required. | Player confidence below `tracker_conf`, invalid boxes, missed players, or both detections projecting to one half produces no player pair. |
| Ball rows | `adapter.py:236-237, 251-256`; `ball.py:192-250` | A calibrated frame must produce a motion candidate that survives confidence, jump, and isolation checks before projection. | Motion from players/camera, ambiguity, a low-confidence candidate, or an isolated/impossible jump leaves no ball row. |

The solver has no separate learned-keypoint confidence floor in this adapter:
`_stable_homography()` constructs each of its four corner detections with
confidence `1.0` (`adapter.py:156-158`). The active confidence requirement is
therefore the temporal calibrator's default `min_conf=0.3`
(`keypoint_calib.py:143-153`), which those forced values pass whenever the
court solver supplied four corners.

## Re-track implication

To create a table with `coordinate_space=court_feet`, **nothing has to change
in the existing declaration path**: any successfully opened input that returns
from the adapter is stamped as `court_feet`, including an empty result. A
declaration alone therefore does not demonstrate that the clip contained
usable geometry.

To create a table with actual projected, geometry-backed rows, a re-track must
instead supply enough selected rally-view frames for the unchanged frame-level
geometry path above to pass. That is the only point at which the G34
rally-view constraint is relevant. This lane cannot measure its yield on the
specified local source because that source is absent.

## Verifier-contract self-check

### A

- **A1:** No code was added or changed, so no new per-file test exists.
- **A2:** The premise result was reproduced locally by direct filesystem check
  and the empty-table declaration was reproduced by direct local function call.
  No unavailable clip metric is quoted.
- **A3:** No source frame exists, hence there is no decision set from which to
  head-slice a render. No render claim is made.
- **A4:** The relevant local unit is a reference video file; the scoped
  enumeration found zero such files, not a recycled row or track-id count.
- **A5:** Evidence only; no field was changed. The declaration writer and its
  adapter caller were traced, and `adapter_run.py:108-117` was read as the
  normalized writer path.
- **A6:** This worktree commit uses explicit pathspecs only. No archive landing,
  deployment, or pod action occurred.
- **A7:** Checked before commit: this memo,
  `g152_declaration/README.md`, G152 spec, verifier contract, adapter,
  court solver, temporal calibrator, camera lock, provenance writer, and
  `adapter_run.py` all exist. The absent `data/videos/reference/` is the
  measured negative premise, not claimed as an evidence artifact.

### B

- **B1:** Clear. No rate is calculated after dropping failed rows; both
  requested rates are explicitly undefined because the denominator is 0.
- **B2:** Clear. No schema, status, field, or reader changed.
- **B3:** Clear. No gate changed; absent source evidence is reported as absent,
  not classified as bad footage or a solver failure.
- **B4:** Clear. No claim, queue, retry, or ownership code changed.
- **B5:** Clear. No pod, SSH, deployment, copy, restart, kill, or re-track was
  attempted.
- **B6:** Clear. No module, import, command, or test moved or retired.
- **B7:** Clear. No source renders exist and none is presented as evidence.
- **B8:** Clear. No fitted residual or independent-performance claim is made.
- **B9:** Clear. No rate or recycled denominator is claimed.
- **B10:** Clear. No threshold, gate, contract, or verdict was changed.

## NOT VERIFIED

- The decoded-frame count, all-frame declaration rate, rally-only declaration
  rate, and five failed-frame eye checks on the specified local reference clip.
- Whether any particular real clip reaches the fresh-solve or camera-lock gates.
- The rate at which a re-track produces geometry-backed rows; no table was
  written and no tracking run was performed.
- Any downstream jump-gate or quality result.
- No focused test was run because no code was added; no full test suite was run.
