GAP S287 | sport nba (in-game) | worktree a13 | log cx_s287_nba_sim_third_arm_full_pod
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
RECOVERY: a17 commit afb5a9460; module scripts/platformkit/ingame/s256_nba_sim_engine_v3.py; construct memo
  docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04.md.
PREMISE (step 0, INFORMATIONAL): print the S255 cluster_qualification.csv qualifying count (expect 355 of 661);
  print the S266 construct numbers (30 clusters / 180 ticks; sim delta -0.077) from its landed memo; `stat` the
  S92 archive CSV and the two S255 snapshot parquets on the pod (ship them with --ship if absent, one at a time).
CHANGE (step 1): additive <= 120-line pod entrypoint scripts/platformkit/ingame/s287_sim_full_pod.py importing
  s256_nba_sim_engine_v3 unchanged; generalize selection in the new entrypoint (do not call select_games or
  select_grid, whose landed contract is exactly 30 games); score all 355 clusters through the shared evaluator
  (purge + symmetric embargo, callback producing every probability). Run ONLY via `pod_run <aN> --ship
  docs/evidence/harness/S255_asof_rate_snapshot_producer_2026-09-04 --fetch <outputs> -- python -m
  scripts.platformkit.ingame.s287_sim_full_pod`; never --ship a data/ path (scp single files to
  /workspace/wt/<aN>/inputs/ and pass the path); md5 of every shipped input both sides; never write the deployed
  pod tree; never copy backtest_fwer.jsonl, hypotheses*.sqlite or data/registry.
PREREG: seal a prereg FIRST as its own commit (LF); hash the STAGED bytes above the seal line via git show :<path>.
Verify with git show HEAD:<path>; the seal test normalizes CRLF to LF and hashes the bytes above the seal line.
WHERE: local; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command> under the B5 NOTE.
Never write data/ or docs/research/; never rewrite an existing artifact; use new dated filenames.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = recal_null Brier minus simulator Brier, with a game-clustered 95 pct CI.
  before        = S266 construct: 30 clusters / 180 ticks, simulator delta -0.077 (BEHIND); no 355-cluster number
  bar           = the frozen +0.004 bar on the 355-cluster simulator delta (SCREEN NULL or BEHIND is the expected
                  valid SUCCESS); printed denominators equal the S255 qualification count; pod RSS printed;
                  both-sided md5 parity for every shipped input; the construct-scale numbers reproduce when the
                  entrypoint is restricted to the S266 sealed 30 clusters (max abs diff <= 1e-9)
  sign          = improvement = baseline loss minus candidate loss; positive = candidate better; compared with
                  the frozen +0.004 bar.
  n             = 355 games x 6 frozen targets = 2,130 unique game-target rows.
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
REPORT: denominators, three-arm table, CI, pod RSS, md5 parity, restriction check, test, SHA. No push. NEVER PARK.
