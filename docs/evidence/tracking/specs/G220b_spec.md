GAP G220b | sport ncaa_basketball / soccer (amateur tier) | worktree a5 | log g220b_amateur_footage_local_slice
**ACQUISITION AND CLASSIFICATION ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only.
`scripts/platformkit/footage_bridge.py` is READ ONLY -- you may reuse its constants and helpers, **do not
edit it.** Build in `scripts/platformkit/tracking/`.

**READ `docs/evidence/tracking/specs/G220_spec.md` AND
`docs/evidence/tracking/g220_amateur_footage_acquisition_2026-09-04.md` FIRST.** This row inherits
G220's candidate list, budget discipline, disk guards, rubric and honesty requirements unchanged. **The
lane that ran G220 behaved correctly and acquired nothing; the route it was told to use is blocked.**

**WHY G220 GOT ZERO, AND IT IS NOT THE LANE'S FAULT.** All six candidates returned **`Requested format
is not available`**. **Cause, verified by the orchestrator: `data/videos/youtube_cookies.txt` is ZERO
BYTES** (mtime 2026-09-02 21:25). `footage_bridge.py:283-286` documents the consequence precisely --
WITH cookies the ladder uses the default player client; **WITHOUT cookies it forces
`player_client=web`, which the comment says "now yields ZERO media"** -- and :117-122 records that this
client otherwise exposes only itag 18 at **640x360**. **So bounded SECTION downloads are blocked until
someone refreshes the cookie file, and even a successful one would have been 360p.**

**THE WORKAROUND THIS ROW USES, and the evidence it rests on: WHOLE-FILE downloads are NOT blocked.**
Roughly **27 GB of footage arrived through the bridge earlier the same night with this same empty cookie
file**, so the whole-file ladder works. **Therefore: download the whole file LOCALLY, slice a bounded
section LOCALLY with `ffmpeg -c copy`, and upload only the slice.** The pod receives the same small
artifact G220 intended; only the fetch path changes. **The local disk has 904 GB free, so local space is
not a constraint; the POD volume still is.**

**S1 MACHINE: LOCAL for download and slicing; the POD receives only the finished slices.** G211 is
measuring per-frame cost on the pod -- **your uploads are bounded disk writes, not route jobs, and G216
established that read/write bandwidth is not this route's bottleneck, so a bounded upload is acceptable.
Record the pod load you observed when you began.** The `track_daemon` and its `adapter_run` jobs are
PERMANENT residents and the load floor, **not** a reason to wait; never kill or restart them.

**THE CANDIDATES, unchanged from G220 -- use THESE SIX and never a substitute**, so what lands is what
was reviewed. An id that no longer resolves, is region-blocked or age-gated is a NORMAL outcome: record
it with the error and move on.

    | youtube id | duration s | listed height | what it is | gap category targeted |
    |---|---:|---:|---|---|
    | `jh3fnwMi7dM` | 8845 | 1080 | Coaches Camera, Lorain vs Bedford HS boys varsity | **fixed camera + amateur/HS** |
    | `qpZfGp_fScU` | 4190 |  720 | Bismarck HS varsity at Dickinson, full game | amateur/HS |
    | `1MwO3CDkeeM` | 1858 | 1080 | Bremen at Triton, 5th grade boys | amateur, youth, likely dim gym |
    | `3asBuhRd_LI` | 1772 | 1080 | Pella 8th grade boys vs Newton (main gym) | amateur, youth, school gym |
    | `lAs8JaoWNwg` | 4770 |  720 | GACS mens soccer, sideline camera | **fixed camera + amateur, soccer** |
    | `XwpLBtt1G2g` | 3869 | 1080 | Nepean Hotspurs U15-16, full match | amateur youth soccer |

**BINDING BUDGET -- stop at it rather than negotiating with it:**
  - **LOCAL download cap: 20,000 MB total.** Check the running total after every file and **STOP at the
    cap**, reporting what you skipped.
  - **POD upload cap: 4,000 MB total** (unchanged from G220). One 16-minute slice per candidate.
  - **Prefer 720p to keep both totals down.** Request at most 1080p; **record the height you ACTUALLY
    got for every clip.** **A 360p result must be reported as a failure of this row, not quietly
    accepted** -- but note that unlike G220, whole-file downloads should offer real formats, so 360p
    here would mean something different and worth saying.
  - **DELETE every locally downloaded whole file once its slice exists**, and report bytes freed
    locally as well as on the pod.
  - **DISK GUARD on the pod, BINDING:** `df` is NON-AUTHORITATIVE (it reports the whole cluster
    filesystem against a 50 GB volume cap, which caused a `Disk quota exceeded` incident). **Before and
    after each upload, do a real `dd conv=fsync` write probe of a few MB and record
    `du -sm /workspace/nba-ai-system/data` (baseline ~31,000 MB of 50,000). If a probe fails, STOP and
    report -- do not delete anything to make room.**
  - **Do NOT resume the general acquisition loop, the watchdog, or the bridge supervisor.** One-shot
    targeted fetch only.
  - **Bound every external command with a timeout so a hang is RECORDED rather than parked** -- G220 did
    this well and it is why its null result is trustworthy.

METHOD:
  1. Download each candidate whole, locally, within the local cap. **State the format rung used and the
     height obtained.** Reuse `footage_bridge.py`'s format rungs where they apply; **do not pass its
     `SECTION_CLIENT`, which is the thing that breaks without cookies.**
  2. Slice **one 16-minute section** per clip locally with `ffmpeg -ss <start> -t 960 -c copy`, using the
     same offset policy as the bridge's `plan_section` (`footage_bridge.py:308-318`) so the slices are
     comparable to what G220 would have produced. **`-c copy` re-encodes nothing; confirm the slice is
     readable with `ffprobe` and record its duration and height.**
  3. Upload only the slices to the pod, within the upload cap and behind the disk guard.
  4. **Run `footage_content_gate.py` on each slice and report its verdict.** It is fail-open and an
     ingest decision only -- **say explicitly that it must never touch a metric denominator**, which is
     its own module docstring's rule.
  5. **Classify each acquired slice against G213's rubric, using G213's categories unchanged**, from
     **5 evenly spaced single-frame seeks** (`ffmpeg -ss ... -frames:v 1`), never a full decode. Commit
     the frames, downscaled.
  6. **Then answer the question this whole line of work exists for: which of G213's ZERO-representation
     categories now have at least one example, and which are STILL zero?** Quote G213's list exactly --
     zero handheld game-camera; zero fixed **single-camera** game footage (tennis's fixed-wide broadcast
     explicitly does NOT count); zero **amateur/high-school direct field/court camera acquisition** (the
     corpus's one amateur item is a desktop-commentary screen capture, not a game camera); zero
     graphics-free; zero high surface visibility; zero dim-gym. **"We fetched six clips and the corpus
     is still monolithic" is a FULL SUCCESS if that is what the frames show** -- for instance if
     "Coaches Camera" turns out to pan after all.
  7. **These are single-labeller eye judgements with no second labeller, exactly as G213's were. Say
     so.** Where a clip is ambiguous, say ambiguous. **Do not infer capture style from the title** -- a
     title is a hypothesis and the frames are the evidence.

**DO NOT track these clips, run the route on them, add them to any tracking queue, or draw any tracking
conclusion.** Whether the tracker degrades on amateur footage is a later row needing a quiet pod.

ACCEPTANCE RULE:
  metric        = per-candidate outcome (acquired / unavailable with the error), local bytes downloaded
                  and freed, slice bytes uploaded, height actually obtained, running totals against both
                  caps, every disk-guard probe result, content-gate verdict, the G213-rubric
                  classification, and the updated zero-representation list beside G213's
  before        = G220 acquired ZERO because the empty cookie file blocks section downloads; G213's
                  zero-representation list is unchanged and no robustness claim about arbitrary footage
                  is supportable
  bar           = NO pass bar. **At least one clip credibly classified as an amateur GAME CAMERA or a
                  fixed SINGLE camera would close a category that is currently empty. Closing none,
                  honestly reported, is also a full success.** Do not stretch a classification to close
                  a category, and do not accept 360p silently.
  n             = 6 reviewed candidates (CONSTRUCT, exhaustive; no substitutions) x 5 frames each
  eye check     = the classification IS the eye check; commit the frames
  must not move = every threshold, bar and verdict, the coordinate contract, `src/` (READ ONLY),
                  `footage_bridge.py` (READ ONLY), the pod daemon, keeper, bridge supervisor and
                  watchdog, the existing corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g220b_amateur_footage_local_slice_2026-09-04.md with the per-candidate
table, heights and rungs, both running byte totals, every disk-guard probe result, the content-gate
verdicts, the committed frames, the rubric classification, the updated zero-representation list, bytes
freed locally and on the pod, an explicit statement that the classifications are single-labeller
judgements, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
