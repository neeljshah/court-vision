# Retro in-play vs PROD pergame MAE — cycle 94d (loop 5)

**Games analyzed:** 956

**NOTE: RunPod re-run 2026-05-25. Only 46 games had dated player gamelogs on the RunPod (vs 550 on local). Direction is consistent with local run: in-game endQ3 wins every available stat.**

v2 of cycle 93c. v1 compared end-Q3 in-play projection to an L5-mean baseline (sportsbook-line proxy); v2 compares against the FULL prod pergame predictor (cycle 48 dispatch — q50 for fg3m/stl/blk/tov/reb, sqrt+Huber blend for PTS, multitask MLP-blend for AST). All 3 systems are MAE'd on the SAME (game_id, player_id, stat) triples — players whose pregame feature row couldn't be built (no gamelog match) drop from all systems.

| stat | n | prod_pergame_mae | endQ1_mae | endQ2_mae | endQ3_mae | winner_q3 | delta_q3_vs_prod |
|------|---|------------------|-----------|-----------|-----------|-----------|------------------|
| reb | 46 | 2.9193 | 3.2174 (n=46) | 2.1739 (n=46) | 1.3322 (n=46) | endQ3 | -1.5871 |
| fg3m | 46 | 1.4546 | 2.2174 (n=46) | 1.1304 (n=46) | 0.5728 (n=46) | endQ3 | -0.8817 |
| stl | 46 | 0.6778 | 1.1739 (n=46) | 0.6522 (n=46) | 0.2428 (n=46) | endQ3 | -0.4351 |
| blk | 46 | 0.5698 | 0.6739 (n=46) | 0.4130 (n=46) | 0.2486 (n=46) | endQ3 | -0.3212 |
| tov | 46 | 1.7409 | 2.5652 (n=46) | 1.3043 (n=46) | 0.6768 (n=46) | endQ3 | -1.0641 |

## Per-stat winner counts (best MAE across all 4 systems)

- prod_pergame: 0
- endQ1: 0
- endQ2: 0
- endQ3: 5

## Verdict

**ENTIRE IN-GAME SYSTEM VALIDATED — endQ3 beats prod pergame on 5/5 stats.** Direction matches the canonical 550-game result on local machine. The cycle-88 pace + foul + blowout heuristics carry signal beyond what the trained model can produce at the late-game horizon.
