GAP G148 | sport tennis | worktree a11 | log cx_g148_two_slot_all_or_nothing
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A MEASUREMENT of a verified all-or-nothing rule. Do not change the rule in this row.
THE RULE, verified in the code by the orchestrator, not inferred.
domains/tennis/tracking/adapter.py:195, inside `detect_players`:
    if set(per_half) != {0, 1}:
        return []
The adapter keeps at most one detection per court half and emits BOTH or NEITHER. A frame in which
one player is tracked cleanly and the other is missed, occluded, or out of frame yields **zero
rows** -- the good detection is discarded with the bad one.
WHY IT MATTERS NOW. Tennis is the only sport clearing the court_feet contract, yet the pod ledger
shows **39 tennis rows and 0 passes**. Coverage is the gate under suspicion: G34 measured tennis
rally share at 41.7 pct (125/300, Wilson [0.362, 0.473]), which caps whole-clip coverage, and the
harness inflates coverage 2.5x-4.9x by not using a decoded-frame denominator. G147 is separately
laying out the bar adjudication. This row asks a different and independent question: how much
coverage does the ADAPTER throw away on its own?
MEASURE, DO NOT FIX:
  (a) On at least 3 tennis clips, instrument `detect_players` read-only and count frames by outcome:
      both halves populated (emitted), exactly one half populated (**discarded by the rule**),
      neither populated. Report the three counts and their shares per clip and pooled.
  (b) The one-half count IS the size of the prize. State it plainly as a share of decoded frames and
      as a share of RALLY frames, since non-rally frames could not have produced two players anyway
      and inflating the prize with them would be dishonest.
  (c) THE CATCH, and this row is worthless without it: tracking_harness SPORTS["tennis"] sets
      `min_players: 2`. A frame carrying one player may still fail the harness gate, so emitting
      single-player rows might raise row counts without raising the metric anyone cares about.
      Establish exactly what the harness does with a frame that has one player -- read the code and
      say which metrics count it and which do not. If single-player frames cannot help coverage as
      the harness computes it today, SAY SO, and the honest conclusion is that this rule is not the
      blocker and the row ends there.
  (d) If they could help, estimate the coverage change from your counts, clearly labelled an
      ESTIMATE, and state what would need to change in the harness for it to be real.
  (e) LOOK AT 5 discarded frames. Is the single detection actually a player, or is the rule
      protecting the corpus from junk? A rule that discards one good detection is a loss; a rule
      that discards one hallucination is doing its job. This is the difference between a fix and a
      regression, and only the eye settles it.
DO NOT change adapter.py, the harness, min_players, any threshold, or the coordinate contract. Do
not re-track anything into a durable artefact.
ACCEPTANCE RULE:
  metric        = per-clip and pooled frame counts by outcome (both / one / neither), the one-half
                  share of decoded and of rally frames, and the harness's treatment of a
                  single-player frame
  before        = the rule is known to exist and discard frames; the amount it discards is unmeasured
  bar           = NO pass bar. Success is the three counts measured, the harness treatment
                  established from the code, and the eye check on five discarded frames. "The rule
                  discards little, or discards junk, or cannot help because of min_players" are all
                  full successes and each closes the question.
  n             = >= 3 tennis clips; state decoded frame counts per clip
  eye check     = REQUIRED on 5 discarded one-half frames. Commit them.
  must not move = adapter.py, tracking_harness.py, min_players, every threshold, the coordinate
                  contract, and every verdict
EVIDENCE: docs/evidence/tracking/g148_two_slot_all_or_nothing_2026-09-0X.md with the count table, the
rally-frame normalisation, the harness treatment quoted from code, the five rendered frames, and a
NOT VERIFIED list. Commit under docs/evidence/tracking/g148_two_slot/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything.
COMMIT: explicit pathspec only, in a11, no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token -- READ it, do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
