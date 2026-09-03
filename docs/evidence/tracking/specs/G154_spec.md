GAP G154 | sport all | worktree a8 | log cx_g154_local_table_census
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7 and Q8; self-check
section B before reporting. This is a MEASUREMENT that must leave a REUSABLE census behind. Move
nothing.

THE PREMISE THIS ROW EXISTS TO NAIL DOWN. The orchestrator measured on 2026-09-03 that 361 tracking
tables survive under local `data/tracking/` and that ZERO reach the jump-gate eligibility definition,
every one being a coordinate-contract rejection or insufficient data. That number is currently a
one-off measurement with no artefact behind it, and the whole rebuild plan rests on it. A number the
program leans on should be reproducible by anyone in one command.

DO THIS:
  (a) Re-measure it yourself, from scratch, using the SAME eligibility definition and the SAME
      first-blocker vocabulary and ordering that G109 and G142 used -- read those before you start so
      the buckets are comparable. Do not invent a new vocabulary; if the existing one does not cover
      a case you hit, add a bucket and say why.
  (b) Report the first-blocker breakdown over ALL local tables: reaches gate / coordinate-contract
      rejection / INSUFFICIENT_DATA / empty or header-only / other, with counts and shares. Name the
      ELIGIBLE denominator explicitly and take every share over it. Never report a bare sample size.
  (c) Break it down by sport as well as pooled. Tennis is the only sport with a reachable coordinate
      contract, so the tennis sub-table is the one that matters for the rebuild; report it separately
      even if it is empty.
  (d) Leave behind ONE small runnable script that reproduces the whole census, so the next session
      re-measures instead of re-deriving. It reads local files only. No pod, no network. Keep it
      small -- a census, not a framework.
  (e) If your count differs from 361, or if any table DOES reach the gate, that is the headline and
      the premise is FALSIFIED. Report it as such (Q8): a falsified premise is a valid result and the
      row closes on it.
  (f) Hand-verify exactly 3 tables against their raw CSV, one from the largest bucket and two chosen
      to be awkward, so the census is not trusting its own parser. Show the arithmetic.

DO NOT change the eligibility definition, the 10-eligible bar, any threshold, the coordinate
contract, or any verdict. Do not re-track anything. Do not repair a malformed table -- classify it.

ACCEPTANCE RULE:
  metric        = local table count; first-blocker counts and shares pooled and per sport; the tennis
                  sub-table
  before        = "361 local tables, 0 eligible" asserted from a single unreproducible measurement
  bar           = NO pass bar. Success is the census reproduced with an artefact and a script behind
                  it. Confirming 0 eligible is a full success; falsifying it is a better one.
  n             = every local table (CONSTRUCT, exhaustive -- state that the enumeration is complete)
  eye check     = REQUIRED: the 3 hand cross-checks in (f), with arithmetic shown
  must not move = the eligibility definition, the 10-eligible bar, every threshold, the coordinate
                  contract, and every verdict
EVIDENCE: docs/evidence/tracking/g154_local_table_census_2026-09-03.md plus the per-table CSV and the
census script under docs/evidence/tracking/g154_census/ (script may live in scripts/platformkit/ if
that is the natural home -- say which and why). Commit BEFORE reporting (A7). NOT VERIFIED list.
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test for the census script. Run ONLY that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
