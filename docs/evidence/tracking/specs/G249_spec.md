GAP G249 | sport basketball (amateur) | worktree a6 | log g249_amateur_court_corner_seed
**MEASUREMENT ONLY, with a CONDITIONAL acquisition step.** Change NO production code. `src/` and
`domains/` are READ and IMPORT only. **Change NO existing label file and NO threshold.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G248 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began. EXCLUDE
YOUR OWN PROCESS AND YOUR OWN CHECKER COMMAND** -- a G243c dispatch refused on a self-match and had to be
re-issued. The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor.

**READ THE LANDED G243b, G246, G245 AND G243c MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G243c MAY HAVE BEEN LOOKING AT THE WRONG FEATURES.**
G243c surveyed the whole amateur clip (contact sheet at stride 60, 61 frames covering all 3,601) and
correctly reported **NO ELIGIBLE SEED FRAME**. But look at what blocked every candidate, in its own words:
frame 660 -- *"player bodies stand on the remaining lane/free-throw intersections"*; frame 840 -- *"the
painted lane intersections needed to complement it are player-occluded"*; frames 3300 and 3525 -- *"players
occupy the line intersections"*, *"the same free-throw formation still obscures the usable key
intersections."*

**Every blocker is the SAME feature class: the lane and free-throw intersections, which is exactly where
basketball players stand.** G243b and G243c both sought paint corners and centre-circle extrema.

**THE FOUR COURT CORNERS -- the baseline-sideline intersections -- are the one set of court features that
players almost never occupy**, because they are out of play, and this footage is a wide coaches-camera
view that G245 verified shows painted baseline and sidelines with three-point arcs at BOTH ends. **Nothing
has checked whether they are visible and unoccluded.** If they are, an eligible frame may already exist in
the clip we have, and no new footage is needed.

THE QUESTION: **does the existing amateur clip contain a frame with four identifiable, unoccluded COURT
CORNERS -- and if not, can a section that does be acquired?**

**THE SOURCE** (verify it yourself): `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4`,
24,523,745 bytes, SHA-256 `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`, 1280x720,
3,601 frames, 30 fps, 120.1 s.

METHOD -- THE ORDER IS BINDING:
  1. **RE-SURVEY THE EXISTING CLIP FOR COURT-CORNER VISIBILITY FIRST. Do not acquire anything yet.** Reuse
     G243c's committed whole-clip contact sheet if it serves, or rebuild one. **For each of the four
     court corners, report in how many surveyed frames it is (i) within the camera's field of view at all
     and (ii) unoccluded.** **A corner that is simply outside the frame is a different and more permanent
     limitation than one a player is standing on -- distinguish them explicitly**, because the first
     cannot be fixed by waiting for a clear moment and the second can.
  2. **If a frame has four identifiable unoccluded court corners, run G243c's protocol on it, unchanged:**
     frame-exact decode with `select=eq(n,N)`; **committed zoomed identity crop for every point with a
     written statement of what is at that pixel, BEFORE any fit**; three independent labellings with the
     spread reported and the explicit statement that **repeatability is not correctness**; then the HARD
     GATE under both court models -- the row-local high-school 84x50 ft / 12-ft lane and the existing
     `ncaa_basketball` key 94x50 ft / 12-ft lane -- **PASS or FAIL in ONE LINE EACH, before anything
     else.** **Do NOT add a `court_points_for_sport` key.** **Judge on INDEPENDENT geometry: the arc, the
     lane, the centre circle. IGNORE RMS -- with four points it is identically zero.** Adjusting a label
     after seeing a gate is FORBIDDEN and voids the row.
  3. **ONLY IF the existing clip has no eligible frame, acquire additional short probe sections of the
     SAME source** using the proven explicit-HLS recipe (a rung like `-f "232+233"` with
     `--download-sections`; three prior acquisition failures were all selector problems -- **if a rung
     stalls, change the rung, do not wait it out**). **Target moments when the court is likely clear:
     the pre-tip opening, timeouts, and quarter breaks. Probe SEVERAL short sections rather than one long
     one.** For each probe, build a contact sheet and check court-corner eligibility **before** deciding
     whether to keep it.
  4. **KEEP ONLY A SECTION THAT CONTAINS A PROVEN ELIGIBLE FRAME**, and prove it with the contact sheet
     plus the identity crops. **Landing footage without an eligible frame would repeat G245's limitation
     rather than fix it.** Use the existing `<sport>__<name>.mp4` convention, report full identity (path,
     bytes, SHA-256, resolution, frames, fps, duration, source URL, exact command), and **end with an
     `ls -la` of the corpus directory showing the file**.
  5. **If neither the existing clip nor the probes yield an eligible frame, say so plainly and stop.**
     That is a complete result and a real, quantified limitation of this footage: **state which corners
     were out of frame versus occluded, with counts**, because that tells us whether the problem is the
     camera's framing or the players.
  6. **Do NOT substitute professional footage. Do NOT relabel after a gate. Do NOT propose a production
     change.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,059 MB of 50,000), STOP and report if it fails.**
Roughly 17 GB is free; **short probe sections are a few tens of MB each, so prefer several short probes
over one long download.** **Do NOT delete the existing amateur clip, any corpus source, or the two
abandoned partials in `footage_bridge`** (2,490,710,544 and 4,999,500,276 bytes). **NEVER commit a video
-- `data/` is gitignored and must stay untracked.** Delete every temporary artifact and report bytes
freed.

**HONEST LIMITATIONS to state, not discover:** one source, one camera, one labeller. **This CONSUMES A
HAND LABEL and is not automatic calibration**, which remains 0/17. Eye-label reliability in this programme
has never cleared 80 pct blind agreement on any of four measured criteria, and **G246 showed repeatable
labels can be uniformly wrong**. The court model is assumed, not measured -- **an uncalibrated oblique view
cannot establish 84 versus 94 ft.** **G242, G244 and G247 together mean match counts, inliers, ratio, RMS
and quad shape do NOT establish that a court is correct: ONLY THE RENDERS DO**, so never report a hold
from acceptance.

ACCEPTANCE RULE:
  metric        = per-corner visibility and occlusion counts over the surveyed frames, with out-of-frame
                  distinguished from occluded; then either the identity crops plus both gate verdicts
                  stated FIRST, or the acquisition record with its eligibility proof, or a plain statement
                  that no eligible frame exists anywhere tried
  before       = G243c found no eligible seed frame, but every blocker it named was a lane or free-throw
                 intersection -- the feature class players stand on; court corners were never checked
  bar          = NO pass bar. **A PASS would be the first calibration of non-broadcast footage this
                 programme has produced.** **"The court corners are out of frame" is a FULL SUCCESS** and
                 is a permanent framing limitation worth knowing. **"They are visible but always occluded"
                 is a different full success** and is fixable by acquiring more footage. **A FAIL with
                 verified identity is also a full success.** Do not relabel to reach a verdict.
  n            = 1 clip plus any probe sections, 4 court corners, 3 independent labellings if a frame is
                 eligible -- state every denominator in the verdict line
  eye check    = the corner visibility survey and the identity crops ARE the measurement
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract, the
                  harness, G222's matcher settings, existing label files, the existing corpus clips,
                  `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the two
                  abandoned partials
EVIDENCE: docs/evidence/tracking/g249_amateur_court_corner_seed_2026-09-04.md with the source check, the
per-corner visibility and occlusion survey with counts, any identity crops and gate verdicts, any
acquisition record with its eligibility proof and `ls -la`, every disk-guard probe, bytes freed, and a NOT
VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
