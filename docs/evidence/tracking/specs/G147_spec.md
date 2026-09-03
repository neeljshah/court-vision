GAP G147 | sport tennis | worktree a3 | log cx_g147_coverage_bar_adjudication
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This prepares an ADJUDICATION the orchestrator must make. It gathers the evidence
and states the options; it does NOT move any bar.
THE PROBLEM, and it was surfaced by a Fable review that the orchestrator then verified:
  - Tennis is the only sport clearing the court_feet coordinate contract (G47, 0 of 15 rejections),
    but the pod daemon ledger shows **39 tennis rows and 0 passes**. Not one end-to-end pass.
  - G34 measured tennis rally share at **41.7 pct (125/300, Wilson [0.362, 0.473])**. Non-rally
    frames -- replays, crowd, serve preparation, graphics -- cannot carry court-registered player
    tracks, so rally share caps achievable whole-clip decoded-frame coverage.
  - The harness does NOT use a decoded-frame denominator, which **inflates coverage 2.5x to 4.9x on
    four tennis clips**.
So the coverage gate is being met or missed against a denominator that is not the number of frames
the clip actually offers, and its 0.90 bar sits far above a ceiling of roughly 0.42 that the footage
imposes. Both facts point the same way: **a whole-clip coverage verdict for tennis is not a
meaningful measurement today.**
DO NOT CHANGE THE BAR. Read that twice. A threshold moved to make a blocked result pass is the exact
failure that forced the G88 retraction this morning. This row produces the evidence and the options;
the orchestrator decides.
DELIVER:
  (a) RESTATE the arithmetic precisely from the artefacts, not from this spec: the rally share and
      its interval, the inflation factor per clip, and the current coverage bar. Cite where each
      comes from. If any of it fails to reproduce, that is the finding -- say so and stop.
  (b) COMPUTE, for every gate-eligible tennis table, what its coverage WOULD be under a
      decoded-frame denominator, beside what the harness currently reports. Show both columns. Note
      that the corrected number will be LOWER, so this makes the gate harder, not easier -- state
      that plainly so nobody reads this row as an attempt to manufacture passes.
  (c) LAY OUT THE OPTIONS with their consequences, taking no position on which is right:
        1. Score tennis on RALLY-RANGE scopes rather than whole clips -- what would have to exist
           for that (rally segmentation), and is any of it built?
        2. Adopt a decoded-frame denominator -- which numbers move, and by how much, across every
           sport, not just tennis.
        3. Declare whole-clip tennis coverage CLOSED AT LIMIT, as soccer and football were, and stop
           reporting a verdict that the footage cannot satisfy.
        4. Leave it and accept that tennis will never pass end-to-end.
      For each, name what it would invalidate among already-published numbers.
  (d) STATE which sports besides tennis are exposed to the same denominator inflation, with numbers
      if the artefacts support them and an explicit "not measured" if they do not.
DO NOT change any threshold, any verdict, the coordinate contract, the harness or the rung ladder.
Do not re-score anything into a durable artefact.
ACCEPTANCE RULE:
  metric        = per-table current coverage versus decoded-frame-denominator coverage for
                  gate-eligible tennis tables, plus the reproduced rally share and inflation factors
  before        = 39 tennis daemon rows, 0 passes; coverage measured against a denominator that
                  inflates it 2.5x-4.9x, against a 0.90 bar over a roughly 0.42 footage ceiling
  bar           = NO pass bar and NO bar change. Success is the arithmetic reproduced, both coverage
                  columns computed, four options laid out with consequences, and the cross-sport
                  exposure named. Finding that the arithmetic does NOT reproduce is a full success.
  n             = every gate-eligible tennis table; state the count and your census moment
  eye check     = not required, but if you claim a frame is non-rally, show one.
  must not move = every threshold including the 0.90 coverage bar, every verdict, the harness, the
                  coordinate contract, and the rung ladder
EVIDENCE: docs/evidence/tracking/g147_coverage_bar_adjudication_2026-09-0X.md with the reproduced
arithmetic, the two-column table, the four options with consequences, the cross-sport exposure, and
a NOT VERIFIED list. Commit derived tables under docs/evidence/tracking/g147_coverage/ BEFORE
reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a3, no push. Report the sha.
SHARED MODULE: tracking_harness.py is under the token -- READ it, do not change it.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
