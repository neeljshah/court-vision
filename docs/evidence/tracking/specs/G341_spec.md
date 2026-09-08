GAP G341 | sport basketball | worktree a14 | log cx_g341_shot_router

**SHOT ROUTER + FLOOR-MOTION PROPAGATION (label-free; codex PREPARES, a finisher MEASURES).** `src/`,
`kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/tracking/`. NEVER
write `data/registry/`, never flip a flag, never claim an edge, never touch
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`. No src hook in this row (G334 owns registration).

**WHERE THIS ROW RUNS:** the codex lane prepares LOCALLY on synthetic constructs only (no video needed).
The finisher runs the six staged sections (`data/footage_corpus/` in worktree a20 or a6: the 2 `nba__*`
and 4 `basketball__eurocup|euroleague|nbl*` 130 s cuts; copy, never move) LOCALLY on CPU at 320x180 /
5 fps if >= 1.5 GB RAM is free, else on the pod under `/workspace/wt/a14/` (CPU only, nice -n 19, never
touch the daemon pid 1596016 or the guards; nohup detached; short polls). Never commit video.

**WHY THIS ROW EXISTS.** G330 measured that the route registers 181/199 clips against one shared fallback
panorama and holds ONE mapping per clip; broadcast footage is a sequence of SHOTS (wide, close-up, crowd,
replay) separated by cuts, and a mapping estimated on one shot is meaningless on the next. G336 found the
route emits zero rows on some 60-frame windows. Any registration G334 produces is per-shot at best, so the
program needs (a) a cut detector with hysteresis that assigns `shot_id`, (b) a view class per frame
(WIDE / CLOSEUP / CROWD / UNKNOWN) so calibration is only attempted where court lines can exist, (c) a
replay flag (LIVE / REPLAY / UNKNOWN) so replays never enter live trajectories, and (d) floor-motion
propagation inside a shot (A_t<-a from floor-only feature matches; G_t = A G_a) with an explicit state
{DIRECT, PROPAGATED, UNOBSERVABLE} and a hard stop instead of holding a stale mapping through a zoom.
This is astra's section 2 of the 2026-09-08 self-training plan, built as its own measurable row.

**PREMISE (step 0, BINDING before-condition):** grep `src/pipeline/unified_pipeline.py` and
`src/tracking/` for every cut / scene / replay / shot handler (`file:line`, what it does, whether it
resets the homography). PRINT the table. **If the route already resets registration at detected cuts
AND flags replays, the premise is FALSE: STOP, write the memo, commit, report PREMISE FALSE.** (G330's
per-clip fallback says it does not; measure, do not assume.)

METHOD:
  1. **ROUTER (`scripts/platformkit/tracking/shot_router.py`, <= 250 lines).** Per frame at 5-10 fps on a
     320x180 downscale: cut = HSV-histogram Bhattacharyya distance to the previous kept frame > 0.5 AND
     static-feature inlier fraction (ORB + RANSAC homography, 500 features) < 0.2; 0.3 s hysteresis (a new
     shot needs 3 supported samples); `shot_id` increments per cut. View class from cues stated as
     PROPOSAL cues, not classifiers: unoccluded straight segments > 40 px (at 720p scale) in >= 2
     orientation families -> line support count; floor-texture share (low-saturation, mid-value pixels
     below the horizon band); median person-box height / image height from the committed tracking table
     when one exists for the section, else `null`. CLOSEUP when supports < 4 AND median box height > 0.35;
     CROWD when floor share < 0.15 AND supports < 2; WIDE when supports >= 4; else UNKNOWN. Replay flag:
     64-bit dHash per kept frame; a run of >= 8 kept frames whose hashes match (Hamming <= 6) an EARLIER run
     in the same clip -> REPLAY; a frozen scorebug band (bottom 12 pct row variance < 1 percent of the
     frame's) is reported as a cue only; else LIVE is NOT claimed: emit UNKNOWN unless no cue fires.
  2. **PROPAGATION (`scripts/platformkit/tracking/floor_motion.py`, <= 200 lines).** Inside a shot, between
     consecutive kept frames: mask out dilated person boxes (from the tracking table when present), the top
     15 pct band and the bottom 12 pct band; ORB/LK matches + RANSAC homography A; ACCEPT when inliers >= 30,
     inlier share >= 0.6, inlier hull >= 10 pct of the image and p90 residual <= 3 px; chain A across
     accepted steps; state DIRECT only when an anchor mapping exists for the frame (G334's per-shot H if
     landed on master, else the anchor set is EMPTY and every state is PROPAGATED-from-identity or
     UNOBSERVABLE: say so in the memo); stop the chain at a cut, at a rejected step, or when the chained
     hull leaves the image. Never carry a mapping across a cut.
  3. **REPORT (`--report`).** Per section: n frames sampled, n shots, cut frame indices, view-class share,
     REPLAY / UNKNOWN share, propagation acceptance share, longest accepted chain (frames and seconds), p90
     residual over accepted steps, n rejected steps by reason. CSVs: `shots.csv` (one row per shot) and
     `propagation.csv` (one row per step). Compare the router's cut count to the route's own handler count
     from the premise table (both with n).
  4. **TESTS.** Synthetic constructs only: a frame sequence of two distinct textures switched at a known
     index (the cut fires there and nowhere else; hysteresis holds under one flashed frame); a planar
     texture warped by a known A (recovered A within 0.5 px on 9 grid points; a chain of 5 steps composes to
     the known product); a replayed segment detected by dHash; the state machine never emits DIRECT with an
     empty anchor set.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** thresholds are proposed starting values, not tuned; the
view-class cues are proposals (a zoom can remain calibratable; an empty court can be); cheap cues cannot
prove LIVE; with no landed anchor, propagation is measured as geometric consistency only, not registration;
six sections are a screening.

ACCEPTANCE RULE:
  metric        = premise table; per-section router table and propagation table with n; the two CSVs; tests
  before        = the route holds one mapping per clip across cuts; no shot_id, view class or replay flag
  bar           = every synthetic test passes; every section row carries n; no DIRECT state without an
                  anchor; no mapping carried across a cut (assert in the report: 0 cross-cut chains)
  n             = 6 sections x >= 600 sampled frames; every step; every cut
  eye check     = OPTIONAL: one contact sheet per section of the first frame of each shot (<= 200 KB each)
  must not move = `src/`, `data/`, `data/registry/`, every flag, the pod daemon and guards, every committed
                  artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** if the bar holds; **PARTIAL** with the section or test that failed and why.
EVIDENCE: `docs/evidence/tracking/g341_shot_router_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables; NOT
VERIFIED; wall time; SHA-256s) + `.../g341_shot_router_2026-09-08/shots.csv` and `propagation.csv` (integer
cells zero-padded to 6 digits). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (one `>>` append, LF).
**Do NOT edit `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g341_shot_router.py`, alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone, with the thresholds above and the six
section names), both modules, the tests and the memo skeleton, and exits `PREPARED FOR FINISHER` listing the
exact commands; it must NOT run the sections itself (Q1). A missing `data/registry` or an absent section in
the worktree is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
