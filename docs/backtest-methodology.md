Status: current as of 2026-04-23.

# Backtest Methodology

This document describes how CourtVision backtests prop models and CLV. It covers the
walk-forward harness, bet labeling, closing-line sourcing, and the distinction between
historical backtest and live paper trading. Every claim cites a source file or a
ROADMAP phase number.

---

## Walk-Forward Harness

**File:** [src/prediction/prop_backtester.py](../src/prediction/prop_backtester.py)

The backtester replays each test-set game using only the features that would have been
known at tip-off. This requires three guarantees:

1. **No future box scores.** The feature store is queried with a `cutoff_timestamp`
   equal to tip-off time. Any box score or stat update from the same game date but
   after tip-off is excluded.

2. **No look-ahead in rolling features.** Rolling windows (e.g., `pts_L10`) are
   computed on a per-game basis sorted by `game_date` ascending. A game at position N
   in a player's game log uses only games 0 through N−1. This is enforced by the
   `add_rolling_features` function in
   [src/features/feature_engineering.py](../src/features/feature_engineering.py).

3. **Season purge.** Any game from the same team within 48 hours of the test game is
   dropped from the training window. This prevents same-series autocorrelation leakage
   (see [docs/quant-methodology.md](quant-methodology.md)).

The harness runs over each game in the test period sequentially, appending predictions
and updating the running P&L and CLV ledger.

---

## CLV Labeling

**What CLV measures.** Closing-line value (CLV) is the difference between the
probability implied by the bet's take price (devigged at placement time) and the
probability implied by Pinnacle's closing line (devigged at game start). Positive CLV
means the book moved toward the bet after placement — the signal that the bet was on
the sharp side of the market.

$$\text{CLV}_i = p_{\text{devig, close}} - p_{\text{devig, open}}$$

For over/under prop bets, "toward the bet" means the line moved in the direction that
benefits the bettor after the bet was placed.

**Why CLV over ROI.** On 312 settled bets, realized ROI has a standard error of
~3–4% — it cannot distinguish a 3.8% edge from noise. CLV against Pinnacle's close
is approximately unbiased because Pinnacle's closing line is the best available
estimate of the game's true probability at tip-off. CLV converges to the edge at
roughly 5× the rate of ROI on typical bet counts.

**Source:** Closing lines are fetched from Pinnacle by `src/data/line_monitor.py`
and recorded with a `recorded_at` timestamp. Only lines recorded within 5 minutes of
tip-off are used for CLV; stale lines (> 5 min pre-tip) are excluded.

---

## Shin Devig on Closing Lines

Both the opening price (at bet placement) and the closing price are Shin-devigged
before CLV is computed. This prevents the CLV estimate from absorbing artifacts when
the vig level changes between open and close.

On illiquid alt-line markets, books sometimes widen the vig closer to game time as
uncertainty increases. Symmetric devig would register this as positive CLV even with
no true edge. Shin devig is less susceptible because it fits the insider-fraction
parameter *z* per market, which partially absorbs the vig-level change.

Implementation: [src/prediction/betting_edge.py](../src/prediction/betting_edge.py).
See [docs/quant-methodology.md](quant-methodology.md) for the mathematical derivation.

---

## What Counts as a Settled Bet

A bet in the ledger is marked `settled=true` when all three conditions hold:

1. **Game completed.** The final box score is available and recorded in the database.

2. **Closing line recorded.** Pinnacle's closing line for this market was fetched
   before tip-off and stored with a valid timestamp. A bet without a recorded closing
   line is excluded from CLV calculations (counted in ROI only, marked `clv=null`).

3. **Player participated.** The player was not a late-reported DNP. A player who is
   listed as Active but does not play due to a late scratch is treated as a DNP if
   he logged 0 minutes. Such bets are voided and removed from both CLV and ROI tallies.

Bets that are settled but flagged `data_quality: degraded` (because a fallback data
source was active, Phase 38) are included in the tally but reported separately.

---

## Paper Trading vs Historical Backtest

| Dimension | Historical backtest | Paper trading (Phase 19) |
|-----------|--------------------|-----------------------------|
| Feature source | Reconstructed from `game_date` cutoff | Live daily stack output |
| Closing line | Post-hoc fetch from historical odds store | Fetched during live daily run |
| Lineup data | Scraped retroactively | Real-time from official injury reports |
| Edge cases | Not modeled (API timeouts, stale lines) | Captured in live run logs |
| Kelly sizing | Computed from historical bankroll | Computed from live bankroll tracker |
| Primary purpose | Validate strategy; tune thresholds | Validate live execution; catch bugs |

The paper-trading gate (Phase 19) requires ≥50 settled paper bets before flipping
`LIVE_BETTING=1`. This is the only gate that validates the full system under realistic
operating conditions — including API latency, partial lineup data, and the timing
decisions that the backtest cannot replicate.

---

## Reproducibility Hashing

Release v0.14.0-80g ships:
- `data/release/v0.14/game_list.json` — ordered list of 80 game IDs used in the holdout
- `data/release/v0.14/seeds.json` — random seeds for Monte Carlo and model training
- `data/release/v0.14/pod_config.json` — RunPod instance spec used for the CV run
- `data/release/v0.14/output_hashes.txt` — SHA256 of every tracking JSON and model file

A reviewer with access to the source video files can run:

```bash
python scripts/reproduce.py --seed 42 --games data/release/v0.14/game_list.json
sha256sum -c data/release/v0.14/output_hashes.txt
```

and reproduce the headline Results table bit-exactly. The SHA256 manifest is the
primary reproducibility artifact; it makes the claims falsifiable without trusting
any intermediate representation.

---

## Full-System Backtester (Phase 18.5)

The historical backtest in `src/prediction/prop_backtester.py` operates at the model
level — it tests whether the model predictions are accurate, not whether the full
daily stack (lineup refresh → bet_selector → portfolio optimizer → simulated fill)
behaves correctly end-to-end.

Phase 18.5 adds a full-system replay engine (`scripts/backtest_system.py`) that
replays the complete daily flow including:

- Simulated slippage and fill-price friction (modeled from historical spread data)
- Book repricing after large bets (adverse market impact)
- Limit simulation (book restricts positions after N consecutive winning bets)
- P&L output metrics: total ROI, CLV beat rate, max drawdown, Sharpe, bet count,
  per-book and per-stat breakdown

This becomes a regression test: run after every model change to catch P&L regressions
before deploy.
