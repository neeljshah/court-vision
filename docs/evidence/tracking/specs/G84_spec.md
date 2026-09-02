GAP G84 | sport basketball | worktree a4 | log cx_g84_candidate_line_quality
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. MEASURE THE INPUT. Build no solver and no role rule.
WHY THIS ROW EXISTS: G75 attempt 1 tried to assign paint roles and failed -- it did not beat the
naive image-position baseline, 23 of 30 held-out frames emitted NOTHING, and the quadrilaterals it
did emit followed GRAPHICS, BORDERS and NON-PAINT STRUCTURES. That is not a role-rule failure. If
the candidate line groups reaching the rule are graphics and borders, then no naming scheme built on
top of them can work, because the input is already wrong. So this row measures the input.
READ FIRST: docs/evidence/tracking/g60_clay_horizontals_2026-09-02.md. G60 found structurally the
SAME thing on tennis clay -- 250-265 spurious horizontals per frame from the crowd and the sponsor
band swamping far-line role assignment. Two sports, two surfaces, one shape. G60 also found that
EXCLUDING the spurious segments did not rescue the solve (0/40 accepts), so be alert for the same
outcome here: a clean input is necessary, not automatically sufficient.
MEASURE:
  (a) On >= 30 frames that the G76-AUDITED labelling calls PAINT_SOLVABLE -- use the AUDITED labels,
      not the original census ones, because the census criterion was measurably permissive (20 of 69
      positives were over-called) -- run `candidate_line_groups` and render EVERY returned group
      with its index drawn on it.
  (b) Hand-label each group by eye: court_line / graphic / border / reflection / other. Report the
      court-line fraction with a Wilson 95 pct interval.
  (c) THE NUMBER THAT MATTERS: the count and fraction of frames where ALL FOUR paint lines are
      actually PRESENT among the candidates. That is the ceiling on any role rule whatsoever. If it
      is low, the paint route is limited by DETECTION rather than by naming, and G75 attempt 2 must
      not be written at all.
  (d) Say whether you see the venue hazards the calibration strategy named: a glossy reflective
      floor, and court-coloured paint fills that vary by venue.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = court-line fraction among candidate groups, and the all-four-present frame fraction
  before        = unmeasured; G75 assumed the candidates were court lines and the renders say they
                  are not
  bar           = THERE IS NO PASS BAR. Success is the two measured fractions with intervals and the
                  renders behind them. A LOW court-line fraction is a valuable answer and would
                  redirect basketball from naming to detection.
  n             = >= 30 PAINT_SOLVABLE frames; state the per-clip counts and the seed
  eye check     = this row IS the eye check. Every candidate group is labelled by looking at it.
  must not move = every harness threshold, the coordinate contract, line_calibration.py itself, and
                  the basketball producer. You measure; you change nothing.
NON-TAUTOLOGY: do not label a group `court_line` because the role rule accepted it, or `graphic`
because it rejected it. The label comes from the PICTURE alone -- the rule's opinion is the thing
being tested, so using it as truth is circular (B7/B8).
DURABILITY (A7): commit the per-group labels, the seed and the renders under
docs/evidence/tracking/g84_candidate_quality/ BEFORE reporting.
FOOTAGE: basketball footage is POD-ONLY; the G68 contact sheets already exist under
docs/evidence/tracking/g68_paint_census/contact_sheets/. Read-only frame work on the pod is fine.
EVIDENCE: docs/evidence/tracking/g84_candidate_line_quality_2026-09-0X.md with both fractions and
their intervals, the renders, the venue-hazard observations, an explicit statement on whether G75
attempt 2 should be written at all, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. No scp, no deploy, never kill anything -- another session has live processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
