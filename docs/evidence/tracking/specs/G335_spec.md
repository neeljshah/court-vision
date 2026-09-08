GAP G335 | sport basketball | worktree a22 | log cx_g335_ball_detection_coverage

**MEASUREMENT + PROTOTYPE ROW (src edits authorized by the user 2026-09-08; this row adds a ball
detector arm behind a flag that defaults OFF and measures it label-free).** G29 measured that 165 of 173
pod tracking tables (95.4 pct) contain ZERO rows with `cls == "ball"`; G314/G320 found the inferred-ball
path writing flags without coordinates; G310 found the native-input arm changes ball detections (414 vs
173 per 500 frames). The possession sim and every in-game engine need the ball. This row establishes
where ball coverage is lost (detector recall on the ball class at 640 input vs. writer/route drops) and
prototypes the cheapest coverage gain. NEVER write `data/registry/`, never flip a flag, never claim an
edge, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` or any threshold.

**WHERE THIS ROW RUNS:** pod GPU scratch under `/workspace/wt/a22/` under the 8,192 MiB lease rule (never
touch `track_daemon` or the guards 1039858 / 1519254; never write under `/workspace/nba-ai-system`), or
locally with peak RSS under 1.5 GB (RAM guard at 99 pct). Sections: 6 from different broadcasts (fixed
stride from a sealed offset, >= 60 frames each); never commit video. Print the interpreter version line.

**PREMISE (step 0, BINDING before-condition):** re-census the pod ledger's tracking tables (read-only)
for `cls == "ball"` rows: tables total, tables with 0 ball rows, median ball rows per table with >= 1;
PRINT with n. **If fewer than 60 pct of tables have zero ball rows, the premise is FALSE: STOP, write the
memo, commit, report PREMISE FALSE.**

METHOD:
  1. **WHERE THE BALL IS LOST (trace + measure).** Cite with `file:line` the detector call (classes kept,
     conf, imgsz), the ball filter/tracker (`src/tracking/ball_detect_track.py`), and the writer. On the
     6 sections run the raw detector at the route's settings and count raw `sports ball` detections per
     frame BEFORE any filter, then after each stage (class filter, conf, size gate, tracker acceptance,
     writer). Table per section with n frames: raw / after-class / after-conf / after-size / tracked /
     written. This localises the loss.
  2. **COVERAGE ARMS (label-free).** Same frames, same everything except ONE change per arm: (A) imgsz
     1280 for the ball class only (a second pass on the frame, or tiled 2x2 at 640 -- say which); (B)
     conf for the ball class lowered to the value that maximises the plausibility score below without
     exceeding 2 candidates per frame on median; (C) a dedicated small-object pass on a court-region
     crop (the upper half of the frame where the ball is airborne). Optional (D): TrackNetV3 (MIT; see
     memory `sports_cv_licensed_assets`) if its weights are already present locally or on the pod -- no
     new downloads without saying so; skip otherwise.
  3. **PLAUSIBILITY SCORE (no labels).** Per arm per section: ball rows per frame (n), share of frames
     with exactly one ball candidate, median candidate size in px vs. the expected size from the frame
     height (a basketball is ~9.5 in; at typical broadcast scale 8-25 px), temporal smoothness = share of
     consecutive ball positions moving <= 60 px, and the share of ball positions within 120 px of any
     player box (possession plausibility). A wrong-but-plentiful detector fails smoothness and size.
  4. **RECOMMENDATION + FLAG.** Pick the arm with the best plausibility at <= 1.5x the route's detector
     time; implement it in `scripts/platformkit/tracking/` and, if it beats the route on >= 4 of 6
     sections, add a <= 15-line hook in the ball path behind `BALL_COVERAGE_ARM=off` (default off).
  5. CHANGE NOTHING ELSE; no default moves.

**HONEST LIMITATIONS to state, not discover:** no ball ground truth; plausibility is a proxy; the 640
detector's ball recall is bounded by its training data; six sections are a screening; possession
plausibility penalises fast passes.

ACCEPTANCE RULE:
  metric        = the premise census; the loss-localisation table; the arm x section plausibility table
                  with n; the detector time per arm; the flag + test if added
  before        = 95.4 pct of tables carry no ball row; ball rows per frame at the route's settings
  bar           = the loss stage is named from the counts (not guessed); the recommended arm raises
                  ball rows per frame on >= 4 of 6 sections while keeping one-candidate share >= 0.70,
                  smoothness >= 0.80 and size within 8-25 px median; <= 1.5x detector time
  n             = 6 sections x >= 60 frames; every detection
  eye check     = OPTIONAL: 6 frames with candidates drawn (<= 200 KB each), illustrative only
  must not move = `data/`, `data/registry/`, every flag default, the pod daemon and guards, every
                  committed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED -- BAR MET** / **MEASURED -- BAR NOT MET** (with the failure mode);
                  PARTIAL only if a section or arm could not be scored (say why).
EVIDENCE: `docs/evidence/tracking/g335_ball_detection_coverage_2026-09-08.md` (<= 60 lines; VERDICT line
1; tables; NOT VERIFIED; wall time; SHA-256s) + `.../g335_ball_detection_coverage_2026-09-08/stages.csv`
and `arms.csv` (integer cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g335_ball_detection_coverage.py` (plausibility score on a hand-pinned
synthetic sequence; the stage counter on a construct) plus the existing test file of every touched
module, each alone. **NEVER a full pytest.** Every new file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08

---
**VERSION 2026-09-08b (orchestrator amendment after codex attempt 1 stopped at the premise).** Attempt 1
(a75647f6c, dropped, memo kept in the orchestrator scratchpad) found that the pod's 466 tracking tables
carry NO `cls` column, so `cls == "ball"` is undefined: G29's premise was measured on a different table
shape. The ball lives in the per-clip `data/tracking/<game_id>/ball_tracking.csv` (G314/G320: columns
incl. `detected`, `ball_inferred`, `ball_x2d`, `ball_y2d`). PREMISE REPLACED: census the pod ledger's
clips read-only for `ball_tracking.csv` presence, rows, `detected == 1` rows, and rows with a coordinate;
PRINT with n (clips total / with a ball table / with >= 1 detected row / median detected rows per clip).
**If fewer than 60 pct of clips with a ball table have zero detected-ball rows AND the median detected
share per frame exceeds 0.20, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**
Everything else in the rule above stands (stage counts, three arms, plausibility score, bar, flag
default off). The census is read-only over ssh `cat`/`wc` and needs no pod writes; the sections for the
arms must be pre-staged under `<worktree>/data/footage_corpus/` by the orchestrator (the sandboxed lane
cannot fetch from the pod) -- list the files present and use them.
