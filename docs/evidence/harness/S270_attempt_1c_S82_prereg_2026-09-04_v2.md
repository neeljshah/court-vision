# S270 attempt 1c preregistration v2: S82 enlarged-pool re-screen

Date: 2026-09-04

This is a new sealed preregistration. It supersedes the unscored v1 execution,
which was stopped before emitting any metric artifact because its tick-level
shared-evaluator representation was computationally quadratic.

## Fixed selection and inputs

S82 remains selected from
`docs/evidence/harness/S270_ingame_power_feasibility_2026-09-04_v2.json`:
required_n_eff=762.528967, available=227 game_id clusters, and
shortfall=535.528967. The raw pool is
`data/cache/ingame_grade_joined/mlb`: 227 JSONL files and 35,859,254 bytes.
The feasibility JSON records every member path and byte total.

The frozen route loads the canonical MLB corpus, calls `e4_gd_series`, builds
the causal S82 `tick_index_in_game` feature, and calls the unchanged
`walk_forward_feature` with its settlement purge and one-day embargo. No model
default, feature, partition, or +0.004 Brier-delta bar is changed.

## Fixed shared-evaluator measurement

For each game's timestamp-sorted frozen prediction series, the median tick is
the one canonical game state. Candidate and null states are evaluated by two
callbacks to `scripts.platformkit.eval_gate.walkforward.walk_forward`; its
nonzero one-day symmetric embargo remains active. Every reported Brier loss,
delta, MDE80, and archived paired-loss row comes from those callbacks at this
game-cluster grain. The CSV records game_id, timestamp, loss_null,
loss_candidate, and delta. n_game_clusters must be at least 30.

Report NULL or BEHIND when the fixed bar is not met. No registry, ledger,
flag, deployment, pod, or external action is permitted.

## Code identities

- `scripts/platformkit/s270_ingame_power_feasibility.py` SHA-256 6661a49d571476847b1e8ca2aa07ff9fd9028318f3379f36b62f21c34d51dcf6
- `scripts/platformkit/foundry/ingame_screen.py` SHA-256 35c6cde0e54b457edca55cd4233f737cdafff120b84938ce533c83e06ae07d7b
- `scripts/platformkit/eval_gate/walkforward.py` SHA-256 1058f981a328121802a996e8d46ff9502212a026918c723b7ebe28f49dce0c69
- `scripts/platformkit/eval_gate/stacker.py` SHA-256 add4be80d19f448535a51b2a3036ab9da4703bc212981ca713fc61cbf0643140
- `scripts/platformkit/hedge_trial_arms.py` SHA-256 20cb519e911d19509dc9bc3af1d69a4c75aab9fad1b046dbfeb06381ff2e6683
- `scripts/platformkit/ingame_replay_scoreboard.py` SHA-256 41a0933aefeefa2b21d9f971b5b4ca0c26ff3116a4092c6e62be95273d629f91

SHA256_SEAL: 561246d2d2bd4c6621cbdb96157c36df110a66e74a8295fca3521e357b56c32f
