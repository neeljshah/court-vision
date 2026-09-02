GAP G80 | sport all | worktree a5 | log cx_g80_insufficient_data_verdict
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This IMPLEMENTS a REVERSED adjudication. Implement it; do not
re-open it.
THE REVERSAL (orchestrator, 2026-09-02): I previously ruled that a degenerate report should null its
n-dependent metrics but that `passed` must NOT change, because moving it would flip 10 historical
verdicts. That ruling was WRONG and is reversed. The gate audit found the consequence and the
orchestrator reproduced it independently with ONE data pattern at three sizes:
    3-frame  -> passed=True,  verdict=PASS, failures=[]   (every metric None)
    10-frame -> passed=True,  verdict=PASS, failures=[]   (every metric None)
    40-frame -> passed=False, verdict=FAIL, failures=['oob 0.24 > 0.05']
The same defect PASSES at 3 and 10 frames and FAILS at 40. A degenerate table is not merely
uninformative; it actively passes a check it would fail with more data.
IMPLEMENT: when `insufficient_data` is true, the report emits an explicit INSUFFICIENT_DATA verdict
with passed=False. It must never emit PASS.
  (a) KEEP the existing nulling of n-dependent metrics -- that half of the ruling was right.
  (b) INSUFFICIENT_DATA is its own verdict, distinct from FAIL. A table with too little data has not
      failed a quality bar; it was never measurable. Do not collapse the two.
  (c) `failures` must not be an empty list on such a report. State the reason in it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = whether a report with n_frames below MIN_FRAMES_FOR_METRICS can report PASS
  before        = it can, and does -- reproduced at 3 and 10 frames
  bar           = no degenerate report can report PASS or passed=True, AND no report with n_frames
                  at or above MIN_FRAMES_FOR_METRICS changes verdict at all. If an adequate-data
                  table flips, that is a REJECT and you report it rather than adjusting the fixture.
  n             = the three sizes above reproduced, plus a replay over >= 10 existing reports
  eye check     = n/a (a verdict change). Reproduction = the three-size table before and after.
  must not move = every threshold, every metric value, and every verdict on an adequate-data report
THE FLIP LIST IS PART OF THE DELIVERABLE: name every historical report whose verdict changes, with
its n_frames, and state the count. Up to 10 are expected. These are FALSE PASSES being corrected,
not results being disturbed -- say so. If the count is much larger than 10, STOP and report that,
because it would mean the degenerate population is bigger than anyone believed.
EVIDENCE: docs/evidence/tracking/g80_insufficient_data_verdict_2026-09-0X.md with the three-size
reproduction before and after, the flip list, the no-change proof for adequate data, and a
NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: no deploy. The verifier lands code on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push except the token. Report the sha.
SHARED MODULE: tracking_harness.py is under the token. Take it in
docs/evidence/SHARED_MODULE_TOKEN.md and PUSH THE RELEASE when you report.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
