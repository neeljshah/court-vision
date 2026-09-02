GAP G111 | sport basketball | worktree a7 | log cx_g111_basketball_reachability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This CLOSES the one hole in the consolidated reachability verdict. Read the REACH
row in TRACKING_GAPS_2026-09-01.md, plus g101_soccer_reachable_solve_2026-09-02.md and
g104_baseball_reachability_2026-09-02.md, and copy their method exactly so the sports compare.
THE HOLE. Four sports now have a reachability answer: soccer unreachable (points >=4 in 0/100, lines
>=4 in 0/100, never more than two independent directions), football unreachable (two directions in
17/60, a third in 0/60, absolute-yard reference in 0/60), baseball 1/120 = 0.8 pct overhead-only,
tennis reachable. BASKETBALL HAS ONLY DETECTOR NUMBERS, never a reachability census: candidate
precision 11.22 pct over 1,764 audited candidates (G84), all four paint lines co-present in 0 of 33
frames (G84), and the parallel/orthogonal gate exonerated at 11 of 12 true paints passing (G87).
Nobody has asked whether the geometry is even ON SCREEN often enough.
BASKETBALL MAY GENUINELY DIFFER and that is why this is worth measuring rather than assuming:
a basketball court is small, a broadcast frame often contains a whole half-court, and the paint is a
rectangle with FOUR DISTINCT-ROLE lines meeting at right angles -- two independent directions by
construction, plus the three-point arc as a conic and the centre circle. So it has a better shot at
four independent constraints than football, whose stripes are all mutually parallel.
METHOD, matching G101 and G104:
  (a) Seeded stratified sample of >= 100 frames across ALL basketball pod clips (ncaa_basketball and
      wnba). State the seed and per-clip counts. Do not head-slice. You may NOT reuse the 33 G84
      frames as the whole sample: they were selected as PAINT_SOLVABLE, which is a positive-biased
      slice and would overstate reachability. If you include them, report them separately.
  (b) Per frame count identifiable POINT features (paint corners, free-throw-line intersections,
      centre-circle and arc landmarks, court corners) and named LINES with their number of
      INDEPENDENT directions. Two parallel lines are one constraint.
  (c) Report >= 4, >= 3 and >= 2 shares for points, and the independent-direction distribution.
  (d) ONE SENTENCE: is basketball court_feet reachable from this corpus, and in what share of frames.
DO NOT build a solver, tune any detector, touch line_calibration.py, declare a coordinate space, or
change any threshold.
ACCEPTANCE RULE:
  metric        = per-frame identifiable point features and independent line directions over >= 100
                  seeded frames
  before        = uncensused; only detector precision 11.22 pct and 0/33 four-line co-occurrence
  bar           = NO pass bar. Success is the census with the G101/G104 method and the one-sentence
                  answer. Either answer completes the five-sport picture and is a full success.
  n             = >= 100 seeded frames; state the seed, per-clip counts, and the G84-overlap count
  eye check     = REQUIRED and it is the whole measurement. Commit every frame you judged.
  must not move = every threshold, the coordinate contract, every verdict, line_calibration.py, and
                  the G84/G87 findings
EVIDENCE: docs/evidence/tracking/g111_basketball_reachability_2026-09-0X.md with the distributions,
the one-sentence answer, the renders, and a NOT VERIFIED list. Commit under
docs/evidence/tracking/g111_basketball_reach/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
