GAP G60 | sport tennis | worktree a3 | log cx_g60_clay_horizontals
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. This is a LIMIT MEASUREMENT, not a fix. Do not change the solver.
PREMISE (step 0, reproduce it): G57 measured tennis court-solver acceptance per frame and found
clay at 5.0 pct [2.7,9.0] on tennis_06 at 1080p, against hard 31.2 pct and grass 17.8 pct. The
reason is NOT resolution and NOT framing: 6 of the 10 rejected frames that were rendered and
viewed are pristine, full-court, 1080p views. The solver finds the near half, never the far
baseline or far service line, and fails at `horizontal_roles`. The rendered diagnosis counted
250-265 SPURIOUS HORIZONTAL segments per frame originating from the crowd and the sponsor band.
Reproduce that count on at least those 6 frames before doing anything else; if you cannot
reproduce the 250-265 range, STOP and report that -- a premise that does not reproduce is a
result, and the G57 memo (g57_tennis_solver_generalization_2026-09-02.md, renders in g57_renders/)
is the artifact to reproduce it from.
LIMIT (step 1): the question is how much of the clay failure is attributable to non-court
horizontals ALONE. Partition every horizontal segment on each failing frame by whether its
midpoint lies ABOVE the court region or inside it. You must define "above the court region"
from something the solver already knows -- the near-half geometry it successfully recovers, or
the horizon implied by it -- and NOT from a hand-drawn per-clip rectangle, which would be a
tautology (contract B7). State the definition in the memo in one sentence.
MEASURE (step 2): report, on the failing clay frames, (a) the count and fraction of horizontals
above the court region, (b) what `horizontal_roles` would accept if those alone were excluded --
computed by re-running role assignment on the filtered segment set, NOT by asserting it, and
(c) the same two numbers on a HARD-COURT control set of failing frames, so the reader can see
whether spurious horizontals are clay-specific or general.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-frame solver acceptance on clay, and the horizontal-partition fractions
  before        = clay 5.0 pct [2.7,9.0] (G57), 250-265 horizontals per frame
  bar           = THERE IS NO PASS BAR. This row succeeds by producing a reproducible number and
                  a named mechanism, and it succeeds equally if the answer is "excluding
                  above-court horizontals changes acceptance by 0.0 pct" -- that would falsify
                  the leading hypothesis, which is worth more than a fix.
  n             = >= 30 clay frames sampled seeded and evenly spaced (not a head slice), plus
                  >= 30 hard-court control frames, with Wilson 95 pct intervals on every fraction
  eye check     = MANDATORY. Render >= 10 clay frames with the horizontals colour-coded by the
                  above/inside partition and LOOK at them. A partition you have not seen is not
                  measured. Say in the memo what you saw, including anything that contradicts you.
  must not move = every harness threshold, the solver, the camera lock, and the coordinate contract
SECOND SOURCE: clay in the corpus is one clip at one venue, so any statement of the form "the
solver fails on clay" is unsupported by n=1 venue. Either measure a second clay source or state
explicitly in the memo that the finding is venue-scoped and must not be generalised. Do not
acquire footage for this -- if no second clay clip is already in the corpus, say so.
EVIDENCE: docs/evidence/tracking/g60_clay_horizontals_2026-09-0X.md with the reproduction of the
premise, both partitions with intervals, the counterfactual acceptance, the renders committed
under docs/evidence/tracking/g60_renders/, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add any code; run only that file. Never a full pytest.
POD: read-only. You may read tables and footage; NO scp of any module, no daemon restart, never
kill anything on the pod.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a3,
no push. Report the sha.
SHARED MODULE: none expected. If you find yourself editing track_daemon.py or tracking_harness.py,
STOP -- you have left the scope of this row.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
