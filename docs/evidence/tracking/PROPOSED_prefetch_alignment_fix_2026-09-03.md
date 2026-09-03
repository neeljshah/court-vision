# PROPOSAL (human-gated, NOT applied): align cached YOLO results to their own frame

**Status: PROPOSAL ONLY. Nothing has been changed.** Both files are inside
`src/`, which is human-gated. This document exists so the user can decide.

## The defect, measured not inferred

G198, three instrumented runs on the pod (`wnba__wnba_01.mp4`, `--frames 1200`):

- All **400 of 400** `get_players_pos` calls were served from the prefetch cache.
- **Every served detection came from source frame `processed + 3`.** The route
  strides by 3, so that is exactly the *next processed frame*.
- Zero unmatched source identities, in all three runs.

**So 100 pct of detections are attributed to the frame before the one they were
computed on.** At 30 fps and stride 3 that is about 100 ms of real motion. On a
panning broadcast camera every box shifts together, which is the condition under
which association degrades worst.

## Why it happens

| site | what it does |
|---|---|
| `unified_pipeline.py:1673` | `ok, frame, _fi = _prefetcher.read()` at the TOP of the loop, so while frame `k` is processed the queue head is already `k+1` |
| `unified_pipeline.py:1899-1903` | later in the SAME iteration, and only when the buffer is empty, calls `_prefetcher.peek(7)` and hands those frames to `prefetch_yolo` |
| `unified_pipeline.py:301-311` | `peek` snapshots `list(self._q.queue)[:n]` and **returns bare frames, discarding `_fi`** |
| `advanced_tracker.py:409-454` | runs YOLO on them and `extend`s `_yolo_result_buf`, a `deque(maxlen=16)`, **with no frame identity attached** |
| `advanced_tracker.py:1194-1200` | pops the first cached result and uses it for whatever frame is current |

The root cause is one thing: **the cache stores results without recording which
frame produced them**, so nothing downstream can check the pairing.

## The proposed change, smallest version that fixes it

1. `peek` returns `(frame_idx, frame)` pairs instead of bare frames. It already
   has `_fi` in hand and throws it away.
2. `prefetch_yolo` stores `(frame_idx, results, ran_pose)` in `_yolo_result_buf`.
3. `get_players_pos` serves a cached entry **only when its `frame_idx` matches
   the frame being processed**. On a mismatch it discards the entry and runs
   inference on the current frame, which is the existing fall-through path.

That is additive to the data carried, changes no threshold, no model, no
detector parameter and no coordinate contract.

## What I am NOT claiming

- **This is not proposed as a determinism fix.** G198 measured the bypass arm --
  cache never populated, `cudnn.benchmark=False` -- as **still varying across
  three runs**, so the cache is eliminated as the cause of route
  non-determinism. Anyone who reads this as "fixing this makes the route
  reproducible" has read it wrong.
- **This is not measured to improve tracking quality.** It removes a systematic
  100 ms association error, and it is reasonable to expect that helps, but no row
  has measured survivor counts or coverage before and after. That measurement is
  what should justify the change, and it cannot be run until the fix exists.
- **The performance cost is real and unquantified.** Point 3 will cause a cache
  miss and a fresh inference on any frame whose cached entry does not match.
  Under the currently measured behaviour every entry is off by one, so a naive
  reading is that the cache stops helping entirely and throughput drops toward
  the bypass arm's. **Fixing the pairing at the source (points 1 and 2) is what
  restores the hit rate**; point 3 alone is a correctness guard, not the fix.

## Suggested sequence if approved

1. Apply points 1-3 together, not point 3 alone.
2. Re-run the G198 instrumentation to confirm the measured offset becomes 0 and
   the cache-hit rate stays near 100 pct.
3. Only then measure survivor counts and coverage against the pre-fix baseline,
   on the corrected denominator, and report the difference as a distribution over
   repeats rather than a single run (the route is still non-deterministic).

## Also awaiting the user, unrelated to this fix

`scripts/run_clip.py:581` states in a comment that a per-clip homography "is
solved in memory and discarded". **G192b and G194 both measured that nothing is
solved** -- the solver returns `None` on 17 of 17 corner-visible frames and the
pipeline falls back to the static `Rectify1.npy`. That comment sent both an
adversarial review and me toward a fix that does not exist and cost a full row to
disprove. It needs correcting.
