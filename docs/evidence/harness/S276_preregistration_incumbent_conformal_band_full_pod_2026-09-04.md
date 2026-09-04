# S276 preregistration: incumbent conformal band full-source pod scratch

## Scope

This preregistration covers one additive, full-source STATIC grouped conformal
calibration measurement for the S123 NBA `ladder_base` incumbent. It reports
held-out empirical grouped coverage at nominal 0.90 and 0.80 plus mean
interval half-width for each phase and ALL. This is a calibration measurement,
not a superiority claim.

## Binding premise and inputs

Before this preregistration, a game_id-only streaming scan of
`data/cache/inplay_odds/nba_checkpoints_full.parquet` measured 465249 ticks
and 1593 games. The source is a 2829826-byte Parquet tabular input; pixel
resolution is not applicable. The S101 references are
`data/cache/eval_gate/s101_aci_coverage_2026-09-03.json` (30939-byte JSON
tabular summary; pixel resolution not applicable) and
`data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz` (compressed
CSV tabular input; pixel resolution not applicable). The pod stat confirmed
the S101 JSON at 30939 bytes. Its deployed S265 sibling was absent, so no
deployed-tree write is permitted or planned; the scratch ship includes this
worktree's S265 module.

## Fixed protocol

- Add only `scripts/platformkit/eval_gate/s276_incumbent_conformal_band_full.py`.
  It calls `s86.load_ticks(s86.CHECKPOINTS)` with no SEED or tick cap, reuses
  S265's row/fold/archive helpers and its unchanged S101 `run_fold` and
  `score` callbacks, and leaves S265 byte-identical.
- Keep S101 values byte-identical: `COVERAGE_MIN_GROUP=400`,
  `COVERAGE_MAX_GROUPS=50`, a two-group minimum, and nominal levels 0.90 and
  0.80. Every cell below the group requirement retains its count and
  `ABSENT_BECAUSE`; it is never replaced by a pooled metric.
- Use S86/S101's five-fold expanding game-first-date walk-forward route with
  game-disjoint purge plus its symmetric nonzero one-day embargo assertion.
  Calibration is fit only on train folds and applied only to held-out folds.
- Replay all 24 S101 STATIC market/model, nominal, and grouped-cell coverages
  from its retained screen input; require max absolute difference at most
  1e-9 versus the committed S101 JSON.
- Archive per-game paired losses plus each grouped coverage unit, including
  the game cluster and time span, so every reported full-source cell is
  reproducible. The model state is reconstructible from the named source and
  code hashes.

## Execution boundary and reporting

The computation runs only through `~/bin/pod_run a17` in
`/workspace/wt/a17`; its built-in dd write probe, nohup process, unique log,
and read-only `data` link are required. The deployed
`/workspace/nba-ai-system` tree is not written, no process is stopped or
restarted, and none of backtest_fwer.jsonl, hypotheses*.sqlite, or data/registry
is shipped. Returned JSON and CSV are evaluated locally before they are
committed or reported. The result will name the stream and loaded-source
denominators, every cell, absent cells if any, S101 result, peak pod RSS, code
identities, and an explicit full-source versus S265 sample worst-cell and
widest-half-width statement.

This is an uncharged calibration measurement: it makes no ledger or register
write and has no AHEAD verdict.

SEAL_SHA256: 47ba0dfcf075c7800c38485eed71e4eb572046b82ef94bbf19fd0fee23495bf0
