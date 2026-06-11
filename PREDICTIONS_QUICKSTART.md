# Predictions Quickstart

How to generate predictions from this codebase.

> **Canonical claim reference:** [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)
> is the truth source for all numbers. This file covers HOW to run the CLIs.
>
> **Betting read (honest):** vs real closing lines the market is efficient —
> break-even-minus-vig overall; AST ~+4–5% ROI is the one durable edge (breaks
> in playoffs). The earlier "+18.38% ROI" was a market-follow grading artifact
> (retracted). Source-of-truth JSON: `data/models/quantile_pergame_metrics.json`.

---

## Honest Baseline (Leak-Free Walk-Forward)

Prop accuracy, ~51K held-out player-games, OOF predictions
(`data/cache/pregame_oof.parquet`):

| Stat | MAE | Model recipe |
|---|---|---|
| PTS | ~4.58 | sqrt + Huber XGB/LGB blend + 5-seed MLP, NNLS-stacked |
| REB | ~1.90 | log1p LGB quantile q50 |
| AST | ~1.34 | log1p XGB+LGB + multitask MLP, NNLS-stacked |
| FG3M | ~0.88 | log1p XGB quantile q50 |
| STL | ~0.72 | log1p XGB quantile q50 |
| BLK | ~0.44 | log1p XGB quantile q50 |
| TOV | ~0.89 | log1p XGB quantile q50 |

Win-probability walk-forward: **0.709 accuracy / 0.193 Brier**.

In-play (end-of-Q3) Brier: **~0.141 leak-free** (the earlier "0.1191" had two
Q4-derived features leaking into the model; retracted).

---

## 1. Predict One Player

```bash
python scripts/predict_player.py --name "Nikola Jokic" --opp LAL --home --rest 2
```

Key flags:

| Flag | Description |
|---|---|
| `--name` | Player name (diacritic-insensitive) |
| `--opp` | Opponent team abbreviation |
| `--home / --away` | Player's team venue |
| `--rest N` | Days rest (default 2) |
| `--pid <int>` | Fallback if name lookup fails |
| `--require-starter` | Exit 2 if starter_rate < 0.4 (for batch flows) |
| `--save [PATH]` | Append to `data/predictions/<date>.csv` |
| `--injuries` | Exit 2 on OUT, soft-warn on QUESTIONABLE |

Output: 7 stat predictions with 80% quantile intervals (q10–q90), L5/L10
baselines, and Kelly-sized estimate if `|edge| > 0.5` vs a supplied line.

---

## 2. Predict Tonight's Full Slate

```bash
python scripts/predict_slate.py                    # today
python scripts/predict_slate.py --date 2025-04-13  # historical date
python scripts/predict_slate.py --top 5            # top 5 players per team
python scripts/predict_slate.py --save             # write data/predictions/<date>.csv
```

Runtime: ~3 min for a 15-game slate (0.6 s API sleep between roster calls).

---

## 3. Compare Predictions to Sportsbook Lines

1. Populate `example_lines.csv`:

```csv
player,opp,venue,stat,line,over_odds,under_odds
Nikola Jokic,LAL,home,pts,28.5,-115,-105
Nikola Jokic,LAL,home,reb,11.5,-105,-115
```

2. Run:

```bash
python scripts/compare_to_lines.py example_lines.csv --kelly --bankroll 1000
```

Output: ranked by estimated EV, with Kelly-sized stake suggestions.

> **Honest framing:** these are estimates. The model is approximately
> break-even-minus-vig against real closing lines overall. AST is the one
> signal with a documented durable edge (~+4–5% ROI, regular season only).

To normalize DraftKings or PrizePicks exports to the canonical schema first:

```bash
python scripts/normalize_lines.py raw_dk.csv -o tonight.csv
python scripts/compare_to_lines.py tonight.csv --kelly --bankroll 1000
```

---

## 4. Fetch Injuries and Projected Lineups

```bash
python scripts/fetch_injury_report.py   # NBA official PDF
python scripts/fetch_injury_espn.py     # ESPN fallback (more reliable)
python scripts/fetch_lineups.py         # RotoWire projected starters
```

Both write `data/injuries_<date>.json`. All three prediction CLIs accept
`--injuries` and `--lineups` flags to incorporate these.

---

## 5. Fetch Live Sportsbook Lines

```bash
python scripts/fetch_dk_props.py                          # DraftKings default
python scripts/fetch_dk_props.py --book draftkings --book fanduel
```

Writes `data/lines/<date>.csv`. Set `ODDS_API_KEY` in `.env` for the
most reliable path (The Odds API → DK direct scraper → manual seed fallback).

---

## 6. Verify Production Matches the Honest Baseline

```bash
python scripts/verify_production_mae.py   # prop MAE for 7 stats vs claim
python scripts/verify_winprob.py          # walk-forward acc / Brier vs claim
python scripts/verify_winprob.py --retrain  # also fail if results > 30 days old
```

Both scripts exit 0 within tolerance, 1 with a drift report. Safe to wire
into CI.

> **Fresh-clone caveat:** `verify_winprob.py` reads a cached walk-forward
> results file (`data/models/winprob_walk_forward_results.json`). Run
> `scripts/winprob_walk_forward.py` first if the file does not exist.

---

## 7. Backtest Against Real Closing Lines

```bash
python scripts/backtest_vs_closing_lines.py historical.csv \
    --kelly --bankroll 1000 --threshold-edge 0.5
```

Input format: `date,player,opp,venue,stat,closing_line,over_odds,under_odds,actual_value`.

The walk-forward result against real DK/FD/MGM closing lines is
approximately break-even-minus-vig overall. The in-sample synthetic-line
backtest (`betting_backtest.py`) shows +25–32% ROI — that is a model-quality
ceiling against a soft proxy, not a realized edge. See
[docs/BETTING.md](docs/BETTING.md).

---

## 8. Daily Orchestrator

```bash
# Morning (runs ingest → predict → compare chain)
python scripts/daily_run.py --auto-lineups --auto-lines --kelly --bankroll 1000

# Evening (fetch actuals + settle)
python scripts/daily_run.py --settle --date 2026-05-24

# Dry run (print plan only)
python scripts/daily_run.py --dry-run
```

---

## 9. Ledger and P&L View

```bash
python scripts/ledger_summary.py                           # last 7 days
python scripts/ledger_summary.py --player "Nikola Jokic"   # one player
python scripts/ledger_summary.py --stat pts --top 20       # top-20 PTS predictions
```

Three rolling per-date CSVs:

| File | Contents |
|---|---|
| `data/predictions/<date>.csv` | Every prediction (predict_slate + predict_player) |
| `data/bets/<date>.csv` | Every positive-EV recommendation (compare_to_lines --bet-log) |
| `data/bets/<date>_settled.csv` | Settled bets with W/L/P, payout, P&L |

---

## 10. Retrain

```bash
# Quantile heads (powers 5 of 7 stats)
python -m src.prediction.prop_quantiles
python -m src.prediction.quantile_calibration   # always re-run after quantile retrain

# Full prop_pergame stack (XGB+LGB+MLP per stat)
python -c "from src.prediction.prop_pergame import train_pergame_models; train_pergame_models()"

# Win-prob (binary home-win classifier)
python -c "from src.prediction.win_probability import train; train()"
```

---

## Architecture Notes

- **q50 dispatch:** `prop_pergame._USE_Q50_STATS` routes five stats through
  `_load_q50_model` instead of the 3-way blend. Quantile regression fits
  the median rather than the mean, which is correct for sportsbook O/U lines.
- **AST + STL:** use the cycle-23 multitask MLP — 7-output MLPRegressor with
  a `_MultitaskMLPProxy` wrapper.
- **Calibration:** `quantile_calibration.py` widens/narrows q10/q90 to hit
  empirical 80% coverage. Asymmetric scaling for FG3M/STL/BLK/TOV (q10 floored
  at 0).
- **Leak guard:** `walk_forward_backtester.py` asserts
  `max_train_date < min_test_date` on every fold. The multi-corpus
  calibration gate (`validate_calibration_multicorpus.py`) requires
  improvement on ≥2 independent OOS corpora before a calibration ships.

---

## What Is Not Yet Built

| Gap | Impact |
|---|---|
| Real-time injury feed (inactives 90 min pre-tip) | ~-1% MAE across stats |
| Real sportsbook closing-line CLV (first reading Oct 2026) | Honest edge measurement |
| CV `defender_distance` at scale (10 games processed, target 50+) | Shot-quality features |
| Lineup projection (who starts, not assume L5 = starter) | Reduces role-assignment noise |

---

See also: [docs/DATA.md](docs/DATA.md) · [docs/BETTING.md](docs/BETTING.md) ·
[docs/DEMO.md](docs/DEMO.md) · [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)
