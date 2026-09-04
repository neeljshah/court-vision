GAP G232 | sport tennis | worktree a3 | log g232_tennis_solver_scale_cause
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. `domains/tennis/` is
**READ and IMPORT only** -- import its solver and call it from your own process; edit nothing there.
Build in `scripts/platformkit/tracking/`.

**HELD UNTIL THE POD IS FREE OF MEASUREMENT ROWS** (G211b, then G226c). **Check first and say in your
memo that you checked and when you began.** The `track_daemon`, `keep_track_daemon.sh`, `adapter_run`
jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT residents and the load floor -- never
wait for them, never kill or restart them. Harness and test preparation may proceed immediately.

**WHY THIS ROW EXISTS -- FOUR CANDIDATE CAUSES HAVE ALREADY BEEN ELIMINATED AND THE SEARCH IS NOW
NARROW.** Tennis is the ONLY sport emitting `coordinate_space=court_feet`, so it is the only place the
programme can ask whether its coordinates are right. G230 found that in two of three tables **about
three quarters of player rows fall outside the adapter's own declared 78 x 36 ft plane** (76.37 pct and
75.80 pct, against 13.71 pct for `tennis_ref01`). Since then:
  - **G231: the pattern is an X-AXIS SCALE/EXTENT signature**, mass beyond BOTH ends of x (11,904 of
    12,805 and 1,092 of 1,140), persistent across many tracks and across each table's whole source-frame
    range -- not a few bad tracks, not one time span.
  - **G231: a single uniform positive rescale does NOT explain it.** At the best-fit k (1.579292 and
    1.479525) **46.46 pct and 46.68 pct of rows remain out, and they are exactly the negative-coordinate
    rows.**
  - **G231: singles-vs-doubles is arithmetically impossible** -- 36/27 = 1.333 matches neither k, and a
    doubles model is LARGER than singles so the mix-up could not push players outside its bounds.
  - **G231-ELIM: a centre-origin convention mismatch is REFUTED** -- shifting by (+39, +18) moves
    `tennis_01` only 23.6 -> 25.9 pct in-bounds, makes `tennis_02` WORSE (24.2 -> 18.4), and destroys
    `tennis_ref01` (86.3 -> 29.0).
  - **G231-ELIM: "the tracker is emitting non-players" is REFUTED, decisively** -- **every frame in all
    three tables carries EXACTLY TWO player track ids** (8,383 / 752 / 715 frames, distribution `{2: N}`,
    no frame with one or three). The off-court rows are the two TRACKED PLAYERS.
  - **AND THE ONE THAT SETS THIS ROW'S TARGET -- G231 measured out-of-bounds rate BY
    `calibration_provenance` and camera-lock REUSE IS ELIMINATED: `tennis_01` is 76.55 pct for freshly
    `solved` rows against 76.24 pct for `camera_lock_drift_checked` rows.** **Fresh solves are just as
    wrong as reused ones, so the defect is in the SOLVE, not in the reuse guard at
    `domains/tennis/tracking/camera_lock.py:176-181`.** `projection_status` is blank on every eligible
    player row and can discriminate nothing.

**THE HYPOTHESIS THIS ROW TESTS, and you should try to refute it: the tennis solver assigns LINE ROLES
incorrectly on these two clips**, fitting the court model to the wrong lines -- for example a service
line taken as a baseline, or singles sidelines taken as doubles -- which would produce exactly a
scale-like error with a consistent x-extent inflation. `domains/tennis/tracking/court_lines.py` assigns
roles by **projective cross ratios** (`cross_ratio` at :46-56), and its own docstring records that this
replaced a first/last-cluster heuristic which had made the scoreboard the "far baseline". **A cross-ratio
match that lands on the wrong permutation is the specific failure mode to look for.**

**WHY THE RETAINED TABLES CANNOT ANSWER THIS AND YOU MUST RE-RUN THE SOLVER:** G231 said it plainly --
the tables "do not contain the residuals needed to diagnose that code as the cause". You need the solver
run on real frames with its intermediate line set and role assignment exposed.

METHOD:
  1. **Identify the source clips** for `tennis_01`, `tennis_02` and `tennis_ref01` on the pod and record
     each path, byte size and resolution. **If a source clip is no longer present, say so and drop that
     table** -- do not substitute another.
  2. Extract a modest number of frames per clip by **single-frame seeks** (`ffmpeg -ss ... -frames:v 1`),
     not a full decode. **State the count and how you chose them.** Keep them small and delete them,
     reporting bytes freed. **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE here; do a real
     `dd conv=fsync` probe, record `du -sm /workspace/nba-ai-system/data`, and STOP if it fails.
  3. **Run the UNCHANGED tennis solver on those frames from your own process**, capturing for each
     frame: the detected line set, **the role assigned to each line**, the cross-ratio evidence used,
     and the resulting homography. **Do not modify `court_lines.py` to get this -- import it and
     instrument around it, or re-implement only the reporting.**
  4. **Project the four court corners through each solved homography and report the implied court
     extent in feet.** **If the bad clips imply an extent near 123 x 67 ft where the good clip implies
     near 78 x 36, that is the scale error made visible at its source** -- G231-ELIM measured emitted
     ranges of x in [-13.11, 110.05] and y in [-10.50, 56.85] for `tennis_01`, against
     [-6.08, 84.71] and [-7.24, 46.70] for `tennis_ref01`.
  5. **Compare the ROLE ASSIGNMENTS between a good clip and a bad clip on visually similar views.**
     **A consistent, reproducible role permutation difference is the finding.** If roles agree and the
     homography is still wrong, **say so -- that refutes my hypothesis and is equally valuable**, and
     points instead at the line geometry or the model constants.
  6. **EYE CHECK IS THE DELIVERABLE:** render each solved court model back onto its frame for a good and
     a bad clip and state plainly whether the projected court lands on the painted court. Commit them.
  7. **Diagnose only. Do NOT fix, do NOT propose a `domains/` or `src/` change, do NOT tune a threshold,
     and do NOT introduce a gate.** If you identify a cause, name it with a `file:line` and stop.

**HONEST LIMITATIONS to state, not discover:** the retained tables were produced by an earlier run of a
NON-DETERMINISTIC route, so a fresh solve on the same clip is NOT guaranteed to reproduce the historical
table's homography -- **say this explicitly, and if your fresh solves look fine while the tables are bad,
that mismatch is itself the finding and you must not paper over it.** Three clips of one sport is not a
population. The renders are single-labeller eye judgements. Source width is unrecorded in the tables.

ACCEPTANCE RULE:
  metric        = per clip: detected line set, assigned roles, the implied court extent in feet from the
                  solved homography, and the projected-court renders; plus a good-versus-bad role
                  comparison
  before        = the out-of-bounds mass is a persistent x-axis scale/extent signature; camera-lock
                  reuse, centre-origin, singles/doubles, non-player emission and a single uniform
                  rescale are all eliminated; the solve itself is unexamined
  bar           = NO pass bar. **"Role assignment is identical and correct on both, so the hypothesis is
                  refuted" is a FULL SUCCESS**, and so is naming a reproducible role permutation. **"A
                  fresh solve does not reproduce the historical table" is also a full success** and would
                  say the tables cannot be diagnosed from code at all. Do not force a story.
  n             = 3 clips (or fewer if a source is gone), a stated small number of frames each
  eye check     = the projected-court renders described above -- this is the deliverable
  must not move = every threshold, bar and verdict, the coordinate contract, the 78 x 36 ft court model,
                  the harness, `src/` (READ ONLY), `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the committed historical tables
EVIDENCE: docs/evidence/tracking/g232_tennis_solver_scale_cause_2026-09-04.md with the source-clip
manifest, per-frame line sets and role assignments, the implied court extents, the good-versus-bad role
comparison, the renders, every disk-guard probe, bytes freed, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
