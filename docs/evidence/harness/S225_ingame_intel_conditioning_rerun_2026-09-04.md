# S225 in-game intelligence conditioning rerun

Verdict: BEHIND (calibration screen). This is a sealed, uncharged screen. No
feature flag, register, FWER ledger, or deployment path was touched.

## ATTEMPT 2

Preregistration: `docs/evidence/harness/S225_ATTEMPT2_PREREG_2026-09-04.json`

Preregistration SHA-256: `b457d7ac03bfe8745bd52334166d4d159d029f93fed786a85dc5c1a5dab9bb17`

The seal is the SHA-256 of canonical UTF-8 JSON with `seal_sha256` removed,
as stated in the preregistration artifact. The artifact was written and sealed
before this attempt's fresh-process score. Its fixed protocol uses four arms,
the two conditioning families, six CPCV groups with one test group each, the
shared evaluator's one-day symmetric embargo and purge, the unchanged +0.004
bar, and the verdict rule.

| row | hot_night | scheme_fit |
|---|---:|---:|
| BEFORE (archived same-season fit; unchanged) | Brier base 0.1723; Brier prior 0.1689 | delta -0.00027 |
| ATTEMPT 2 after, real arm vs S123 incumbent | +0.000062, CI [-0.000402, 0.000526] | -0.000038, CI [-0.000278, 0.000201] |
| ATTEMPT 2 after, real arm vs market | -0.000468, CI [-0.001225, 0.000289] | -0.000568, CI [-0.001264, 0.000128] |

Positive differential means lower Brier for the arm. Neither real-arm paired
interval is positive, and neither reaches the fixed +0.004 bar. The planted
nulls are reported alongside their real arms on the same rows and folds; none
has a positive incumbent differential, so the preregistered planted-null
REJECT rule does not fire.

## Premise and alignment

The exact bridge has 1,299 games. Its traded-checkpoint intersection has
187,203 ticks across 635 games. The 2024-25 hot-night corpus has 1,225 games;
579 have a checkpoint match and 646 do not. The matched home-outcome base rate
is 0.550950, versus 0.544490 across the full 1,225-game corpus.

The conversion is `period_clock = seconds_remaining - (4 - period) * 720`.
The printed tolerance is 60.0 seconds. For 2024-25, 3,100 of 3,474 rows are
exact and all 3,474 are within tolerance (maximum 51.1 seconds). For 2025-26,
302 of 336 are exact and all 336 are within tolerance (maximum 49.2 seconds).

## Method

`scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate` performs the shared
purge and one-day symmetric embargo. The S225 predictor additionally asserts
that every model-fit game has `game_first_date` strictly before the scored
game's date. The scored game and all later games are excluded from every fit.

The hot-night value is the per-team Laplace-smoothed prior win rate, home minus
away. The scheme-fit value is the sigmoid-scaled per-team mean first-period
signed score differential, home minus away. Both use only earlier game dates.
The planted null deterministically draws only from the same earlier-game
history. The archived `cond_prior` and `cond_val` columns are not read.

All 187,203 ticks are retained for each arm. There are 635 game clusters per
arm, above the 30-cluster requirement. Eight truncation-as-of probes pass per
layer. The shared evaluator has six groups, one test group per path, and a
nonzero one-day embargo.

## Results

`improvement` is reference Brier minus arm Brier. ECE is the shared evaluator
ECE, and n_eff is calculated from the CSV's game-clustered incumbent loss
differential.

| arm | Brier | ECE | improvement vs S123 incumbent (95 percent CI) | improvement vs market (95 percent CI) | n_eff |
|---|---:|---:|---:|---:|---:|
| hot_night planted null | 0.070016 | 0.009501 | -0.000018 [-0.000985, 0.000950] | -0.000547 [-0.001743, 0.000648] | 1636.58 |
| hot_night real | 0.069936 | 0.008171 | +0.000062 [-0.000402, 0.000526] | -0.000468 [-0.001225, 0.000289] | 1677.50 |
| scheme_fit planted null | 0.070076 | 0.008871 | -0.000077 [-0.000492, 0.000338] | -0.000607 [-0.001362, 0.000148] | 1667.67 |
| scheme_fit real | 0.070037 | 0.009071 | -0.000038 [-0.000278, 0.000201] | -0.000568 [-0.001264, 0.000128] | 1654.09 |
| S123 incumbent | 0.069998 | 0.009071 | - | - | - |
| raw market | 0.069468 | 0.010827 | - | - | - |

## Reproduction and artifacts

Run `python -m scripts.platformkit.ingame.s225_intel_conditioning_rerun` in a
fresh process. The generated artifacts all embed the preregistration path and
SHA-256:

- `docs/evidence/harness/S225_ingame_intel_conditioning_rerun_2026-09-04_summary.json`
- `docs/evidence/harness/S225_ingame_intel_conditioning_rerun_2026-09-04_per_game_differentials.csv`
- `docs/evidence/harness/S225_ingame_intel_conditioning_rerun_2026-09-04_state_differentials.csv`

The per-game CSV retains its legacy seven-column, one-row-per-game-and-arm
schema. The state CSV has one row per scored state and arm, with game,
timestamp, outcome, arm/incumbent/market predictions, three losses, both
paired differentials, split and train diagnostics, plus the preregistration
path and SHA-256. Thus Brier, shared-ECE, and n_eff recompute from the state
CSV alone. The independent recomputation matched Brier and ECE within 1e-12
and n_eff within 1e-9.

Opened inputs, all read one store at a time: `data/domains/basketball_nba/espn_nba_game_bridge.parquet`
(46,002 bytes); `data/cache/inplay_odds/nba_checkpoints_full.parquet` (2,829,826
bytes); hot-night rows 2024-25 (77,688 bytes) and 2025-26 (12,262 bytes); and
scheme-fit rows 2024-25 (50,166 bytes) and 2025-26 (10,843 bytes). These are
tabular inputs; resolution is not applicable.

Focused test: `python -m pytest scripts/platformkit/ingame/test_s225_intel_conditioning_rerun.py -q -p no:cacheprovider`

## NOT VERIFIED

The archived 2024-25 `cond_prior` and `cond_val` values remain unverified as
historical same-season-fit artifacts. Attempt 2 does not use those values as
out-of-sample inputs; it does not independently validate their archived source
construction.
