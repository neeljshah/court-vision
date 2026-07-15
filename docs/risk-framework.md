Status: last reviewed 2026-06-18. Several sections below describe Phase 16, 30, and 37
requirements that are still unimplemented (marked inline) -- read this as the target
design, not a description of what currently runs.

# Risk Framework

This document specifies the position sizing constraints, circuit breakers, tail risk
reporting, and factor hedging rules for CourtVision's betting portfolio. All thresholds
cited here are specified in ROADMAP Phase 16 (automation and circuit breakers) and
Phase 37 (tail risk reporting). No live capital is deployed until all Phase 16 circuit
breakers are implemented and the Phase 19 paper-trading gate passes.

---

## Position Sizing Rules

Position sizes are intended to be computed by a QP optimizer (Phase 15.7,
`src/prediction/portfolio_optimizer.py`) subject to the constraints below. Phase 15.7
is not shipped -- that module does not exist yet -- so greedy fractional Kelly in
[src/prediction/betting_portfolio.py](../src/prediction/betting_portfolio.py) applies
the same numeric limits as soft constraints today.

### Per-bet constraints

| Constraint | Limit | Rationale |
|-----------|-------|-----------|
| Total portfolio exposure per slate | ≤ 20% of bankroll | Prevents over-deployment on any single game day |
| Per-game exposure | ≤ 5% of bankroll | Caps single-game correlation concentration |
| Per-player exposure | ≤ 8% of bankroll | Prevents over-concentration on a star player (pts + reb + ast all from same player) |
| Correlated-cluster cap | ≤ 15% of bankroll | Defined as all bets whose prop residuals have ρ > 0.40 |

### Kelly scaling

Fractional Kelly multiplier *k* varies by market maturity:
- *k* = 0.25 for markets with fewer than 50 calibrated observations
- *k* = 0.50 after 50+ observations with ECE < 0.05 on that market
- *k* = 0.10 when model and Pinnacle disagree on direction (Phase 14.7 triangulation)

When the QP optimizer is active (Phase 15.7), it further scales stakes by:
- 0.25× for edge 4–6%
- 0.50× for edge 6–10%
- Capped at 0.25× for edge > 10% (high-edge bets are likely stale-line traps)

### Drawdown-adaptive scaling

When the portfolio drawdown exceeds 10% of the high-water mark, all stake multipliers
are reduced by 0.5 until the drawdown recovers. This is enforced by the QP optimizer
and the daily orchestrator (Phase 16).

### Kelly math as implemented

The greedy fractional-Kelly path that backs these soft constraints is
`src/prediction/betting_portfolio.py::kelly_corr`. The numeric chain:

```
full_kelly  = (p * b - q) / b          # b = net payout per unit, q = 1 - p
f           = full_kelly * 0.25         # KELLY_FRACTION = quarter-Kelly
f           = f * max(0, 1 - corr_with_open * existing_exposure / bankroll)
f           = min(f, 0.04)              # MAX_BET_PCT cap
stake       = f * bankroll
```

| Constant (`betting_portfolio.py`) | Value | Role |
|---|---|---|
| `KELLY_FRACTION` | 0.25 | quarter-Kelly de-risking of noisy edges |
| `MAX_BET_PCT` | 0.04 | hard per-bet cap (fraction of bankroll) |
| `KELLY_PCT_MAX` | 0.25 | absolute clamp on any reported Kelly fraction |
| `MAX_OPEN_BETS` | 20 | portfolio in-flight cap |
| `MAX_DRAWDOWN_PCT` | 0.15 | `check_drawdown_ok` returns False past this -> stake 0 |

**Win probability source.** When a calibrated `win_prob_override` is supplied
(isotonic-calibrated `P(win)`), Kelly uses it directly; otherwise it falls back to
`implied_prob + edge`, clamped to `[0.05, 0.95]`. **Correlation** is resolved from
the persisted residual matrix `data/models/prop_corr_matrix.json` (residual, not
raw-prediction, correlations -- to avoid the inflated `pts-tov=0.80` artifact).

**Drawdown guard is a real-money behavior gate.** When the caller omits
`bankroll_start`, the drawdown guard is **skipped by default** (byte-identical to
the original behavior). Inferring a start from realized PnL -- which can silently
flip a live stake to 0 -- is opt-in behind `CV_INFER_BANKROLL_START=1`. This
default-off posture is deliberate: a silent stake change is a real-money risk, so
it is never enabled autonomously.

> **Units, not dollars, in the public layer.** The pure decision layer
> (`frontend/exec_decision.py`) and the in-game ranker
> (`src/prediction/decision_engine.py`) size in **unit counts / bankroll
> fractions**, never `$`. The dollar-denominated `kelly_corr` path is for the
> internal paper ledger only; nothing here is a dollar edge or ROI claim.

---

## Circuit Breakers

The circuit breakers below are non-negotiable requirements before `LIVE_BETTING=1`.
They are Phase 16 target requirements; only the `LIVE_BETTING=0` enforcement and
alert logging exist in `scripts/daily_run.sh` today. The bet-level filters and
intraday breakers below (ensemble spread, stale-line classifier, DNP guard,
consecutive-loss multipliers, drawdown halt) are not yet coded and must not be
treated as running before any bet_selector output is executed.

### Bet-level filters

| Trigger | Action |
|---------|--------|
| Ensemble spread > 3 stat units on any prediction | Skip that market for the day |
| `data_quality: degraded` tag (fallback vendor active) | Apply 0.5x Kelly multiplier; log alert |
| Stale-line classifier fires (Phase 14.7) | Reduce to 0.1x Kelly or skip |
| DNP probability > 40% | Remove player from slate before bet_selector runs |

### Intraday circuit breakers

| Trigger | Action | Reset |
|---------|--------|-------|
| Daily loss >= 5% of bankroll | Halt all new bets for 24 hours | Midnight reset |
| Drawdown > 10% below high-water mark | Paper-only mode | 24-hour cooldown + manual review |
| 3 consecutive losses | 50% stake multiplier | Resets after 2 consecutive wins |
| 5 consecutive losses | Paper-only mode | Resets after 3 consecutive wins |
| Model disagreement (ensemble spread > 3 units) | Skip that market | Per-game, not slate-wide |
| Adverse selection ratio > 2.0 (market making) | Pull all quotes immediately | Manual reset |

### Failure alerting

Circuit breaker events are logged to `data/output/alerts/ALERT_{date}.txt` and
`vault/alerts.log`. Phase 35 adds a Telegram push notification on any circuit breaker
activation.

---

## Tail Risk Reporting

### Daily risk metrics (Phase 37)

Computed on the open portfolio at end-of-day and written to
`data/output/risk/risk_YYYYMMDD.json`:

| Metric | Method | Frequency |
|--------|--------|-----------|
| Value at Risk (VaR 95%) | Parametric (normal) + historical simulation | Daily |
| Conditional VaR (CVaR) | Expected value beyond VaR threshold | Daily |
| Expected Shortfall (ES) | Mean loss in worst 5% of scenarios | Daily |
| Max drawdown (rolling 30 days) | HWM − current P&L | Daily |
| Sharpe ratio (annualized) | Daily P&L mean / std x √252 | Weekly |
| CLV beat rate | % bets with positive CLV vs Pinnacle close | Per settled bet |
| Per-bet risk contribution | Each bet's % contribution to portfolio VaR | Per slate |

### Monthly risk packet

`scripts/gen_risk_packet.py` (Phase 37, not yet built) would auto-generate
`vault/risk/YYYY-MM.md` covering: max drawdown, VaR 95%, worst single day, annualized
Sharpe, CLV beat rate by market, and stress test results.

### Stress test scenarios

`scripts/stress_test.py` (Phase 37, not yet built) is specified to simulate three
adverse scenarios:

1. **All-correlated-leg loss day.** Every bet in the slate resolves against position.
   Simulates a "black swan" game day where the model is systematically wrong (e.g.,
   a mass injury event). Measures maximum single-day loss and recovery time.

2. **Book limits 50% of positions.** Half of all planned bets cannot be placed due to
   limit restrictions after a winning streak. Measures liquidity risk and forced
   under-deployment.

3. **Model breakdown.** CLV drops to zero for two consecutive weeks. Simulates a
   regime shift (rule change, market efficiency increase, data vendor degradation)
   that invalidates the edge. Measures maximum sustained drawdown and capital
   preservation under zero-edge conditions.

---

## Factor Exposure and Hedging (Phase 30)

### Factor identification

PCA on the 7x7 prop residual covariance matrix identifies latent factors that drive
correlated performance across props. Expected factors include:

| Factor | Interpretation |
|--------|---------------|
| pace_factor | Tempo -- high-pace games inflate all counting stats |
| defense_factor | Opponent defensive quality -- suppresses all offensive props |
| foul_factor | Ref-driven foul rate -- affects FT, pts distribution |
| garbage_time_factor | Blowout probability -- bench players absorb volume |
| momentum_factor | Hot-hand or cold-streak regime |

### Factor hedging

Phase 30 is not yet built: no `factor_loadings` field exists in the live codebase
today. The design calls for each bet in `bets_YYYYMMDD.json` to be tagged with
`factor_loadings` (a dict of factor exposures), with portfolio-level factor exposure
computed as the sum of loadings across all bets.

When any single factor exposure exceeds a threshold (calibrated per factor from
historical data), the optimizer adds a small opposing bet (typically a game total) to
reduce net exposure. Risk parity reweighting then adjusts all position sizes so each
factor contributes equally to total portfolio variance.

**Target:** 25% portfolio variance reduction vs naive Kelly at same expected return.
Required for external capital allocation (where allocators expect factor-neutral P&L
decomposition).

---

## Live Capital Gate (Phase 19)

The following conditions must all be met before `LIVE_BETTING=1` is set:

| Condition | Threshold |
|-----------|-----------|
| Paper bets settled | >= 50 |
| CLV beat rate | >= 55% |
| Paper ROI | >= 3% |
| Calibration drift (any stat) | < 10% probability error |
| Backtest ROI vs paper ROI | Backtest >= 0.7 x paper |
| Circuit breaker events (last 7 days) | 0 |

All six must pass simultaneously. Partial passes do not unlock live capital.

The gate is **default-deny and human-gated**: `LIVE_BETTING=0` is hard-enforced
in `src/prediction/bet_selector.py` (it exits non-zero otherwise), and flipping
the flag is a human action taken only after all six conditions hold. The
load-bearing condition is **CLV beat rate**, not ROI: CLV (holding a better
number than the close, scored by `src/betting/clv.py`) is the honest edge
yardstick; ROI inflates from small-sample variance and is reported for
diagnostics only. No real money has been placed.

---

See also: [BETTING](BETTING.md) (edge/EV/CLV math, paper loop)  - 
[decisions](decisions.md) (tier floors, no-bet, dual gate)  - 
[EXECUTION_GUIDE](EXECUTION_GUIDE.md) (sized-bet runbook)  - 
[architecture/execution-engine](architecture/execution-engine.md) (venue routing,
account health).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
