GAP G102 | sport tennis | worktree a6 | log cx_g102_ball_label_temporal
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This row changes the QUESTION, because writing the answer down
more carefully has now been measured and does not work. Read
docs/evidence/tracking/g98_ball_recall_precision_2026-09-02.md first.
THE MEASURED DEAD END, and it took four rows to establish, so do not repeat it:
  - G65 refused to label balls it could not see: 41/150 visible, 109 uncertain.
  - G78A/B/C resolved those 109 in three chunks and disagreed wildly (96.7 / 84.4 / 27.7 pct).
  - G85 blind-relabelled 60 seeded rows: the clip split is real, but raw agreement with the chunk
    labels is only **45/60 = 75.0 pct**, disagreeing in BOTH directions.
  - G92 wrote an exemplar card to calibrate the criterion, and G98 step 0 then measured that the
    card changed **0 of 109 labels** and left the identical 45 agreeing frames. The criterion was
    documented, not calibrated, and agreement did not move because no decision moved.
So the conclusion is now evidence-backed: a single still frame at tiled 2x does not carry enough
information for two passes to agree on whether a tennis ball is present. More prose about the
boundary will not fix that. The INPUT has to change.
THE HYPOTHESIS TO TEST, and it is the one thing a still frame throws away: MOTION. A small,
low-contrast, motion-blurred ball is genuinely ambiguous in one frame and often obvious across
three, because the eye locks onto a consistent trajectory that noise and court texture do not have.
This is why a human watching video finds the ball trivially and a human shown one frame does not.
DO THIS:
  (a) Build a 3-FRAME STRIP render for a seeded sample of >= 40 of the 109 uncertain rows: the
      labelled frame plus its immediate predecessor and successor, at the same tiled 2x or better,
      spatially aligned so a moving object traces a line across the strip. State the seed. Commit
      the strips.
  (b) ONE labeller labels those 40 rows from the STRIPS ONLY, blind to every prior label, including
      their own from any earlier row. Anchoring on a prior call is what would reproduce the old
      numbers regardless of whether the strip helped.
  (c) MEASURE THE THING THAT MATTERS: agreement. Compare the strip labels against the G85 blind
      labels on whatever subset overlaps, and report the agreement with a Wilson 95 pct interval.
      Then compare it to the 75.0 pct (Wilson 62.8-84.2) that the still-frame method produced. The
      deliverable is whether agreement MOVED, not whether more rows resolved.
  (d) BEWARE THE TRAP THAT WOULD MAKE THIS ROW WORTHLESS: a strip will almost certainly resolve MORE
      rows to ball_visible, and that is NOT the result. Resolving more rows with the same
      disagreement rate is just a more confident version of the same problem, and it is exactly the
      shape of the 78A/B/C chunks that started this. Report the resolved rate, but judge the method
      on AGREEMENT.
  (e) If agreement does not move, say so plainly and state what that implies: the ball genuinely is
      not recoverable from this footage at this resolution, which is a real and reusable fact about
      which tennis footage supports ball work, and it redirects the effort to acquisition rather
      than to labelling.
DO NOT relabel the other 109 rows wholesale, do not overwrite the chunk labels, the G85 blind
labels or the G92 card, do not change any harness threshold, and do not touch the y-gate or the
coordinate contract. Write your labels to a new file.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = inter-pass agreement on the strip-labelled rows, with a Wilson 95 pct interval,
                  compared against the still-frame 75.0 pct (62.8-84.2)
  before        = 75.0 pct agreement from still frames, unchanged by an exemplar card that moved 0
                  of 109 labels
  bar           = there is NO pass bar. Success is the strips built, the blind labelling done, and
                  agreement measured against the same baseline. Agreement that does NOT move is a
                  full success and it closes the labelling branch for good.
  n             = >= 40 seeded rows from the 109; state the seed and the overlap size with the G85
                  blind set, since that overlap is the denominator of the agreement number
  eye check     = this row IS the eye check. Commit every strip you labelled from.
  must not move = the chunk labels, the G85 blind labels, the G92 card, the pooled 110/150 count,
                  every harness threshold, the y-gate, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g102_ball_label_temporal_2026-09-0X.md with the seed, the strips,
the agreement and its interval, the explicit comparison to 75.0 pct, the resolved rate reported but
clearly subordinate, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g102_temporal_labels/ BEFORE reporting (A7).
CAUTION FROM TODAY: two lanes wrote evidence directly into the MAIN working tree and one of them
dropped two ledger rows another session had appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the track daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
