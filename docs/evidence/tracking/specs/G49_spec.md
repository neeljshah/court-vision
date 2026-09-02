GAP G49 | sport soccer | worktree a2 | log cx_g49_soccer_churn_restate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. Restatement plus the eye check nobody has done. No code fix.
PREMISE (step 0, reproduce it): G08's headline identity churn of 0.00778 is ids-per-DETECTION,
which is not interpretable as a defect size -- it shrinks as detections grow, so a worse tracker
with more boxes can score better. Restated per concurrent subject it is 2.47 track ids per person
per 10 s window (n=15 windows, 4,500 decoded frames, range 1.42-4.95). The 417 ids and the 11.916
mean boxes reproduce exactly. Reproduce the 0.00778, the 2.47 and the 1.42-4.95 range yourself
before proceeding; if any of the three does not reproduce, that is the finding -- report it.
LIMIT (step 1): the memo's identity tally is a FLOOR, not a count. Only 4 of 28 renders were ever
viewed. One of those 4, DdnvC6-PGYY w01, is an uncut wide pan whose track ids go from all <= 20 to
including 22, 25 and 26, so it is ASSESSABLE and CHANGED -- which means the memo's "1 changed"
tally was produced by not looking at the other 24. An identity claim resting on 4 of 28 viewed
renders is not measured.
CHANGE (step 2): no code fix in this row. Two deliverables.
  (a) RESTATE. Report identity churn as ids per person per 10 s (2.47, with its range and a
      Wilson or bootstrap interval as appropriate to the statistic -- say which you used and why).
      Report the old 0.00778 once, in a reconciliation line, labelled as ids-per-detection and
      explained as uninterpretable. List every memo and register row quoting 0.00778 so the
      orchestrator can correct them; do not edit other lanes' memos yourself.
  (b) VIEW THE REMAINING 24 RENDERS. For each, record one of exactly three verdicts:
      ASSESSABLE-AND-CHANGED, ASSESSABLE-AND-UNCHANGED, or NOT-ASSESSABLE with a one-clause reason
      (a cut, an occlusion, a replay, too few frames). Then report the changed fraction over the
      ASSESSABLE denominator, not over 28, and state both denominators explicitly.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the fraction of assessable renders showing an identity change, over a stated
                  assessable denominator
  before        = "1 changed" out of 4 viewed of 28, which is a floor and not a measurement
  bar           = THERE IS NO PASS BAR. This row succeeds by producing a per-render verdict table
                  covering all 28 with a stated denominator. A high churn number is a valid result
                  and so is a low one; the failure mode is an unviewed render, not a bad number.
  n             = all 28 renders, none skipped. If a render file is missing, say which and why.
  eye check     = THIS ROW IS THE EYE CHECK. Every verdict must come from looking at the render.
                  Do NOT infer a verdict from the id counts in the table -- that is the tautology
                  this row exists to break (contract B7). Say what you saw, including anything
                  that contradicts the 2.47 figure.
  must not move = every harness threshold, the tracker, and the G08 tables. You are re-reading
                  existing artifacts, not re-tracking.
SCOPE DISCIPLINE: if the renders reveal a fixable tracker defect, NAME it in the memo and STOP.
The fix is a different row and takes a new id from the orchestrator -- lanes never invent gap ids
(two lanes already collided on G25/G23 doing exactly that).
EVIDENCE: docs/evidence/tracking/g49_soccer_churn_restate_2026-09-0X.md with the three reproduced
numbers, the restated statistic with its interval, the full 28-row verdict table, the changed
fraction over the assessable denominator, the list of memos quoting 0.00778, and a NOT VERIFIED
list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none. If you find yourself editing track_daemon.py, STOP.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
