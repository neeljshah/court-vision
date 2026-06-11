# Betting Decision Layer — CourtVision

Engineering documentation for the decision layer: how the system converts model
probabilities into bet-sizing recommendations, tracks closing line value, and
measures against real markets.

> **Disclaimer:** This describes engineering methodology for research purposes.
> Sports betting must comply with laws in your jurisdiction. No real money has
> been placed using this system. No profitable edge is claimed.

---

## What the Market Tells Us

The single most important result from backtesting against real closing lines is
negative: **the market is efficient.** Against DraftKings/FanDuel/MGM closing
lines, the model is roughly **break-even-minus-vig** overall (unfiltered figure
~-2.00% from `gate1_full_analysis.json`).

The one exception is **assists (AST): ~+4–5% ROI**, positive across three
independently-sourced line corpora. Stress-tested and confirmed to be selection
skill (positive in both over/under directions; beats a blind-under baseline by
~12 pp; the flipped anti-model loses cleanly). It is book-robust but
regime-dependent: **the edge breaks in the playoffs.** Conservative estimate is
the right one to quote.

**Why state a negative result prominently?** Because it required building three
independent grading harnesses to confirm, and because finding it is the whole
point. A system that can tell a real edge from a measurement artifact is more
valuable than one that claims profit it cannot substantiate.

### What is NOT claimed

| Retracted claim | Why it fails |
|---|---|
| **+18.38% ROI on 1,535 walk-forward bets** | Market-follow grading artifact. The grader read `devig(over_odds, under_odds)` — the market's own lean — and never read the model. Prices at a flat -110 fiction. Filters tuned in-sample. At real odds: ~-4%. |
| **endQ3 in-play Brier 0.1191** | Two Q4-derived features leaked into the model. Honest leak-free number is ~0.141. |
| **+54% ROI / 78% hit on 55K in-play bets** | Graded against an L5 line proxy, not real closing lines. A model-quality ceiling, not a realized edge. |
| **Real CLV measurement** | First real Pinnacle-close CLV reading is October 2026. None yet exists. |

These retractions are documented at the source-code level in
`docs/JOB_EVIDENCE_PACKET.md`.

---

## The Decision Layer (Engineering)

The decision layer is four components in sequence:

```
Model probability  (calibrated, walk-forward)
       ↓
De-vig             strip the book's overround → fair implied probability
       ↓
Edge / EV          compare model prob to fair book prob
       ↓
Kelly sizing       translate edge into recommended stake
       ↓
CLV tracking       after close: did the line move our way?
```

---

## De-Vig

**Module:** `src/prediction/devig.py`

Converts vigged sportsbook prices to fair implied probabilities. Four methods
are implemented:

| Method | Implementation | Notes |
|---|---|---|
| Proportional | `proportional_devig()` | Simple: divide each prob by the overround. Biased on heavy-favourite markets. |
| Multiplicative | `multiplicative_devig()` | Power-renormalisation via bisection. More balanced. |
| Power | `power_devig()` | n-th root method. Cheap approximation. |
| **Shin (1992)** | `shin_devig()` | **Default.** Insider-trading model via stable bisection solver. Loads the vig asymmetrically onto the longshot, recovering the informed-flow fraction `z`. |

Shin is the theoretically grounded choice: it does not assume vig is split
evenly, so it returns higher probability for the favourite than proportional
on lopsided markets — which is the direction most retail tools get wrong.

```python
from src.prediction.devig import shin_devig, american_to_prob

# -115 / -105 two-sided market
over_prob  = american_to_prob(-115)   # 0.535
under_prob = american_to_prob(-105)   # 0.512

fair_over, fair_under = shin_devig([over_prob, under_prob])
# fair_over ≈ 0.511, fair_under ≈ 0.489
# (vig removed asymmetrically)
```

The `POST /api/devig` endpoint defaults to `shin`.

---

## Kelly Criterion Sizing

**Module:** `src/prediction/betting_portfolio.py` — `kelly_corr()`

Kelly sizing translates an edge into the mathematically optimal bankroll
fraction. The system uses fractional Kelly with hard caps and a drawdown
circuit breaker.

**The formula:**

```
full_kelly = edge / (decimal_odds - 1)

quarter_kelly = full_kelly × 0.25        # KELLY_FRACTION = 0.25
capped_kelly  = min(quarter_kelly, 0.04) # MAX_BET_PCT = 4% of bankroll
```

**Correlation penalty** (`kelly_corr`): when multiple props are in flight
simultaneously, a persisted correlation matrix (`data/models/prop_corr_matrix.json`)
shrinks stakes for positively-correlated bets. A teammate's pts/reb over are
positively correlated; the Kelly fraction for each is reduced so combined
exposure stays rational.

**Drawdown circuit breaker**: betting halts automatically when drawdown exceeds
`MAX_DRAWDOWN_PCT = 15%` of starting bankroll.

**Portfolio caps**: `MAX_OPEN_BETS = 20` in-flight at once.

Why quarter-Kelly and not full? Full Kelly maximises long-run growth in theory
but produces extreme variance in practice when edge estimates are noisy
(as they always are from a model). Quarter-Kelly captures most of the growth
benefit at a fraction of the variance.

---

## Closing Line Value (CLV)

**Module:** `src/validation/clv_tracker.py`

CLV is the correct yardstick for edge quality, not win rate and not short-term
ROI.

```
CLV = closing_implied_prob - bet_implied_prob

Example:
  Bet placed at: player over at -110  →  implied prob 52.4%
  Closing line:  same market at -130  →  implied prob 56.5%
  CLV = 56.5% - 52.4% = +4.1%  (positive: you beat where the market settled)
```

Why CLV over ROI? The closing line aggregates all available public information.
If you consistently beat it, you had information or a process advantage that the
market did not have at bet time. If you win bets but lose to the close, you got
lucky on short-term variance — the edge is not real.

`clv_tracker.py` exposes `compute_clv()` which handles American, decimal, and
implied-prob input formats, and removes vig via `vig_strip()` before comparing
sides.

**Current status:** the methodology and tooling are built; real forward CLV
against Pinnacle closing lines starts October 2026 (first regular-season closing
lines). The system cannot yet report a real CLV figure, only a methodology.

---

## Prop Correlation Structure

**Module:** `src/prediction/betting_portfolio.py` — `kelly_corr()`

The joint probability structure of multi-leg bets matters because sportsbooks
price parlays assuming independence. The simulation in `src/sim/basketball_sim.py`
samples from a shared scoring-pie model, so teammate correlations emerge from
the mechanics rather than from a hand-tuned matrix. Measured teammate
correlation is approximately −0.10 (realistic negative correlation from competing
for scoring opportunities), versus a prior simulator's +0.65 (wrong direction).

`sgp_from_sim.py` prices same-game parlays off the joint sample with a
`validate_joint_calibration` harness. **No SGP edge is claimed** — the value
is the correct pricing structure, not a known market discrepancy.

---

## Walk-Forward Validation Architecture

The honest market-efficiency result required three independent harnesses:

1. `scripts/run_gate1_full_analysis.py` — main walk-forward gate with per-stat splits
2. `scripts/gate1_filtered_vs_vegas.py` — filtered-subset vs real closing lines
3. `scripts/reconcile_edge_source.py` — root-cause audit of how the grader reads the model

All three agree: the model is approximately break-even-minus-vig overall. The
harnesses are in the public repo; the audit methodology is in
`docs/JOB_EVIDENCE_PACKET.md §3`.

Walk-forward protocol: expanding windows, `max_train_date < min_test_date`
asserted per fold, multi-corpus calibration acceptance gate (must beat raw on
≥2 independent corpora before a calibration ships), isotonic calibration on
win-probability inputs.

---

## Canonical Numbers

| Metric | Value | Source |
|---|---|---|
| Overall ROI vs real closing lines | ~-2% (break-even-minus-vig) | `gate1_full_analysis.json` |
| AST ROI (durable signal, reg season only) | ~+4–5% | Three independent corpora |
| Prop MAE — PTS | ~4.58 | `data/cache/pregame_oof.parquet`, ~51K held-out player-games |
| Prop MAE — REB | ~1.90 | Same |
| Prop MAE — AST | ~1.34 | Same |
| Prop MAE — FG3M | ~0.88 | Same |
| Win-prob walk-forward accuracy | 0.709 | `winprob_walk_forward_results.json` |
| Win-prob walk-forward Brier | 0.193 | Same |
| endQ3 Brier (leak-free) | ~0.141 | After removing two Q4-derived features |
| Real CLV first reading | October 2026 | Not yet available |
| Real money placed | $0 | |

---

## Infrastructure Summary

| Component | Module | Status |
|---|---|---|
| Shin de-vig (4 methods) | `src/prediction/devig.py` | Built, 7 tests pass |
| Kelly sizing (corr-aware, drawdown-gated) | `src/prediction/betting_portfolio.py` | Built |
| CLV math (multi-format) | `src/validation/clv_tracker.py` | Built |
| Walk-forward backtester (assertion-level leak guard) | `src/prediction/walk_forward_backtester.py` | Built |
| Multi-corpus calibration gate | `scripts/validate_calibration_multicorpus.py` | Built |
| Shadow logger (all evaluated bets, pass and block) | `src/prediction/shadow_logger.py` | Built |
| P&L ledger (transactional, file-locked) | `src/betting/pnl_ledger.py` | Built |
| Real forward CLV pipeline | — | October 2026 |

---

See also: [docs/DATA.md](DATA.md) · [docs/DEMO.md](DEMO.md) ·
[PREDICTIONS_QUICKSTART.md](../PREDICTIONS_QUICKSTART.md) ·
[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)
