GAP G166 | sport tennis | worktree a7 | log cx_g166_epoch_churn_attribution
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A3, A7 and Q8;
self-check section B before reporting. MEASUREMENT AND ATTRIBUTION ONLY. Change no adapter, no
threshold, no bar, no verdict.

WHY THIS IS THE TENNIS LEVER. Tennis is the only sport with a reachable coordinate contract, and the
first tennis table on the new pod to reach the jump gate, `tennis_smoke`, fails quality on
`median_track_len 1.00 < 3.00`. Its `calibration_provenance=solved` share is 0.8372, so **calibration
is not the blocker**. G162 established why, and that result is landed at
`docs/evidence/tracking/g162_g163_epoch_churn_2026-09-03.md` -- READ IT and do not re-derive it:

  - `domains/tennis/tracking/identity.py:12-25 assign_epoch` DOES associate across frames, comparing
    the direct pairing against the crossed pairing by summed L2 and keeping the cheaper one.
  - Continuity is scoped to an EPOCH. `_end_track_ids` advances `_track_id_base`
    (`domains/tennis/tracking/adapter.py:172-174`) so every later frame gets ids that can never
    associate back.
  - It fires from TWO places: `adapter.py:142` inside `_reset`, on calibration loss; and
    `adapter.py:220-229`, on `detect_cut`.
  - Ids ran 1..586 with no gaps at two per epoch, implying **293 epochs across 726 emitted frames**,
    an epoch ending roughly every 2.5 emitted frames.

**THE QUESTION G162 LEFT UNMEASURED, and it decides where any future effort goes: of those ~293
epoch ends, how many came from `detect_cut` and how many from calibration loss?** They have
completely different remedies and nobody knows the split. If cuts dominate, the epoch reset may be
correct behaviour on broadcast footage and track length is close to a footage ceiling. If calibration
loss dominates, the reset is being driven by solver instability on frames the solver had already
solved, and that is a different and more tractable problem.

DO THIS:
  (a) Instrument READ-ONLY. Add temporary counting that does NOT change behaviour -- count calls to
      `_end_track_ids` by call site, on a local run over the reference tennis clip. Do not commit an
      instrumented adapter; commit the counts and the diff you used, clearly marked as a measurement
      harness that was not landed.
  (b) Report, over an ELIGIBLE DENOMINATOR of total epoch ends: the count and share from `detect_cut`,
      and the count and share from `_reset`/calibration loss. Never a bare sample size.
  (c) Cross-check against the table: your epoch-end count should be consistent with the 293 implied by
      the id numbering. If it is not, say so plainly and do not reconcile by adjusting either number --
      a mismatch is a finding about the id allocation and is worth more than a tidy agreement.
  (d) For the calibration-loss half only, characterise WHY the solver loses lock. `_reset` is reached
      from the camera-lock / drift check around `adapter.py:138-142`, where a transformed-probe
      displacement above 8.0 triggers it. Report the distribution of that displacement across frames,
      not just how often it crosses. **Do NOT change the 8.0 value** -- it is a threshold and B10/Q3
      apply. Reporting that a different value would change the outcome is fine and useful; moving it
      is an automatic reject.
  (e) State plainly what this implies for the `median_track_len >= 3.00` bar, as POSITION not as an
      argument. If the honest reading is that broadcast cut frequency alone caps median track length
      below 3, say so and say the bar is unreachable on this footage -- that is CLOSED AT LIMIT and a
      full success. Do NOT propose lowering it.
  (f) Eye check REQUIRED: render 5 frame PAIRS sampled EVENLY across the clip (A3, B7 -- never a head
      slice), each pair being the last frame of one epoch and the first of the next. Say what the eye
      sees at each boundary: a genuine shot cut, the same continuous rally, or something else. A
      boundary the eye calls "same rally, same two players" is a false reset and is the single most
      valuable observation this row can produce.

DO NOT change the adapter, `identity.py`, the camera lock, the 8.0 drift threshold, `min_players`,
the two-slot rule, the coverage bar, `median_track_len`, the coordinate contract, or any verdict. Do
not write a durable tracking table into the shared store; use a scratch game id you name in the memo.

ACCEPTANCE RULE:
  metric        = epoch-end counts and shares by call site over the total; the drift-displacement
                  distribution; consistency against the 293 implied by id numbering
  before        = 293 epochs are implied by the ids and their CAUSE is entirely unattributed
  bar           = NO pass bar. Success is the split measured with its denominator named and the eye
                  check done. "Cuts dominate, the bar is unreachable on broadcast footage" is a FULL
                  SUCCESS and closes the question.
  n             = every epoch end on one full local run (CONSTRUCT, exhaustive); state the count
  eye check     = REQUIRED: 5 evenly-sampled epoch-boundary frame PAIRS, committed, with a verdict on
                  each as genuine cut or false reset
  must not move = the tennis adapter, identity.py, the camera lock, the 8.0 drift threshold,
                  min_players, the two-slot rule, every bar and threshold, the coordinate contract,
                  and every verdict
EVIDENCE: docs/evidence/tracking/g166_epoch_churn_attribution_2026-09-03.md with the split table, the
displacement distribution, the consistency check, the 5 rendered pairs under
docs/evidence/tracking/g166_epochs/, the uncommitted instrumentation diff, and a NOT VERIFIED list.
Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. A daemon and a footage bridge are live there.
COMMIT: explicit pathspec only, in a7, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
