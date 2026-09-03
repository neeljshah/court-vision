GAP G140 | sport basketball | worktree a2 | log cx_g140_corner_targets_on_g136
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This is the LAST live basketball idea, and it is now unblocked. Read
docs/evidence/tracking/g138_paint_role_assigner_2026-09-02.md,
g136_recensus_second_pass memo and g121_corner_pixel_targets_2026-09-02.md first.
WHY THE LINE ROUTE IS OVER, so this row is not a rerun of it. Eight rows attacked basketball
court_feet through LINE detection: G120 fragment merge REJECT, G123 CLAHE REJECT, G132 union REJECT
on additivity, G134 stable grouping ACCEPT (recall 25/68 -> 30/68 at 25/25 baseline survival), G135
0 of 30 solvable frames, G137 an all-or-none 173/0/0/0/42 distribution, and G138 the closer:
**0 of 84 claimed role assignments correct, with only 1 of 84 roles independently AVAILABLE** from
the stable groups. A human sees the geometry in 46.2 pct of frames; the detector makes roles
available in about 1.2 pct. That is a factor of roughly 38 and it is an absence of signal, not a
thresholding problem. Do not propose another line-stage change.
WHY CORNERS ARE DIFFERENT AND UNTESTED. G111 measured basketball reachability through four visible
paint-CORNER POINTS, not lines. The existing stack detects line SEGMENTS and only intersects them
into corners at the end, so every stage that loses a fragment loses a corner. A corner is a LOCAL
feature and can be found directly. G119 was dispatched to test that and correctly returned NOT
VALIDATED, because G111 recorded which corner ROLES were visible but committed no PIXEL TARGETS, so
scoring a detector against them would have been circular. G121 was then dispatched to label those
targets and ALSO correctly refused, because G111's labels conflicted with its own renders -- which
the G126 audit confirmed, measuring them at 22/45 = 48.9 pct agreement with source frames.
WHAT CHANGED: G136 produced a replacement census -- 210 source-decoded frames, reachability
97/210 = 46.2 pct [39.6, 52.9], with its own blind second-pass agreement measured at 28/42 = 66.7
pct [51.6, 79.0] and the blindness ordering auditable (blind labels committed before the join).
That is trustworthy enough to label targets against, PROVIDED the caveat travels with it.
DO THIS:
  (a) Take a SEEDED subset of the G136 frames that its census marks as having >= 4 visible corners.
      Reuse G136's manifest and seed; do not re-judge visibility and do not draw a new sample. State
      how many such frames exist and how many you take.
  (b) Record the PIXEL COORDINATE of every visible corner in those frames, with its role, using
      G136's role vocabulary. Commit as a tracked CSV keyed by clip, frame index and role.
  (c) MEASURE YOUR OWN PRECISION, as G121's spec required and this one repeats: re-label a seeded
      15 pct blind to your first pass and report median and p90 displacement in pixels. Report it
      BEFORE any other number. A detector cannot be shown more accurate than the labels scoring it,
      and four rows now show eye labels here below 80 pct agreement (G76 68.6, G85 75.0, G111 48.9,
      G136 66.7).
  (d) CARRY THE G136 CAVEAT into every count you report: its 46.2 pct rests on 66.7 pct agreement,
      so a frame it marks as 4-corner-visible may not be. Say what that does to your denominator.
  (e) DO NOT run a detector, measure recall, or tune anything. This row produces ground truth and
      stops. G119's spec already defines the measurement and can run unchanged against your CSV.
DO NOT change the G136 census, its seed, manifest or labels; do not touch line_calibration.py, any
detector or grouping parameter, any threshold, or the coordinate contract.
ACCEPTANCE RULE:
  metric        = corners with a committed pixel target; and the blind self-agreement displacement
                  (median and p90), reported first
  before        = 0 pixel targets exist; G119 blocked as circular; G121 blocked on untrustworthy
                  labels
  bar           = NO pass bar on the displacement. Success is targets committed for the chosen
                  frames and the self-agreement measured and reported first. A large displacement is
                  a valuable finding -- it would say corners cannot be localised reliably by eye at
                  this resolution, which bounds what any detector could be asked to match and would
                  close the corner route too.
  n             = state the qualifying frame count, the number you labelled, the corner count, and
                  the 15 pct re-label seed
  eye check     = this row IS the eye check, from source-decoded frames. Commit the frames with your
                  targets drawn on them.
  must not move = the G136 census, seed, manifest and labels, the G111 retraction, the G126 audit,
                  every threshold, and the coordinate contract
EVIDENCE: docs/evidence/tracking/g140_corner_targets_on_g136_2026-09-0X.md with the self-agreement
first, the target count, the caveat propagation, the rendered targets, and a NOT VERIFIED list.
Commit the CSV and renders under docs/evidence/tracking/g140_corner_targets/ BEFORE reporting (A7).
CAUTION: another session commits into the main checkout concurrently. Work in your worktree and
commit with explicit pathspecs only.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon is live and seven bridge
lane workers run under scripts/platformkit/bridge_keeper.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
