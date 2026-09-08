GAP G334 | sport basketball | worktree a6 | log cx_g334_court_line_registration

**REGISTRATION ROW -- NO HUMAN LABELS.** On 2026-09-08 the user ruled out human landmark annotation and
asked for the registration approach to be chosen and built autonomously. G330 measured the current state:
181/199 pod runs registered against the shared fallback panorama, held-out RANSAC inliers of 6/721, 4/394,
7/359 through the route's own matcher, median held-out reprojection ~1000-1218 px, and 1/408, 9/313, 0/149
detected feet landing inside the court polygon. Frame-to-court mapping on broadcast footage is not
happening. This row builds and measures an AUTOMATIC court-line calibration: detect the painted court
lines in a frame, fit the known NBA court template (94 x 50 ft; key, arcs, centre circle, sidelines) by
line correspondences under RANSAC, and produce a per-frame (or per-shot, EMA-smoothed) homography
frame -> court feet. Build in `scripts/platformkit/tracking/` (harness) with a thin, additive `src/`
hook ONLY after the measurement holds (src edits are authorized by the user for this program; keep the
route's default behaviour selectable and default OFF until this row's bar is met -- a flag flip is a
separate orchestrator decision).

**WHERE THIS ROW RUNS:** the pod as CPU scratch under `/workspace/wt/a6/` (nice -n 19, OMP_NUM_THREADS=2;
never touch `track_daemon` pid 1168432 or its replacement, or the guards 1039858 / 1519254; no GPU unless
a pretrained line/keypoint model is used, then the 8,192 MiB lease rule of G310 applies) OR locally with
peak RSS under 1.5 GB. Sections: the three G330 attempt-2 sealed sections (local copies' sha256s are in
`g330_prereg_attempt2_2026-09-08.md`; re-fetch by name from the pod corpus or bridge if they rotated out;
if absent, apply G330's salted-selection rule and seal new ones) plus at least 3 more from different
broadcasts (say which). Never commit video.

**PREMISE (step 0, BINDING before-condition):** on the sealed sections, reproduce G330's held-out
numbers through the route's `_get_homography` (n per frame) and PRINT them; that is the BEFORE. **If the
route already yields held-out inlier ratios above 0.30 on 2 of 3 sections, the premise is FALSE: STOP,
write the memo, commit, report PREMISE FALSE.**

METHOD (state the design in the prereg, then execute; pick the simplest thing that can work first):
  1. **LINE EXTRACTION.** Court-line pixels by colour/brightness contrast against the floor (white/painted
     lines on wood), morphological cleanup, then line segments via LSD or probabilistic Hough (cv2 only;
     no new dependency unless already installed -- say what is importable on the pod and locally). Record
     segments per frame with length, angle, endpoints.
  2. **TEMPLATE FIT.** The NBA court template in feet (sidelines, baselines, free-throw lanes, free-throw
     lines, three-point arcs, centre circle, half-court line). Hypothesise line correspondences (long
     near-horizontal segments = sidelines/baselines; the lane rectangle; the half-court line), sample
     4-line/4-point correspondences under RANSAC, fit H, score by the reprojection of ALL template lines
     onto the frame (distance of detected line pixels to the projected template lines; symmetric where
     visible). Keep the best H per frame; reject frames with too few segments (report the count).
  3. **TEMPORAL.** EMA/median over a shot (reuse the route's cut detection if callable read-only; else a
     simple histogram-diff cut) so a single bad frame does not flip the mapping; report per-shot validity.
  4. **MEASUREMENT (the bar, no ground truth needed).** Per section: (a) held-out line-pixel reprojection
     error (fit on a random half of the segments, score on the other half; median px, n); (b) share of
     frames with a valid H; (c) share of detected feet (route boxes) whose court coordinate falls inside
     the court polygon (the G03/G330 quantity) with the denominator; (d) plausibility: median inter-player
     nearest-neighbour distance in feet (should be 3-15 ft, not 0.1 or 200) and the fraction of players
     inside the 94 x 50 rectangle. Compare BEFORE (route) vs AFTER (this row) on the same frames.
  5. **BASELINE ARM.** Also score the route's fallback-panorama homography with the SAME metrics (a)-(d),
     so the comparison is like for like.
  6. **INTEGRATION (only if the bar holds).** A new module `src/tracking/court_line_calibration.py`
     (<= 300 lines) plus a <= 10-line additive hook in `unified_pipeline.py` behind a flag that defaults
     OFF (`COURT_LINE_CALIBRATION=0`), a `court_calibration.json` sidecar (H, per-shot validity, metrics)
     written next to the route output so the coordinate contract can find "a court calibration sidecar",
     and one per-file test on a synthetic court image. If the bar does not hold, no src edit: memo + harness
     + measurements only, with the failure mode named.

**HONEST LIMITATIONS to state, not discover:** no ground-truth court coordinates exist; the metrics are
self-consistency and plausibility, not accuracy; broadcast zoom-ins and replays will fail line extraction
(count them); arcs are approximated by chords unless fitted explicitly; six sections are a screening.

ACCEPTANCE RULE:
  metric        = per section x arm: held-out line reprojection median px (n segments), valid-H share
                  (n frames), feet-inside-court share (n feet), NN-distance median ft (n pairs), share of
                  players inside the rectangle; the BEFORE table reproduced; the design in the prereg
  before        = route held-out inliers ~1 pct; feet inside court 1/408, 9/313, 0/149
  bar           = on at least 4 of 6 sections: feet-inside-court share >= 0.60 with n >= 100 feet, valid-H
                  share >= 0.50, and held-out line reprojection median <= 8 px at 1280x720 (scale by
                  height for 1080p); the baseline arm scored on the same frames; every cell with n
  n             = 6 sections x 40 frames minimum (stride fixed in the prereg); all segments and feet
  eye check     = OPTIONAL: render 6 frames (one per section) with the projected template overlaid to
                  `docs/evidence/tracking/g334_court_line_registration_2026-09-08/renders/` (<= 200 KB
                  each, jpg) -- renders illustrate, they do not decide
  must not move = `data/`, `data/registry/`, every feature flag default (the new flag defaults OFF),
                  the pod daemon and guards, every committed artifact,
                  `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **MEASURED -- BAR MET** or **MEASURED -- BAR NOT MET** (with the failure mode); PARTIAL
                  only if a section could not be scored (say why).
EVIDENCE: `docs/evidence/tracking/g334_court_line_registration_2026-09-08.md` (<= 60 lines) with VERDICT
on line 1, the before/after table, the design summary, a **NOT VERIFIED** list, wall time and the
SHA-256s; plus `docs/evidence/tracking/g334_court_line_registration_2026-09-08/metrics.csv` (integer cells
zero-padded to 6 digits) and the per-frame CSV (<= 5 MB). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME
COMMIT** (one `>>` append, LF). **Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g334_court_line_registration.py` -- template fit on a synthetic rendered
court (known H recovered within 1 px), the held-out scorer, the inside-court test; plus the src hook test
if integrated. Run each alone. **NEVER a full pytest.** Every new file <= 300 lines.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
