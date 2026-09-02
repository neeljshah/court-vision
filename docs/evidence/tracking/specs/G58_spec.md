GAP G58 | sport tennis | worktree a5 | log cx_g58_court_length_residual
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. DIAGNOSE the cause. Do not apply a correction factor.
PREMISE (step 0, reproduce it): the tennis solver reads the court about **1.2 pct SHORT every
time**. The solved length ratio is **0.9878 median, sd 0.0058**, and the SIGN IS CONSISTENT across
all four clips, three cameras and two surfaces measured in G46. Reproduce that median and spread
from g46_court_scale_premise_2026-09-02.md before proceeding.
WHY A CONSISTENT SIGN MATTERS: random error has no preferred direction. A bias that is negative on
every clip, every camera and every surface is a systematic calibration offset, and it propagates
into every court_feet quantity -- including the 5.28 ft anchor and therefore every distance, speed
and jump number the harness computes. It is small, but it is the kind of small that never averages
out.
IMPORTANT CONTEXT you must respect: G46 already FALSIFIED the obvious explanation (the solver was
suspected of mislabelling the far baseline; it does not -- it labels it correctly). So do not
re-run that hypothesis. And note G52, resolved today: results differ between local cv2 4.11.0 and
pod cv2 4.14.0, so state where you compute every number and attach the environment stamp
(scripts/platformkit/tracking/run_environment.py). Both arms of any comparison run in ONE
environment.
HYPOTHESES TO SEPARATE (step 1), and you must state which you tested:
  (a) LINE CENTRE VERSUS LINE EDGE. A painted court line has real width -- a tennis baseline is
      about 2 inches, and sidelines likewise. If the detector fits the INNER edge of the near line
      and the INNER edge of the far line, the measured length is short by roughly one line width at
      each end. Work out what fractional shortening that predicts for a 78 ft court and compare it
      against 1.2 pct. This is the leading candidate precisely because it predicts a CONSISTENT
      SIGN, and a hypothesis that predicts the sign is worth more than one that only fits the size.
  (b) LENS DISTORTION not modelled by a pure homography, which would bias the extremes of the frame.
      This predicts a dependence on where the court sits in the image; test that.
  (c) The court dimension CONSTANT the solver targets being wrong for some venue (for example a
      different singles/doubles assumption).
  Rank them by what the evidence supports, and say what would distinguish the survivors.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the solved-length ratio distribution, and each hypothesis's PREDICTED ratio
  before        = 0.9878 median, sd 0.0058, consistent sign across 4 clips / 3 cameras / 2 surfaces
  bar           = THERE IS NO PASS BAR and you must NOT apply a correction. This row succeeds by
                  naming which hypothesis the evidence supports, with a quantitative prediction
                  compared against the measurement. "None of the three explains it" is a legitimate
                  and useful answer.
  n             = all clips available with a solved court; state the count and per-clip ratios
  eye check     = MANDATORY. Render >= 6 frames with the solver's fitted lines drawn ON the painted
                  lines, zoomed enough to see which side of the paint the fit sits on. That single
                  picture is what distinguishes hypothesis (a) from the rest, and no amount of
                  arithmetic substitutes for looking.
  must not move = every harness threshold, the solver, the camera lock, the 5.28 ft anchor, and the
                  coordinate contract. Absolutely no scale correction factor is to be applied in
                  this row -- a correction applied before the cause is named is exactly how a bias
                  becomes permanent and invisible.
NON-TAUTOLOGY: do not fit a correction factor to these clips and then report the residual as small
on the same clips (B8). Any correction, if one is later warranted, is a separate row with a
held-out set.
DURABILITY (A7): commit the per-clip ratios, the zoomed renders and the environment stamp under
docs/evidence/tracking/g58_renders/ BEFORE reporting.
FOOTAGE: local worktree links data/footage_corpus; the full corpus is on the pod and listed in
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Read-only frame work on the pod is fine.
EVIDENCE: docs/evidence/tracking/g58_court_length_residual_2026-09-0X.md with the reproduced
premise, each hypothesis's quantitative prediction against the 1.2 pct, the zoomed renders and what
you saw in them, the ranking, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a5,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
