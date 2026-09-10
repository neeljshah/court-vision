# PROPOSED -- G372 claim-time source identity sidecar for track_daemon.py

PROPOSED ONLY. Not applied in the lane, in `/workspace/deploy/nba-ai-system`, or anywhere on the
pod. `scripts/platformkit/track_daemon.py` is a human-gated producer path; this diff exists so a
human can apply it, and phase B (the authorized deploy-only measurement) is what measures it.

The standalone unified diff is committed beside this wrapper as
`PROPOSED_g372_track_daemon_sidecar.diff`, SHA-256
`e0d8e9247d288df0f3a1c033a725b27331d7c3f0818d963bdb1603062d543b6f`; the fenced copy below is the
same bytes. Generated against the DEPLOYED file, SHA-256
`9747d9a085405c492f04c4e3b162ed8b1d897309da6f0f9c014cb7092056f5ac`
(`/workspace/deploy/nba-ai-system/scripts/platformkit/track_daemon.py`, identical to the lane file
after LF normalization, re-confirmed unchanged after the dry-run). `patch --dry-run -p1` run with
the deploy root as cwd applies all 7 hunks cleanly, return code 0, and the edited scratch copy
parses (`ast.parse` OK). Nothing was applied.

fix 1b (this revision): the source handle is now opened AT THE HOOK, on the tick thread, before any
worker is dispatched -- the att1 revision opened it inside the worker, which the codex-sol verifier
filed as a new gap against the spec's "reserve the claim and open the source handle immediately at
the hook".

What it does, and only this:
- Hook at the claim site, strictly AFTER the duplicate handling at 367-372 and strictly BEFORE the
  `subprocess.Popen` at 376, at the `log_path = path.with_suffix(".log")` line (373 in the deployed
  file, confirmed by the archived before-condition output).
- Reserves the claim, journals a RESERVED row, then OPENS the staged source and takes its `fstat`
  size, all on the tick thread at the instant of the claim. The descriptor pins the bytes, so the
  pod volume guard can unlink the path a moment later and both the digest and the metadata probe
  still read the reserved inode (the probe is handed `/proc/<daemon pid>/fd/<fd>`, since ffprobe is
  a child process and `/proc/self` inside it would name ffprobe's own descriptors).
- Only the bounded work -- one streamed digest, one five-second probe -- runs in its own thread,
  mirroring the existing `_begin_adjudication` pattern so the poll loop never waits. A section whose
  binding is still running is skipped for one tick; the sidecar or one terminal diagnostic therefore
  exists before decode launches.
- Adds exactly one field, `source_identity_path`, to the completion-ledger entry (285-323). No
  column, status value, threshold or flag is renamed, removed or moved.
- Route and weight digests are taken once at import, not per claim.
- A terminal binding failure journals a diagnostic, sets the field to None and lets tracking run. An
  open that fails leaves `thread` None and the section passes straight through on the next tick.
  Nothing is quarantined, gated or re-claimed (contract B3/B4).

```diff
--- a/scripts/platformkit/track_daemon.py
+++ b/scripts/platformkit/track_daemon.py
@@ -8,6 +8,7 @@
 
 import argparse
 import csv
+import hashlib
 import json
 import os
 import subprocess
@@ -27,6 +28,10 @@
     sibling_paths,
 )
 from scripts.platformkit.tracking.source_timebase import probe_source, probe_status, stamp_tracking_csv
+from scripts.platformkit.tracking.g372_source_sidecar import (
+    append_claim, bounded_ffprobe, digest_paths, reservation, sha256_stream,
+    terminal_failure, write_sidecar,
+)
 
 STAGE = Path("data/footage_bridge")
 # Where a tracked video goes instead of being deleted. Re-staging one game is
@@ -43,6 +48,22 @@
 PID_FILE = Path("/workspace/track_daemon.pid")
 LEDGER = Path("data/tracking/track_daemon_ledger.jsonl")
 TRACKING = Path("data/tracking")
+# G372: claim-time source identity. The source is opened at the claim and the
+# digest and bounded metadata probe read that pinned descriptor, so a section
+# stays attributable after the pod volume guard prunes its copy from the corpus.
+IDENTITY = Path("data/tracking/source_identity")
+CLAIM_JOURNAL = IDENTITY / "claim_journal.jsonl"
+# Route and weight digests are a property of the process, not of a claim, so
+# they are taken once at import and never re-hashed per section.
+_ROUTE_DIGEST = digest_paths([Path(name) for name in
+                              ("scripts/run_clip.py", "src/pipeline/unified_pipeline.py",
+                               "src/tracking/ball_detect_track.py")])
+_WEIGHT_DIGEST = digest_paths(sorted(Path("data/models").glob("*.pt")))
+_DEPLOY_MANIFEST = hashlib.sha256(json.dumps(
+    {**_ROUTE_DIGEST, **_WEIGHT_DIGEST}, sort_keys=True).encode()).hexdigest()
+# The claim site is a poll loop; a reservation whose bounded identity work is
+# still running waits here for one tick instead of blocking the loop.
+_PENDING: dict = {}
 # A completed upload is not automatically a video. Smallest real staged game
 # measured 29.3 MB; this floor is two orders of magnitude below that.
 MIN_VIDEO_BYTES = 1_000_000
@@ -242,6 +263,55 @@
                                          job["sport"], _BALL[job["sport"]])
 
 
+def _begin_identity(sport: str, game_id: str, video: Path) -> dict:
+    """Reserve the claim and OPEN the source AT THE HOOK, then bind off the loop.
+
+    The open and the fstat run on the tick thread at the instant of the claim,
+    before any worker is dispatched, so the descriptor pins the staged bytes: the
+    pod volume guard may unlink the path a moment later and both the digest and
+    the metadata probe still read the reserved inode. Only the bounded work (one
+    streamed digest, one five-second probe) runs in its own thread, mirroring
+    `_begin_adjudication`; the caller polls `thread.is_alive()`. The reservation
+    row is journaled BEFORE the work starts, so an in-flight or failed claim is
+    never invisible the way a completion-only ledger makes it. A terminal failure
+    records a diagnostic and leaves `source_identity_path` None; tracking is never
+    gated, quarantined or retried on it (contract B3/B4).
+    """
+    sidecar = IDENTITY / (game_id + ".source_identity.json")
+    row = reservation(game_id, sidecar)
+    append_claim(CLAIM_JOURNAL, row)
+    claim = {"game_id": game_id, "sidecar": sidecar, "sport": sport, "thread": None,
+             "claim_utc": row["claim_utc"], "source_identity_path": None}
+    try:
+        handle = video.open("rb")
+        size = os.fstat(handle.fileno()).st_size
+    except OSError as exc:
+        append_claim(CLAIM_JOURNAL, terminal_failure(game_id, sidecar, type(exc).__name__))
+        return claim
+    # ffprobe is a child process, so the pinned path names THIS process's fd.
+    pinned = Path("/proc/%d/fd/%d" % (os.getpid(), handle.fileno()))
+
+    def run() -> None:
+        try:
+            with handle:
+                probe = bounded_ffprobe(pinned)
+                write_sidecar(sidecar, {
+                    "source_path": str(video), "source_sha256": sha256_stream(handle),
+                    "source_bytes": size, "ffprobe": probe,
+                    "crop_rule": "TOPCUT = 60", "route_digest": _ROUTE_DIGEST,
+                    "weight_digest": _WEIGHT_DIGEST,
+                    "deploy_manifest_sha256": _DEPLOY_MANIFEST,
+                    "claim_utc": row["claim_utc"], "daemon_pid": os.getpid(),
+                    "terminal_diagnostic": ""})
+            claim["source_identity_path"] = str(sidecar)
+        except (OSError, ValueError) as exc:
+            append_claim(CLAIM_JOURNAL, terminal_failure(game_id, sidecar, type(exc).__name__))
+
+    claim["thread"] = threading.Thread(target=run, name="identity-%s" % game_id, daemon=True)
+    claim["thread"].start()
+    return claim
+
+
 def _begin_adjudication(job: dict) -> None:
     """Run the unchanged verdict off the poll loop and retain the claim."""
     _prepare_adjudication(job)
@@ -299,6 +369,10 @@
               "coordinate_space": (graded or {}).get("coordinate_space"),
               "rung": (graded or {}).get("rung"),
               "evaluated_at": (graded or {}).get("evaluated_at"),
+              # ADDITIVE: the only new completion-ledger field. Readers that
+              # do not know it are unaffected; None means the binding was
+              # terminal and the claim journal carries the diagnostic.
+              "source_identity_path": job.get("source_identity_path"),
               "seconds": int(finished - job["started"]),
               "finished_at": int(finished)}
     if source:
@@ -370,6 +444,18 @@
             for video in sibling_paths(STAGE, sport, game_id):
                 retain(video, CORPUS, lambda message: print(message, flush=True))
             continue
+        # G372 hook, strictly after duplicate handling and strictly before
+        # subprocess.Popen: reserve the claim and OPEN the staged source here,
+        # on the tick thread, before any worker dispatch. The poll loop never
+        # waits -- an unfinished binding skips this section for one tick, and a
+        # claim whose open failed carries thread None and passes straight on.
+        claim = _PENDING.get(path.name)
+        if claim is None:
+            _PENDING[path.name] = _begin_identity(sport, game_id, path)
+            continue
+        if claim["thread"] is not None and claim["thread"].is_alive():
+            continue
+        _PENDING.pop(path.name, None)
         log_path = path.with_suffix(".log")
         try:
             handle = log_path.open("w", encoding="utf-8")
@@ -383,7 +469,8 @@
                              "sport": sport, "game_id": game_id,
                              "started": time.time(), "source": probe_source(path),
                              "source_variants": [item.name for item in siblings if item != path],
-                             "retained_videos": siblings}
+                             "retained_videos": siblings,
+                             "source_identity_path": claim["source_identity_path"]}
         tracking_active += 1
         print("tracking %s (%s), %d active" % (game_id, sport, len(active)),
               flush=True)
```
