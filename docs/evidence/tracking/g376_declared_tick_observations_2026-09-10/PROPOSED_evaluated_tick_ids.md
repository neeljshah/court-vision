# PROPOSED (not applied) -- make the producer say which ticks it evaluated

`src/**` and `scripts/run_clip.py` are human-gated, so this row applied NOTHING. What follows is a
proposal for a human to apply, with the exact diff. Each is additive: no existing field changes
meaning, no reader breaks, no threshold or flag moves.

## P1 -- `evaluated_tick_ids` in the route sidecar (the field this row was asked to propose)

The producer already holds the exact evaluated frame indices when it returns: every entry of
`results["predictions"]` is appended on the same two lines as the evaluated counter
(`src/pipeline/unified_pipeline.py:2079-2080`, returned at `:3063`). `run_clip.py` already rewrites
the sidecar with the post-run count (`scripts/run_clip.py:226-244`, G331). Writing the ids there
costs one expression and removes the need for every consumer to reconstruct the schedule.

```diff
--- a/scripts/run_clip.py
+++ b/scripts/run_clip.py
@@ def _publish_evaluated_frames(sidecar_path: str, results: dict) -> None:
         side = json.loads(open(sidecar_path, encoding="utf-8").read())
         count = results.get("evaluated_frames")
+        # G376: the ids the count is OF. Without them every consumer re-derives the
+        # schedule arithmetically and over-counts (0.428 / 0.406 of declared ticks were
+        # never evaluated on the two sealed sets).
+        ticks = sorted({int(entry["frame"]) for entry in results.get("predictions", [])
+                        if entry.get("frame") is not None})
         side.update(evaluated_frames=count,
+                    evaluated_tick_ids=ticks,
+                    evaluated_tick_ids_schema="sorted_source_frame_indices",
                     reason=(None if count is not None else side.get("reason")))
```

Size: about 1,000 integers, roughly 7 KB of JSON per section at the current cap. If that is judged
too large, the same information fits in run-length form as
`[[start, stride, count], ...]`; the plain list is proposed because it needs no decoder and no
consumer has to trust a cadence.

## P2 -- carry the capped denominator that ALREADY EXISTS into the ledger

`scripts/platformkit/track_daemon_done.py:121-138` already computes `attempted_frames_capped`, the
frames the route could attempt under its own `--frames` cap, and publishes it in the per-section
verdict. `scripts/platformkit/track_daemon.py:316-318` does not copy it into the ledger entry, so
no ledger consumer can see it. This is the single cheapest correction available.

```diff
--- a/scripts/platformkit/track_daemon.py
+++ b/scripts/platformkit/track_daemon.py
@@
     entry.update(decoded_frames=(graded or {}).get("decoded_frames", manifest_frames),
                  evaluated_frames=(graded or {}).get("evaluated_frames"),
+                 # G376 ADDITIVE: `evaluated_frames` is ceil(decoded/stride) and ignores both
+                 # the route cap and every gameplay/suspension skip. These two fields are
+                 # already in the verdict; nothing above this line changes.
+                 attempted_frames_capped=(graded or {}).get("attempted_frames_capped"),
+                 route_max_frames=(graded or {}).get("route_max_frames"),
                  stride=(graded or {}).get("stride"), probe_status=probe_status(source),
```

## P3 -- the stride the adjudicator declares is not always the stride the producer uses

`scripts/platformkit/tracking_timebase.py:30-37` declares `max(1, round(fps * 0.1))`;
`src/pipeline/unified_pipeline.py:1532-1533` uses a FIXED `_FRAME_STRIDE = 3` below 35 fps. On the
five sealed sections at about 25 fps the adjudicator declared stride 2 against the producer's 3, so
1,000 declared ticks per section fall on frame indices the producer never decoded. NO code change
is proposed here without a human decision, because either side could be the one to move and the
choice changes the harness denominator. The measurement is `classification.csv`, column
`sub_off_producer_lattice`, and the affected sections are named there.

## What this row did NOT do

No file under `src/`, `kernel/`, `api/`, `intel/`, `scripts/run_clip.py` or
`scripts/platformkit/track_daemon*.py` was edited, and no file under `/workspace/deploy` or
`/workspace/data` was written. The controlled re-run redirected the route's own non-fatal SQLite
write (`src/data/db.py:29-31`) into the scratch directory so the deploy tree stayed untouched; that
redirection lives in this lane's `g376_rerun.py` and is not a producer change.
