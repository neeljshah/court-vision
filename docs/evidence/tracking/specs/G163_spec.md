GAP G163 | sport tennis | worktree a8 | log cx_g163_jump_and_duplicates
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A3, A7 and Q8;
self-check section B before reporting. DIAGNOSIS ONLY. Move no threshold, no gate, no verdict.

THE OPENING. `tennis_smoke` is the first tennis table on the new pod to reach the jump gate
(`/workspace/nba-ai-system/data/tracking/tennis_smoke/`, 1,861 rows, 726 distinct frames,
`court_feet`, `calibration_provenance=solved` on 1,558/1,861 = 0.8372). It still fails the quality
gate on three counts:

    passed=False failures=['duplicate frame-track rows 4', 'median_track_len 1.00 < 3.00',
    'jump_max 48.93 > 8.00']

G162 (worktree a2) owns `median_track_len`. **This row owns the other two: `jump_max 48.93 > 8.00`
and the 4 duplicate frame-track rows. Do not duplicate G162's work on track length.**

DIAGNOSE, do not fix:
  (a) Reproduce both numbers yourself from the table (A2). Never quote a number you have not
      recomputed. Report the jump distribution in feet -- not just the max: the median, the 95th
      percentile, and how many jumps exceed 8.00. Give the ELIGIBLE DENOMINATOR (the consecutive
      same-track observation pairs the statistic is computed over) and take every share over it.
      Never a bare sample size.
  (b) THE OBVIOUS CONFOUND, and this row is worthless without it. If the median track length is 1,
      then "consecutive same-track observations" may barely exist, and a jump statistic computed over
      a handful of pairs is a degenerate denominator (B9). **Report how many pairs the jump statistic
      actually has.** If it is a tiny number, say so loudly: `jump_max 48.93` computed over four pairs
      is not the same object as one computed over four thousand, and the honest conclusion may be that
      this failure is an artefact of the track-length failure rather than an independent defect.
      That finding, if true, is the most valuable thing this row can produce.
  (c) Locate the 4 duplicate frame-track rows exactly: name the frame and track id of each, and show
      the duplicated rows verbatim. Are they byte-identical duplicates, or two different positions
      claiming one (frame, track) key? Those are different bugs with different causes.
  (d) Trace where a duplicate could enter, from quoted code. The tennis adapter emits both players or
      neither and keeps at most one detection per court half; establish from the code how two rows can
      share one (frame, track_id) key at all despite that.
  (e) Say which of the three harness failures are INDEPENDENT and which are consequences of another.
      Be explicit about the direction of causation you are claiming and what evidence supports it. If
      you cannot establish direction, say the failures are correlated and name what would settle it.
  (f) Eye check: render 5 frames sampled EVENLY across the clip (A3, B7 -- not a head slice) that
      contain either an over-threshold jump or a duplicate. If fewer than 5 such frames exist, render
      all of them and say how many there were.

DO NOT edit the adapter, the harness, `jump_max`, `min_players`, the coverage bar, the coordinate
contract, or any verdict. Do not propose raising the 8.00 threshold -- a bar found unmeetable is
reported CLOSED AT LIMIT, never moved (Q3, B10). Do not re-track into the shared store.

ACCEPTANCE RULE:
  metric        = the jump distribution in feet with its pair-count denominator stated; the four
                  duplicates named and shown; the independence-versus-consequence verdict
  before        = both failures are reported by the harness with no diagnosis and no denominator
  bar           = NO pass bar. Success is both numbers reproduced with their denominators exposed.
                  "The jump failure is an artefact of the track-length failure" is a full success and
                  the most useful outcome available.
  n             = every consecutive same-track pair in the table (CONSTRUCT, exhaustive); state the
                  count explicitly
  eye check     = REQUIRED: up to 5 evenly-sampled frames containing a jump or duplicate, committed
  must not move = the tennis adapter, the harness, jump_max, min_players, the coverage bar, the
                  coordinate contract, and every verdict
EVIDENCE: docs/evidence/tracking/g163_jump_and_duplicates_2026-09-03.md with the jump distribution,
the pair-count denominator, the four duplicates verbatim, the causation verdict, the renders under
docs/evidence/tracking/g163_jump/, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: READ-ONLY table access only. The daemon and bridge are LIVE. Never kill or restart anything.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
