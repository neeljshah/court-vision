# S270 attempt 1c preregistration: S82 enlarged-pool re-screen

Date: 2026-09-04

This preregistration is sealed before the S82 score. Calibration quantities only.

## Selection

The frozen bar is +0.004 Brier delta. The real-store count in
`docs/evidence/harness/S270_ingame_power_feasibility_2026-09-04_v2.json`
selects S82: required_n_eff=762.528967, available=227 game_id clusters,
shortfall=535.528967. It is the unique smallest valid shortfall. S119's same
raw prefix is not eligible because its own route only re-quotes an archived
series and cannot refit predictions.

## Fixed inputs and route

- Raw pool: `data/cache/ingame_grade_joined/mlb`, 227 JSONL files,
  35,859,254 bytes. The feasibility JSON records every exact member path and
  its aggregate byte size; each file is streamed one at a time for counting.
- Frozen S82 feature: `tick_index_in_game`; null and candidate arms are the
  existing `scripts.platformkit.foundry.ingame_screen` implementation.
- The original route loads the canonical MLB corpus, builds causal features,
  calls `e4_gd_series`, then calls `walk_forward_feature` with its existing
  settlement purge and one-day embargo. No default is changed.
- The reported paired Brier quantities are produced only by two callbacks to
  `scripts.platformkit.eval_gate.walkforward.walk_forward`, one for each
  frozen arm. Its nonzero one-day symmetric embargo remains active. Per-game
  paired losses and timestamps are archived in the re-screen CSV.
- Outputs: `S270_attempt_1c_S82_rescreen_2026-09-04.csv` and
  `S270_attempt_1c_S82_rescreen_2026-09-04.json` under
  `docs/evidence/harness/`.

## Fixed result rule

Report n_ticks, n_game_clusters, Brier null, Brier candidate, Brier delta,
and MDE80=2.872 times the game-clustered standard error of paired loss.
The +0.004 bar is not changed. A delta below the bar or an interval spanning
zero is reported as NULL or BEHIND; no deployment, flag change, registry,
ledger, or pod action is permitted.

## Code identities

- `scripts/platformkit/s270_ingame_power_feasibility.py` SHA-256 db51ace829a87cb5ff0d915abf62aac06fef52677c9687c7643143d731111aaf
- `scripts/platformkit/foundry/ingame_screen.py` SHA-256 35c6cde0e54b457edca55cd4233f737cdafff120b84938ce533c83e06ae07d7b
- `scripts/platformkit/eval_gate/walkforward.py` SHA-256 1058f981a328121802a996e8d46ff9502212a026918c723b7ebe28f49dce0c69
- `scripts/platformkit/eval_gate/stacker.py` SHA-256 add4be80d19f448535a51b2a3036ab9da4703bc212981ca713fc61cbf0643140
- `scripts/platformkit/hedge_trial_arms.py` SHA-256 20cb519e911d19509dc9bc3af1d69a4c75aab9fad1b046dbfeb06381ff2e6683
- `scripts/platformkit/ingame_replay_scoreboard.py` SHA-256 41a0933aefeefa2b21d9f971b5b4ca0c26ff3116a4092c6e62be95273d629f91

SHA256_SEAL: e5fe8f9782a8445cc57071647198279f252ce5bc04a6e51f494b3b641ff150fa
