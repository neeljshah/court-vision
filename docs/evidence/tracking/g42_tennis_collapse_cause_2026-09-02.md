# G42 -- the 2026-09-01 tennis tracking collapse: cause

Status: CAUSE ESTABLISHED (primary), with two measured secondary contributors.
Investigated 2026-09-02. Read-only on the pod except one scratch re-track in /tmp.
No threshold moved, no daemon killed, no pod env changed, no git on the pod.

---

## 1. Premise reproduced

Row counts are `wc -l` on `/workspace/nba-ai-system/data/tracking/<id>/tracking_data.csv`
(header included, matching the premise as stated). mtimes are pod UTC.

| table | lines | mtime (UTC) | header cols |
|---|---|---|---|
| tennis_01 | 9548 | 2026-09-01 06:04:44 | 5 |
| tennis_02 | 2422 | 2026-09-01 06:48:34 | 5 |
| tennis_03 | 5611 | 2026-09-01 07:30:24 | 5 |
| tennis_04 | 7493 | 2026-09-01 07:31:13 | 5 |
| tennis_05 | 4304 | 2026-09-01 07:39:12 | 5 |
| tennis_3x3eEWCZmWQ | 267 | 2026-09-01 17:14:58 | 9 |
| tennis_nyYk2nPZAwY | 416 | 2026-09-01 17:18:36 | 9 |
| tennis_07 | 9 | 2026-09-01 18:58:05 | 9 |
| tennis_08 | 229 | 2026-09-01 18:58:22 | 9 |
| tennis_459iho5_AFs | 1 | 2026-09-01 21:20:21 | 9 |
| tennis_09 | 5 | 2026-09-01 21:20:36 | 9 |
| tennis_06 | 1 | 2026-09-01 21:15:47 | 9 |
| tennis_10 | 1 | 2026-09-01 21:22:22 | 9 |

Every premise figure matches. **The header-width column is the finding.** The
split is exact and has no exception: every healthy table has

```
frame,track_id,cls,x,y
```

and every degenerate table has

```
frame,track_id,cls,x,y,calibration_provenance,coordinate_space,observation,calibration
```

Those four extra columns are written by `write_csv` in
`domains/tennis/tracking/adapter.py`. A different adapter module produced the
two sets. The daemon was not running the same code at 06:04 and at 17:14.

Frame spans (`awk` over the `frame` column) confirm the corpus also changed:

| table | min frame | max frame | rows |
|---|---|---|---|
| tennis_01 | 417 | 28770 | 9547 |
| tennis_03 | 45 | 28236 | 5610 |
| tennis_05 | 138 | 23994 | 4303 |
| tennis_3x3eEWCZmWQ | 1706 | 23844 | 266 |
| tennis_nyYk2nPZAwY | 0 | 12128 | 415 |
| tennis_08 | 208 | 3732 | 228 |
| tennis_07 | 1592 | 7500 | 8 |

---

## 2. Cause

**The tennis adapter stopped emitting a court-coordinate row on frames whose
court solve is not fresh, and that is nearly every frame.**

Commit `f16b3863a` (2026-09-01 10:32:50 -0500 = **15:32 UTC**),
`fix(tennis,soccer): stop labelling stale and ordinal calibration as current`,
lands squarely between the healthy window (ends 07:39 UTC) and the degenerate
window (starts 17:14 UTC). The diff on `domains/tennis/tracking/adapter.py`:

```
-            self._calibration_provenance = "propagated" if self._homography is not None else "unavailable"
-            return self._homography
+            self._calibration_provenance = "unavailable"
+            return None
```

applied at both failure branches (lost corners, and rejected/out-of-tolerance
solve). Before it, a frame with no fresh solve reused the previous frame's
homography and emitted rows stamped as this frame's calibration. After it, such
a frame emits nothing.

The magnitude was measured independently the same day and is recorded in
`docs/TRACKING.md:34`:

> the recorded coverage 0.976 was 99.3% carried-over calibration -- 4 fresh
> solves propagated over 600 frames; honest coverage 0.0067

0.976 / 0.0067 = **145.7x**. That is the order of magnitude of the collapse, and
it is a correction, not a regression: the healthy 06:04-07:39 row counts were
inflated by carried calibration. `docs/evidence/SESSION_2026-09-01_INDEX.md:21`
records the same regime from the other side -- **0 of 725 fresh-solve accepts**
on the nyYk 720p section, measured in the degenerate window itself.

Why re-tracking works today: `1c5f1e6b7` (2026-09-01 19:07:48 -0500 =
**2026-09-02 00:07 UTC**, shadow-invariant court lines + cross-ratio role
selection) and the camera-lock work restored real fresh-solve coverage
(`docs/TRACKING.md`: 599 decoded -> 50 fresh solves -> 5 locks -> 11
drift-checked reuses = 10.18% solved-per-decoded). That commit postdates the
last degenerate write (21:22 UTC) by 2h45m. The pod's
`domains/tennis/tracking/adapter.py` was last written **2026-09-02 02:23:12 UTC**
and contains zero occurrences of `"propagated"` -- it is a post-fix,
post-recovery adapter. So the tracker working today and the tables collapsing
that afternoon are consistent with one timeline, not a contradiction.

### Secondary contributor 1 -- clip resolution (measured today)

Same code, same budget (`--max-frames 600 --stride 3`, 200 processed frames):

| clip | resolution | rows |
|---|---|---|
| tennis_09 | 1920x1080 | 313 (from the task brief) |
| tennis_3x3eEWCZmWQ | 640x360 | **70** (measured this session, `/tmp/g42_3x3e.log`) |

4.5x from resolution alone. `ffprobe` on the pod corpus:
`tennis__tennis_3x3eEWCZmWQ.mp4` and `tennis__tennis_nyYk2nPZAwY.mp4` are both
**640x360**. Those are exactly the two degenerate clips with the highest row
counts (267, 416) -- they were long (960 s) but low-res. Consistent with
`docs/evidence/tracking/tennis_resolution_controlled_2026-09-01.md` (720p
improves the five-cluster gate 3.7x).

### Secondary contributor 2 -- clip length

`tennis_06/07/08/09/10/459iho5_AFs` are all **300 s / ~7500 frames**
(1080p except 07 and 08 which are 720p). The healthy tables span up to frame
28,770, so the healthy sources were roughly **4x longer**. Fewer frames in,
fewer rows out, independent of solve rate.

---

## 3. Ruled out, and how

**(b) daemon restart onto different settings -- RULED OUT as the differentiator.**
`/workspace/track_daemon.log` shows `24 active` in *both* windows: tennis_01..05
were launched at 17-21 active during a cold ramp and relaunched at 24 active;
tennis_06..10 were launched at 24 active. The `--workers 24 -> 10` change
(`f31940ba1`, 06:46 -0500 = 11:46 UTC) never took effect in either window --
the currently running daemon (pid 4035, started 2026-09-02 13:34:46) is the
first to carry `--workers 10`. Its cwd is `/workspace/nba-ai-system`;
`/proc/4035/environ` contains no `CV_*`, `MAX_*`, `STRIDE`, `TIMEOUT` or
`MODEL` variable. `adapter_run.py` takes `--max-frames` default 30000 and
derives stride from `sampling_plan(frame_rate)`; the daemon passes neither, so
neither changed between the windows.

**The 2700s job timeout is real but is NOT the cause of the final row counts.**
`JOB_TIMEOUT_SECONDS = 2700` was introduced by `abdafbec5` (04:49:28 -0500 =
09:49 UTC), i.e. after the healthy runs and before the degenerate ones, and
`track_daemon_ledger.jsonl` shows tennis_06/07/08/09 each killed at ~2701-2714 s
with `rows=0`, twice each. That matters -- every healthy run took **4827, 6482,
8545, 8575 and 8773 seconds**, so under either the 2700 s or the later 3600 s
budget not one of them would have survived. But the tables that actually sit on
disk were written by *later* runs that exited on their own in 90-1216 s with
status `thin`, not `timeout`. The timeout explains why tennis stopped producing
long runs; it does not explain 4 rows out of a 7500-frame clip.

**(c) corpus / staging change -- CONTRIBUTED, but not sufficient.**
`ffprobe` on all nine tennis corpus files: every degenerate source is a valid,
complete h264 mp4 (300.04-960.01 s, `nb_frames` 7252-24024), none truncated or
mis-encoded. The two 640x360 clips and the ~4x shorter clips are real,
quantified contributors (above), but 4.5x x 4x does not reach three orders of
magnitude, and it cannot explain tennis_06/10/459 emitting a header and nothing
else.

**(d) model / weights path -- RULED OUT.** `/workspace/nba-ai-system/yolov8n.pt`
is present; no `CV_DETECTOR_MODEL` is set in the pod environment or in daemon
pid 4035's environ. Detection demonstrably works on the same clips today
(313 rows on tennis_09, 70 on tennis_3x3eEWCZmWQ), and the collapse is in the
court-solve gate downstream of detection, not in the detector.

**cv2 5 -- already retracted upstream, and independently reconfirmed here.**
`RESULTS_LEDGER.md` row 57 retracts it on dist-info timestamps (cv2 5 existed
only 2026-09-02 13:33-14:41). Every table in this investigation predates that by
more than 16 hours.

---

## 4. Why nothing recorded it

The ledger *did* record every run. It could not be read as a timeline:

- `finished_at` was only added by `2de1d706c` (10:07 -0500 = 15:07 UTC), so
  every ledger row for the healthy window and the first degenerate runs carries
  no timestamp at all -- 21 of the 36 tennis rows read `NO_TS`.
- `source_fps`, `source_height` and `source_duration` are `None` on every
  tennis row, so the resolution and duration change was invisible in the ledger.
- The degenerate outcomes were logged as `thin` and `timeout`, which read as
  ordinary bad luck, not as a step change. No process ever compared a table
  against the previous table for the same sport.

---

## 5. Single next action

**Have the daemon record, per run, the adapter's fresh-solve count and the
source resolution alongside `rows`, and fail loud on a step change.** The
mechanism that hid this was not a missing log line -- it was a ledger with no
denominator: `rows=228` is uninterpretable without "out of how many decoded
frames, at what resolution, with how many fresh solves". `adapter_run` already
computes `plan` and `metadata` and already writes `timebase_metrics` into the
harness report; the daemon's `_finish` should copy `solved_frames /
decoded_frames` and `source_height` into the ledger row it writes. One field
group, one comparison against the previous row for the same sport.

(Note for the register: G28b already landed duration-first sibling selection,
which prevents the 640x360 sibling being enqueued over the 720p one -- that
closes the resolution half of contributor 1 going forward. It does not address
the missing denominator.)

---

## 6. NOT VERIFIED

- **The resolution and duration of the tennis_01..05 source clips.** Those mp4s
  are no longer in `/workspace/nba-ai-system/data/footage_corpus/`. The ~4x
  length difference is inferred from the emitted frame span (max frame 28,770
  vs 7,500), not from `ffprobe` on the original files. Their resolution is
  unknown, so the healthy-vs-degenerate resolution delta is not established for
  those five clips.
- **The exact pod deploy time of `f16b3863a`.** `domains/tennis/tracking/adapter.py`
  on the pod carries only its last mtime (2026-09-02 02:23:12), so the
  intermediate deploy cannot be dated from the filesystem. Deploys into the gap
  are evidenced only indirectly: `tennis_court_visibility_probe.py` 15:45:14,
  `tennis_gate_funnel.py` 16:21:31, `tennis_court_gate_probe.py` 16:33:18,
  `detection/shim.py` 18:43:27 -- all UTC, all inside the gap. The causal claim
  rests on the CSV header change, which is direct evidence that the adapter
  changed, not on a deploy log.
- **The exact row-count attribution between the three factors.** 145.7x
  (carried calibration, from `docs/TRACKING.md`), 4.5x (resolution, measured
  this session) and ~4x (clip length, inferred) are each measured or cited
  separately. They have not been measured jointly on one clip, and they are not
  independent, so they do not multiply to a defensible total.
- **Why the task brief's tennis_09 re-track yields 313 rows over 200 processed
  frames (~78% of frames carrying two player rows) when `docs/TRACKING.md`
  records 10.18% solved-per-decoded.** These two numbers are not reconciled.
  The re-track went through `tracking_corpus_worker.py`, the ledger figure came
  from the sequential-plan path. I did not establish whether they measure the
  same denominator.
- **No degenerate run was re-executed under its own contemporaneous code.** The
  pre-`f16b3863a` adapter was never run on the pod during this investigation
  (no git on the pod, and I did not write repo files there), so the 145.7x is
  cited from the repo's own recorded measurement rather than reproduced here.
- **The other seven sports.** Only tennis was examined. Whether the same
  fresh-solve tightening hit soccer's tables in the same window is untested;
  `f16b3863a` touched the soccer adapter too.
