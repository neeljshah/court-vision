GAP G162 | sport tennis | worktree a2 | log cx_g162_track_continuity
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A3, A7 and Q8; self-check
section B before reporting. DIAGNOSIS ONLY. Move no threshold, no gate, no verdict.

THE OPENING, and it is a new one. Until today no tennis table on the new pod reached the jump gate.
One now does. `tennis_smoke` (produced by the orchestrator's bootstrap run of the tennis adapter on
the local reference clip, tracked on the pod at `/workspace/nba-ai-system/data/tracking/tennis_smoke/`)
carries 1,861 rows over 726 distinct frames, declares `court_feet`, and has a
`calibration_provenance=solved` share of 1,558/1,861 = **0.8372**. G157 classified its first blocker
as `reaches_gate`.

So calibration is NOT what stops this table. The harness verdict was:

    tennis_smoke rows=1861 passed=False failures=['duplicate frame-track rows 4',
    'median_track_len 1.00 < 3.00', 'jump_max 48.93 > 8.00']

**`median_track_len 1.00` is the one this row is about.** A median track length of exactly 1 means the
typical track id appears in ONE frame and never again: identities are not persisting across frames at
all. On a clip where 83.72 pct of rows have solved geometry, the binding problem is track continuity,
not court recovery. That is a different failure from everything the program has chased for tennis so
far, and it is worth understanding before anyone re-tracks anything.

DIAGNOSE, do not fix:
  (a) Reproduce the number yourself from the table (A2). Report the track-length distribution, not
      just the median: how many track ids appear in 1 frame, 2, 3-5, 6-10, more. Give the ELIGIBLE
      DENOMINATOR (distinct track ids) and take every share over it. Never a bare sample size.
  (b) Find where `track_id` is assigned in the tennis path and quote the deciding lines with
      file:line. Is there any cross-frame association at all -- an IoU match, a Hungarian assignment,
      a Kalman predict, a centroid nearest-neighbour -- or is a fresh id minted per frame? The adapter
      keeps `self._centroids` and a `self._track_id_base`; establish what they actually do.
  (c) If association exists, find why it fails here. If it does NOT exist on this path, say so plainly
      and quote the code: "there is no cross-frame association" is a complete and valuable answer, and
      it would explain a median of exactly 1 without any tuning question.
  (d) THE CATCH you must handle: the tennis adapter emits BOTH players or NEITHER
      (`domains/tennis/tracking/adapter.py`, the `if set(per_half) != {0, 1}: return []` rule that
      G148 measured). Frames drop out entirely when one player is missed. Say whether that gappiness
      alone could produce a median track length of 1 even with working association, and how you
      distinguish the two causes from the table.
  (e) State what a fix would have to change, and what it must NOT change. `min_players`, the coverage
      bar, the jump threshold and the coordinate contract are all frozen. Do not propose moving any
      of them, and do not propose relaxing the two-slot rule -- G148 already established that relaxing
      it cannot raise coverage as the harness computes it.
  (f) Eye check: render 5 CONSECUTIVE frames from the middle of the clip (A3 -- not the head) with
      detections and track ids drawn. Say what the eye sees: are the same two people being given new
      ids each frame, or are the detections themselves jumping?

DO NOT edit the adapter, the tracker, the harness, any threshold, or any verdict. Do not re-track into
the shared store. Do not touch the pod beyond READ-ONLY table access.

ACCEPTANCE RULE:
  metric        = track-length distribution over distinct track ids; the association mechanism quoted
                  from code; the cause attributed between no-association and frame gappiness
  before        = `median_track_len 1.00 < 3.00` is a reported failure with no diagnosis behind it
  bar           = NO pass bar. Success is the distribution measured and the mechanism established from
                  quoted code. "There is no cross-frame association" is a full success and closes the
                  question.
  n             = every distinct track id in the table (CONSTRUCT, exhaustive)
  eye check     = REQUIRED: 5 consecutive mid-clip frames with ids drawn, committed
  must not move = the tennis adapter, the harness, min_players, the two-slot rule, jump_max, the
                  coverage bar, the coordinate contract, and every verdict
EVIDENCE: docs/evidence/tracking/g162_track_continuity_2026-09-03.md with the distribution table, the
quoted association code, the cause attribution, the 5 renders under
docs/evidence/tracking/g162_continuity/, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: READ-ONLY table access only. The daemon and bridge are LIVE. Never kill or restart anything.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
