# RECEIPTS.md

Pre-registered, honesty-gated receipts ledger. Every row below is read
verbatim from a machine-readable artifact on disk (path cited per row) --
no number here is hand-typed. This file claims calibration/sharpness only,
never a dollar edge, ROI, or bankroll result; verdicts include losses
(MARKET_SHARPER, UNDERPOWERED) exactly as measured. Immutable git history is
the provenance trail: each dated section below is append-only and keyed to a
content hash of the source artifacts, so re-running the generator never
duplicates a section.

**Navigate:** [Full doc map](docs/INDEX.md) - [Home](README.md) - [Evidence pages](docs/evidence/) - [Glossary](docs/GLOSSARY.md)

<!-- receipts-batch: 6eba592d3a77 -->
## 2026-07-22 -- batch 6eba592d3a77
_generated 2026-07-22T19:46:55Z UTC by scripts/platformkit/receipts/build_receipts.py_

| Sport/Market | Checkpoint | Model | Market | Delta (95% CI) | n | Verdict | Source artifact |
|---|---|---|---|---|---|---|---|
| mlb/total_runs | pregame | 2.9331 (CRPS) | 2.8808 (CRPS) | -0.0523 [-0.1657, 0.0482] | 300 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_mlb.json` |
| mlb | home_margin|end_inning_3 | 2.3943 (CRPS) | 2.8443 (CRPS) | 0.4499 [-0.0206, 1.0687] | 20 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | home_margin|end_inning_5 | 1.6806 (CRPS) | 2.5360 (CRPS) | 0.8555 [0.3259, 1.4888] | 26 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | home_margin|end_inning_6 | 1.4476 (CRPS) | 2.4059 (CRPS) | 0.9583 [0.2409, 1.8046] | 22 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | home_margin|end_inning_7 | 1.3449 (CRPS) | 2.4109 (CRPS) | 1.0660 [0.2656, 1.9602] | 21 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | home_margin|end_inning_8 | 0.4873 (CRPS) | 2.2813 (CRPS) | 1.7940 [0.8721, 3.0590] | 21 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | total_runs|end_inning_3 | 2.5416 (CRPS) | 2.6307 (CRPS) | 0.0891 [-0.3032, 0.5064] | 49 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | total_runs|end_inning_5 | 1.7340 (CRPS) | 1.9944 (CRPS) | 0.2604 [-0.0526, 0.5751] | 54 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | total_runs|end_inning_6 | 1.3103 (CRPS) | 1.9495 (CRPS) | 0.6392 [0.3174, 0.9632] | 54 | MODEL_SHARPER_PROVISIONAL | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | total_runs|end_inning_7 | 1.0273 (CRPS) | 1.7600 (CRPS) | 0.7327 [0.4131, 1.0810] | 55 | MODEL_SHARPER_PROVISIONAL | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| mlb | total_runs|end_inning_8 | 0.5117 (CRPS) | 1.9318 (CRPS) | 1.4201 [0.9659, 1.8977] | 49 | MODEL_SHARPER_PROVISIONAL | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` |
| nba | end_q1 | 0.2006 (Brier) | 0.1922 (Brier) | -0.0084 [-0.0161, -0.0008] | 1592 | MARKET_SHARPER_PROVISIONAL | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` |
| nba | halftime | 0.1677 (Brier) | 0.1638 (Brier) | -0.0040 [-0.0098, 0.0015] | 1593 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` |
| nba | end_q3 | 0.1233 (Brier) | 0.1244 (Brier) | 0.0011 [-0.0028, 0.0052] | 1593 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` |
| nba | q4_under5 | 0.0938 (Brier) | 0.0957 (Brier) | 0.0019 [-0.0010, 0.0048] | 1593 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` |
| soccer_intl/brier | home_win_prob|minute_60 | 0.2961 (Brier) | 0.2030 (Brier) | -0.0931 [-0.1570, -0.0336] | 22 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_soccer.json` |
| soccer_intl/brier | home_win_prob|minute_75 | 0.3719 (Brier) | 0.2645 (Brier) | -0.1075 [-0.1885, -0.0316] | 17 | UNDERPOWERED | `scripts/platformkit/benchmarks/crps_market/last_run_ingame_soccer.json` |
| nba/pregame_winprob | 3-fold walk-forward (mean) | 0.1930 (Brier, std 0.0084) | no market baseline in artifact | n/a | 1473 | NO_MARKET_COMPARISON_IN_ARTIFACT | `results/winprob_walk_forward_results.json` |
