GAP G124 | sport all | worktree a5 | log cx_g124_header_only_cause
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This explains the LARGEST failure class in the pipeline. Read
docs/evidence/tracking/g100_pod_job_outcome_census_2026-09-0X.md and
g105_recover_lost_gpu_hours_2026-09-0X.md first.
WHAT IS ALREADY KNOWN, and what is conspicuously not:
  - G100 censused the pod ledger and found `thin` is exactly the non-timeout branch where
    `graded is None` -- no durable adjudication payload. It is NOT a row-count threshold. Counts:
    165 thin, 50 timeout, 183 tracked, 3 corrupt over 401 rows and 187 unique games.
  - **158 of the 165 thin outcomes are on the adapter-registry path**, not the clip path.
  - G100 opened three evenly distributed thin outputs and every one was HEADER-ONLY.
  - G105 sized them at 145,702 seconds = 40.47 estimated job-hours, and confirmed **0 recoverable**:
    the opened cases were non-timeout header-only outputs, so those jobs genuinely produced nothing
    rather than being truncated.
So the largest failure class in the system -- 40 job-hours, 158 jobs, more than a third of all
outcomes -- is confirmed to produce nothing, and NOBODY HAS ASKED WHY. G105 sized it; it did not
diagnose it. That is this row.
THE QUESTION: why does an adapter-registry job run to completion and write a header-only table?
  (a) OPEN at least 12 thin outputs spread across sports and across time, not a head slice. State
      how you selected them. For each, record: the sport, the adapter, the job duration, the input
      video's presence and size, and whatever the job log says.
  (b) CLASSIFY the causes into a vocabulary you declare up front. Candidates worth expecting: the
      detector found nothing on any frame; decoding failed after the first frame; the adapter raised
      after writing its header; the video is not game footage at all; the video is corrupt or
      truncated. Declare the vocabulary BEFORE you classify.
  (c) CHECK THE OBVIOUS CONFOUND FIRST. G113 measured that live-action share is 93.3 pct
      [86.9, 96.7] outside baseball but far lower inside it, concentrated in KBO studio and
      statistics programming, and G117 is quarantining those clips now. If thin outcomes are
      concentrated on non-game footage, the cause is acquisition and not the adapter, and that
      changes the fix entirely. Report the thin rate for the clips G117 names versus the rest.
  (d) SEPARATE "the input was worthless" from "the adapter failed on a usable input". Those have
      completely different fixes and the whole value of this row is telling them apart. Quantify
      both, with denominators.
  (e) RECOMMEND, do not build. If a cheap guard would turn a silent header-only success into a
      loud failure, describe it in one paragraph. A job that reports success while writing nothing
      is worse than one that fails, because it consumes a slot and leaves a table that looks real.
DO NOT re-run any job, change the daemon, change any threshold, or touch the coordinate contract.
NEVER KILL ANYTHING ON THE POD -- the track daemon, its keeper, seven bridge lanes and other
sessions' processes are live.
ACCEPTANCE RULE:
  metric        = cause distribution over >= 12 opened thin outputs, and the thin rate on
                  G117-named non-game clips versus the rest
  before        = 158 adapter-path thin jobs, 40.47 job-hours, 0 recoverable, cause unknown
  bar           = NO pass bar. Success is >= 12 outputs opened and classified under a preregistered
                  vocabulary, the non-game confound checked with numbers, and the two causes
                  separated with denominators. "Nearly all of them are non-game footage" is the best
                  possible outcome because it makes the fix cheap.
  n             = >= 12 thin outputs, spread across sports and time; state your selection rule
  eye check     = REQUIRED for any output you attribute to bad footage -- look at a frame of the
                  input and say what it shows. G100 found three thin outputs header-only by opening
                  them; attributing a cause without looking is the error this row must not repeat.
  must not move = every threshold, the daemon, the coordinate contract, every verdict, every pod
                  process, and the ledger
EVIDENCE: docs/evidence/tracking/g124_header_only_cause_2026-09-0X.md with the preregistered
vocabulary stated first, the per-output table, the cause distribution, the non-game comparison, the
recommendation, and a NOT VERIFIED list. Commit derived tables under
docs/evidence/tracking/g124_headers/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, strictly.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: track_daemon.py is under the token; READ it, do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
