GAP G241 | sport wnba | worktree a5 | log g241_seed_horizon_to_failure
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G240 may be running; N=2 is optimal per G200/G216). **Check first, do
NOT interrupt a running row, and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**WHY THIS ROW EXISTS -- G233d WORKED AND THE NUMBER IT PRODUCED IS A FLOOR, NOT AN ANSWER.**
G233d seeded at the G196-validated frame **19599** of `wnba__wnba_01.mp4` (scale 1.0, WNBA 16-ft lane),
**passed its distance-zero gate on independent geometry**, and then held for **all 1,200 frames tested**:
finite maps throughout, direct matches 452-1,863, inliers 421-1,848, inlier ratio 0.839901-0.991948, RMS
residual 0.299365-0.702623 px, in-court fraction stable at 0.828-0.918, and renders at 0/200/400/600/800/
1000/1200 showing **"the direct court did not come off the painted court in this observed span."**

**It reported `ceil(108000 / 1200) = 90` labels per hour and explicitly called that the tested horizon,
not a rate. THE HORIZON WAS NEVER REACHED -- 1,200 was simply where the run stopped.** **The operational
difference is large: 1,200 frames means 90 labels per hour of 30 fps footage; 5,000 means 22; 10,000
means 11. That is the difference between a tedious labelling job and a cheap one.**

THE QUESTION: **how far does direct-to-seed propagation actually hold from frame 19599, and what breaks
it first?**

METHOD:
  1. **Reuse G222's landed harness and G233d's exact seed construction UNCHANGED** -- same clip, same
     frame 19599, same four labels at scale 1.0, same `court_points_for_sport("wnba")`. **This row must
     differ from G233d in ONE respect only: how far it runs.** If you change anything else the comparison
     is void.
  2. **Reproduce G233d's first 1,200 frames as a control before extending.** **If the numbers do not
     match, STOP and report that** -- G240 is separately testing whether the adapter path is repeatable,
     and a mismatch here would be an important finding in its own right.
  3. **Extend well past 1,200 -- state your target and why -- and run until it FAILS or you hit a stated
     bound.** Report **drift and matched-feature counts versus distance at regular intervals**, as G222
     and G233d did, so all three rows are commensurable.
  4. **REPORT WHAT BREAKS IT, which is the real deliverable.** G215 found chained propagation decayed
     from an ordinary camera PAN with no shot cut present. Candidates here: a **shot cut**, a replay, a
     hard zoom, a crowd-only frame, or gradual overlap loss. **Say which occurred in your span and what
     each did.** **A collapsing matched-feature count is the signature of overlap loss and looks
     different from a cut, which is abrupt -- distinguish them.**
  5. **EYE CHECK IS THE DELIVERABLE, as in G215, G222 and G233d**: render the projected court at
     increasing distances and **state the distance at which a human can see it leave the painted court.**
     Commit the renders. **Judge on INDEPENDENT geometry -- arc, sidelines, centre circle -- never on the
     four fitted corners.**
  6. **Then restate labels-per-hour with the horizon you actually measured**, with the arithmetic and its
     assumptions. **If it fails at a shot cut, the operational unit is the CAMERA SHOT, not a frame
     count** -- say so, and report how many cuts your span contained.
  7. **Do NOT tune the seed, adjust a label, or change the matcher.** If propagation fails early, that is
     the finding.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,740 MB of 50,000), STOP and report if it fails.** A
long run decodes many frames -- **decode to memory, keep renders small, delete every temporary artifact
and report bytes freed.** Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one camera. **The direct-reference
drift is 0.0 BY CONSTRUCTION and is not independent evidence** -- G233d said so and you must too; the
renders and the matched-feature counts carry the claim. This **CONSUMES A HAND LABEL** and says nothing
about automatic calibration, which remains 0/17. **Plausibility is necessary, never sufficient**, and the
in-court fraction includes officials, bench and spectators -- G225's eye check found 19 raw boxes
yielding only 2 on-court players in one frame. G140's p90 label repeatability is 11.39 px.

ACCEPTANCE RULE:
  metric        = drift and matched-feature counts versus distance from the seed, out to failure or a
                  stated bound; the distance at which the eye check fails; the named cause of failure;
                  the in-court fraction over the extended span; and labels-per-hour recomputed from the
                  measured horizon
  before       = G233d held for all 1,200 frames tested without reaching a limit; 90 labels/hour is a
                 floor derived from where the run stopped, not from where propagation breaks
  bar          = NO pass bar. **"It fails at frame N because X" is the ideal outcome** -- a named limit
                 is worth more than an unreached one. **"It holds to the stated bound without failing"
                 is also a full success** and would push labels-per-hour down further. Do not tune, and
                 do not extrapolate past what you ran.
  n            = 1 clip, 1 seed, one extended span (a horizon and a decay shape, not a rate)
  eye check    = the distance renders ARE the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the
                  harness, the label files, G222's matcher settings, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g241_seed_horizon_to_failure_2026-09-04.md with the G233d control
reproduction, the drift and feature-count table versus distance, the failure distance and its named
cause, the cut/zoom inventory of the span, all renders, the recomputed labels-per-hour, every disk-guard
probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
