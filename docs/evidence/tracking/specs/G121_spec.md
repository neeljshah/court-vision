GAP G121 | sport basketball | worktree a7 | log cx_g121_corner_pixel_targets
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A GROUND-TRUTH labelling row that unblocks a blocked measurement. Read
docs/evidence/tracking/g119_paint_corner_detector_2026-09-02.md and
g111_basketball_reachability_2026-09-02.md first.
WHY THIS EXISTS. G119 was dispatched to test whether a corner-first detector beats the line route on
basketball, and it correctly returned NOT VALIDATED. G111 recorded **616 visible named-corner roles
across 220 frames** -- which corners are visible -- but committed **no pixel targets**, so there is
nothing to compare a proposed corner location against. Scoring a detector against its own proposals
is circular and is contract B1. The refusal was right; the gap is in the evidence, not the lane.
WHY IT IS WORTH FIXING RATHER THAN ABANDONING. Basketball is the one sport of five where calibration
is reachable: G111 found court_feet geometrically reachable in 147/220 = 66.8 pct of frames through
four visible paint-corner points, against soccer 0/100, football 0/60 on a third direction, and
baseball 1/120. And G115 measured the line route finding only 25 of 68 visible lines = 36.76 pct,
with 14 of its 43 misses being lines split into fragments -- precisely the failure a corner, as a
LOCAL feature, does not inherit. The corner route is the most promising untried idea in the
programme and it needs exactly one thing: pixel targets.
DO THIS:
  (a) Take a SEEDED SUBSET of the G111 frames -- reuse the G111 seed and manifest, do not draw a new
      sample. Aim for enough frames to give a usable denominator without labelling all 220; state
      how many you chose and why that number, BEFORE labelling.
  (b) For every VISIBLE corner in those frames, per the G111 labels, record its PIXEL coordinate by
      eye, with its corner ROLE. Use the role names G111 already uses; do not invent a second
      vocabulary.
  (c) RECORD YOUR OWN PRECISION. Re-label a seeded 15 pct of the corners a second time, blind to
      your first pass, and report the median and 90th-percentile displacement in pixels between the
      two passes. That number is not decoration: it is the floor on any tolerance a later row may
      claim, because a detector cannot be shown to be more accurate than the labels it is scored
      against. G76 found a basketball criterion 68.6 pct reliable and G85 found a tennis one 75 pct,
      so do not assume your own labels are exact -- measure them.
  (d) Commit the targets as a plain tracked CSV keyed by clip, frame index and corner role, next to
      the G111 artefacts, so G119 can be re-run against them unchanged.
  (e) DO NOT run a detector, do not measure recall, and do not tune anything. This row produces
      ground truth and stops. Mixing labelling and evaluation in one pass is how a tolerance gets
      chosen to fit the errors.
DO NOT relabel G111 visibility, change its seed or manifest, touch line_calibration.py, change any
threshold, or declare court_feet for any clip.
ACCEPTANCE RULE:
  metric        = number of visible corners with a committed pixel target, plus the measured
                  self-agreement displacement (median and p90) from the blind re-label
  before        = 616 visible corner roles recorded, 0 pixel targets, G119 blocked as circular
  bar           = NO pass bar on the displacement value. Success is targets committed for every
                  visible corner in the chosen subset, and the self-agreement measured and reported.
                  A large displacement is a valuable finding: it would say corners cannot be
                  localised reliably by eye at this resolution, which changes what a detector could
                  ever be asked to match.
  n             = state the frame count you chose and the corner count you labelled; the re-label
                  subset is a seeded 15 pct of the corners, and state that seed too
  eye check     = this row IS the eye check. Commit the frames with your targets drawn on them.
  must not move = the G111 sample, seed, manifest and visibility labels, the corner role vocabulary,
                  line_calibration.py, every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g121_corner_pixel_targets_2026-09-0X.md with the subset size and its
justification stated first, the target count, the self-agreement displacement, the rendered targets,
and a NOT VERIFIED list. Commit the CSV and renders under
docs/evidence/tracking/g121_corner_targets/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the daemon and seven bridge lanes are live.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
