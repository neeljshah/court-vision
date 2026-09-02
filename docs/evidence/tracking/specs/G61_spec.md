GAP G61 | sport baseball + basketball + tennis | worktree a7 | log cx_g61_unversioned_pod_code
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. Read the NEW A7 clause: a memo naming an evidence path that no longer
exists is NOT VALIDATED.
PREMISE (step 0, reproduce it): the G51 drift check, on its first live run 2026-09-02, found FIVE
pieces of code that produce tracking numbers on the pod and exist in NO version control anywhere:
  POD-ONLY (4): domains/baseball/tracking/pitch_view_gate.py,
                scripts/platformkit/tracking/basketball_floor_gate.py,
                scripts/platformkit/tracking/tennis_keypoint_train.py,
                scripts/platformkit/tracking/tennis_vertical_probe.py
  DIVERGED (1): domains/baseball/tracking/geometry.py -- the pod copy is 78 lines against master's
                64 and matches NO commit in the last 25 for that path. It adds an OPT-IN `gate_mode`
                parameter routing the field precondition through pitch_view_gate.classify_pitch_view,
                with master's `dominant_green` preserved as DEFAULT_MODE.
All five are preserved at docs/evidence/tracking/pod_only_modules_2026-09-02/ (the baseball one as
baseball_geometry_POD_VERSION.py). Reproduce the drift list yourself by running the check in
scripts/platformkit/tracking/pod_drift.py before you touch anything.
LIMIT (step 1): code that exists only on one machine cannot be reviewed, cannot be tested by
anyone else, is destroyed by a pod reallocation, and silently becomes the thing that produced a
number in the ledger. This is the same failure family as G59 (the pod ran REJECTED code for hours)
and it is invisible without the drift check that just landed.
CHANGE (step 2), and the ORDER matters:
  (a) For EACH of the five, determine and state: what it does in one sentence, whether anything on
      the pod actually CALLS it (grep the pod for imports -- read-only), and whether it duplicates
      something already on master. A module nothing imports is dead code and the answer is to
      record it and delete it, not to land it.
  (b) For each one that IS called, land it to master WITH a per-file test. It is entering version
      control for the first time, so it does not inherit anyone's review.
  (c) For baseball geometry.py specifically: the pod change is additive and default-preserving, so
      landing it must not alter DEFAULT_MODE behaviour. Prove that with a test asserting the
      default path still calls dominant_green and produces identical output on a constructed frame.
  (d) Do NOT deploy anything to the pod in this row. Master catches up to the pod here, not the
      other way round.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the POD-ONLY and DIFFERS sets reported by pod_drift.py
  before        = POD-ONLY 4, DIFFERS includes domains/baseball/tracking/geometry.py
  bar           = every one of the five is either (i) on master with a passing per-file test, or
                  (ii) documented as dead code with the evidence that nothing imports it. No file
                  may be left in the "exists only on the pod" state without a stated reason.
  n             = all 5; state for each which of the two outcomes it took
  eye check     = n/a (a provenance and version-control question), EXCEPT that any behaviour claim
                  ("this changes nothing by default") needs its test, not an assertion.
  must not move = every harness threshold, DEFAULT_MODE behaviour for baseball geometry, and the
                  pod. Do not deploy, do not restart the daemon, never kill anything.
NON-TAUTOLOGY: "it imports cleanly" is not evidence that it is used. Show the caller, or show there
is none.
EVIDENCE: docs/evidence/tracking/g61_unversioned_pod_code_2026-09-0X.md with the reproduced drift
sets, the five one-sentence descriptions, the caller evidence for each, what you landed, the test
output, and a NOT VERIFIED list.
TEST: one per-file test per landed module; run only those files. Never a full pytest.
POD: READ-ONLY, absolutely. Grep for callers; copy nothing to it.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a7,
no push. Report the sha.
SHARED MODULE: none expected.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
