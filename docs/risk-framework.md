Status: current as of 2026-04-23.

# Risk Framework

This document specifies the position sizing constraints, circuit breakers, tail risk
reporting, and factor hedging rules for CourtVision's betting portfolio. All thresholds
cited here are specified in ROADMAP Phase 16 (automation and circuit breakers) and
Phase 37 (tail risk reporting). No live capital is deployed until all Phase 16 circuit
breakers are implemented and the Phase 19 paper-trading gate passes.

---

## Position Sizing Rules

Position sizes are computed by the QP optimizer (Phase 15.7,
`src/prediction/portfolio_optimizer.py`) subject to the constraints below. Until Phase
15.7 is shipped, greedy fractional Kelly in
[src/prediction/betting_portfolio.py](../src/prediction/betting_portfolio.py) applies
the same numeric limits as soft constraints.

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

---

## Circuit Breakers

The circuit breakers below are non-negotiable requirements before `LIVE_BETTING=1`.
They are coded into `scripts/daily_run.sh` (Phase 16) and enforced before any
bet_selector output is executed.

### Bet-level filters

| Trigger | Action |
|---------|--------|
| Ensemble spread > 3 stat units on any prediction | Skip that market for the day |
| `data_quality: degraded` tag (fallback vendor active) | Apply 0.5× Kelly multiplier; log alert |
| Stale-line classifier fires (Phase 14.7) | Reduce to 0.1× Kelly or skip |
| DNP probability > 40% | Remove player from slate before bet_selector runs |

### Intraday circuit breakers

| Trigger | Action | Reset |
|---------|--------|-------|
| Daily loss ≥ 5% of bankroll | Halt all new bets for 24 hours | Midnight reset |
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
| Sharpe ratio (annualized) | Daily P&L mean / std × √252 | Weekly |
| CLV beat rate | % bets with positive CLV vs Pinnacle close | Per settled bet |
| Per-bet risk contribution | Each bet's % contribution to portfolio VaR | Per slate |

### Monthly risk packet

`scripts/gen_risk_packet.py` (Phase 37) auto-generates `vault/risk/YYYY-MM.md`
covering: max drawdown, VaR 95%, worst single day, annualized Sharpe, CLV beat rate
by market, and stress test results.

### Stress test scenarios

`scripts/stress_test.py` simulates three adverse scenarios:

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

PCA on the 7×7 prop residual covariance matrix identifies latent factors that drive
correlated performance across props. Expected factors include:

| Factor | Interpretation |
|--------|---------------|
| pace_factor | Tempo — high-pace games inflate all counting stats |
| defense_factor | Opponent defensive quality — suppresses all offensive props |
| foul_factor | Ref-driven foul rate — affects FT, pts distribution |
| garbage_time_factor | Blowout probability — bench players absorb volume |
| momentum_factor | Hot-hand or cold-streak regime |

### Factor hedging

Each bet in `bets_YYYYMMDD.json` is tagged with `factor_loadings` (a dict of factor
exposures). Portfolio-level factor exposure is the sum of loadings across all bets.

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
| Paper bets settled | ≥ 50 |
| CLV beat rate | ≥ 55% |
| Paper ROI | ≥ 3% |
| Calibration drift (any stat) | < 10% probability error |
| Backtest ROI vs paper ROI | Backtest ≥ 0.7 × paper |
| Circuit breaker events (last 7 days) | 0 |

All six must pass simultaneously. Partial passes do not unlock live capital.
