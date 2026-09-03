GAP G188 | sport wnba, tennis | worktree a5 | log g188_player_selection_defect
**DIAGNOSIS ONLY. Change NO production code.** No bar, threshold, gate, detector constant, selection
rule, coordinate contract or verdict. `src/` is HUMAN-GATED: run it, never edit it. A fix is a
FINDING to report, not a change to make.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full. Self-check section B before
reporting. Q8 premise-first.

WHY (landed, do not re-derive):
  - **G187**: a bounded WNBA clip now runs end to end (1,104 rows over 394 of 400 attempted gameplay
    frames, exit 0, 125.8 s). But the output is not usable. Orchestrator eye check on the committed
    renders: at frame 1377, of four emitted boxes one is a seated SPECTATOR and three are bench or
    staff behind the far baseline, while **not one of roughly ten clearly visible on-court players is
    detected**. Frame 474 is the same shape. Aggregate: **2.80 rows per frame against roughly ten
    players on court.**
  - **G18** (tennis, landed earlier): "the oob rows are courtside non-players that `detect_players`
    picks as the per-half box" -- at one frame the two emitted feet were staff and a ball kid while
    NEITHER real player was emitted.
  - Two sports, same shape. This is a cross-sport player-SELECTION problem, not a tennis quirk.

THE QUESTION, and it is the only one that matters here: **is the underlying person detector finding
the on-court players and the SELECTION logic discarding them, or is the detector not finding them at
all?** Those have opposite fixes and the evidence so far cannot tell them apart.

METHOD:
  1. Q8 premise: reproduce G187's frame 1377 and frame 474 independently. If your box set differs
     from the committed renders, STOP and report that instead -- it would mean the run is not
     reproducible.
  2. For an evenly spaced sample of frames, record BOTH stages per frame:
     (a) the RAW detector output before any selection -- every person box with its confidence, and
     (b) the boxes that SURVIVE into emitted rows.
     The delta between them is the deliverable. Route through the existing detector shim
     (`scripts/platformkit/detection/shim.py`, `get_box_detector` / `get_detector`); the default
     backend is `ultralytics` via `CV_DETECTOR`.
  3. Report per frame: raw person count, surviving count, and how many of each a human would call an
     ON-COURT player. **Name the ELIGIBLE denominator on every row** (frames sampled), never the
     sample size.
  4. **Say which of the two causes the evidence supports, or that it cannot separate them.** "The
     detector genuinely does not find them" is a FULL SUCCESS. So is "the detector finds them and
     selection drops them". So is "cannot separate on this evidence".
  5. Do the same for ONE tennis clip so the cross-sport claim is measured rather than asserted. If
     tennis behaves differently from basketball, that is a finding, not a problem.

MANDATORY:
  - **A3 even sampling**; state positions and resulting frame indices. B7 head-slice is an auto-reject.
  - **Store PER-FRAME records** in the artifact, with raw and surviving boxes both retained. An
    aggregate-only artifact cannot be verified and will be downgraded (G182b was).
  - Eye check: render at least 5 evenly spaced frames showing RAW boxes and SURVIVING boxes in
    visually distinct colours, and state for each how many on-court players a human counts. The
    human count is the ground truth this row rests on, so state it per frame, not as a total.
  - A per-file test for any harness added under `scripts/platformkit/tracking/`.
  - **Do NOT claim a recall or precision rate from the eye check alone.** Five frames is an existence
    sample. If you want a rate, say exactly what population it is over.

ACCEPTANCE RULE:
  metric        = per-frame raw-vs-surviving box counts, with a human on-court player count, across
                  both sports; and a stated verdict on which cause the evidence supports
  before        = 2.80 rows/frame against ~10 players; spectators and bench emitted while on-court
                  players are missed; cause unknown
  bar           = NO pass bar. Naming the cause, or honestly declining to, is the success.
  n             = >= 20 frames per sport (CONSTRUCT sample, evenly spaced); name the eligible set
  eye check     = the 5 dual-colour renders described above
  must not move = every threshold and constant, the detector backend default, the coordinate
                  contract, every bar and verdict, `src/` (human-gated), the pod daemon and keeper
EVIDENCE: docs/evidence/tracking/g188_player_selection_defect_2026-09-03.md with the per-frame table,
the dual-colour renders, the stated cause verdict, and a NOT VERIFIED list. Commit BEFORE reporting.
TEST: your per-file test, pasted. NEVER a full pytest.
**RUN EVERY MEASUREMENT ON THE POD, NOT LOCALLY.** This was missing from the first dispatch and a
local `run_clip.py` was killed at 95 pct box RAM on 2026-09-03; the local box has 16 GB and other
lanes run on it, so a local decode job risks taking them down with it. The pod has an idle RTX 3090
and 24 GB. Copy nothing INTO the pod checkout; run your measurement as its own process there and pull
results back.
POD: read-only and batched, except running your own bounded measurement job THERE. Never kill, restart or
deploy over the daemon or keeper; do not wait on the daemon, it is slow by a known defect (G186).
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.

## RE-DISPATCH 2026-09-03, read this before anything else

The first attempt STOPPED at Q8 and was RIGHT to. Two things it hit are now fixed
in this spec; a third is your job.

1. **THE SOURCE IS AMBIGUOUS AND THAT IS WHAT BROKE THE FIRST RUN.** Two different
   videos both answer to `wnba_01`:
   - `data/footage_corpus/wnba__wnba_01.mp4` on the POD -- 1920x1080,
     2,931,985,407 bytes. **THIS ONE. G187 measured it and it is authoritative.**
   - `data/footage_corpus/g130_recensus/wnba__wnba_01.mp4` locally -- a 1280x720
     DERIVATIVE. Not interchangeable.
   State the full path, byte size and resolution of whatever you open, in the memo
   and in the artifact. If you cannot reach the 1080p pod file, STOP and say so.
2. **RUN ON THE POD.** Stated above and repeated here because the first run did
   not: two RAM guards fired on the 16 GB local box at 95 and 96 pct with other
   lanes live. The pod has an idle RTX 3090 and 24 GB.
3. **The first run found something you must engage with, not repeat.** On the
   720p derivative's frame 474, the existing survivor path retained **6 on-court
   players from 11 raw person detections** -- while G187's 1080p run at the same
   frame retained 3, including a foreground spectator. Same code, different input,
   materially different answer. So the live question is now sharper than the
   original one:

   **Does the 1080p pod source reproduce G187's 3 non-court survivors, or does it
   behave like the derivative?** Answer that FIRST, on frame 474, before any
   20-frame table. If it reproduces, the cause is in the input or the route, not
   the detector. If it does not reproduce, then G187's own run is not reproducible
   and THAT is the finding -- report it and stop.

Carry the `TOPCUT=60` crop question explicitly: the first run applied the normal
crop before detection. Say whether G187's route did, since a different crop is a
sufficient explanation on its own and would make this a route difference rather
than a selection defect.

Everything else in the spec above stands unchanged.
