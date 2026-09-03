GAP G152 | sport tennis | worktree a6 | log cx_g152_court_feet_declaration
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a CODE-READING AND MEASUREMENT row. Move nothing.

WHAT G142 ESTABLISHED, and why it is the whole rebuild recipe. A read-only census of 16 tennis
source-table directories found 8 reaching the jump gate and 8 blocked. The discriminator was NOT
table size: five of the eight blocked tables already carried at least 1,951 frames, and the eligible
group's median distinct-frame count (1,053) was LOWER than the blocked group's (2,428). The
discriminator was the COORDINATE DECLARATION -- all 8 gate-reaching tables declared `court_feet`, and
5 of the 8 blocked ones declared nothing at all.

Those 16 directories are gone: the pod holding them died on 2026-09-03 and the current eligible count
is 0, not 8. So the only question worth asking now is the one that makes a re-track worth running:
**what, exactly, in the code, decides whether a tennis table declares court_feet?**

DO THIS:
  (a) Trace it in the code, not by inference. Start at the tennis adapter and follow the coordinate
      declaration to the point where it is written into the table. Quote the deciding lines with
      file:line. Name every condition on the path -- solver success, keypoint count, frame selection,
      confidence floor, whatever is actually there.
  (b) For each condition, say what makes it FAIL on a real broadcast clip, in one sentence, grounded
      in the code rather than in a guess.
  (c) Run the path on the local reference tennis clip under `data/videos/reference/` and report which
      conditions pass and which fail, frame by frame or in whatever unit the code actually uses.
      State the decoded-frame count of that clip.
  (d) THE CATCH: G34 measured tennis rally share at 41.7 pct (125/300, Wilson [0.362, 0.473]), and
      the classical solver is known to work on SELECTED RALLY-VIEW RANGES rather than whole clips. So
      report the declaration rate BOTH over all decoded frames AND over rally frames only. If the
      declaration only ever succeeds inside rally view, that is the finding and it is a useful one:
      it means a re-track's yield is capped by rally share, not by the solver.
  (e) Say plainly what a re-track would have to do differently, if anything, to produce court_feet-
      declaring tables. If the honest answer is "nothing -- the existing path already declares it
      whenever the geometry is there", say that; it is a full success and it de-risks the re-track.

DO NOT change the adapter, the solver, the harness, the coordinate contract, any threshold, or any
verdict. Do not lower or relax any condition you find. Do not write a durable tracking table.

ACCEPTANCE RULE:
  metric        = the traced condition list with file:line quotes; per-condition pass/fail on the
                  local reference clip; the declaration rate over decoded frames and over rally frames
  before        = the discriminator is known to BE the coordinate declaration; what produces the
                  declaration has never been traced
  bar           = NO pass bar. Success is the trace being complete and grounded in quoted code, plus
                  the two declaration rates. "The path already works and the cap is rally share" is a
                  full success.
  n             = every condition on the declaration path (CONSTRUCT, exhaustive -- state that the
                  enumeration is complete), plus >= 1 local reference clip with its decoded frame count
  eye check     = REQUIRED on 5 frames where the declaration FAILED. Render them and say what is
                  actually missing in each -- a failure the eye cannot explain is a finding too.
  must not move = the tennis adapter, the solver, tracking_harness.py, the coordinate contract, every
                  threshold, and every verdict
EVIDENCE: docs/evidence/tracking/g152_court_feet_declaration_2026-09-03.md with the quoted condition
trace, the per-condition table, the two rates, the 5 rendered frames under
docs/evidence/tracking/g152_declaration/, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- this row is LOCAL ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a6, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
