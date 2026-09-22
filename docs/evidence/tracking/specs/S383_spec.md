GAP S383 | sport nba (scorer extension) | worktree harness-h43 (master-based) | log cx_s383_period_stratified_cell
# Period-stratified four-arm cell as a NEW module over saved paired rows (no edit to the sealed scorer)

SINGLE PROBLEM: the NBA corpus is 61 percent fourth-quarter ticks, so the landed scorer's tick-weighted and equal-game cells would
be fourth-quarter measurements. The design audit requires a PERIOD-STRATIFIED primary (equal weights over Q1-Q4, tick losses
averaged within game-period then across games, whole-game bootstrap). The sealed MLB scorer must not be edited while its trial
is running or before its verdict is read, so the cell is a separate module that consumes paired_rows.json.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/ingame/baseline_four_arm_period.py` fails. Read on master and quote:
scripts/platformkit/ingame/baseline_four_arm.py (_cell: the comparison dict shape {point, ci95, verdict, leave_one_game_out_range,
largest_absolute_share, concentration_pass}; summarize; the paired row keys incl. phase, warmup, paired_losses),
scripts/platformkit/ingame/gate_a0_ingame_vs_market.py (cluster_bootstrap: default_rng(SEED=13), N_BOOT=2000, integers(0, ng, ng),
percentile 2.5 / 97.5; verdict()), baseline_four_arm_features.py (phase labels Q1..Q4 / OT for nba).

CHANGE (NEW files only):
1. scripts/platformkit/ingame/baseline_four_arm_period.py (<= 300 LOC): `stratified_cells(rows, periods=("Q1","Q2","Q3","Q4"))` over
   SCORED (non-warm-up) paired rows: for each metric (brier, logloss) and arm B / C / D, per game and period compute the mean of
   (loss_arm - loss_A) over that game's ticks in that period; a game contributes to a period only if it has >= 1 tick there; the
   game-level statistic is the equal-weight mean over the periods the game has (state this rule and report per game how many
   periods contributed); the point estimate is the mean over games; the interval is the SAME game-clustered bootstrap (seed 13,
   2,000 draws, integers(0, ng, ng), games in sorted game_id order, percentile 2.5 / 97.5) applied to the game-level statistics
   -- reimplement it locally with numpy, do not import cluster_bootstrap, and add a test proving the local draw stream equals
   numpy.random.default_rng(13).integers(0, ng, ng) repeated 2,000 times; verdict via the inherited rule (upper < 0 AHEAD ->
   printed as SINGLE-WINDOW, lower > 0 BEHIND, else UNDERPOWERED; fewer than 30 games UNDERPOWERED); leave-one-game-out range;
   largest absolute single-game share; concentration_pass. Output shape mirrors _cell's comparison dict plus
   `games_by_period_count` and `periods_per_game` histograms (strict ints). Refuses: a scored row without a phase, a phase outside
   the declared set (OT rows are EXCLUDED from the stratified primary and counted), non-finite losses, duplicate keys.
   CLI: `--paired-rows <json> --out <json> [--periods Q1,Q2,Q3,Q4]`; prints counts and verdict labels ONLY (no point, no
   interval) unless `--show-values` is passed, so the tool can be dry-run on a sealed output without reading it.
2. tests/platformkit/ingame/test_baseline_four_arm_period.py: hand-worked 3-game fixture (one game missing Q3) with the
   expected game-level statistics computed in the docstring; draw-stream equality; OT exclusion counted; a fourth-quarter-heavy
   fixture where the tick-weighted difference has the opposite sign to the stratified one (prove the weighting matters); refusals;
   order independence; the --show-values gate (no value in stdout without it).
3. Memo docs/evidence/harness/S383_period_stratified_cell_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only, construct tests, no real paired rows (the MLB trial output must not be opened), no
network. ACCEPTANCE: per-file test passes; --help works; <= 300 LOC; ASCII; contract Q6 vocabulary (assemble retracted-figure
literals from single digits); the memo ends with a NOT VERIFIED list. The pod is OFF.

AMENDMENT 1 (2026-09-22; binding; astra round 14 row 8 found that the landed module estimates a DIFFERENT quantity from the S382
draft's declared primary). The landed formula averages each game's available periods first, then games. The draft's primary is:
for each scored game g and period p in {Q1, Q2, Q3, Q4}, m[g,p] = mean over the ticks of (g,p) of (loss_candidate - loss_A),
defined only when the game has at least one tick in p; for each period, M[p] = mean over the games with m[g,p] defined; PRIMARY
POINT = (M[Q1] + M[Q2] + M[Q3] + M[Q4]) / 4. Bootstrap: resample whole games (seed 13, 2,000 draws, integers(0, ng, ng) over games
in sorted game_id order), recompute every M[p] over the drawn games (a game drawn k times contributes m[g,p] k times) and the
primary; a draw in which any period has ZERO contributing games is DISCARDED and counted; if more than 20 of the 2,000 draws are
discarded the cell is UNDERPOWERED with reason period_support_insufficient; percentiles 2.5 / 97.5 over the retained draws. Report
per period: M[p], its game count, and the number of scored games missing that period. The previous per-game-first quantity is KEPT
as a labelled SECONDARY block `game_first` (never the primary) so the two formulas can be compared; a fixture where one game lacks
Q3 must give DIFFERENT primary and game_first points, worked by hand in the test docstring. Leave-one-game-out range and the
largest single-game share are recomputed for the new primary. Owned files unchanged (module, test, memo).

