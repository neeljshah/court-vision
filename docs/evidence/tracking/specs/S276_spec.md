GAP S276 | sport nba (in-game) | worktree a12 | log cx_s276_incumbent_conformal_band_full_pod
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S265 stage 2 (S265 landed ACCEPT 0194a9ab4, SAMPLE-scale only): seed 258104, 79919 ticks / 269 games; all
  12 STATIC grouped cells (P1/P2/P3/P4/OT/ALL x nominal 0.90/0.80) had >= 400 ticks; worst coverage OT 0.833333333
  both nominals; widest mean half-width P2 nominal 0.90 at 0.207218181; S101 24-cell regression matched the
  committed JSON at max_abs_coverage_diff=0.0. Module: scripts/platformkit/eval_gate/
  s265_incumbent_conformal_band_sample.py (238 lines), SEED/LIMIT=258104/80000, COVERAGE_MIN_GROUP=400. S101_JSON=
  data/cache/eval_gate/s101_aci_coverage_2026-09-03.json. S238/S258 CLOSED AT LIMIT on the same wall: the full
  465,249-tick / 1,593-game source (s86.load_ticks(s86.CHECKPOINTS)) needs ~900 MB, over the local 600 MB guard.
PREMISE (step 0, INFORMATIONAL): re-stream ONLY the game_id column of s86.load_ticks(s86.CHECKPOINTS) and print
  n_ticks/n_games (expect 465249/1593); `stat` the landed S265 module and the committed S101_JSON on the pod copy.
CHANGE (step 1): additive only. New sibling scripts/platformkit/eval_gate/s276_incumbent_conformal_band_full.py
  imports S265's run_fold/score callbacks and load_ticks unchanged, adds a full-source entrypoint with no SEED/
  80000-tick cap (LIMIT=None); S265's own SEED/LIMIT/MEMORY_LIMIT constants and sample entrypoint stay byte-
  identical. Same PHASES, COVERAGE_MIN_GROUP/MAX_GROUPS, S86 fold/embargo design, unchanged. Deploy AFTER local
  premise + `stat`: `git -c core.autocrlf=false archive HEAD -- <paths> | ssh -F ~/.ssh/config.pod pod 'cd
  /workspace/nba-ai-system && tar -x --no-same-owner'`, md5 parity checked both sides. dd write-probe FIRST on the
  pod. Never kill or restart any pod process; never copy backtest_fwer.jsonl, hypotheses*.sqlite, or data/
  registry; never `2>/dev/null` on a deploy command; batch ssh calls. Run under nohup/setsid, unique /workspace
  log, poll without blocking; scp the JSON + paired-loss CSV back under docs/evidence/harness/S276_*/ only AFTER
  local ACCEPT of the returned numbers (B5).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = full-source empirical coverage vs nominal (0.90, 0.80) + mean half-width per grouped cell,
                  STATIC arm; S101 24-cell regression vs the committed JSON; full-source denominator both sides
  before        = sample-scale only (79919 ticks / 269 games, S265); no full-source claim exists (S238/S258)
  bar           = printed denominator = 465249 ticks / 1593 games on both the stream census and the scored set;
                  every cell with >= 400 ticks reported (smaller cells ABSENT_BECAUSE); S101 24-cell regression
                  <= 1e-9 vs the committed JSON; peak pod RSS printed (pod run, no forced local abort)
  n             = full source: 1593 games, 465249 ticks (n >= 30 trivially; NOT a sample)
  eye check     = n/a (S-row); reproduction = verifier replays the returned JSON/CSV and re-diffs every cell plus
                  the S101 24-cell match; SHA-256 of the deployed module matches the archived commit
  must not move = COVERAGE_MIN_GROUP/MAX_GROUPS, S86 fold/embargo design, S265's SEED/LIMIT/MEMORY_LIMIT and
                  sample entrypoint byte-identical, the committed S101 JSON, existing artifacts (new dated names)
NON-TAUTOLOGY: all 1,593 games / 465,249 ticks scored, none excluded; the full-source vs sample worst-cell and
  widest-half-width comparison is stated explicitly, not just a repeat of the sample numbers.
EVIDENCE: docs/evidence/harness/S276_incumbent_conformal_band_full_pod_2026-09-04.md + JSON + paired-loss CSV
  (Q9, gzip if needed to stay under 50 MB).
TEST: one per-file test recomputing one cell from the archived full-source paired-loss CSV, run only that file.
REPORT: full-source denominator both sides, cell table (worst coverage, widest half-width), S101 24-cell match
  line, peak pod RSS, pod-rule compliance line, test line, SHA. No push. NEVER PARK.
