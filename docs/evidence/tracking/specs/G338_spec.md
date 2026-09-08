GAP G338 | sport basketball | worktree a20 | log cx_g338_detector_input_decision

**DECISION ROW (label-free; src edits authorized by the user 2026-09-08 but this row changes production
only through a flag that defaults to the current value).** G310 measured, on the same frames, that the
detector at native 1920 input emits about 2x the person rows of the production 640 input, longer
slot-keyed tracks but fewer ball detections (173 vs 414 per 500 frames) and a 2.7x higher p95 footpoint
step; the memo called it MIXED and could not say whether the extra rows are players or false boxes,
because no ground truth exists. This row decides the input size by PLAUSIBILITY, not by row counts:
players per frame during play (8-13 with the non-player gate of G337 applied), box height in feet at
the box position (from the fallback homography, labelled as such; a player is 5.5-7.5 ft), the share of
boxes wholly inside the court polygon, and detector time per frame. NEVER write `data/registry/`, never
flip a flag, never claim an edge, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** the pod as GPU scratch under `/workspace/wt/a20/` under the 8,192 MiB lease rule
(daemon pid 1596016 owns the card -- never touch it or the guards 1039858 / 1519254; never write under
`/workspace/nba-ai-system`; nohup detached; short polls) -- a sandboxed codex lane prepares the harness,
prereg and tests; an orchestrator FINISHER runs the pod arms if the lane cannot. Sections: 6 across
broadcasts and resolutions (>= 2 native 1080p, >= 2 720p; fixed stride from a sealed offset, >= 60
frames each); never commit video. Print the interpreter/environment line.

**PREMISE (step 0, BINDING before-condition):** reproduce G310's row-count ratio on one section: the
1920 arm emits >= 1.5x the person rows of the 640 arm on the same frames (n frames). **If the ratio is
below 1.2 on two sections, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **ARMS (one difference each, same frames, same weights, same conf, same classes):** imgsz 640
     (production), 960, 1280, 1920; plus 640 with 2x2 tiling if cheap. Record detector ms/frame and GPU
     memory per arm.
  2. **PLAUSIBILITY per arm per section (n frames, n boxes):** (a) players per frame after the G337
     non-player gate (median, p10, p90; target band 8-13 during play -- report the share of frames in
     band); (b) box-height plausibility: project the box bottom-centre with the route's current
     homography (state it is the fallback), estimate height in feet from box pixel height and local
     scale, report the share of boxes in 5.5-7.5 ft (label the homography caveat); (c) share of boxes
     wholly inside the frame (G325 rule) and inside the court polygon; (d) temporal stability: share of
     boxes that persist >= 3 consecutive frames (IoU >= 0.5), a false-box proxy; (e) ball detections per
     frame (from G335's stage counts if landed, else the raw ball-class count).
  3. **DECISION RULE (prereg it):** the recommended input size is the smallest imgsz whose plausibility
     (a)-(d) is within 5 pct of the best arm on >= 4 of 6 sections and whose ms/frame keeps the daemon's
     8-worker throughput (>= 0.8x of the 640 arm's clips/hour estimate per G328's formula). Ball count
     (e) is reported, not decided (G335 owns it).
  4. **FLAG.** Implement in `scripts/platformkit/tracking/` the arm runner and, if the decision differs
     from 640, a <= 10-line hook so `DETECTOR_IMGSZ` (env/flag, default 640 = current) selects the size
     in the route, with a test that the default path is byte-identical. No default change in this row.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** plausibility is not accuracy; the height check inherits
the fallback homography's error (G330); six sections are a screening; throughput is an estimate.

ACCEPTANCE RULE:
  metric        = premise ratio; the arm x section plausibility table (a)-(e) with n; ms/frame and GPU
                  MB per arm; the decision with its rule applied; the flag + test if added
  before        = production at 640; G310's MIXED result with no plausibility judgement
  bar           = every cell carries n; the decision rule is applied as preregistered (met or not); the
                  default path stays byte-identical (test); 0 register edits
  n             = 6 sections x >= 60 frames x 4-5 arms; every box
  eye check     = OPTIONAL: one frame per section at 640 vs the recommended size (<= 200 KB each)
  must not move = `data/`, `data/registry/`, every flag default, the pod daemon and guards, every
                  committed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DECIDED: <imgsz>** with the rule's numbers, or **UNDECIDED** with the failure mode;
                  PARTIAL only if arms could not run (say why).
EVIDENCE: `docs/evidence/tracking/g338_detector_input_decision_2026-09-08.md` (<= 60 lines; VERDICT line
1; tables; NOT VERIFIED; wall time; SHA-256s) + `.../g338_detector_input_decision_2026-09-08/arms.csv`
(integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>`
append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g338_detector_input_decision.py` (the plausibility scorer and the decision
rule on a hand-pinned construct; the default-path byte-identity if a hook is added) plus the existing
test file of every touched module, each alone. **NEVER a full pytest.** Every new file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08

---
**VERSION 2026-09-08b (orchestrator amendment after codex attempt 1 stopped on the G337 dependency).**
G337 is SUPERSEDED (its court-polygon gate needs G334's validated calibration). Replace every reference to
"the G337 non-player gate" with the G325 FRAME-CONTAINMENT rule only: a box counts if its unpadded
rectangle intersects the decoded frame (no colour, size or polygon gate). The players-per-frame band
(a) is therefore computed on in-frame person boxes and will include referees/bench; state that and
report the band share as a screening number. The court-polygon share (c) stays labelled as inherited
from the fallback homography. Division of labour: the codex lane prepares the arm runner, the
plausibility scorer, the prereg (sealed alone) and the tests on a synthetic construct; an orchestrator
FINISHER runs the arms on the pod and writes the measured memo. The lane must NOT stop on missing
sections or missing pod access: it reports `PREPARED FOR FINISHER` with the exact commands the finisher
runs. A missing `data/registry` in the worktree is expected (local-only; never write it).
