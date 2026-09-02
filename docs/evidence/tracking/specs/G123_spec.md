GAP G123 | sport basketball | worktree a3 | log cx_g123_low_contrast_lines
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This takes the OTHER half of a measured failure. Read
docs/evidence/tracking/g115_paint_line_recall_2026-09-02.md first.
THE MEASURED SPLIT. G115 measured basketball paint-line detection recall at 25 of 68 visible lines
= 36.76 pct, Wilson [26.30, 48.64], on the 30 valid G84 frames under the protocol frozen at
98b7d6974. Of its 43 misses, the fixed-vocabulary histogram gives **low contrast 17** and **split
into fragments 14**. G120 is taking the fragmentation half in parallel. This row takes low contrast,
which is the larger single bucket.
THIS IS THE ONE SPORT WHERE IT IS WORTH DOING. G111 measured basketball court_feet as geometrically
reachable in 147/220 = 66.8 pct of frames, against soccer 0/100, football a third direction in 0/60,
and baseball 1/120. And G87 exonerated the parallel/orthogonal gate at 11 of 12 true paints passing.
So the geometry is on screen, the gate is fine, and the detector is the whole problem.
THE TASK: test whether contrast normalisation before segment detection recovers low-contrast lines,
and measure what it costs.
  (a) Try the SIMPLEST preprocessing that could work, applied before `detect_lsd_segments`. CLAHE or
      an equivalent local contrast operator is the obvious candidate. Resist building anything
      learned for a feasibility test, and implement in scripts/platformkit or domains/basketball --
      NOT in line_calibration.py and NOT under src/, kernel/, api/, scripts/team_system/ or intel/.
  (b) PRE-REGISTER the parameters before you run: clip limit, tile grid, colour space, and whether
      it is applied to the whole frame or a court region. Write them in the memo BEFORE any recall
      number. Choosing them against the frames you then measure on is B8 self-fit.
  (c) RE-MEASURE recall on the SAME 30 frames and the SAME 68 visible lines under the frozen
      protocol. Do not re-choose the correspondence tolerances and do not relabel visibility. Report
      before and after with Wilson intervals, and report the miss-reason histogram after, so it is
      visible whether the 17 low-contrast misses actually moved or whether some other bucket grew.
  (d) MEASURE THE COST. Report candidate PRECISION before and after against the G84 audited labels.
      Contrast enhancement amplifies noise as readily as signal: crowd texture, court logos, shadow
      edges and sponsor paint all become more line-like. A recall gain bought with a precision
      collapse is not a gain, and reporting that honestly is a full success.
  (e) STATE the implied all-four-line co-occurrence under your new recall and compare it to the
      1.83 pct that 36.76 pct implies. That is the number that decides whether a solve becomes
      possible.
DO NOT change any harness threshold, the coordinate contract, the rung ladder, the G84 sample or
seed, the G115 visibility labels, or the detector parameters 28.0 / 5.0 / 10.0. Do not declare
court_feet for any clip.
ACCEPTANCE RULE:
  metric        = recall on the same 68 visible lines before and after preprocessing, with Wilson
                  95 pct intervals; AND candidate precision before and after; AND the after
                  miss-reason histogram
  before        = recall 25/68 = 36.76 pct [26.30, 48.64]; 17 of 43 misses low contrast; candidate
                  precision 11.22 pct
  bar           = NO pass bar on the gain. Success is parameters preregistered, recall and precision
                  BOTH re-measured on the frozen sample, and the histogram shown after. A REJECT on
                  precision grounds is a full success.
  n             = the same 30 frames and 68 visible lines; state both denominators
  eye check     = REQUIRED. Render the preprocessed frames with detected segments and look at them.
                  Contrast enhancement that turns crowd texture into convincing court lines is the
                  exact failure mode and it will score well while being wrong. Commit the renders.
  must not move = the G93/G115 protocol at 98b7d6974, the G84 sample and seed, the G115 visibility
                  labels, line_calibration.py, every detector parameter, every harness threshold,
                  the coordinate contract, and the G87 finding
EVIDENCE: docs/evidence/tracking/g123_low_contrast_lines_2026-09-0X.md with the parameters stated
first, before/after recall and precision, the after histogram, the implied co-occurrence, the
renders, and a NOT VERIFIED list. Commit under docs/evidence/tracking/g123_contrast/ BEFORE
reporting (A7).
NOTE: G120 is taking the fragmentation bucket in parallel and G121 is labelling corner pixel targets
for a corner-first route. All three are deliberately independent. Do not wait for them, do not merge
fragments here, and do not build a corner detector here.
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
