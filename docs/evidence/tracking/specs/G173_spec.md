GAP G173 | sport tennis | worktree a8 | log cx_g173_first_tennis_ledger_row
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A3, A7, Q8); self-check B.
RAILS: read .claude/skills/lane-spawn-rails/SKILL.md and obey its RAILS block.

WHAT THIS UNBLOCKS. G168 adjudicated the 0.90 coverage bar CLOSED AT LIMIT for whole-clip
denominators, but could NOT compute its per-table three-column comparison, because the pod ledger held
12 rows and **zero tennis rows**: no tennis table had a ledger partner carrying `decoded_frames`.
`tennis_smoke` has 1,861 rows and no ledger row because the orchestrator ran it by hand rather than
through the daemon.

The orchestrator has since staged `data/footage_bridge/tennis__tennis_ref01.mp4` on the pod so the
DAEMON will claim it and produce a real tennis ledger row. **Check whether that has happened before
doing anything else** (Q8) -- it may have completed, may still be running, or may have failed.

DO THIS:
  (a) Read the pod ledger in ONE batched ssh. Report the total row count and every tennis row
      verbatim: `game_id`, `rows`, `decoded_frames`, `coverage_pct`, `seconds`, `passed`,
      `failure_heads`, `coordinate_space`, `rung`.
  (b) If a tennis row exists, compute G168's blocked comparison for it, with G164's three quantities
      named separately and never conflated: the harness figure over EMITTED frames, the harness figure
      over DECODED frames, and the ledger's completeness. Show the arithmetic from the raw CSV by hand
      for at least one of them (Q7 reproduction).
  (c) Report the solved-geometry share separately from the coordinate declaration, per G152's rule
      that the `court_feet` stamp is unconditional and is NOT evidence of recovered geometry.
  (d) If NO tennis row exists yet, that is a FULL SUCCESS: report the staging state, whether the file
      is still in `data/footage_bridge`, whether a `.log` sits beside it, whether a job is running,
      and what the daemon log says. Do NOT stage anything, do NOT re-run the daemon, do NOT poll in a
      loop, and do NOT run the adapter by hand to manufacture a row -- a hand-run row is exactly what
      left G168 blocked in the first place.
  (e) State the ELIGIBLE DENOMINATOR for every share. Never a bare sample size.

**DO NOT move the 0.90 bar or propose an alternate, rally-scoped or corrected bar.** G168 left the
question of which denominator the bar should use open FOR THE ORCHESTRATOR; answering it here is an
automatic REJECT. Report the numbers and stop.

ACCEPTANCE RULE:
  metric        = every tennis ledger row verbatim; the three-column comparison with one hand
                  reproduction; the solved-geometry share reported separately from the declaration
  before        = zero tennis ledger rows; G168's per-table comparison uncomputable
  bar           = NO pass bar. "No tennis row yet, here is the staging state" is a full success.
  n             = every tennis ledger row present (CONSTRUCT, exhaustive); state the count
  eye check     = REQUIRED only if a tennis row exists: 5 frames sampled EVENLY from that table
                  (A3, B7 -- never a head slice), committed, with what the eye sees in each
  must not move = the 0.90 bar, every threshold, the harness, the coordinate contract, the
                  eligibility definition, every verdict, and every pod process
EVIDENCE: docs/evidence/tracking/g173_first_tennis_ledger_row_2026-09-03.md with the verbatim rows,
the comparison, the hand arithmetic, any renders under docs/evidence/tracking/g173_tennis/, and a NOT
VERIFIED list. Commit BEFORE reporting (A7).
TEST: one per-file test only if you add code. NEVER a full pytest.
POD: READ-ONLY and BATCHED. NEVER kill, restart or deploy over the daemon or keeper, and never stage.
COMMIT: explicit pathspec only, in a8, no push. Report the sha.
NEVER PARK: do not wait for the daemon; report what is true when you look.
