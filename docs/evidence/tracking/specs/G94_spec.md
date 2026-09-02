GAP G94 | sport all | worktree a11 | log cx_g94_pipeline_liveness
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This is an AUTONOMY row. It exists because of a measured
outage, not because a watchdog sounds like a good idea.
THE OUTAGE, found by hand by the orchestrator on 2026-09-02 at about 21:30:
  - scripts/platformkit/bridge_supervisor.py was NOT RUNNING on the workstation. Its last status
    file (data/tracking/bridge_supervisor_status.json) still claimed every one of its seven lanes
    was "alive": true, because a status file written at death is indistinguishable from one written
    in health. It had been down since 2026-09-01.
  - Consequence, measured: pod GPU utilisation 0 pct with 24,576 MiB free, the track daemon (pid
    4035, --workers 10) alive and idle with an EMPTY work queue, and three abandoned .mp4.part
    files sitting in data/footage_bridge dated 2026-09-01 that no process will ever finish or
    clean up. The queues were not empty -- they held 37 untracked baseball, 36 soccer, 12 wnba and
    more. Roughly a day of free GPU was spent on nothing, and nothing anywhere reported it.
THE DEFECT IS OBSERVABILITY, NOT THE SUPERVISOR. The supervisor restarts its own workers correctly.
What is missing is anything that notices the SUPERVISOR is gone, and anything that distinguishes
"the pipeline is healthy and idle" from "the pipeline is dead and therefore idle". Those two states
look identical from every artefact that exists today.
BUILD THE SMALLEST THING THAT CLOSES IT:
  (a) A LIVENESS CHECK that is honest about its own staleness. Every status artefact must carry the
      wall-clock time it was written, and every reader must treat a status older than a stated
      budget as UNKNOWN rather than as its last value. A cached "alive": true is exactly the lie
      that hid this outage for a day, and re-emitting it with a timestamp beside it is not enough
      unless the reader actually refuses it when stale.
  (b) Do NOT use pgrep on a command line that mentions the process. track_daemon.py:38-44 already
      documents why in this exact codebase: any command line mentioning the daemon self-matches,
      including the watchdog's own check and an operator ssh diagnostic, so the check reports "up"
      precisely because it ran. The daemon publishes a pid file and the watchdog uses kill -0.
      Follow that established pattern; do not invent a second one.
  (c) A RESTART only where restarting is safe and idempotent. The bridge supervisor is safe to
      restart: lanes are disjoint and workers are already auto-restarted. The pod track daemon is
      NOT yours to restart and must never be killed -- there are live long-running jobs on that box
      and a standing never-kill rule. State this boundary explicitly in the code, not just here.
  (d) A stale .part REAPER, or an explicit written decision not to build one. Three abandoned
      .part files is small; the question worth answering in one paragraph is whether an abandoned
      partial upload can ever be mistaken for a complete one. track_daemon.py:1-5 says only plain
      .mp4 files are complete and warns "never add size-stability polling", so read that contract
      before touching anything in the stage directory.
MEASURE, do not assert. This row is only worth landing if it can show it would have caught the real
outage. Reproduce the failure: with the supervisor stopped, show the check reporting DOWN, and with
it running, show it reporting UP. Both transcripts go in the memo. A watchdog that has never been
observed to fire is an untested branch on the one path that only matters when something is wrong.
DO NOT build a dashboard, a metrics backend, a notification service or a config system. One check,
one status artefact, one restart path.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = whether the check correctly distinguishes DOWN, UP and STALE-therefore-UNKNOWN,
                  demonstrated on all three
  before        = a status file claiming seven lanes alive while the process had been dead a day
  bar           = all three states demonstrated with transcripts, AND the restart shown to be a
                  no-op when the supervisor is already healthy, AND nothing on the pod killed
  n             = the three states, each demonstrated at least once
  eye check     = n/a. Reproduction = the DOWN and UP transcripts against the real supervisor.
  must not move = the pod track daemon and every process on the pod, the .part / .mp4 completion
                  contract, every harness threshold, the coordinate contract, and the lane list
EVIDENCE: docs/evidence/tracking/g94_pipeline_liveness_2026-09-0X.md with the three transcripts, the
staleness budget and why that number, the restart boundary, the .part decision, and a NOT VERIFIED
list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY. Never kill anything. Seven footage bridge lanes and the track daemon are live right
now and a restart of the workstation supervisor must not disturb either.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a11,
no push. Report the sha.
SHARED MODULE: none. Do not edit track_daemon.py -- it is under the token and this row does not
need it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
