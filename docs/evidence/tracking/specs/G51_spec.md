GAP G51 | sport all | worktree a9 | log cx_g51_pod_drift_check
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. Small, cheap, and it prevents a defect that has ALREADY happened.
PREMISE (step 0, reproduce it): the pod is what actually produces every number in the tracking
ledger, and it silently drifts from master. A measured sweep found 3,415 shared modules, 16
differing, 8 pod-only (3 under tracking/) and 21 master-only. Worse, on 2026-09-02 the G59 row
recorded that code REJECTED by the verifier was running in production on the pod and writing live
tennis tables, and the only reason anyone found out was a hand sweep. A separate lane independently
noticed that the pod's domains/tennis/tracking/court_lines.py hash differs from the committed one.
Reproduce the drift yourself: md5 the tracked tracking modules on the pod and on master and report
the current differing set. Do NOT assume the earlier 16 is still the number.
LIMIT (step 1): drift is currently discoverable only by a manual sweep that nobody runs on a
schedule. A landed fix may not be what ran, and a rejected change may be what ran. No amount of
care in the lanes fixes this, because the lanes cannot see the pod's file state.
CHANGE (step 2): add a drift check that scripts/platformkit/tracking/loop_status.sh runs, so every
session sees drift instead of discovering it in a sweep. Requirements:
  (a) Scope it to the modules that produce tracking numbers -- domains/*/tracking/,
      scripts/platformkit/tracking/, scripts/platformkit/track_daemon*.py, tracking_harness.py.
      State the glob in the memo. A whole-repo md5 is too slow and too noisy to be run every time.
  (b) Output THREE named sets, never a single count: DIFFERS, POD-ONLY, MASTER-ONLY. A bare
      "16 differ" is the same denominator-free defect G56 fixed in the ledger.
  (c) It must be fast enough to run every session. Measure and report the wall-clock time. If it
      exceeds about 20 s, narrow the glob rather than accepting a check nobody will run.
  (d) It must FAIL SOFT: no pod, no network, or an ssh timeout prints an explicit UNKNOWN line and
      exits 0. A drift check that breaks loop_status.sh when the pod is down is worse than none.
  (e) ASCII only on stdout.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the check's ability to name a KNOWN planted difference
  before        = drift is invisible without a hand sweep; 16 differing modules were found by one
  bar           = the check correctly reports (i) a module that differs, (ii) a module present only
                  on the pod, and (iii) a module present only on master, in a constructed test where
                  you KNOW the answer, AND it prints UNKNOWN and exits 0 with the pod unreachable
  n             = 3 planted cases plus 1 unreachable case, plus one real run against the live pod
  eye check     = paste the real run's output verbatim into the memo, all three sets, not a summary
  must not move = every harness threshold, the daemon, and loop_status.sh's existing output lines.
                  APPEND your section; do not restructure what is already printed.
POD SAFETY, ABSOLUTE: this row READS the pod and nothing else. Do NOT scp, do NOT deploy, do NOT
restart the daemon, do NOT kill anything -- the track daemon and the book capture are 24/7 jobs and
a running measurement (a G52 bisection) may be in flight. No git on the pod. If you think the fix
is to make the pod match master, that is a DIFFERENT row and it is not yours.
EVIDENCE: docs/evidence/tracking/g51_pod_drift_check_2026-09-0X.md with the reproduced current
drift sets, the planted-case results, the timing, the unreachable-case behaviour, and a
NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: none -- loop_status.sh is not under the token. If you find yourself editing
track_daemon.py, STOP; you have left the scope of this row.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
