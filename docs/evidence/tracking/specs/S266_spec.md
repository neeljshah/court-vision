GAP S266 | sport nba (in-game) | worktree a17 | log cx_s266_nba_sim_third_arm_construct
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S247 and S256 both CLOSED AT LIMIT on the same wall: the simulator third arm on all 355 as-of clusters
  (S255, b559352ed) needs ~900 MB, the laptop RAM guard kills it, and contract B5 forbids a pod run before ACCEPT.
  S256 attempt 1d proved the construct path: 30 whole-game clusters via a streaming --game-ids filter at RSS
  490 MB (commit 8a41501d1; prereg 79608edc2). This row is stage 1 of the B5 shape: a sealed construct-scale
  acceptance that lands the module with legacy aliases intact; stage 2 (a successor row) runs the landed module
  on all 355 clusters on the pod. Recover code with `git show 8a41501d1:<path>` for scripts/ and tests/ files.
PREMISE (step 0, INFORMATIONAL): print the S255 cluster_qualification.csv qualifying count (expect 355 of 661);
  print market Brier 0.142876712852 and recal_null 0.144293050901 reproduced from the archive (79,554 ticks).
CHANGE (step 1): additive; the S256 module under scripts/platformkit/ingame/ with EVERY legacy callable, summary
  field, output name and status value (select_sample, price_snapshot_only, evaluate, SCREEN_NULL, ...) restored as
  aliases beside the new names. Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above
  the seal line via git show :<path>, verified with git show HEAD:<path>) fixing: a seeded set of >= 30 and <= 60
  whole-game clusters from the 355 (print seed, clusters, frozen-grid ticks), the three arms, the +0.004 bar, the
  fold scheme with purge + symmetric embargo. Score through the shared evaluator with the callback producing every
  probability; RSS printed before/after; abort with MEMORY LIMIT above 600 MB; never a full-set call; never a pod
  copy (B5); src/ byte-identical asserted; S255 artifacts sha256 before/after; every league-mean fill named.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE for market, recal_null incumbent and simulator on the frozen grid over
                  the sealed clusters; improvement of simulator over recal_null with game-clustered 95 pct CI
  before        = S256 construct measurement (rejected only on denominator and aliases): 30 games / 180 ticks
  bar           = the frozen +0.004 bar on the sealed clusters (SCREEN NULL or BEHIND is the expected valid SUCCESS);
                  printed denominators equal the sealed ones; peak RSS < 600 MB; legacy aliases present (test)
  n             = the sealed >= 30 whole-game clusters; NOT the 355 (that is stage 2)
  eye check     = n/a (S-row); reproduction = verifier recomputes Brier, ECE and the CI from the archived per-game
                  paired-loss series (Q9) and reruns the scorer with the sealed seed
  must not move = every file under src/ byte-identical; recal_null defaults; the S92 archive CSV; the three S255
                  artifacts; backtest_fwer.jsonl untouched, K unread; nothing charged; new dated filenames only
NON-TAUTOLOGY: the sim is reported on every sealed tick including its worst periods; the memo states plainly that
  construct-scale evidence is not the 355-cluster claim and names the stage-2 pod row as the only route to it.
EVIDENCE: docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04.md + summary JSON + paired-loss CSV.
TEST: one per-file test recomputing one game's paired loss from the archived series and asserting the aliases,
  under 200 MB; run only that file.
REPORT: seed/denominators, three-arm table, CI, RSS, alias check, test line, SHA. No push. NEVER PARK.
