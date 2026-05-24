# Predictions Quickstart

Honest production state at master `d87a76b3` (loop 5, cycle 47). All MAEs measured on held-out games (last 20% chronologically). Walk-forward verified per stat. Verify production matches with `python scripts/verify_production_mae.py`.

## Honest baseline

| stat | MAE | recipe |
|---|---|---|
| PTS | 4.62 | sqrt + Huber XGB/LGB blend + 5-seed MLP, NNLS-stacked |
| REB | 1.90 | log1p LGB quantile q50 |
| AST | 1.36 | log1p XGB+LGB + multitask MLP, NNLS-stacked |
| FG3M | 0.89 | log1p XGB quantile q50 |
| STL | 0.72 | log1p XGB quantile q50 |
| BLK | 0.44 | log1p XGB quantile q50 |
| TOV | 0.89 | log1p XGB quantile q50 |

WinProb walk-forward: **0.71 acc / 0.193 Brier**. Single-split: **0.717 / 0.188**.

## What to run

### 1. Predict one player vs one opponent
```bash
python scripts/predict_player.py --name "Nikola Jokic" --opp LAL --home --rest 2
python scripts/predict_player.py --name "Some Bench" --opp LAL --home --require-starter   # skip if rate <40%
python scripts/predict_player.py --name "Nikola Jokic" --opp LAL --home --save             # append to daily ledger
```
- `--name` accepts diacritics insensitively (Jokic → Jokić)
- `--opp` is the OPPONENT team abbreviation
- `--home / --away` is the PLAYER's team's venue
- `--rest` is days rest (default 2)
- `--pid <int>` works if name lookup fails
- `--lookback-games N` (cycle 46) controls the starter-rate window (default 5)
- `--require-starter` (cycle 46) exits 2 when starter_rate < 0.4 — for batch flows
- `--save [PATH]` (cycle 49) appends to `data/predictions/<date>.csv`, same schema as `predict_slate --save`

Output: a "Recent role" line (cycle 46 — full starter / rotation player / out of rotation), then 7 stat predictions + 80% intervals (q10..q90) + L5/L10 baselines + bet recommendation if |edge| > 0.5.

### 2. Predict every player in tonight's slate
```bash
python scripts/predict_slate.py                       # today
python scripts/predict_slate.py --date 2025-04-13     # historical
python scripts/predict_slate.py --top 5               # top 5 per team
python scripts/predict_slate.py --save                # also write data/predictions/<date>.csv
python scripts/predict_slate.py --save tonight.csv    # custom output path
```
~3 min runtime for a 15-game slate (0.6s API sleep between roster calls).

The `--save` flag (cycle 47) writes one row per (player, stat) so a future
backtest can join on (date, player_id, stat) once actuals are available.

### 3. Compare model predictions to sportsbook lines
1. Edit `example_lines.csv` to your tonight's lines:
    ```csv
    player,opp,venue,stat,line,over_odds,under_odds
    Nikola Jokic,LAL,home,pts,28.5,-115,-105
    Nikola Jokic,LAL,home,reb,11.5,-105,-115
    ```
2. Run:
    ```bash
    python scripts/compare_to_lines.py tonight.csv --kelly --bankroll 1000
    ```
Output: ranked by EV, with Kelly fraction + suggested $ stake per bet (using calibrated quantile intervals from `data/models/quantile_calibration.json`).

### 4. Backtest against synthetic sportsbook lines
```bash
python scripts/betting_backtest.py                    # vs L5 line proxy
python scripts/betting_backtest_smart_line.py         # vs L5 × opp_def × home_adj
```
Result on the cycle-30 holdout (~20k games): **+25-32% ROI at +0.5 edge threshold across all 7 stats vs the smart line**. Real sportsbook closing lines are ~30-50% sharper; realistic expected ROI is ~10-20% on selective bets post-vig.

### 5. Normalize sportsbook exports → backtest vs real closing lines
```bash
python scripts/normalize_lines.py raw_dk.csv -o tonight.csv     # DraftKings / PrizePicks adapter
python scripts/backtest_vs_closing_lines.py historical.csv      # honest ROI vs real lines
python scripts/backtest_vs_closing_lines.py h.csv --kelly --bankroll 1000 --threshold-edge 0.5
```
`normalize_lines.py` (cycle 44) auto-detects DraftKings or PrizePicks export
formats and produces the canonical `compare_to_lines.py` schema. The
historical backtest takes `date,player,opp,venue,stat,closing_line,
over_odds,under_odds,actual_value` rows and reports realistic ROI / max DD.

### 6. NBA daily injury report (cycle 43 + 60)
```bash
python scripts/fetch_injury_report.py                 # NBA PDF source (cycle 43)
python scripts/fetch_injury_espn.py                   # ESPN fallback (cycle 60)
```
Both write `data/injuries_<date>.json` (cycle-43 schema). The ESPN fallback
is the more reliable source (no auth, rarely blocked) — live-verified
pulling 125 active injuries in one fetch this session.

Cross-referencing flags (cycle 51 + 53):
- `compare_to_lines.py --injuries` — skip lines for OUT/DOUBTFUL/NOT-WITH-TEAM players
- `predict_player.py --injuries` — exit 2 on OUT, soft-warn on QUESTIONABLE
- `predict_slate.py --injuries` — drop unavailable, tag QUESTIONABLE in output
- `--include-injured` overrides

### 6b. Projected starting lineups (cycle 61-67)
```bash
python scripts/fetch_lineups.py                       # rotowire scrape
```
Writes `data/lineups_<date>.json` — projected starter, position, play_pct,
injury tag, lineup status (Confirmed / Expected / Projected). Wired into
all three CLIs:
- `--lineups` flag prints classification (STARTER / QUESTIONABLE / BENCH / NO-GAME)
- `--require-starter-lineup` (predict_player) — exits 2 for bench/no-game
- `--scale-by-status` (cycle 66+67) — applies factor to predictions:
  starter ×1.00, questionable ×0.75, bench ×0.30, no-game ×0.00

### 6c. Sportsbook lines (cycle 44 + 59)
```bash
python scripts/fetch_dk_props.py                      # DraftKings (default)
python scripts/fetch_dk_props.py --book draftkings --book fanduel
python scripts/normalize_lines.py raw_dk.csv -o tonight.csv  # any export → canonical
```
Writes `data/lines/<date>.csv`. Wraps the existing 3-tier scraper (Odds API → DK direct → manual seed). Set `ODDS_API_KEY` env var for the most reliable path.

### 7. Verify production matches the honest baseline (cycles 48 + 56)
```bash
python scripts/verify_production_mae.py    # prop_pergame 7 stats vs claim
python scripts/verify_winprob.py           # WinProb WF acc/brier vs claim
python scripts/verify_winprob.py --retrain # also fail if results > 30 days old
```
`verify_production_mae.py` loads the same 80/20 chronological holdout
`prop_pergame.train` uses and scores the production model per stat in one
vectorized pass. Respects the cycle-27 `_USE_Q50_STATS` dispatch.

`verify_winprob.py` reads cached `data/models/winprob_walk_forward_results.json`
(written by `scripts/winprob_walk_forward.py`) and compares to the 0.71 acc /
0.193 brier claim. Both scripts exit 0 within tolerance, 1 with drift report
otherwise — safe for CI wiring.

### 8. One-shot daily orchestrator (cycles 54 + 65 + 71)
**Morning (before games)** — runs the full ingest → predict → compare chain:
```bash
python scripts/daily_run.py --auto-lineups --auto-lines --kelly --bankroll 1000
```
Chains: fetch_injury_report → fetch_lineups → fetch_dk_props → predict_slate
--save --injuries --lineups → compare_to_lines --injuries --lineups --kelly.

**Evening (after games complete)** — fetches actuals + settles bets:
```bash
python scripts/daily_run.py --settle --date 2026-05-24
```
Chains: fetch_actuals (NBA box scores) → settle_bets (W/L/P + P&L per bet).

Other flags: `--dry-run` (print plan only), `--skip-injuries`, `--lines /path/`
(explicit file), `--top N` (players/team for slate).

### 9. Ledger + bet log + settlement artifacts (cycles 47-49 + 68-70)
Three rolling per-date CSVs accumulate the betting season:
- `data/predictions/<date>.csv` — every prediction (predict_slate + predict_player both append)
- `data/bets/<date>.csv` — every recommended positive-EV bet (compare_to_lines --bet-log)
- `data/bets/<date>_settled.csv` — settled bets with W/L/P, payout, P&L (settle_bets)

Ops view:
```bash
python scripts/ledger_summary.py                              # last 7 days
python scripts/ledger_summary.py --player "Nikola Jokic"      # one player history
python scripts/ledger_summary.py --stat pts --top 20          # top-20 PTS preds
```

### 10. Backtest infrastructure (cycles 44 + 52 + 70)
```bash
python scripts/backtest_vs_closing_lines.py historical.csv --kelly --bankroll 1000
python scripts/synthetic_backtest_validation.py --threshold-edge 0.5
```
Cycle-52 synthetic validation confirms the math: **+27.42% ROI mean** on the
synthetic L5 line proxy, matching the cycle-30 `+25-32%` claim. Once the
cycle-68/70 bet log + actuals accumulate 30+ days, the backtest produces
the honest closing-line ROI.

## Daily ops workflow (recommended)
```bash
# Morning, ~90 min before tip-off
python scripts/daily_run.py --auto-lineups --auto-lines --kelly --bankroll 1000

# After last game
python scripts/daily_run.py --settle

# Anytime, ops view
python scripts/ledger_summary.py
```
All steps append to the same per-date artifacts, so a future analysis joins
on (date, player, stat) without per-source branching.

## Retraining

Quantile heads (the q50 models that power 5 of 7 stats):
```bash
python -m src.prediction.prop_quantiles
python -m src.prediction.quantile_calibration   # always re-run after quantile retrain
```

Full prop_pergame stack (XGB+LGB+MLP per stat):
```bash
python -c "from src.prediction.prop_pergame import train_pergame_models; train_pergame_models()"
```

WinProb (binary home-win classifier):
```bash
python -c "from src.prediction.win_probability import train; train()"
```

## Architecture notes (cycle 40 production)

- **q50 dispatch** lives in `prop_pergame._USE_Q50_STATS`. Stats in this set route `predict_pergame` through `_load_q50_model` instead of the 3-way blend.
- **`_Q50_LGB_BACKEND_STATS`** controls which q50 stats load the LGB variant (currently REB only — XGB-q50 was 3/4 WF, LGB-q50 4/4).
- **AST + STL** use the cycle-23 multitask MLP — 7-output MLPRegressor trained on all-stat target matrix, with a `_MultitaskMLPProxy` exposing single-stat predictions.
- **Calibration** widens or narrows q10/q90 per stat to hit empirical 80% coverage. Asymmetric scaling for FG3M/STL/BLK/TOV (q10 floored at 0).

## Loop 5 wins summary

Cumulative MAE improvement vs the original LEAKED baseline (pre-cycle-3):

| stat | leaked baseline | cycle 40 | improvement |
|---|---|---|---|
| PTS | 4.6442 | 4.6210 | -0.50% |
| REB | 1.9180 | 1.9023 | -0.82% |
| AST | 1.3735 | 1.3559 | -1.28% |
| FG3M | 0.9205 | 0.8943 | -2.85% |
| STL | 0.7435 | 0.7153 | -3.79% |
| BLK | 0.5241 | 0.4398 | **-16.08%** |
| TOV | 0.9089 | 0.8932 | -1.73% |

WinProb walk-forward: 0.7176 (leaked) → 0.7094 (honest). Single-split: 0.7250 (leaked) → 0.7169 (honest).

The single biggest lesson of the loop: **q50 quantile regression beats squared-error/Huber blends for skewed counts** because sportsbook prop O/U lines score against the median, not the mean. BLK went -16% MAE in a single cycle. Other low-rate stats followed (STL/FG3M/TOV).

## What's NOT yet built (potential future gains)

1. **Live injury feed** — pre-game inactives 90 min before tip. ~-1% MAE across stats, +1 pp WinProb.
2. **Real sportsbook closing lines** — for actual backtesting (currently synthetic). Need scraping or CSV ingest from sportsbook.
3. **CV `defender_distance` at scale** — currently 10 games processed. Process 50+ → unlocks shot-quality features (CLAUDE.md moat).
4. **Lineup projection** — predict who's starting, not assume L5 = starter.
