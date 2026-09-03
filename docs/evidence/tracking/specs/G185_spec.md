GAP G185 | sport baseball, soccer, football | worktree a4 | log g185_coordinate_contract_wall
**DIAGNOSIS ONLY. Change NO production code.** No bar, threshold, gate, coordinate contract, adapter
flag default, or verdict. If you find yourself making `image_px` acceptable for a sport, STOP -- that
is the coordinate contract, it is deliberate, and editing it is an automatic REJECT under B10/Q3.

CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read in full. Self-check section B before
reporting. Q8 premise-first is the first phase of this job.

WHY THIS IS THE HIGHEST-LEVERAGE OPEN ROW (measured by the orchestrator from the live pod ledger
`data/tracking/track_daemon_ledger.jsonl`, 34 rows, 2026-09-03):
  - **0 of 34 rows pass.** 26 `passed:false`, 8 `passed:null`.
  - **24 of 34 rows fail at `coordinate_contract`** -- 19 baseball, 3 football, 2 soccer -- with the
    head `rows declare coordinate_space image_px not accepted for sport <s>`. They are rejected
    BEFORE any quality gate is evaluated.
  - Tennis, which several lanes have chased, is **2 rows**. This row is 12x that by ledger weight.
  - **G182** established the tennis analogue: `detect_court_corners` returns nothing on
    26,113/28,773 = 90.755 pct of frames, so calibration is starved. **G182b** then showed the loss
    is not purely a footage property -- a frame carrying all four corners also failed.

THE HYPOTHESIS TO TEST, stated so you can falsify it rather than confirm it:
  Each of these three sports has a calibrated emit path AND an uncalibrated `image_px` path, the
  daemon is taking the uncalibrated one, and the reason is that the sport's calibration detector
  fires on a small minority of broadcast frames -- the same wall G182 measured for tennis.
  Supporting quotes, which are STARTING POINTS and not established facts:
  - `domains/baseball/tracking/adapter.py:210-224` emits `coordinate_space: image_px` under an
    `image_space` flag, with a comment stating pitch geometry "passes ~24 of 500 broadcast frames"
    so gating on it "emitted 0 rows". **That figure is a CODE COMMENT, not a measurement. Do not
    quote it as measured. Measure it.**
  - `domains/baseball/tracking/adapter.py:225+` has a separate calibrated path under
    `if self._geometry is not None`.
  - `domains/soccer/tracking/adapter.py:140` sets `image_px` conditionally on the same kind of flag.
  - `domains/football/tracking/adapter.py:116` emits `coordinate_space: court_feet` with a homography
    calibration -- **yet football's ledger rows still report image_px.** Football is therefore the
    most informative of the three: explain that contradiction specifically.

DELIVER, in this order:
  1. **Which path each ledger row actually took, and why.** For all 24 coordinate_contract rows, name
    the flag/config that selected the uncalibrated path on the daemon route. Quote the call site that
    sets it. If it is a default, say which default and where.
  2. **The calibration-detector hit rate per sport, measured**, on the same footing as G182's tennis
    number: frames where the sport's calibration succeeded over frames the adapter evaluated. Put
    tennis's landed 9.245 pct in the same table as a reference column. Use real pod footage.
  3. **State whether the walls are the same phenomenon or merely similar.** A shared low hit rate is
    NOT by itself evidence of a shared cause. If you cannot separate them with the evidence available,
    say so -- "these are two separate walls that happen to look alike" is a FULL SUCCESS.

MANDATORY:
  - **A3 even sampling** on any frame subset; state positions and resulting indices. A head slice is
    an automatic reject under B7.
  - **Name the ELIGIBLE denominator on every row**, never the sample size. Say explicitly whether a
    denominator is decoded, evaluated, or emitted frames -- G164 found three quantities sharing one
    name and G179 corrected the gating one to evaluated frames.
  - **Store PER-FRAME records in your artifact, not just aggregates.** G182b's aggregate-only artifact
    could not be independently recomputed by the verifier and was downgraded for it.
  - A per-file test for any harness you add under `scripts/platformkit/tracking/`.

ACCEPTANCE RULE:
  metric        = the path-selection cause for all 24 rows; the per-sport measured calibration hit
                  rate with tennis alongside; a stated same-or-different verdict on the walls
  before       = 24/34 ledger rows rejected at coordinate_contract, cause unexamined; the only
                  quantitative claim in the area is an unverified code comment
  bar          = NO pass bar. Success is the cause named and the hit rates measured. "The
                 uncalibrated path is a deliberate preservation path and these rows were never
                 intended to be scorable" is a FULL SUCCESS and would be a major clarification.
  n            = all 24 coordinate_contract rows (CONSTRUCT, exhaustive); name any excluded and why
  eye check    = for the modal failing sport, render 5 evenly spaced frames where calibration failed
                 and say whether a human sees the geometry the detector wanted
  must not move = the coordinate contract, every bar and threshold, every adapter flag DEFAULT, every
                 verdict, src/ (human-gated), the pod daemon and keeper
EVIDENCE: docs/evidence/tracking/g185_coordinate_contract_wall_2026-09-03.md with the path-selection
table, the per-sport hit-rate table with eligible denominators, the eye check, the same-or-different
verdict, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: your new per-file test, pasted. NEVER a full pytest.
POD: READ-ONLY and BATCHED. Never kill, restart or deploy over the daemon or keeper.
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
