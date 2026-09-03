GAP G145 | sport all | worktree a11 | log cx_g145_not_verified_sweep
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. A DEBT SWEEP. The precedent is G35, which did this for an earlier batch.
WHY NOW. Roughly forty tracking memos landed on 2026-09-02 (G80 through G143). Every one carries a
NOT VERIFIED section by contract and nobody has swept them. Unswept caveats are how a soft claim
hardens into an assumed fact, and today proved it three times: baseball reachability was corrected
0.8 -> 1.3 pct, basketball 66.8 -> 46.2 pct, and the thin-bucket characterisation was rewritten.
Every one of those corrections came from a downstream lane that went and checked, not from the memo
that first wrote the caveat.
DO THIS:
  (a) COLLECT every NOT VERIFIED item from memos dated 2026-09-02 under docs/evidence/tracking/.
      Report the count and list which memos you read, so the sweep itself can be checked.
  (b) CLASSIFY each item as CHEAP (minutes of read-only checking), EXPENSIVE (needs a real
      measurement or its own lane), or PERMANENT (cannot be verified at all -- for example the G96
      tennis_10 eye check, whose source is pruned from both pod and local corpus with three
      retrieval paths already failed).
  (c) DO the cheap ones, read-only, and report each result with its evidence. Aim for at least five.
      If a check overturns something, say so plainly and name the memo and the claim.
  (d) LIST the expensive ones in priority order by what they would invalidate if wrong. An unchecked
      caveat under a number steering the programme matters far more than one under a closed row.
  (e) NAME the permanent ones so nobody spends a lane rediscovering that they cannot be done.
DO NOT change any threshold, verdict, coordinate contract or published number. If a check overturns
a claim, REPORT it -- the orchestrator adjudicates and records the correction.
ACCEPTANCE RULE:
  metric        = NOT VERIFIED items found, classified, and the count resolved cheaply
  before        = about 40 memos landed 2026-09-02, none swept
  bar           = NO pass bar. Success is the full inventory with classifications, at least five
                  cheap checks actually performed with evidence, and a priority-ordered expensive
                  list. Finding that everything holds is a full success.
  n             = every 2026-09-02 tracking memo; state how many you read and how many items you found
  eye check     = only where a cheap check needs one; say which
  must not move = every threshold, every verdict, the coordinate contract, every published number
EVIDENCE: docs/evidence/tracking/g145_not_verified_sweep_2026-09-0X.md with the inventory table, the
cheap-check results, the priority list, the permanent list, and its own NOT VERIFIED list. Commit
under docs/evidence/tracking/g145_sweep/ BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a11, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
