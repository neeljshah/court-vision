GAP G115 | sport basketball | worktree a8 | log cx_g115_paint_line_recall
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This finally RUNS a measurement three rows have been blocked on. Read
docs/evidence/tracking/g110_tile_nonreproducibility_2026-09-02.md and the committed G93 protocol
first.
THE BLOCKAGE IS NOW UNDERSTOOD AND IT IS SMALLER THAN IT LOOKED. G93 preregistered a paint-line
detection-recall protocol (12 degree angle, 12 px perpendicular, 20 px endpoint extension, a fixed
miss-reason vocabulary) and refused to report because its source tiles were absent. G103 rebuilt
them and got 0/33 checksum matches and correctly stopped. G110 then diagnosed it properly:
  - **33/33 seek-versus-sequential pixel-identical**, so decoding is deterministic and frame
    seeking is NOT the problem.
  - **30 of 33 are the SAME PICTURE** with only JPEG write-path byte differences.
  - **3 frames are genuinely different content**, because the `WFl3V7ZY4ss` source has a timeline
    divergence -- it was re-acquired, the same class of loss as the pruned tennis_10 source.
WHY THAT UNBLOCKS THIS. The G93 measurement is a HUMAN deciding which paint lines are visible in a
frame. It never needed byte-identical tiles; it needed the same picture. Thirty of the thirty-three
are the same picture and are therefore valid input. G110 separately established that the G84 renders
carry overlays and so are not valid unannotated detector input -- use the REBUILT tiles, not the
renders.
RUN G93 EXACTLY AS PREREGISTERED, on 30 frames:
  (a) EXCLUDE the 3 content-divergent frames. Name them, state that G110 identified them, and
      report the denominator as 30, not 33. Do NOT substitute replacement frames -- a fresh draw
      would break commensurability with G84's 11.22 pct precision, which was measured on this
      sample.
  (b) Do NOT re-choose the angle tolerance, the distance tolerance or the miss-reason vocabulary.
      They are committed at 98b7d6974 and were fixed before anyone saw the candidates. Re-picking
      them now, with the data visible, is B8 self-fit and would waste the preregistration.
  (c) Hand-mark by eye which of the four paint lines (baseline, free-throw, two lane lines) are
      VISIBLE per frame. Visible is the denominator; a line off-frame or fully occluded is not a
      detection failure.
  (d) Report detection recall OVERALL and PER LINE ROLE with Wilson 95 pct intervals, the exact
      visible-line denominator, and the miss-reason histogram.
WHAT THE NUMBER MEANS, so it is framed correctly: G84 measured candidate PRECISION at 11.22 pct over
1,764 audited candidates and found all four paint lines co-present in 0 of 33 frames. G87 falsified
the idea that the parallel/orthogonal gate discards true lines: 11 of 12 pass it. So the loss is
upstream of the gate and recall is the missing half. A LOW recall is a decisive, valuable result --
it says basketball court_feet is detector-limited and names which line to attack first. A high
recall would be equally decisive and would move suspicion back downstream.
DO NOT tune the detector, change 28.0 / 5.0 / 10.0, touch line_calibration.py, alter the G84 sample
or seed, or change any threshold.
ACCEPTANCE RULE:
  metric        = paint-line detection recall overall and per role, Wilson 95 pct intervals, plus
                  the miss-reason histogram
  before        = unmeasured and blocked three times; precision 11.22 pct and 0/33 four-line
                  co-occurrence are known
  bar           = NO pass bar on recall. Success is the frozen protocol run unchanged on the 30
                  valid frames with the 3 exclusions named, and the recall reported with its exact
                  denominator.
  n             = 30 frames; state the visible-line denominator exactly, which will be under 120
  eye check     = REQUIRED and it is the measurement. Commit the overlays you judged from.
  must not move = the G93 protocol at 98b7d6974, the G84 sample and seed, every detector parameter,
                  line_calibration.py, the G87 finding, and every harness threshold
EVIDENCE: docs/evidence/tracking/g115_paint_line_recall_2026-09-0X.md with the 3 named exclusions,
the recall table by role, the miss-reason histogram, the overlays, and a NOT VERIFIED list. Commit
under docs/evidence/tracking/g115_recall/ BEFORE reporting (A7). Do NOT commit the 116 MB of contact
sheets.
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
