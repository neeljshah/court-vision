GAP G342 | sport basketball | worktree a4 | log cx_g342_court_templates

**COURT TEMPLATE VARIANTS + TEMPLATE SELECTION (label-free, synthetic; codex PREPARES, a finisher
MEASURES).** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/court_templates/`. NEVER write `data/registry/`, never flip a flag, never claim an
edge, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No video, no GPU, no pod.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Synthetic renders
with cv2 only. A missing `data/registry` in the worktree is expected (never write it).

**WHY THIS ROW EXISTS.** G334 fits ONE template (NBA 94 x 50 ft, 16 ft lane, 23 ft 9 in arc) to every
frame, but 4 of the 6 staged sections are FIBA-rule courts (eurocup, euroleague, nbl: 28 x 15 m =
91.86 x 49.21 ft, 4.9 m lane, 6.75 m arc, 6.60 m corners), WNBA uses a 22 ft 1.75 in arc, and NCAA a 12 ft
lane with a 22 ft 1.75 in arc and 21 ft 7.375 in corners. Fitting the wrong rules template yields a
coherent but metrically wrong mapping (astra failure mode C, 2026-09-08). Registration needs versioned
templates in native rule units and a selector that returns UNKNOWN when the evidence cannot separate them,
instead of a confident wrong winner.

**PREMISE (step 0, BINDING before-condition):** grep `scripts/platformkit/`, `src/tracking/`,
`domains/basketball_nba/` for hard-coded court dimensions (`94`, `50`, `16`, `23.75`, `22.15`, `28.0`,
`15.0`, `lane`, `three`, `arc`) in calibration and template code; list `file:line` and the league each
implies. PRINT the table. **If a versioned multi-league template registry with per-league arc, lane and
corner values already exists and is imported by the calibration code, the premise is FALSE: STOP, write
the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **TEMPLATES (`templates/<league>.json` + `templates.py`, <= 200 lines).** NBA, WNBA, FIBA, NCAA
     (current men/women), each in NATIVE rule units with the rule-book source URL and the accessed date in
     the JSON, converted to feet on load: court length/width, centre line, centre circle, lane (both ends,
     inside edges), free-throw circles, three-point arc radius + corner straight distance from the sideline,
     restricted-area arc, hash marks optional. Marking centre-lines derived from the prescribed inside /
     outside edges with the painted thickness recorded (2 in NBA/NCAA, 5 cm FIBA). A `render(template, H,
     size)` that rasterises strokes through a homography into an image (cv2), and `segments(template)` that
     returns the straight strokes and sampled arcs as court-feet polylines with a semantic id
     (SIDELINE, BASELINE, CENTRE, LANE_L, LANE_R, FT_CIRCLE, ARC_3, CORNER_3, RA, CIRCLE) and an orientation
     family (X, Y, ARC).
  2. **SELECTOR (`template_select.py`, <= 200 lines).** Input: observed image-space segments (px polylines
     with orientation family) and a candidate H per template hypothesis (the caller fits H per template with
     an equal search budget; this row supplies the scoring and the rule). Cost per template = median
     symmetric distance (px) between observed segments and the nearest template stroke of a compatible
     family, normalised by the visible supported stroke length, plus a penalty for predicted-visible
     template strokes with no support within 4 px. Decision: winner cost <= 0.8 x runner-up on >= 5 frames
     from >= 2 shots, and >= 2 distinctive feature groups (arc radius, lane width, court length, corner
     straight) each favouring the winner; bootstrap the frames 100 times, same winner >= 90 pct; otherwise
     return UNKNOWN with the plausible set. A quadrilateral alone never identifies a template (assert).
  3. **SYNTHETIC VALIDATION (finisher).** For each template render 200 random camera-like homographies
     (sealed seed; pan/tilt/focal ranges stated), add 1-3 px Gaussian noise to the sampled segments and
     occlude 30 pct of stroke length at random; run the selector with (a) the TRUE H per template hypothesis
     (the template's own H for the true one, the best-of-50 random re-fits for the others -- state the
     re-fit method) and (b) a 2 px corner-jittered H. Report the 4 x 5 confusion matrix (4 true templates x
     4 winners + UNKNOWN) with n for (a) and (b), and the pairwise separation NBA vs WNBA (arc differs by
     1.60 ft), NBA vs FIBA (length differs by 2.14 ft), NBA vs NCAA (lane differs by 4 ft) as the share of
     frames where the true template wins outright.
  4. **INTEGRATION NOTE.** A <= 10-line PROPOSED snippet (under `docs/research/organization-sprint/
     G342_PROPOSED_template_hook.md`, gitignored; carry its sha256 in the memo) showing how G334's
     calibrator would call `template_select` before locking a per-game template. No edit to G334's files.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** synthetic renders are not broadcast frames (no lighting,
logos, wood texture or real occluders); real-frame selection waits for G334's line extractor; era variants
(archival NCAA arcs) are out of scope; the re-fit for non-true hypotheses is a stated approximation.

ACCEPTANCE RULE:
  metric        = premise table; the four templates with cited sources and a render each; the selector; the
                  two confusion matrices with n; the pairwise separations; the PROPOSED hook
  before        = one hard-coded NBA template; no selector; FIBA sections fitted with NBA geometry
  bar           = every template's numbers are asserted by a test against the cited rule values; on
                  arm (a) the true template wins outright on >= 0.95 of frames per template (n = 200 each)
                  and the WRONG-winner share is <= 0.02 per template (ambiguity must land in UNKNOWN);
                  arm (b) is reported, not gated; all tests pass; 0 src edits
  n             = 4 templates x 200 renders x 2 arms; every stroke
  eye check     = OPTIONAL: one rendered image per template (<= 150 KB each)
  must not move = `src/`, `data/`, `data/registry/`, every flag, G334's worktree files, every committed
                  artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the template or arm that failed and why.
EVIDENCE: `docs/evidence/tracking/g342_court_templates_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; SHA-256s) + `.../g342_court_templates_2026-09-08/confusion.csv` and
`separation.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g342_court_templates.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines (the four JSON files are data, exempt).
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the seed, the camera ranges, the
noise and occlusion levels, the decision rule), the templates, the renderer, the selector, the tests and
the memo skeleton, and exits `PREPARED FOR FINISHER` listing the exact commands; it must NOT run the 200
renders per template itself (Q1: measurements follow the sealed commit).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
