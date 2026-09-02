GAP G105 | sport all | worktree a11 | log cx_g105_recover_lost_gpu_hours
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A THROUGHPUT recovery, sized by a measurement that already
exists. Read docs/evidence/tracking/g100_pod_job_outcome_census_2026-09-0X.md first.
WHAT G100 MEASURED, on 401 live pod ledger rows over 187 unique games:
  - 165 thin, 50 timeout, 183 tracked, 3 corrupt.
  - `thin` is NOT a row-count threshold. It is exactly the non-timeout branch where `graded is
    None` -- the job produced no durable adjudication payload. Three evenly distributed thin
    outputs were opened and every one was HEADER-ONLY with no verdict sidecar. 158 of 165 are on
    the adapter-registry path.
  - **25 of the 50 timeouts carry the clip-path pre-checkpoint signature (0 to 4 rows) and together
    consumed 82,113 seconds = roughly 22.8 GPU-hours** for essentially nothing.
THE MECHANISM IS ALREADY DOCUMENTED IN THE CODE, at length, in track_daemon.py: unified_pipeline
checkpoints tracking_data.csv every 2,000 frames and never flushes the residual, so a run_clip job
is worth nothing until it crosses frame 2,000 and worth about 2,700 rows the moment it does. A job
killed at frame 1,999 returns the four rows from the frame-0 checkpoint. That is a cliff, not a
budget, and CLIP_JOB_TIMEOUT_SECONDS was already raised to 5,400 s once because of it.
YOUR JOB IS TO SIZE THE FIX, NOT TO APPLY IT. Two candidate fixes exist and they have very
different costs:
  (a) Raise the clip timeout again. Cheap, but it is a THRESHOLD CHANGE and needs adjudication, and
      it trades slot occupancy for completion. Quantify it: from the 25 pre-checkpoint timeouts and
      their measured frame rates, what timeout would have let each cross frame 2,000? Report the
      distribution, not a single number, and state how much longer slots would be held.
  (b) Flush the residual checkpoint so a killed job keeps its work. This is the real fix -- it
      removes the cliff instead of moving it. BUT the checkpoint lives in
      src/pipeline/unified_pipeline.py and `src/**` is HUMAN-GATED: you must NOT edit it. Write a
      PROPOSED diff under docs/research/organization-sprint/ instead, and say plainly in the memo
      that it awaits human application.
ALSO ANSWER THE `thin` QUESTION, which is larger (165 rows) and completely unexplained: 158 of 165
sit on the adapter-registry path. Are those jobs failing early, or completing and failing to write
a payload? Open at least 5 more thin cases spread across sports and say which. If they are
completing and losing the payload, that is a second recoverable bucket at least as large as the
first and it must be sized the same way.
DO NOT change any timeout, any threshold, track_daemon.py, unified_pipeline.py, or anything on the
pod. Do not re-run any job. NEVER KILL ANYTHING ON THE POD -- the track daemon (pid 4035), its
keeper, seven footage bridge lanes and other sessions' long-running processes are all live.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = GPU-hours recoverable under each candidate fix, with the timeout distribution
                  that would clear the first checkpoint, plus a cause for the 158 adapter-path thin
                  jobs
  before        = 22.8 GPU-hours confirmed lost to pre-checkpoint timeouts; 165 thin unexplained
  bar           = there is NO pass bar. Success is both buckets sized with their evidence and one
                  clear recommendation per bucket. "The thin jobs genuinely failed and nothing is
                  recoverable there" is a full success and closes a 165-row question.
  n             = all 25 pre-checkpoint timeouts; >= 5 additional thin cases opened, spread across
                  sports; state the ledger row count you actually read, since it is growing
  eye check     = n/a for the arithmetic, but you must OPEN the thin outputs rather than trusting
                  the label. G100 opened three and found them header-only; that is the standard.
  must not move = every timeout budget, every threshold, track_daemon.py, unified_pipeline.py,
                  every pod process, the coordinate contract, and the ledger
EVIDENCE: docs/evidence/tracking/g105_recover_lost_gpu_hours_2026-09-0X.md with both sizings, the
timeout distribution, the thin cause, the PROPOSED diff path if you write one, and a NOT VERIFIED
list. Commit derived tables under docs/evidence/tracking/g105_recovery/ BEFORE reporting (A7).
CAUTION FROM TODAY: two lanes wrote evidence directly into the MAIN working tree and one dropped
two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, and strictly. Never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a11,
no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token and this row does NOT edit it. Read only.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
