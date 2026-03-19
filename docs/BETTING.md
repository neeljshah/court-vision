# Betting System — NBA AI System

How the system identifies +EV betting opportunities, sizes positions, and tracks performance.

> **Disclaimer:** This describes technical capabilities for research and analytical purposes. All sports betting must comply with applicable laws and regulations in your jurisdiction.

---

## Overview

The betting system has three components:

1. **Edge Detection** — Compare model probability to book-implied probability
2. **Position Sizing** — Kelly Criterion to determine optimal bet size
3. **CLV Tracking** — Closing line value as the primary ROI metric

```
Model prediction → your_prob (e.g. 58% for Tatum over 26.5 pts)
                     ↓
Book odds        → book_implied_prob (e.g. 52.4% at -110)
                     ↓
Edge             → 58% - 52.4% = +5.6%
                     ↓
EV               → +$0.056 per $1 wagered
                     ↓
Kelly size       → $22 on a $1,000 bankroll (2.2%, capped at 2%)
                     ↓
CLV tracking     → Did the line move our way by closing? (yes = bet had value)
```

---

## Edge Detection

**Module:** `src/analytics/betting_edge.py`

### Core Functions

```python
from src.analytics.betting_edge import calculate_ev, kelly_fraction, find_edges

# Convert American odds to implied probability
# -110 → 52.4% (includes vig)
book_prob = implied_probability(-110)   # 0.524

# Calculate expected value
# your_prob=0.58, odds=-110 (decimal: 1.909)
ev = calculate_ev(your_prob=0.58, american_odds=-110)
# EV = (0.58 × 0.909) - (0.42 × 1.0) = +0.107 per unit

# Kelly fraction
fraction = kelly_fraction(
    edge=0.056,           # your_prob - book_prob
    odds=-110,            # American odds
    bankroll=1000,        # Bankroll in dollars
    fraction=0.25         # Fractional Kelly factor (0.25 = quarter Kelly)
)
# → $14 bet size
```

### Finding Edges

```python
edges = find_edges(props_list, odds_feed)
# Returns list of BettingEdge dataclasses, sorted by EV

# BettingEdge fields:
edge.player       # "Jayson Tatum"
edge.stat         # "pts"
edge.line         # 26.5
edge.direction    # "over"
edge.your_prob    # 0.58
edge.book_prob    # 0.524
edge.edge_pct     # 0.056 (5.6%)
edge.ev           # 0.107
edge.kelly_size   # 14.0 (dollars)
```

---

## Expected Value Calculation

```
EV = (your_prob × net_payout) - (1 - your_prob) × stake

For -110 odds (bet $110 to win $100):
  decimal_odds = 1 + 100/110 = 1.909
  net_payout = 0.909 (per unit staked)

EV = (0.58 × 0.909) - (0.42 × 1.0)
   = 0.527 - 0.420
   = +0.107 per unit staked
```

A positive EV means your model says this bet is profitable over a large sample. It does not mean any individual bet wins.

---

## Kelly Criterion Position Sizing

Kelly tells you the mathematically optimal fraction of your bankroll to bet:

```
kelly_fraction = edge / (decimal_odds - 1)
               = 0.056 / 0.909
               = 6.2% of bankroll

Fractional Kelly (0.25): 6.2% × 0.25 = 1.55%
Hard cap: min(1.55%, 2.0%) = 1.55%

On $1,000 bankroll: $15.50 per bet
```

**Why fractional Kelly?** Full Kelly maximizes long-run growth but produces extreme variance. Fractional Kelly (0.25–0.50) reduces variance significantly while capturing most of the growth benefit.

**Hard cap at 2%:** Never bet more than 2% of bankroll on a single wager, regardless of perceived edge. Protects against model miscalibration.

---

## Closing Line Value (CLV)

CLV is the primary metric for evaluating betting edge quality — more reliable than short-term win rate.

```
CLV = closing_implied_prob - bet_implied_prob

Example:
  Bet placed at: Tatum over 26.5 at -110 (52.4% implied)
  Closing line:  Tatum over 26.5 at -130 (56.5% implied)
  CLV = 56.5% - 52.4% = +4.1%  ← positive, you beat the line
```

**Why CLV matters:** Books set closing lines efficiently — the closing line is the market's best estimate of true probability. If you consistently beat it, you have real edge. If you win bets but consistently lose to the closing line, you're getting lucky and the edge isn't real.

**Current baseline:** 70.7% correct winner prediction, MAE 10.2 pts (using actual game margins as CLV proxy). Phase 3.5 upgrades to real historical closing lines from OddsPortal.

---

## Prop Correlation Adjustment

**Module:** `src/analytics/prop_correlation.py`

When multiple props are included in a parlay, books assume independence. Your model computes true joint probability using historical co-occurrence:

```python
from src.analytics.prop_correlation import get_correlation_penalty

# Example: Tatum pts over AND Brown pts over are positively correlated
# (both thrive in same games)
joint_prob = get_correlation_penalty(
    prop_a=("Tatum", "pts", "over"),
    prop_b=("Brown", "pts", "over"),
    prob_a=0.58,
    prob_b=0.55
)
# → adjusts combined probability from 0.58×0.55=0.319 to actual ~0.31 (slightly positive correlation)
# → or from independence to negative if stats compete
```

**Current coverage:** 508 player correlation pairs, 3,447 lineup pairs
**Source:** 3-season joint gamelog distributions

---

## Sharp Money Detection

**Module:** `src/analytics/betting_edge.py` → `compute_clv()`

When sharp (syndicate) money is detected on the opposing side:
- Model confidence is reduced by 20%
- Trigger: reverse line movement (line moves against public %'s)
- Source: line monitor watching Pinnacle (sharpest book) vs public books

```python
# Currently implemented as heuristic:
if sharp_signal_opposing:
    adjusted_prob = your_prob × 0.80  # 20% confidence reduction
```

Phase 4.5 trains a proper sharp detector classifier on historical line movements.

---

## Specific Edge Markets

Where this system's edge is most reliable:

### 1. Role Player Props

Star player props are heavily analyzed by sharp syndicates — the market is efficient. Role player props (5–15 pts/g) are priced lazily.

Your edge: spatial CV data (contested shot %, defender distance) that books don't use for pricing role players.

### 2. Injury Reaction Window

When a star is announced questionable/out, props for teammates need to adjust:
- Books are slow to adjust replacement player props (15–60 minute lag)
- Your DNP predictor (AUC 0.979) reacts before the market
- Roster opportunity model identifies exactly which players absorb the usage

### 3. Same-Game Parlay Correlation

Books price SGPs assuming player props are independent. They're not:
- When Jokic assists are up, teammate pts are up (positive correlation)
- When a team's pace is high, both teams' players go over (positive correlation)
- When one team's star dominates, the other team's props compress (negative)

Your prop correlation matrix (3,447 pairs) finds the discrepancy between book's independence assumption and true joint probability.

### 4. Back-to-Back Fatigue Props

Books use aggregate B2B discount factors. Your model uses player-specific curves:
- High-mileage guards: large efficiency drop game 2
- Big men with lower cardio demand: minimal B2B effect
- Stars with load management history: very high DNP probability

### 5. Live Props (Phase 11)

Once the simulator runs in real-time, live prop lines can be compared to updated simulation distributions based on what's happened in-game:
- Player at 14 pts in Q3, line 24.5 → simulator says 78% chance of hitting → over edge
- Player fouled out → simulator recalculates all teammate props

---

## Backtest Results (Current)

| Metric | Value | Notes |
|---|---|---|
| Correct winner prediction | 70.7% | 3,685 games, walk-forward |
| MAE (point margin) | 10.2 pts | Using actual margins as CLV proxy |
| Win probability Brier | 0.203 | Phase 4 trained model |
| Props pts MAE | 0.308 | Walk-forward, 3 seasons |

**Limitation:** Current CLV backtest uses actual game margins, not real closing lines. Phase 3.5 replaces with OddsPortal historical closing lines for true CLV measurement.

---

## Betting Infrastructure Roadmap

| Phase | Component | Status |
|---|---|---|
| Current | EV + Kelly calculation | ✅ Built |
| Current | Prop correlation matrix | ✅ Built (3,447 pairs) |
| Current | Sharp money detection (heuristic) | ✅ Built (20% penalty) |
| Current | CLV backtest (margin proxy) | ✅ Built |
| Phase 3.5 | Real historical closing lines (OddsPortal) | 🔲 |
| Phase 4.5 | Sharp money detector (ML classifier) | 🔲 |
| Phase 4.5 | CLV predictor (will line improve?) | 🔲 |
| Phase 4.5 | SGP optimizer (true joint probability) | 🔲 |
| Phase 4.5 | Soft book lag model | 🔲 |
| Phase 11 | The Odds API (20+ books real-time) | 🔲 |
| Phase 11 | Full CLV tracking pipeline | 🔲 |
| Phase 11 | Paper trading mode | 🔲 |
| Phase 11 | Daily edge report automation | 🔲 |

---

## Bankroll Management Principles

1. **Never bet > 2% per wager** — one bad model day shouldn't materially hurt the bankroll
2. **Fractional Kelly only (0.25)** — model edges are estimates, not certainties
3. **Track CLV, not win rate** — 40-bet samples are statistically meaningless; CLV tells you if the process is right
4. **Paper trade first** — validate edge is real before risking capital
5. **Avoid parlays except SGP** — traditional parlays compound book edge; SGPs are where correlation advantage lives
6. **Separate bankrolls by market type** — props, game lines, and SGPs should each have their own tracking
