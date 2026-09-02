GAP G120 | sport basketball | worktree a8 | log cx_g120_fragment_merge
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This attacks the largest ADDRESSABLE cause of a now-measured failure. Read
docs/evidence/tracking/g115_paint_line_recall_2026-09-02.md first.
BASKETBALL IS NOW FULLY DIAGNOSED across four rows, and this is the one actionable piece:
  - G111: the geometry IS on screen -- court_feet geometrically reachable in 147/220 = 66.8 pct of
    frames through four visible paint-corner points. Basketball is the only sport of five where a
    detector improvement is a lever that exists at all.
  - G87: the parallel/orthogonal gate is exonerated -- 11 of 12 true paint lines PASS it.
  - G115: the LINE DETECTOR finds 25 of 68 visible lines = 36.76 pct, Wilson [26.30, 48.64].
  - Cross-check: 0.3676^4 = 1.83 pct for all four lines, giving 0.60 expected all-four frames in 33,
    and G84 observed 0 of 33. Consistent. The recall number explains the co-occurrence number.
  - Miss reasons over the 43 misses: low contrast 17, split into fragments 14.
Fragmentation is the addressable one: the line IS detected, in pieces, and the pieces are never
rejoined. Low contrast is a property of the footage and is not this row.
THE TASK: merge collinear fragments before grouping, and re-measure recall under the SAME frozen
protocol.
  (a) Implement fragment merging in scripts/platformkit or domains/basketball. Do NOT modify
      line_calibration.py and do NOT touch src/, kernel/, api/, scripts/team_system/ or intel/.
  (b) PRE-REGISTER the merge rule before you run it: the collinearity tolerance in degrees, the
      maximum gap in pixels between fragments to be joined, and any minimum merged length. Write
      them in the memo BEFORE any recall number. Tuning them against the frames you then measure on
      is B8 self-fit and would invalidate the result.
  (c) RE-MEASURE recall on the SAME 30 frames and the SAME 68 visible lines under the protocol
      frozen at 98b7d6974. Do not re-choose the correspondence tolerances and do not relabel
      visibility. Report before and after with Wilson intervals, per line role.
  (d) MEASURE THE COST, because merging is not free. Report candidate PRECISION before and after
      against the G84 audited labels where they apply. Merging fragments that are not the same line
      manufactures false lines, and a recall gain paid for with a precision collapse is not a gain.
      Report both or the row is incomplete.
  (e) STATE the all-four-line co-occurrence implied by your new recall and compare it to the 1.83
      pct the current recall implies. That is the number that decides whether a solve becomes
      possible at all.
DO NOT change any harness threshold, the coordinate contract, the rung ladder, the G84 sample or
seed, the G115 visibility labels, or any detector parameter other than the merge rule you add. Do
not declare court_feet for any clip.
ACCEPTANCE RULE:
  metric        = paint-line detection recall on the same 68 visible lines, before and after
                  merging, with Wilson 95 pct intervals; AND candidate precision before and after
  before        = recall 25/68 = 36.76 pct [26.30, 48.64]; candidate precision 11.22 pct (G84)
  bar           = NO pass bar on the recall gain. Success is the merge rule preregistered, recall
                  and precision BOTH re-measured on the frozen sample, and the implied co-occurrence
                  stated. A recall gain that costs more precision than it buys is a REJECT and
                  reporting it as such is a full success.
  n             = the same 30 frames and 68 visible lines; state both denominators
  eye check     = REQUIRED. Render merged lines and look at them. A merge that joins two different
                  court lines into one plausible-looking line is the exact failure mode here, and it
                  will score well while being wrong. Commit the renders.
  must not move = the G93/G115 protocol at 98b7d6974, the G84 sample and seed, the G115 visibility
                  labels, line_calibration.py, every harness threshold, the coordinate contract, and
                  the G87 finding
EVIDENCE: docs/evidence/tracking/g120_fragment_merge_2026-09-0X.md with the merge rule stated first,
before/after recall and precision, the implied co-occurrence, the renders, and a NOT VERIFIED list.
Commit under docs/evidence/tracking/g120_merge/ BEFORE reporting (A7).
NOTE: G119 is separately testing a corner-first route on the same sport, which sidesteps
fragmentation entirely by finding corners directly. The two are deliberately parallel and will be
compared. Do not wait for it and do not build a corner detector here.
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
