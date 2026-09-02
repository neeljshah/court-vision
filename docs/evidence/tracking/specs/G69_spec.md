GAP G69 | sport baseball (contract question, affects all) | worktree a6 | log cx_g69_metric_local_scorability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. This is a CONTRACT and MEASUREMENT row, not a CV row.
THE FINDING THAT CREATED IT: the calibration strategy
(docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md -- READ IT FIRST) establishes that the
baseball centre-field pitch view is **structurally uncalibratable**: the landmarks a homography
needs (rubber, mound, plate, batter's boxes) are NEAR-COLLINEAR along the pitch axis, so the solve
is ill-posed by geometry and no detector improvement fixes it. Baseball's honest ceiling is
METRIC_LOCAL -- the lateral mound-row pixels-per-foot already gate-validated on roughly 22-25 pct
of day pitch-view frames -- and NOT court_feet.
WHY IT MATTERS NOW: G47 measured that 119 of 187 harness reports fail on coordinate_contract and
nothing else, and **baseball is 66 of 93 -- the largest single block of any sport**. Those clips
were never scored for tracking quality at all. If baseball can only ever produce metric_local rows,
then leaving the contract as it is means baseball fails forever, silently, and its "zero pass" is
read as a quality statement when it is not one.
THE QUESTION, and answer it with code and evidence rather than opinion:
  (1) Does the harness, as it stands TODAY, score METRIC_LOCAL rows at all? Trace it: read
      scripts/platformkit/tracking_harness.py and scripts/platformkit/coordinate_provenance.py and
      the rung ladder in the contract. Construct a metric_local row set and RUN the harness on it.
      Report what actually happens -- accepted, rejected, or silently mis-scored. Do not infer this
      from reading; run it and paste the output.
  (2) Which harness metrics are even MEANINGFUL in metric_local? Go metric by metric and say so:
      coverage is a count and should survive; a jump bar in FEET cannot mean the same thing when
      the units are local pixels-per-foot at one image row; oob depends on a court rectangle that
      does not exist. State for each: meaningful as-is, meaningful with a stated unit change, or
      not meaningful.
  (3) What is the SMALLEST contract change that would let a metric_local sport be scored on the
      metrics that ARE meaningful, WITHOUT weakening the rung ladder for sports that can reach
      court_feet? The ladder exists to stop image_px rows being laundered into court_feet claims
      (that is the whole point of it) and nothing you propose may make that laundering possible.
      PROPOSE it; do not implement it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = whether a metric_local row set is scorable today, and which metrics survive
  before        = unknown; baseball simply fails coordinate_contract and nobody has asked why
  bar           = THERE IS NO PASS BAR. Success is a run harness output on constructed
                  metric_local rows, a metric-by-metric meaningfulness table, and one proposed
                  minimal change. "Metric_local is already scorable and baseball is failing for a
                  different reason" would be an excellent outcome -- check that first.
  n             = every harness metric enumerated, none skipped; state the list you found in code
  eye check     = n/a (a contract question). Any behavioural claim needs its run output pasted.
  must not move = EVERYTHING. This row changes NO code, NO threshold, NO contract clause and NO
                  verdict. It produces a proposal for adjudication. Implementing it here would be
                  changing a gate without adjudication, which is the thing the contract forbids.
NON-TAUTOLOGY: do not conclude "metric_local is unscorable" from the fact that baseball reports
fail -- baseball may be failing for an unrelated reason (a missing declaration, a producer bug).
Separate the two by constructing a CLEAN metric_local row set yourself and scoring that.
DO NOT: attempt a baseball court_feet homography from the centre-field view. The strategy already
rules that out as geometrically ill-posed, and re-litigating it is the ruled-out work.
DURABILITY (A7): commit the constructed row sets and the harness output under
docs/evidence/tracking/g69_metric_local/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g69_metric_local_scorability_2026-09-0X.md with the traced answer
to (1) plus pasted run output, the metric-by-metric table for (2), the single proposed minimal
change for (3) with an explicit statement of why it cannot enable coordinate laundering, and a
NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only if at all. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token, but this row does NOT edit it. If you find
yourself editing it, STOP -- you have left the scope of this row.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
