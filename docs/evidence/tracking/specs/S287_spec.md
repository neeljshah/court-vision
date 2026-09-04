GAP S287 | sport nba (in-game) | worktree aXX | log cx_s287_nba_sim_third_arm_full_pod
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: stage 2 of S266 (LANDED afb5a9460: the simulator third arm at construct scale, 30 whole-game clusters,
  simulator BEHIND recal_null by -0.077 with a clustered CI, RSS 490 MB). The 355-cluster run S247/S256 could not
  make locally (~900 MB, RAM guard). User decision 2026-09-04 09:30: heavy compute runs on the pod. This row runs
  the LANDED S266 module on ALL 355 qualifying S255 as-of clusters on the pod via /c/Users/neelj/bin/pod_run and
  publishes the three-arm table on the full frozen grid. Read docs/evidence/harness/S266_*2026-09-04.md for the
  module path, the sealed callable names and the legacy aliases (quote them); do not edit the module.
PREMISE (step 0, INFORMATIONAL): print the S255 cluster_qualification.csv qualifying count (expect 355 of 661);
  print the S266 construct numbers (30 clusters / 180 ticks; sim delta -0.077) from its landed memo; `stat` the
  S92 archive CSV and the two S255 snapshot parquets on the pod (ship them with --ship if absent, one at a time).
CHANGE (step 1): additive only: a <= 120-line pod entrypoint scripts/platformkit/ingame/s287_sim_full_pod.py that
  imports the landed S266 module unchanged and scores all 355 clusters through the same shared-evaluator route
  (purge + symmetric embargo, callback producing every probability). Seal a prereg FIRST as its own commit (LF;
  seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git show HEAD:<path>;
  the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Run ONLY via
  `pod_run <aN> --ship docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04 --fetch <outputs> -- python
  -m scripts.platformkit.ingame.s287_sim_full_pod`; print pod RSS before/after; md5 of every shipped input on both
  sides; never write the deployed pod tree; never copy backtest_fwer.jsonl, hypotheses*.sqlite or data/registry.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE for market, recal_null incumbent and simulator on the frozen grid
                  over all joined clusters; simulator-minus-recal_null with game-clustered 95 pct CI
  before        = S266 construct: 30 clusters / 180 ticks, simulator delta -0.077 (BEHIND); no 355-cluster number
  bar           = the frozen +0.004 bar on the 355-cluster simulator delta (SCREEN NULL or BEHIND is the expected
                  valid SUCCESS); printed denominators equal the S255 qualification count; pod RSS printed;
                  both-sided md5 parity for every shipped input; the construct-scale numbers reproduce when the
                  entrypoint is restricted to the S266 sealed 30 clusters (max abs diff <= 1e-9)
  n             = 355 whole-game clusters (<= 661), frozen-grid tick count printed
  eye check     = n/a (S-row); reproduction = verifier recomputes Brier, ECE and the CI from the fetched per-game
                  paired-loss series (Q9) and re-runs the 30-cluster restriction locally
  must not move = the S266 module bytes (sha256 printed); every file under src/; the S255 artifacts; the S92
                  archive; recal_null defaults; nothing charged; new dated filenames only
NON-TAUTOLOGY: report the simulator on every tick including its worst periods; state plainly whether the
  construct-scale BEHIND persists, shrinks or reverses at full scale, with the CI.
EVIDENCE: docs/evidence/harness/S287_nba_sim_third_arm_full_pod_2026-09-04.md + summary JSON + paired-loss CSV
  (fetched from the pod; each under 50 MB) + the pod log tail.
TEST: one per-file test: the 30-cluster restriction reproduces S266's archived numbers from the fetched series
  (< 200 MB locally); run only that file.
REPORT: denominators, three-arm table, CI, pod RSS, md5 parity, restriction check, test line, SHA. No push. NEVER PARK.
