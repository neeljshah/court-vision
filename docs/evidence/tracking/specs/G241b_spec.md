GAP G241b | sport wnba | worktree a5 | log g241b_seed_horizon_to_failure
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G242 is running on a6; N=2 is optimal per G200/G216, so ONE more lane
is allowed). **Check first, do NOT interrupt a running row, and say in your memo that you checked and when
you began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and
`foundry_runner` are PERMANENT residents and the load floor.

**READ `docs/evidence/tracking/specs/G241_spec.md` AND ITS LANDED MEMO FIRST. G241 STOPPED CORRECTLY AND
THE FAULT WAS IN MY SPEC, NOT IN THE LANE.**

G241 required the G233d 1,200-frame control to reproduce, and stopped when it did not. **It was right to
stop.** But the mismatch was in a quantity this programme had ALREADY measured as non-deterministic, so
the control I wrote could never have passed:

| half of the control | result |
|---|---|
| **Propagation geometry (what the horizon question depends on)** | **REPRODUCED EXACTLY** -- all 1,200 direct-to-seed records equal record-for-record; matched features 452-1,863; inliers 421-1,848; inlier ratio and RMS identical to ten decimal places; **zero unequal paired records** |
| Detector / projection records | **808 of 1,201 differ (67.3 pct of frames)** -- total boxes 11,236 vs 11,242, inside 9,720 vs 9,723, overall in-court fraction 0.865077 vs 0.864882 |

**The detector half was never going to reproduce.** G189, G190, G195, G198, G199 and G203 all hunted the
route's non-determinism and none of them sourced it; G203 showed decode itself is byte-identical. G241
simply re-measured that known fact and my spec made it a stop condition. **The correction is landed as the
G233d-INCOURT-CORRECTION row.**

**THE HORIZON QUESTION IS THEREFORE STILL COMPLETELY UNANSWERED, AND IT IS THE SAME QUESTION.**
G233d held for all 1,200 frames tested and 1,200 is where the run STOPPED, not where it broke. **The
operational difference is large: 1,200 frames means 90 labels per hour of 30 fps footage; 5,000 means 22;
10,000 means 11.**

THE QUESTION: **how far does direct-to-seed propagation actually hold from frame 19599, and what breaks it
first?**

**THE CONTROL, CORRECTED -- THIS IS THE ONLY CHANGE FROM G241:**
  - **The control is the PROPAGATION GEOMETRY ONLY: matched features, inliers, inlier ratio, RMS
    reprojection residual, and finite-map status over the first 1,200 post-seed frames.** G241 proved
    these reproduce bit-exactly, so **require exact equality and STOP if they differ** -- a geometry
    mismatch would be a genuine and important finding.
  - **Detector and projection figures are ADVISORY, NOT A GATE.** Report them, and report how far they
    move against G233d and G241, but **do NOT stop on a detector difference** -- it is expected, its
    magnitude is about 0.05 pct of boxes, and the horizon does not depend on it.
  - **Report in-court fractions to THREE decimal places, not six**, and say in the memo that they are one
    draw from a non-deterministic detector.

METHOD:
  1. **Reuse G222's landed harness and G233d's exact seed construction UNCHANGED** -- clip
     `wnba__wnba_01.mp4`, frame 19599, four labels at scale 1.0, `court_points_for_sport("wnba")` (16-ft
     lane). **This row must differ from G233d in ONE respect only: how far it runs.**
  2. **Run the corrected geometry control over the first 1,200 frames, confirm exact equality, and say so
     in one line.** Then extend.
  3. **Extend well past 1,200 -- state your target and why -- and run until it FAILS or you hit a stated
     bound.** Report matched features, inliers, inlier ratio and RMS versus distance at regular intervals
     so G222, G233d, G241 and this row are all commensurable.
  4. **REPORT WHAT BREAKS IT, which is the real deliverable.** G215 found CHAINED propagation decayed from
     an ordinary camera PAN with no cut present -- but chaining is not what this row does. Candidates
     here: a **shot cut**, a replay, a hard zoom, a crowd-only frame, or gradual overlap loss. **Say which
     occurred in your span and what each did.** **A collapsing matched-feature count is the signature of
     overlap loss and looks different from a cut, which is abrupt -- distinguish them.**
  5. **EYE CHECK IS THE DELIVERABLE**: render the projected court at increasing distances and **state the
     distance at which a human can see it leave the painted court.** Commit the renders. **Judge on
     INDEPENDENT geometry -- arc, sidelines, centre circle -- NEVER the four fitted corners.**
  6. **Then restate labels-per-hour with the horizon you actually measured**, with the arithmetic and its
     assumptions. **If it fails at a shot cut, the operational unit is the CAMERA SHOT, not a frame
     count** -- say so, and report how many cuts your span contained.
  7. **Do NOT tune the seed, adjust a label, or change the matcher.** If propagation fails early, that is
     the finding.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~32,835 MB of 50,000), STOP and report if it fails.** A
long run decodes many frames -- **decode to memory, keep renders small, and do NOT re-commit G241's
control artifact, which is already landed at 4.3 MB.** Delete every temporary artifact and report bytes
freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one camera. **The direct-reference
drift is 0.0 BY CONSTRUCTION and is not independent evidence** -- G233d and G241 both said so and you must
too; the renders and the matched-feature counts carry the claim. This **CONSUMES A HAND LABEL** and says
nothing about automatic calibration, which remains 0/17. **Plausibility is necessary, never sufficient**,
and the in-court fraction includes officials, bench and spectators -- G225 found one frame with 19 raw
boxes yielding 2 visibly on-court players. G140's p90 label repeatability is 11.39 px.

ACCEPTANCE RULE:
  metric        = the geometry control result stated FIRST in one line; then matched features, inliers and
                  RMS versus distance out to failure or a stated bound; the distance at which the eye
                  check fails; the named cause of failure; advisory in-court fractions to three decimals;
                  and labels-per-hour recomputed from the measured horizon
  before       = G233d held for all 1,200 frames tested without reaching a limit; G241 confirmed that
                 geometry reproduces bit-exactly but stopped on a detector control that could not pass
  bar          = NO pass bar. **"It fails at frame N because X" is the ideal outcome** -- a named limit is
                 worth more than an unreached one. **"It holds to the stated bound without failing" is
                 also a full success** and would push labels-per-hour down further. Do not tune, and do
                 not extrapolate past what you ran.
  n            = 1 clip, 1 seed, one extended span (a horizon and a decay shape, not a rate)
  eye check    = the distance renders ARE the deliverable
  must not move = every threshold, bar and verdict, the court model, the coordinate contract, the harness,
                  the label files, G222's matcher settings, `src/` and `domains/` (READ and IMPORT ONLY),
                  the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g241b_seed_horizon_to_failure_2026-09-04.md with the geometry control
result, the feature-count and RMS table versus distance, the failure distance and its named cause, the
cut/zoom inventory of the span, all renders, advisory detector figures, the recomputed labels-per-hour,
every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
