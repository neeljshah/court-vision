GAP G159b | sport all | worktree a5 | log cx_g159b_supply_window
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A7 and Q8; self-check
section B before reporting. READ-ONLY measurement of a live system. Change nothing, including the
worker count and MAX_POD_BACKLOG.

WHAT ATTEMPT 1 GOT RIGHT, and must not be undone. G159 (landed at 88e7e6211) sampled for 116 seconds,
saw no completed job, and **refused to name either supply or capacity as binding**. That refusal was
correct and is not the thing being fixed. It also established two results that stand: the immediate
observed blocker is daemon poll-loop availability, and the quota arithmetic gives roughly 24 games of
~2 GB before the ~50 GB volume binds, with 22 backlog slots free. Do not re-derive those.

TWO DEFECTS TO CLEAR (Q8 -- verify each before measuring, do not assume):
  1. The window was 116 seconds against a required 30 minutes.
  2. **The worktree could not see the local staging directory at all**, so "no download growth" was
     partly an artefact: the main repo was holding about 14 GB of in-flight downloads at that moment.
     `videos/bridge` is now junctioned. **Confirm you can see it and that it is non-empty before you
     measure anything**, and say the byte total you start from. If it is empty or absent, stop and
     report the provisioning is still broken.

MEASURE over a window of AT LEAST 30 MINUTES, sampling on a schedule you control:
  (a) Local download throughput from the staging directory: per-lane and aggregate MB/s, with the
      sampling interval stated. At least 10 samples. Never a rate from two points.
  (b) Pod-side occupancy at each sample: live tracking jobs out of the configured worker count.
      Report the DISTRIBUTION, not a mean. Use `ps -eo pid,etimes,args`, NEVER `pgrep -f`, which
      matches the ssh command line running the check and reports phantoms.
  (c) Per-job service time and completions from the ledger: `seconds` per completed job and games per
      hour. Name the ELIGIBLE DENOMINATOR (completed jobs inside your window). Never a bare sample size.
  (d) The comparison that settles it: **games arriving per hour versus games the pod completes per
      hour at the current worker count.** Say which is smaller and therefore which binds.
  (e) THE CONFOUND, handled explicitly or the row is worthless. `_finish` calls `adjudicate` calls
      `decoded_frame_count` calls `ffprobe -count_frames`, synchronously, inside the poll loop
      (G156's row -- read it, do not duplicate its fix). At 2026-09-03T14:5xZ the pod was observed
      with ZERO tracking jobs and TWO live `ffprobe -count_frames` processes at 129 s and 85 s
      elapsed. So occupancy can read 0/10 for a reason that has nothing to do with supply. At every
      sample, record whether an `ffprobe -count_frames` is live. Then report occupancy TWICE: over all
      samples, and over only the samples with no live count in flight. If the second set is too small
      to say anything, say that instead of quoting a clean number.
  (f) Report total `ffprobe -count_frames` seconds observed inside your window as a share of window
      length. That share is the direct throughput cost of G156's defect and it is the number that
      tells the orchestrator how urgently to land the fix.

DO NOT change the worker count, MAX_POD_BACKLOG, any threshold, the coordinate contract, or any
verdict. Do not delete a pod file. Do not restart or kill the daemon, keeper or bridge.

ACCEPTANCE RULE:
  metric        = aggregate and per-lane MB/s from >= 10 samples; occupancy distribution over all
                  samples and over count-free samples; per-job seconds and completions/hour; arrival
                  versus completion rate; ffprobe seconds as a share of the window
  before        = attempt 1's window was 116 s with a blind staging directory; nothing rate-like was
                  establishable
  bar           = NO pass bar. Success is the comparison over a real window with the confound reported
                  separately. Either binding answer is a full success; so is "still not separable, and
                  here is why".
  n             = >= 30 minutes, >= 10 samples at a stated interval; state the completed-job count
  eye check     = replaced by REPRODUCTION (Q7): every command quoted with raw output and timestamp
  must not move = the worker count, MAX_POD_BACKLOG, every threshold, the coordinate contract, every
                  verdict, and every pod file and process
EVIDENCE: docs/evidence/tracking/g159b_supply_window_2026-09-03.md with the full sample series, both
occupancy distributions, the two rates, the ffprobe share, and a NOT VERIFIED list. Raw samples under
docs/evidence/tracking/g159b_window/. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: STRICTLY READ-ONLY. Everything on it is LIVE. Never kill or restart anything.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
NEVER PARK: take your samples on a timer and write each one to disk as you go, then STOP and report.
Never sit in a blocking wait and never end your turn waiting for the window to pass.
