GAP G92 | sport tennis | worktree a6 | log cx_g92_ball_criterion_calibration
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This UNBLOCKS G44B. Read
docs/evidence/tracking/g85_ball_label_consistency_2026-09-02.md first -- it is the row that
produced this one.
WHAT G85 SETTLED AND WHAT IT DID NOT. Settled: the low resolved rate on tennis_10 is a CLIP
property, not a labeller property. A blind seeded relabel (seed 850917, 20 rows per clip, 60 total)
preserved the ordering: nyYk 19/20 = 95.0 pct, tennis_09 16/20 = 80.0 pct, tennis_10 6/20 = 30.0 pct.
NOT settled, and this is the blocker: raw agreement with the prior chunk labels was only
**45/60 = 75.0 pct**, and on tennis_10 the disagreements ran in BOTH directions (1 prior-visible /
blind-uncertain, 5 prior-uncertain / blind-visible). Two-directional disagreement means an
AMBIGUOUS CRITERION, not a biased labeller, and those have different fixes. The closing sentence of
G85 names the required fix: criterion calibration with examples at the ball_visible / uncertain
boundary, before any pooling.
WHY IT MATTERS CONCRETELY: pooled, the three chunks take tennis ball-visible from 41/150 to
110/150, which clears the >= 100 resolved positives that G44B named as its precondition for
measuring ball recall and precision at all. That pooled figure MUST NOT be used until this row
lands. One criterion on one clip is currently what stands between here and the tennis ball
measurement.
PRECEDENT: G76 found the basketball paint criterion measurably permissive at 68.6 pct raw
agreement. Two sports, two criteria, both near 70-75 pct. That repetition deserves a sentence in
your memo: an unexemplified natural-language criterion lands around 70 pct agreement, which is why
this row is a METHOD and not a one-off.
DO THIS:
  1. WRITE THE CRITERION AS EXEMPLARS, not as more prose. Pick and commit boundary cases from the
     existing renders: at least 4 clear ball_visible, 4 clear uncertain, and at least 6 sitting ON
     the boundary with a written adjudication of each and the ONE feature that decided it (ball
     diameter in pixels, motion-blur streak length, contrast against whatever it is over, partial
     frame exit). Prose alone is what produced 75 pct; a reader must be able to hold your card next
     to a new tile and get your answer.
  2. RE-LABEL all 109 previously-uncertain rows ONCE under the exemplar card, at tiled 2x or
     better. Write to a NEW file; do not overwrite the chunk labels or the G85 blind labels. Both
     are evidence of what a criterion-free pass produces and they stay.
  3. RE-MEASURE agreement of the new pass against the G85 blind labels on the SAME 60 rows. That is
     the test of whether the card worked. Report it with a Wilson 95 pct interval.
  4. REPORT the pooled resolved count under the calibrated criterion, per clip and total, and say
     plainly whether it clears 100 positives. If it does NOT clear 100, say so and stop -- do not
     stretch the criterion to reach the number. A criterion moved to hit a precondition is the
     purest form of B8 self-fit and it would poison every measurement downstream of it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = agreement between the calibrated relabel and the G85 blind labels on the 60
                  seeded rows, with a Wilson 95 pct interval
  before        = 45/60 = 75.0 pct raw agreement, criterion unexemplified
  bar           = there is NO pass bar on the agreement number. Success is the exemplar card
                  existing, the relabel done once under it, the agreement measured, and the pooled
                  count reported honestly. An agreement that does NOT improve is a real finding: it
                  says the boundary is intrinsically ambiguous at this zoom, which routes the next
                  row to higher zoom or to a different definition rather than to more labelling.
  n             = all 109 uncertain rows relabelled; agreement measured on the 60 G85 blind rows
  eye check     = this row IS an eye check, at tiled 2x or better. A call made at lower zoom is the
                  error G65 attempt 1 made when it returned 100 pct uncertain from whole frames.
  must not move = the existing chunk labels, the G85 blind labels, the G85 seed, every harness
                  threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g92_ball_criterion_calibration_2026-09-0X.md with the exemplar card
inline, the re-measured agreement and its interval, the per-clip and pooled counts, a plain yes/no
on the 100-positive precondition, and a NOT VERIFIED list. Commit the card, the exemplar renders and
the new labels under docs/evidence/tracking/g92_criterion/ BEFORE reporting (A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the tracking daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
