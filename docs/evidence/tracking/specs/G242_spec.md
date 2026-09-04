GAP G242 | sport wnba | worktree a6 | log g242_seed_reacquisition_whole_game
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G241 is running on a5; N=2 is optimal per G200/G216, so ONE more lane
is allowed). **Check first, do NOT interrupt a running row, and say in your memo that you checked and when
you began** -- G236b and G240 both did this correctly. The `track_daemon`, `keep_track_daemon.sh`,
`adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load
floor.

**WHY THIS ROW EXISTS -- G241 IS MEASURING THE WRONG AXIS IF CONTIGUITY DOES NOT MATTER.**
G233d seeded ONE hand label at the G196-validated frame **19599** of `wnba__wnba_01.mp4`, passed its
distance-zero gate on independent geometry, and held for all 1,200 contiguous frames tested (direct
matches 452-1,863, inliers 421-1,848, RMS 0.299365-0.702623 px). G241 is now extending that CONTIGUOUS
span to failure.

**But a basketball broadcast is shot mostly by ONE main camera that keeps returning to the same pose
family all game.** If a frame 100,000 away matches the seed **DIRECTLY** -- skipping everything between --
then the contiguous horizon is not the operational number at all. **The whole clip is 174,430 frames
(5,814.354 s, 30 fps): 19,599 frames BEFORE the seed and 154,830 after.**

THE QUESTION: **across an ENTIRE game, what fraction of sampled frames acquire a homography DIRECTLY
against a single seed, and what are the ones that fail?**

**The operational stake is larger than G241's.** If most of a game re-acquires from one label, the unit is
ONE LABEL PER ARENA-CAMERA and labels-per-hour approaches 1. If almost nothing outside the local span
acquires, then G241's contiguous horizon IS the number and this row says so decisively.

METHOD:
  1. **Reuse G233d's seed construction EXACTLY and G222's landed harness UNCHANGED** -- same clip, frame
     19599, the same four labels at scale 1.0, `court_points_for_sport("wnba")` (16-foot lane), the same
     homography. **Do not re-derive the seed; reproduce it and confirm it matches G233d's published
     matrix.** If it does not, STOP and report that.
  2. **Sample the WHOLE clip at a wide stride in ONE sequential decode pass** -- a single strided
     `select` filter giving roughly 88 frames from 0 to 174,000 at a stride of about 2,000. **Do NOT
     decode each sample with its own `eq(n,N)` pass; that re-decodes the whole prefix every time and will
     not finish.** **Cover frames BEFORE the seed as well as after** -- negative distance is half the
     evidence.
  3. **VERIFY YOUR INDEX MAPPING before trusting it.** Re-decode ONE sampled frame independently with a
     frame-exact `eq(n,N)` select and report its MAD against the strided frame at that index. **A wrong
     frame index is the exact failure that cost G233b (MAD 61.33) and G233c** -- do not assume the stride
     arithmetic. Include the seed frame 19599 itself as an explicit positive control.
  4. **For every sampled frame, attempt a DIRECT match to the seed and report matches, inliers, inlier
     ratio and RMS residual versus signed distance from the seed.** **Use G222's OWN acceptance criteria
     unchanged to decide "acquired" -- do NOT invent a threshold and do NOT lower one to raise the
     fraction.** Report the **acquisition fraction over the named sample denominator** and the inlier
     distribution.
  5. **CLASSIFY THE FAILURES -- this is the deliverable, not the fraction.** A failure is not one thing.
     **The seed is a HOOP-END view, so a frame showing the OTHER END is a different part of the court
     model and will fail even though the camera and pose are perfectly fine.** That is a completely
     different and far more tractable finding than a replay, a close-up, a crowd shot, a graphic, or a
     genuinely different camera. **Open the failing frames and say which each one is, with counts.**
  6. **EYE CHECK IS THE DELIVERABLE.** Render the projected court on acquired frames spread across the
     game **including the most distant acquisition in each direction**, and state whether it lands on the
     painted court. **Judge on INDEPENDENT geometry -- arc, sidelines, centre circle -- NEVER the four
     fitted corners.** Also render several FAILED frames so a reader can see what they are. Commit every
     render.
  7. **Then restate labels-per-hour under what you measured**, with arithmetic and assumptions, and say
     plainly whether the operational unit is a contiguous span (G241's axis) or an arena-camera.
  8. **Do NOT tune the seed, adjust a label, change the matcher, or re-open G241's contiguous question.**

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,735 MB of 50,000), STOP and report if it fails.** A
whole-clip decode pass is long -- **stream it, keep only the roughly 88 sampled frames, never write a full
decode to disk, keep renders small, delete every temporary artifact and report bytes freed.** Delete no
corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one arena, one camera plan.
**ACQUISITION IS NOT CORRECTNESS** -- a homography can be accepted and still be wrong, so the renders and
not the inlier counts carry the claim. **Direct-reference drift at distance 0 is 0.0 BY CONSTRUCTION and
is not evidence.** This **CONSUMES A HAND LABEL** and says nothing about automatic calibration, which
remains 0/17. **Plausibility is necessary, never sufficient**, and any in-court fraction includes
officials, bench and spectators -- G225 found 19 raw boxes yielding 2 visibly on-court players in one
frame. G140's p90 label repeatability is 11.39 px. A wide stride measures WHETHER a pose family recurs,
not how long any individual shot lasts -- that is G241's question, not this one.

ACCEPTANCE RULE:
  metric        = the acquisition fraction over a named sample denominator across the whole clip; inliers
                  and RMS versus SIGNED distance from the seed; the classified failure inventory with
                  counts; the renders at the most distant acquisition each way; and labels-per-hour
                  restated
  before       = G233d established a seed holds 1,200 contiguous frames; nothing has tested whether a
                 distant, non-contiguous frame acquires from the same seed at all
  bar          = NO pass bar. **A LOW acquisition fraction is a FULL SUCCESS** -- it would prove the
                 seeded path is span-local and make G241's contiguous horizon the operational number.
                 **A HIGH fraction is the other full success** and would move the unit from a span to an
                 arena-camera. **"It fails because the camera is at the other end" is a THIRD and more
                 useful outcome than either.** Do not tune, and do not extrapolate past what you ran.
  n            = 1 clip, 1 seed, roughly 88 sampled frames -- state the exact denominator in the verdict
                 line
  eye check    = the acquired and failed renders ARE the deliverable
  must not move = every threshold, bar and verdict, G222's matcher settings and acceptance criteria, the
                  court model, the coordinate contract, the harness, the label files, `src/` and
                  `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g242_seed_reacquisition_whole_game_2026-09-04.md with the reproduced seed
homography and its agreement with G233d, the index-mapping verification MAD, the full per-sample table
versus signed distance, the acquisition fraction with its denominator, the classified failure inventory,
all renders, the restated labels-per-hour, every disk-guard probe, bytes freed, and a NOT VERIFIED list.
Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
