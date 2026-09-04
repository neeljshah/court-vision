# S276 attempt 2 preregistration: full-source CPCV STATIC conformal coverage

## Scope and status

This is one additive, uncharged NBA in-game calibration measurement. It names
no comparative promotion, writes neither a ledger nor a register, and uses
calibration language only. It supersedes neither the attempt-1 preregistration
nor its REJECT evidence.

## Inputs and premise

Before sealing, the game_id-only streaming census of
`data/cache/inplay_odds/nba_checkpoints_full.parquet` measured 465249 traded
ticks in 1593 game clusters. The source is a 2829826-byte Parquet tabular
input; pixel resolution is not applicable. The S101 references are
`data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` (30939-byte JSON
tabular summary) and
`data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz` (compressed
CSV tabular input); pixel resolution is not applicable for both.

## Fixed OOS design

- The route creates exactly one evaluator state for every loaded source tick.
  Its stable key is `game_id|source_row|ts`. The state timestamp is its
  game-first-date block timestamp, so CPCV partitions only whole S86
  game-first-date blocks.
- It calls `cpcv_evaluate` with five contiguous S86 date blocks, one test
  block per path, game-disjoint training, and the engine's symmetric one-day
  embargo plus purge. Every date block is a test block exactly once. Purged or
  embargoed states may only leave a path's training set; no source state is
  excluded from its assigned test path.
- The CPCV callback fits the ladder-base incumbent only from the received
  purged training states. The conformal measurement consumes only the emitted
  evaluator predictions and calls the unchanged S101 STATIC `run_fold` and
  `score` callbacks. No residual is fitted against an in-sample model score.
- The route must assert loaded ticks, evaluator records, unique stable keys,
  paired-loss ticks, and paired-loss game clusters all equal 465249 / 1593.
  Every exclusion reason is counted. A residual is reported CLOSED AT LIMIT
  with its exact count and reason; it is never described as every row.
- Preserve S101 values exactly: 0.90 and 0.80 nominal levels,
  `COVERAGE_MIN_GROUP=400`, `COVERAGE_MAX_GROUPS=50`, two-group minimum, and
  S101's 24-cell replay tolerance of 1e-9. Cells below the group requirement
  retain `ABSENT_BECAUSE`.

## Execution and evidence

The compute runs only by `/c/Users/neelj/bin/pod_run a17 --fetch <outputs> --
python -m <entrypoint>` in `/workspace/wt/a17`. The scratch workflow's dd
write probe, unique nohup log, read-only data link, peak RSS, and both-sided
MD5 for every shipped input are required. `/workspace/nba-ai-system` is never
written before acceptance; no process is stopped or restarted; and
backtest_fwer.jsonl, hypotheses*.sqlite, and data/registry are never shipped.
Fetched JSON and paired-loss CSV are locally checked before commit. The new
attempt-2 evidence names its census, exclusions, coverage/width table, S101
line, pod RSS, MD5 parity, and code identities.

SEAL_SHA256: 8217203a503ebcf52c90889d4b97629c964cdae00e932d6a3f9f367ff22de2a2
