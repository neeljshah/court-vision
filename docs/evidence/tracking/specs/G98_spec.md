GAP G98 | sport tennis | worktree a6 | log cx_g98_ball_recall_precision
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This is G44B attempt 4. Attempts 1-3 all refused for good
reasons and each refusal removed the blocker for the next. Read
docs/evidence/tracking/g92_ball_criterion_calibration_2026-09-02.md and the G44B ledger row first.
THE CHAIN THAT LED HERE, because it is the reason this attempt is allowed to run at all:
  - G44B refused to fabricate precision from uncertain rows. Correct.
  - G65 refused to label balls it could not see, returning 41/150 visible and 109 uncertain.
  - G78A/B/C resolved the uncertain rows in three chunks and disagreed sharply, 96.7 / 84.4 / 27.7.
  - G85 blind-relabelled 60 seeded rows and showed the split is a CLIP property, not a labeller
    one, but measured only 45/60 = 75.0 pct raw agreement with the chunk labels.
  - G92 wrote an exemplar card, relabelled all 109 under it, and pooled to **110/150**, which
    clears the >= 100 resolved positives that G44B named as its precondition.
SO THE PRECONDITION IS MET. It is met with a caveat that must appear in every number this row
reports.
STEP 0, A VERIFICATION YOU OWE BEFORE ANYTHING ELSE. G92 reports agreement against the G85 blind
labels as 45/60 = 75.0 pct, which is EXACTLY the figure G85 measured before the exemplar card
existed. An identical count before and after a criterion change is possible, but it is also what
you would see if the relabel had not actually changed any decision. Check which it is: report how
many of the 109 rows CHANGED label under the card, and whether the 45 agreeing rows are the SAME 45
rows or a different set that happens to total 45. If nothing changed, the card did not do its job
and this row must stop and say so. Do not build a measurement on top of an unverified premise --
that is precisely how the retracted numbers in this repo got made.
THE MEASUREMENT, if step 0 clears: ball detection RECALL and PRECISION on tennis, against the
calibrated labels.
  - Recall  = of the frames labelled ball_visible, how many does the tracker produce a ball row for.
  - Precision = of the ball rows the tracker produces, how many land on a frame labelled
    ball_visible, and how close to the labelled position.
  - State the position tolerance BEFORE you measure and justify it in one clause. A tolerance
    chosen after seeing the errors is B8 self-fit.
  - Report Wilson 95 pct intervals on both. With ~110 positives the intervals will be wide; that is
    the honest width and it must not be narrowed by pooling in rows you did not label.
CARRY THE LABEL NOISE INTO THE RESULT, do not bury it in a caveat section. G92 measured 75.0 pct
agreement (Wilson 62.8-84.2) between two independent passes over the same rows. That means roughly
a quarter of your ground truth is contested. A recall of 0.80 against a ground truth that two
labellers agree on only 75 pct of the time cannot be quoted as 0.80 full stop. State plainly what
the label noise does to each number and its interval. If you conclude the noise is large enough
that the measurement cannot separate a good tracker from a mediocre one, SAY THAT AND STOP -- that
is a fourth honest refusal and it is worth more than a precise-looking number built on contested
labels.
PER-CLIP, NOT ONLY POOLED. The three clips differ enormously (95.0 / 80.0 / 30.0 pct ball-visible
under the blind pass), so a pooled recall is dominated by whichever clip contributed most rows.
Report per clip and pooled, and say which clips the pooled figure is really describing.
DO NOT change any harness threshold, do not change the y-gate, do not relabel anything, and do not
touch the coordinate contract. The unresolved 78 pct versus 52 pct y-gate disagreement is NOT this
row; if your numbers bear on it, note it in one sentence and leave it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tennis ball recall and precision per clip and pooled, with Wilson 95 pct
                  intervals, each stated against the measured label agreement
  before        = never measured; blocked four times on an insufficient positive count
  bar           = there is NO pass bar on the recall or precision values. Success is step 0
                  verified, the tolerance preregistered, both metrics reported per clip with
                  intervals, and the label noise carried into every claim. A refusal on label
                  noise grounds is a full success.
  n             = the calibrated positives (110 expected) and the tracker ball rows over the same
                  frames; state both denominators exactly
  eye check     = REQUIRED on the disagreements. Render at least 10 frames where the tracker and
                  the label disagree, both directions, and say which one is right in each. That is
                  what distinguishes a tracker error from a label error, and with 25 pct contested
                  labels you cannot assume it is always the tracker.
  must not move = the G92 calibrated labels, the G85 blind labels, the chunk labels, the y-gate,
                  every harness threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g98_ball_recall_precision_2026-09-0X.md with the step 0 result, the
preregistered tolerance, per-clip and pooled metrics with intervals, the disagreement renders and
their adjudication, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g98_ball_metrics/
BEFORE reporting (A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the track daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
