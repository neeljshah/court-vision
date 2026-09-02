GAP G52 | sport tennis | worktree a4 | log cx_g52_tennis_reproducibility
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. This is a QUANTIFY-THEN-BISECT lane. Do NOT fix anything yet.
PREMISE (step 0, reproduce it): re-running the tennis selector over the SAME committed 15
sequential ranges (seed 20260901, 300 decoded frames each, solver / camera lock /
domains/tennis/tracking/court_lines.py all untouched) returned DIFFERENT solver coverage in 7 of
15 ranges: nyYk 0.6100->0.6000, 0.9900->0.9933, 0.9967->1.0000, 0.5600->0.5300; tennis09
1.0000->0.9967; tennis10 0.3967->0.3933. Source: docs/evidence/tracking/
tennis_player_select_limit_2026-09-04.md, against the committed baseline in
docs/evidence/tracking/tennis_sequential_plan_2026-09-01/*.json. If coverage reproduces exactly
this time, STOP and report FALSIFIED -- that is a valid and valuable result.
WHY IT MATTERS: coverage MUST be identical when the solver is untouched. If it drifts on its own
it cannot serve as the control in any before/after test, which is exactly what the G26 acceptance
rule assumed. Every tennis comparison the program has made inherits this.
LIMIT (step 1): THE WORK. Quantify the drift before touching anything. Take ONE range and run it
N >= 5 times completely unchanged, on the pod, and report the coverage spread (min, median, max,
and the exact set of distinct values). Then repeat on a second range from a different match. That
spread is the noise floor of every tennis measurement in this program and it has never been
measured.
CHANGE (step 2): BISECT the source, do not fix it. G22 solved exactly this class of defect for
soccer by pinning JPEG decode, the model path, seeds and single-thread cv2 -- see
scripts/platformkit/detection/deterministic.py and build_soccer_packet_detector. Tennis has never
had that treatment. Candidates to separate, each testable by holding one thing fixed and re-running:
  - detector nondeterminism (YOLO / torch): fix seeds and threads, re-run, see if the spread closes
  - cv2 thread count / OpenCL: cv2.setNumThreads(1), cv2.ocl.setUseOpenCL(False)
  - GPU nondeterminism: run on CPU and compare the spread against the GPU spread
  - frame-decode drift: does the SAME frame index decode to a byte-identical image across runs?
    (This one is decisive and cheap -- test it first, it is the soccer G22 root cause.)
Report which candidate accounts for the drift, with the measurement that shows it.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = solver coverage per range across N identical repeat runs (denominator = 300
                  decoded frames per range)
  before        = a single run per range; the spread has never been measured
  bar           = the report is COMPLETE and attributable: N >= 5 repeats on at least 2 ranges
                  from different matches, the distinct coverage values listed, and either the
                  source named with the measurement that isolates it or an explicit list of what
                  was ruled out and how. No number has to improve.
  n             = >= 5 repeats per range, >= 2 ranges
  eye check     = n/a for a determinism measurement; reproduction = the per-run coverage table
  must not move = every harness threshold, the seed 20260901, the committed range definitions,
                  the court solver, the camera lock, and court_lines.py
NON-TAUTOLOGY: do not average the repeats into one number -- the SPREAD is the result. Report the
distinct values, not a mean.
EVIDENCE: docs/evidence/tracking/g52_tennis_reproducibility_2026-09-0X.md -- the per-run table,
the spread per range, the bisection results, and a NOT VERIFIED list.
TEST: exactly one new per-file test; run only that file. A determinism test that runs the same
input twice and asserts identical output is the right shape.
POD: all repeats run on the pod (cv2 is PINNED to 4.14.0 there -- do not change the pod env); own
nohup setsid nice job, unique /tmp log, never kill anything, no git on the pod, NO scp of any
module until a verifier accepts.
COMMIT: explicit pathspec, in a4, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
