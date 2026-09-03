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
POD: read-only and batched, except running your own bounded measurement job. Never kill, restart or
deploy over the daemon or keeper; do not wait on the daemon, it is slow by a known defect (G186).
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
