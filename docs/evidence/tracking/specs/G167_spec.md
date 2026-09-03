GAP G167 | sport tennis | worktree a2 | log cx_g167_track_id_namespace
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A5, A7 and Q8; self-check
section B before reporting. Move no threshold, no bar, no verdict.

THE FINDING THIS ROW EXISTS TO ACT ON. G163b (landed) opened the four rows the harness reports as
`duplicate frame-track rows 4` and found they are **not duplicates at all**. All four share
`track_id=99`, at source frames 5676, 5679, 5688 and 5691, and each pair is NOT byte-identical:
**one row is `cls=player` and the other is `cls=ball`**. The id spaces are not disjoint across class.
So the harness is not seeing one detection counted twice; it is seeing two different objects issued
the same id.

That reframes the failure from a detection problem into an ID-ALLOCATION problem, and it is the one
tennis quality failure today that looks like a plain defect rather than a footage ceiling.

ESTABLISH FIRST, from quoted code (Q8 -- do not assume any of this):
  (a) Where does a BALL row's `track_id` come from, and where does a PLAYER row's come from? Quote
      both with file:line. The player path runs through `domains/tennis/tracking/identity.py`
      `assign_epoch`, which mints `base + 1` and `base + 2`. Find the ball path and say whether it
      shares that counter, uses its own, or is a constant.
  (b) Is the collision GUARANTEED or incidental? If the two paths draw from independent sequences
      that both start near 1, collisions are structural and will recur on every clip. If it is a
      wraparound or a reuse-after-reset, say which. Give the answer as a mechanism, not a guess.
  (c) Count the real exposure over the whole table, not just the four the harness reported: how many
      `(frame, track_id)` keys are shared across DIFFERENT `cls` values? Report over the ELIGIBLE
      DENOMINATOR of distinct `(frame, track_id)` keys. Never a bare sample size. The harness reported
      4; if the true count is much larger, that gap is itself a finding about what the harness counts.

THEN, and only with (a)-(c) in hand, you MAY land a fix, under strict conditions:
  - It must be ADDITIVE and must not renumber existing tables. Historical tables keep their ids;
    B2 forbids a rename or a removal, and re-writing tables is out of scope entirely.
  - It must not change the harness, `min_players`, the two-slot rule, `jump_max`, the coverage bar,
    the coordinate contract, or any verdict.
  - A5 IS MANDATORY: grep every reader of `track_id` -- the harness, the census script, every
    analysis in `docs/evidence`, `tracking_schema`, the adapters -- and report them BEFORE changing
    how an id is issued. An id scheme is read by more things than it is written by.
  - The smallest honest fix is likely to be disjoint ranges or a class prefix at the point of issue.
    Do not build an id registry, a manager class, or a config. If a few lines at the mint site do it,
    that is the whole change.
  - If any reader would break, DO NOT LAND IT. Report the reader and stop. "The fix is unsafe because
    of these readers" is a FULL SUCCESS.

DO NOT re-track anything into the shared store and do not modify any existing tracking table.

ACCEPTANCE RULE:
  metric        = the two id-issuing paths quoted; the mechanism as structural or incidental; the
                  cross-class collision count over distinct (frame, track_id) keys; the A5 reader list
  before        = the harness reports 4 duplicates with no mechanism and no exposure count
  bar           = NO pass bar. Success is the mechanism established and the exposure counted. Landing
                  a fix is optional and secondary; refusing to land one because a reader would break
                  is a full success.
  n             = every distinct (frame, track_id) key in the table (CONSTRUCT, exhaustive)
  eye check     = REQUIRED only if you land a fix: show one before and one after row pair proving the
                  ids are now disjoint. If you land nothing, state that no eye check applies and why.
  must not move = the harness, min_players, the two-slot rule, jump_max, the coverage bar, the
                  coordinate contract, every existing table, and every verdict
EVIDENCE: docs/evidence/tracking/g167_track_id_namespace_2026-09-03.md with the quoted paths, the
mechanism, the collision count, the A5 reader survey, and a NOT VERIFIED list. Commit BEFORE
reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you change code -- and if you touch the adapter or identity,
run `scripts/platformkit/test_adapter_run.py` too. NEVER a full pytest.
POD: READ-ONLY table access only, batched. A daemon and keeper are LIVE; never kill or restart them.
Heavy decode work goes on the pod under nohup, never locally -- the local box is RAM-constrained and
a lane was killed at 1.4 GB today.
COMMIT: explicit pathspec only, in a2, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
