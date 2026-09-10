# G376 -- the evaluated-tick rule, reconstructed from the code, with file:line

Every citation below was re-read at the pod worktree `/workspace/wt/a12` this session and lands on
the cited code. The two route files are BYTE-IDENTICAL between that worktree and the deployed tree
`/workspace/deploy/nba-ai-system` (A11):
`src/pipeline/unified_pipeline.py` sha256 `c4eae385bfeebd4e44c8161c791ef7ed4589697020f424d3dde7aec6816d9226`,
`scripts/run_clip.py` sha256 `ccd08d32c8c4cb8625ec5ef67535206f74f4df307a8e191ec01f5700fb40d8c2`.
Also read: `scripts/platformkit/track_daemon.py` `9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac`,
`scripts/platformkit/track_daemon_done.py` `75cbff79cd115952ad14f76c94ab5fdb62239f30841b06e73b967473a2d69f70`,
`scripts/platformkit/tracking_timebase.py` `0dc67ff28e40e1c8b1dba9b191ea5f61d3b15f8904167402c54e9e75c2e2300c`.
Nothing under `src/`, `scripts/run_clip.py`, `scripts/platformkit/track_daemon*.py` or the deploy
tree was edited; they were read and imported only.

## A. DECLARED -- what the ledger says was evaluated, and what G370 counted

1. `scripts/platformkit/tracking/g370_manifest.py:31-36` expands the ledger cadence to frame
   indices: `[index * stride for index in range(evaluated_frames)]`. That set is the DECLARED
   tick set of this row, taken verbatim by import.
2. The ledger fields come from the harness verdict, written by the daemon at
   `scripts/platformkit/track_daemon.py:316-318` (`decoded_frames`, `evaluated_frames`, `stride`).
3. The verdict computes them WITHOUT consulting the producer:
   `scripts/platformkit/track_daemon_done.py:141-149` returns
   `range(0, min(decoded, stride * 30000), stride)` and
   `:203-209` sets `evaluated_frames = len(denominator)`. So
   `evaluated_frames == ceil(decoded_frames / stride)` for every section in both sets.
4. That `stride` is the ADJUDICATOR's sampling plan, not the producer's:
   `scripts/platformkit/tracking_timebase.py:30-37`, `stride = max(1, round(frame_rate * 0.1))`
   with `TARGET_SAMPLE_SECONDS = 0.1` at `:13`.

DECLARED is therefore a pre-tracking arithmetic statement about the SOURCE, and carries no
information about what the producer did.

## B. SCHEDULED -- what the producer actually evaluates

1. STRIDE. `src/pipeline/unified_pipeline.py:1532-1533`:
   `_base_stride = max(_FRAME_STRIDE, round(fps / 10.0)) if fps > 35 else _FRAME_STRIDE`, then
   `_stride = _base_stride if total_video_frames > _FRAME_STRIDE_THRESH else 1`, with
   `_FRAME_STRIDE = 3` (`:378`) and `_FRAME_STRIDE_THRESH = 3000` (`:381`).
   Below 35 fps the producer stride is a FIXED 3, whatever the frame rate; the adjudicator's is
   `round(fps * 0.1)`. The two disagree whenever `round(fps * 0.1) != 3` under 35 fps.
2. LATTICE. `src/pipeline/unified_pipeline.py:271-278`: the prefetcher decodes a frame only when
   `(_fi - start_frame) % self._stride == 0`, so the producer can only ever emit on multiples of
   its own stride (`start_frame = 0` on this route).
3. GAMEPLAY GATE. `:1700` `if not self._is_gameplay(frame, frame_idx): continue` -- the frame is
   dropped with NO row of any kind. `_is_gameplay` (`:996-1036`) runs a person detector and caches
   both verdicts for `_GAMEPLAY_CACHE_FRAMES`, so a negative decision skips a whole window.
4. SUSPENSION. `:1836-1853`: while `self._ball_track_suspended` the frame is hard-skipped after
   writing ONE ball row with `live = 0`, then `continue`. It never reaches the evaluated counter.
5. ROUTE CAP. `scripts/run_clip.py:417` passes `--frames` as `max_frames`;
   `src/pipeline/unified_pipeline.py:1536-1537` rescales it to EVALUATED units
   (`self.max_frames = max(1, self.max_frames // _stride)`) and `:1680` breaks the loop once
   `gameplay_frames >= self.max_frames`. The cap counts EVALUATED frames, so the run stops after
   N evaluated frames wherever in the source that happens to fall -- not at source frame N.
6. THE COUNTER. `:2079-2080` `predictions.append({"frame": frame_idx, ...})` immediately followed
   by `gameplay_frames += 1`, returned as `"evaluated_frames": gameplay_frames` at `:3063`.

## C. Why the producer's own count never reaches the ledger

`scripts/run_clip.py:159-163` mirrors the producer stride and `:203-209` writes
`evaluated_frames = ceil(decoded_frames / stride)` into `evaluated_frame_count.json`, but only when
`max_frames is None`; with a cap it writes `null` and the reason
`max_frames_is_detector_dependent_in_this_route` (`:191-193`). `:226-244`
(`_publish_evaluated_frames`, G331) then rewrites that sidecar with the producer's true
`results["evaluated_frames"]`. The daemon does NOT read that field: it takes
`evaluated_frames` from the harness verdict instead (`track_daemon.py:316-318`), and the verdict
recomputes it arithmetically (section A3). The adjudicator does compute the capped figure --
`attempted_frames_capped` at `track_daemon_done.py:121-138` -- but `track_daemon.py:316-318` does
not carry that field into the ledger entry, so the one corrected denominator that already exists
never reaches any consumer of the ledger.

## D. What the tables make observable

- `ball_tracking.csv` carries exactly one row per frame that reached the tracking body:
  `live = 1` on an evaluated frame (`src/pipeline/unified_pipeline.py:1991-2001`) and `live = 0`
  on a suspended frame (`:1836-1849`). Both appends are unconditional on their branch and no
  outer-loop `continue` separates `:1991` from the counter at `:2079-2080` (the two `continue`
  statements at `:2021` and `:2023` are inside the per-player loop). The `live = 1` frame set is
  therefore the producer's evaluated tick set, and this row uses it as the RECONSTRUCTED SCHEDULE.
- `tracking_data.csv` gets a row ONLY per surviving non-referee track, capped at 12 per frame
  (`:2657-2662`). An evaluated frame whose detections are all referees, or empty, leaves no player
  row at all. That is the class SCHEDULED_NO_DETECTION.
- PRODUCER STRIDE, as measured: the modal positive gap of the reconstructed evaluated frame set,
  via the landed `g331_evaluated_frames_sidecar.modal_gap` (imported). It is the producer's own
  emitted cadence rather than a re-derivation of the constants, and it is what the sub-reason
  `OFF_PRODUCER_LATTICE` is decided against.

## E. The rule in one line

The producer evaluates `frame % producer_stride == 0` AND gameplay-gated AND not suspended AND
before the evaluated-frame cap; the ledger declares `ceil(decoded_frames / adjudicator_stride)`
ticks at `index * adjudicator_stride`, an arithmetic statement that consults none of those four
conditions.
