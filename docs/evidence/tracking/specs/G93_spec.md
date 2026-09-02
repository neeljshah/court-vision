GAP G93 | sport basketball | worktree a8 | log cx_g93_line_detection_limit
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. A LIMIT measurement. Read
docs/evidence/tracking/g84_candidate_line_quality_2026-09-02.md and
docs/evidence/tracking/g87_paint_gate_perspective_2026-09-02.md first.
WHERE THIS SITS. Basketball paint calibration has been chased down two wrong branches and this row
closes the third. G84 measured the candidate line detector on 33 seeded PAINT_SOLVABLE frames
(seed 84092026, 1,764 audited candidates) and found only 11.22 pct of candidate groups are actually
court lines, and that ALL FOUR paint lines were present together in 0 of 33 frames. G87 then tested
whether the parallel / orthogonal gate in domains/basketball/tracking/line_calibration.py:196-198
was what discarded them, and FALSIFIED that: 11 of 12 true paint lines PASS the gate. The gate is
exonerated -- do NOT make it perspective-invariant, and do not re-open G87.
So the loss is UPSTREAM of the gate: the detector does not PROPOSE the lines in the first place.
THE QUESTION, and it is a single number: of the true paint lines VISIBLE to the eye in a frame,
what fraction does detect_lsd_segments(image, 28.0) followed by
candidate_line_group_details(..., 5.0, 10.0) propose as a candidate group AT ALL? That is DETECTION
RECALL and nobody has measured it. G84 measured candidate PRECISION (11.22 pct), which is the other
direction and does not answer this.
METHOD:
  (a) Reuse the G84 seeded frame sample so the two numbers are commensurable -- same 33 frames,
      same seed 84092026, same clips. State that you reused it. Drawing a fresh sample here would
      mean the precision and recall numbers describe different frame sets, which is how two true
      numbers get combined into a false one.
  (b) For each frame, hand-mark by eye which of the four paint lines (baseline, free-throw line,
      two lane lines) are VISIBLE. Visible is the denominator; a line off-frame or fully occluded
      by players is not a detection failure and must not be counted as one. Commit the marks.
  (c) For each VISIBLE line, decide whether any returned candidate group lies on it. Define the
      correspondence rule BEFORE you look -- an angle tolerance and an endpoint or perpendicular
      distance tolerance in pixels -- and state it. A rule chosen after seeing the candidates is
      B8 self-fit.
  (d) Report detection recall overall and per line ROLE. The roles matter separately: if the
      baseline is found 90 pct of the time and the free-throw line 10 pct, the fix is specific and
      cheap; if all four sit near 20 pct, the fix is detector sensitivity and it is expensive. That
      split is the deliverable.
  (e) For every MISSED visible line, record WHY in one word from a fixed vocabulary you declare up
      front -- for example low_contrast, occluded_partial, too_short, merged_with_neighbour,
      split_into_fragments, painted_over_by_court_logo. Counting the reasons is what turns this
      into an actionable next row instead of a discouraging number.
DO NOT build a better detector in this row, do not tune 28.0 / 5.0 / 10.0, and do not touch
line_calibration.py. Tuning against the sample you are measuring on is self-fit; a threshold change
needs its own row with a held-out sample.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = detection recall on VISIBLE paint lines, overall and per line role, with Wilson
                  95 pct intervals, plus a miss-reason histogram
  before        = unmeasured; only precision (11.22 pct) and the 0-of-33 all-four co-occurrence
  bar           = there is NO pass bar. A low recall is a decisive and valuable result -- it says
                  basketball court_feet is detector-limited and names which line to attack first.
  n             = the 33 G84 frames; the denominator is the visible-line count, which will be under
                  132, and it must be stated exactly
  eye check     = this row IS the eye check. Render every frame with its candidates overlaid and
                  your visibility marks, and commit the renders.
  must not move = the G84 sample and seed, every detector parameter, line_calibration.py, every
                  harness threshold, the G87 finding, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g93_line_detection_limit_2026-09-0X.md with the recall table by
role, the correspondence rule stated before use, the miss-reason histogram, the renders, and a NOT
VERIFIED list. Commit under docs/evidence/tracking/g93_detection_limit/ BEFORE reporting (A7).
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the tracking daemon and seven footage bridge lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
