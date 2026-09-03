GAP G156 | sport all | worktree a3 | log cx_g156_daemon_stalls_on_ffprobe
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A5, A7 and Q8; self-check
section B before reporting. This row MAY change code. It must NOT change the decoded-frame
denominator, the coverage definition, any bar, any gate, or any verdict. Read B10 twice.

THE DEFECT, diagnosed live on the pod at 2026-09-03T14:2xZ and not inferred. The track daemon's poll
loop calls, synchronously, in its own process:

    tick()  ->  _finish()  ->  verdict()          track_daemon.py:115
            ->  adjudicate()                      track_daemon_done.py:117-133
            ->  decoded_frame_count()             decode_manifest.py:88-107
            ->  ffprobe -count_frames ...

`-count_frames` FULLY DECODES the video to count frames exactly. On the pod, `/proc/<daemon>/wchan`
read `do_poll.constprop.0` while its only child was:

    ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames
            -of default=nokey=1:noprint_wrappers=1 data/footage_bridge/baseball__mlb_...mp4

So while ANY finished job is being adjudicated, the daemon claims nothing, reaps nothing and starts
nothing. The observable consequences, all already recorded: G146 saw "a synchronous ffprobe child for
at least 527 seconds", GPU utilisation 0 pct throughout, and only one live tracking job at any point
on a 256-core box configured for 10 workers. On 2026-09-03 the first game finished, wrote its 32,380
rows and its verdict, and the daemon still reported "1 active" eight minutes later with a second
staged game untouched.

WHAT IS NOT THE DEFECT, and must not be "fixed". The exact decoded-frame count is CORRECT and
load-bearing: it is the denominator G147 needs, the one G147-CORR showed is missing from every
historical row, and the thing G149 is trying to persist. Do NOT replace `-count_frames` with the
container's `nb_frames`, with duration times fps, or with any estimate. Do NOT sample. The count must
remain byte-identical in definition and value. A cheaper-but-different number is a MOVED BAR (B10)
and an automatic reject.

THE FIX IS ABOUT WHERE IT RUNS, NOT WHAT IT COMPUTES. Get the adjudication off the poll loop so the
daemon keeps claiming and reaping while a count is in flight. Establish first, from the code, which
of these the current structure actually admits, then take the smallest one that works:
  - adjudicate in a worker thread or a child process, with the daemon polling its completion the same
    way it already polls a tracking job;
  - or have the tracking job itself produce the count as it already decodes the whole video anyway,
    so no second full decode is needed at all -- if this is reachable it is strictly better, because
    it removes the work rather than moving it;
  - or bound the daemon's exposure some other way you can defend in one sentence.
Keep it small. No new subsystem, no scheduler, no queue abstraction, no config file. If the answer is
a thread and a poll, that is the whole change.

WHAT YOU MUST MEASURE, because a fix with no number is not a result:
  (a) Time `decoded_frame_count` on at least 3 real staged videos of stated size and duration, and
      report seconds per gigabyte. Local files are fine; say which you used.
  (b) State the resulting stall as a share of a job's own runtime. That share IS the throughput cost.
  (c) After the change, show that the daemon claims a new job while an adjudication is in flight.
      A test that only proves the count is unchanged does not demonstrate the fix.
  (d) A5 IS MANDATORY HERE: grep every reader of the ledger row, the verdict sidecar and the decode
      manifest, and report them. `_finish` writes both a ledger row and a sidecar; if adjudication
      becomes concurrent, say explicitly what now orders those writes and why two jobs finishing at
      once cannot interleave them.
  (e) State the ELIGIBLE denominator for anything you count. Never a bare sample size.

DO NOT change the coverage bar, the 10-eligible bar, any threshold, the coordinate contract, the
eligibility definition, the harness, or any verdict. Do not remove or rename a ledger field. Do not
restart or kill the pod daemon -- it is running and the orchestrator owns it.

ACCEPTANCE RULE:
  metric        = measured seconds-per-gigabyte for the exact count on >= 3 real videos; the stall as
                  a share of job runtime; and a demonstration that a new job is claimed during an
                  in-flight adjudication
  before        = adjudication blocks the poll loop; one job at a time on a 256-core box; GPU 0 pct
  bar           = NO pass bar. Success is the cost measured and the blocking removed with the count
                  definitionally unchanged. "The structure does not admit a small fix, and here is
                  why" is a full success and closes the row honestly.
  n             = >= 3 real videos for the timing (state each one's size and duration)
  eye check     = replaced by REPRODUCTION (Q7): show the before behaviour and the after behaviour,
                  each with the command and its raw output
  must not move = decoded_frame_count's definition and value, build_decode_manifest, the coverage
                  definition, every threshold and bar, the coordinate contract, every ledger field
                  name, and every verdict
EVIDENCE: docs/evidence/tracking/g156_daemon_stalls_on_ffprobe_2026-09-03.md with the timing table,
the stall share, the before/after demonstration, the A5 reader grep, and a NOT VERIFIED list. Commit
BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test. Run ONLY that file. NEVER a full pytest -- it freezes the box.
POD: READ-ONLY. The daemon is RUNNING. Never kill, restart or deploy to it; the orchestrator deploys
after ACCEPT (B5).
COMMIT: explicit pathspec only, no push. Report the sha.
SHARED MODULE: track_daemon.py and track_daemon_done.py are live and G151 may be touching
track_daemon.py concurrently -- keep your diff minimal and local to the blocking call.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
