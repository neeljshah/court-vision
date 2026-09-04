GAP S288 | sport nba (in-game) | worktree aXX | log cx_s288_staleness_gated_blend
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: S277 (market staleness stratification, worktree a15 candidate 0fd33ebe9; read its memo
  docs/evidence/harness/S277_ingame_market_staleness_2026-09-04.md and quote the table): pooled verdict NULL, but the
  stale-minus-fresh interaction of the incumbent's improvement over market is 0.001247896 with game-clustered
  95 pct CI [0.000074233, 0.002549025] -- the incumbent helps more when the venue price has not moved for a while.
  This row turns that lead into a single additive arm: a blend weight w(staleness) that leans on the incumbent
  when the price is stale and on the market when it is fresh, fit walk-forward, scored against recal_null.
PREMISE (step 0, INFORMATIONAL): re-derive S277's staleness definition (seconds since market_prob last moved,
  per game, from data/cache/inplay_odds/nba_checkpoints_full.parquet; print the p50 and p90 cutoffs it used) and
  reproduce the interaction 0.001247896 to <= 1e-9 from S277's archived per-game series; print first 3 game ids.
CHANGE (step 1): additive; one module under scripts/platformkit/ingame/ (<= 300 lines) with an arm
  p_blend = (1 - w(s)) * market_prob + w(s) * p_incumbent, where w(s) is a monotone function of staleness s with
  TWO parameters (floor weight, saturation scale) fit on the TRAIN folds only inside the shared evaluator callback
  (walk_forward / cpcv_evaluate with purge + symmetric embargo; the callback produces every scored probability);
  a planted-future-row test proves s and w use only ticks strictly before the scored tick. Seal a prereg FIRST as
  its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with
  git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Print RSS
  before/after; a scorer above 500 MB runs via ~/bin/pod_run <aN> --fetch <outputs> -- <command>. Never write
  data/ or docs/research/; never rewrite an existing artifact (new dated filenames; legacy fields as aliases).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = tick-weighted Brier and ECE of p_blend vs recal_null on the frozen grid, all ticks AND the S277
                  stale and fresh bins; improvement of p_blend over recal_null with game-clustered 95 pct CI
  before        = S277: pooled improvement NULL; interaction 0.001247896 [0.000074233, 0.002549025]
  bar           = the frozen +0.004 in-game bar on the all-ticks improvement with the CI above 0 on >= 30 game
                  clusters; the fitted (floor, scale) pair per fold archived; SCREEN NULL or BEHIND is the expected
                  valid SUCCESS and is reported as such
  n             = 465,249 ticks / 1,593 games (printed denominators equal the archive; 0 rows dropped, or every
                  dropped row counted by reason)
  eye check     = n/a (S-row); reproduction = verifier recomputes Brier, ECE and the CI from the archived per-game
                  paired-loss series (Q9) and refits w on one fold from the archived train states
  must not move = recal_null defaults; the S277 artifacts; the S92 archive; every existing threshold;
                  backtest_fwer.jsonl untouched, K unread; nothing charged
NON-TAUTOLOGY: report p_blend on every tick including the fresh bin where it should hurt, and the worst periods;
  a fold whose fitted floor weight collapses to 0 or 1 is reported, not smoothed away.
EVIDENCE: docs/evidence/harness/S288_staleness_gated_blend_2026-09-04.md + summary JSON + per-game paired-loss
  CSV + per-fold parameter table (each under 50 MB).
TEST: one per-file test (planted future row; one game's paired loss recomputed from the archived series), under
  200 MB; run only that file.
REPORT: cutoffs, per-fold (floor, scale), all-ticks and per-bin table with CIs, test line, SHA. No push. NEVER PARK.
