GAP G250 | sport basketball (amateur) | worktree a6 | log g250_amateur_feature_inventory
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO existing label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G248 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND** -- a G243c dispatch refused on a self-match. The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**READ THE LANDED G243b, G246, G243c AND G249 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G249 CONFIRMED THE HYPOTHESIS AND CHANGED THE PROBLEM.**
G249 surveyed 61 whole-clip frames plus 4 probe sections and produced this:

| corner | in frame | unoccluded | out of frame | in frame but occluded |
|---|---:|---:|---:|---:|
| far-left | 19/61 | 19/61 | 42/61 | **0/61** |
| far-right | 31/61 | 31/61 | 30/61 | **0/61** |
| near-left | 0/61 | 0/61 | 61/61 | **0/61** |
| near-right | 0/61 | 0/61 | 61/61 | **0/61** |

**Two things follow, and both matter.** First, **the court-corner hypothesis was RIGHT: a court corner is
NEVER occluded when it is in frame -- 0/61 across all four.** Players genuinely do not stand there, unlike
the lane and free-throw intersections that blocked every G243c candidate. Second, **both NEAR corners are
outside the image in every single frame.** That is the camera's framing, not the players, and no amount of
waiting or extra footage from this camera can fix it.

**SO TWO USABLE CORNERS EXIST AND TWO NEVER WILL -- AND THE TWO THAT EXIST ARE BOTH ON THE FAR SIDELINE,
so they are COLLINEAR and cannot determine a homography by themselves.** A homography needs four coplanar
points in a **non-degenerate** configuration; it does not need them to be corners.

THE QUESTION: **which court features in this footage are simultaneously in frame and unoccluded, and do
any four of them form a NON-DEGENERATE configuration?**

**THE DEGENERACY TRAP, WHICH THIS ROW MUST NOT FALL INTO.** Four points exactly determine a homography, so
**the self-fit residual is 0.000000000 px even for a near-collinear, badly conditioned set** -- G243b
reported exactly that and G246 confirmed no fitted number can detect it. **Four points strung along the
far sideline would produce a confident, precise, completely wrong court.** Conditioning must therefore be
measured explicitly, not assumed.

**THE SOURCE** (verify it yourself):
`/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4`, 24,523,745 bytes,
SHA-256 `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`, 1280x720, 3,601 frames, 30 fps,
120.1 s.

METHOD:
  1. **REUSE G249's committed survey and harness.** Do not re-acquire footage and do not re-run work that
     is already landed.
  2. **INVENTORY EVERY CANDIDATE COURT FEATURE, not just corners**, reporting in-frame and unoccluded
     counts per feature in exactly G249's table format, with **out-of-frame distinguished from
     in-frame-but-occluded**. Cover at least: the four court corners; the centre-line intersections with
     each sideline; the centre-circle extrema; the lane/baseline intersections at each end; the
     free-throw-line intersections with the lane at each end; and the three-point arc apex at each end.
     **State for each whether it is a point a human can identify unambiguously**, because an arbitrary
     spot on a curve is not a nameable world coordinate -- that is the error G246 caught.
  3. **FIND THE FRAMES WHERE THE MOST FEATURES ARE SIMULTANEOUSLY AVAILABLE**, and report the best few
     with their feature sets.
  4. **FOR EVERY CANDIDATE FOUR-POINT SET, MEASURE ITS CONDITIONING BEFORE FITTING ANYTHING.** Report the
     area of the quadrilateral they form as a fraction of the image, and **the minimum perpendicular
     distance of any point from the line through the other three** -- a near-zero value means degenerate.
     **Report conditioning for every candidate set, and say plainly which sets are degenerate.**
  5. **IF A NON-DEGENERATE SET EXISTS, run G243c's protocol on it, unchanged:** frame-exact
     `select=eq(n,N)` decode; **committed zoomed identity crop for every point with a written statement of
     what is at that pixel, BEFORE any fit**; three independent labellings with the spread reported and
     the explicit statement that **repeatability is not correctness**; then the HARD GATE under both court
     models -- the row-local high-school 84x50 ft / 12-ft lane and the existing `ncaa_basketball` key
     94x50 ft / 12-ft lane -- **PASS or FAIL in ONE LINE EACH, before anything else.** **Do NOT add a
     `court_points_for_sport` key. Judge on INDEPENDENT geometry. IGNORE RMS -- it is identically zero.**
     Adjusting a label after seeing a gate is FORBIDDEN and voids the row.
  6. **IF NO NON-DEGENERATE SET EXISTS, say so plainly and quantify it** -- which features are available,
     why every four-subset is degenerate, and therefore **what a camera would have to show for this
     footage class to be calibratable at all.** That statement is the most useful thing this row can
     produce if the answer is negative, because it becomes the acceptance criterion for acquiring any
     future amateur source.
  7. **Do NOT acquire footage, do NOT substitute professional footage, do NOT relabel after a gate, and do
     NOT propose a production change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,070 MB of 50,000), STOP and report if it fails.**
**Do NOT delete any corpus source or the two abandoned partials in `footage_bridge`.** Keep crops and
renders small, delete every temporary artifact and report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one camera, one labeller, 120.1 seconds, and a
61-frame survey at stride 60 -- **a feature could be available in an unsurveyed frame.** This CONSUMES A
HAND LABEL if it reaches a fit and is **not automatic calibration**, which remains 0/17. Eye-label
reliability in this programme has never cleared 80 pct blind agreement on any of four measured criteria,
and **G246 showed repeatable labels can be uniformly wrong.** The court model is assumed, not measured.
**G242, G244 and G247 together mean match counts, inliers, ratio, RMS and quad shape do NOT establish that
a court is correct: ONLY THE RENDERS DO.**

ACCEPTANCE RULE:
  metric        = the per-feature in-frame and unoccluded inventory with out-of-frame separated from
                  occluded; the best simultaneous-feature frames; the conditioning of every candidate
                  four-point set; then either both gate verdicts stated FIRST, or a quantified statement
                  of why no non-degenerate set exists and what a camera would need to show
  before       = G249 proved court corners are never occluded when in frame (0/61) but both near corners
                 are out of frame in all 61 frames, leaving only two collinear far corners
  bar          = NO pass bar. **A PASS would be the first calibration of non-broadcast footage this
                 programme has produced.** **"No non-degenerate four-point set exists in this footage" is
                 an equally full success** and would give us a concrete acquisition criterion for every
                 future amateur source. Do not fit a degenerate set to reach a verdict, and do not relabel.
  n            = 1 clip, 61 surveyed frames, the feature list you inventory, and any candidate sets --
                 state every denominator in the verdict line
  eye check    = the feature inventory and any identity crops ARE the measurement
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract, the
                  harness, G222's matcher settings, existing label files, the corpus, `src/` and
                  `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g250_amateur_feature_inventory_2026-09-04.md with the source check, the
full per-feature inventory, the best simultaneous-feature frames, the conditioning of every candidate set,
any identity crops and gate verdicts, the acquisition criterion if the answer is negative, every
disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT
AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
