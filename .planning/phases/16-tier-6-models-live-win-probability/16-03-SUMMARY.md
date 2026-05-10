---
phase: 16-tier-6-models-live-win-probability
plan: "03"
subsystem: prediction
tags: [prop-pricing, monte-carlo, simulation, normal-approximation, backtesting]

requires:
  - phase: 16-01
    provides: "test stubs for test_prop_pricing.py (test_roi, test_distribution)"
  - phase: 8
    provides: "PossessionSimulator 10K Monte Carlo with player_distributions output"

provides:
  - "PropPricingEngine class with get_distribution(), price_vs_line(), backtest()"
  - "src/prediction/prop_pricing_engine.py — importable, 220 LOC, under 250 limit"

affects:
  - 16-04
  - 16-05
  - api-endpoints-props

tech-stack:
  added: []
  patterns:
    - "Graceful degradation: try PossessionSimulator → fallback to normal approx from predict_props → hardcoded defaults"
    - "Implied prob from American odds: abs(odds) / (abs(odds) + 100)"
    - "Edge threshold 3% for over/under/pass recommendation"

key-files:
  created:
    - src/prediction/prop_pricing_engine.py
  modified:
    - tests/test_prop_pricing.py

key-decisions:
  - "Fallback chain: PossessionSimulator (10K sims) → predict_props normal approx (std=mean*0.25) → hardcoded league-average defaults — ensures get_distribution never raises"
  - "backtest() uses prop_residuals.json residuals with coin-flip + edge-adjusted win_prob; no-data returns roi=0.0 without crash"
  - "Removed @pytest.mark.skip decorators from test_roi and test_distribution (implementation now exists); pytestmark skipif remains as guard for environments where module is absent"

patterns-established:
  - "Simulation-first with normal fallback: try sim → on any exception → fall back to parametric distribution"
  - "American odds implied probability: negative odds formula abs(o)/(abs(o)+100)"

requirements-completed: [16-SC-03, 16-SC-04, 16-D-05]

duration: 20min
completed: 2026-04-24
---

# Phase 16 Plan 03: Prop Pricing Engine Summary

**PropPricingEngine with 10K Monte Carlo distribution, +EV line pricing, and holdout ROI backtest — simulation-first with normal fallback**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-24T13:25:00Z
- **Completed:** 2026-04-24T13:45:00Z
- **Tasks:** 1 (TDD)
- **Files modified:** 2

## Accomplishments

- Built `src/prediction/prop_pricing_engine.py` (220 LOC, under 250 limit) with three public methods
- `get_distribution()` returns 7-key percentile dict (mean, std, p10, p25, p50, p75, p90) and never raises
- `price_vs_line()` computes over_prob, ev_over, ev_under, edge, recommendation (over/under/pass at 3% threshold)
- `backtest()` evaluates holdout ROI from prop_residuals.json; returns `{'roi': 0.0, ...}` safely when file missing
- Both `test_roi` and `test_distribution` PASSED (2/2)

## Task Commits

1. **Task 1: PropPricingEngine — distribution + pricing** - `1a60fcc9` (feat)

## Files Created/Modified

- `src/prediction/prop_pricing_engine.py` — PropPricingEngine class; simulation-based prop pricing engine
- `tests/test_prop_pricing.py` — removed @pytest.mark.skip stubs; both tests now active and passing

## Decisions Made

- Fallback chain: PossessionSimulator (10K sims) → predict_props normal approx (std=mean*0.25) → hardcoded league-average defaults — ensures get_distribution never raises regardless of environment
- backtest() uses residuals from prop_residuals.json with edge-adjusted win probability; no-data safe (returns roi=0.0)
- Removed individual @pytest.mark.skip decorators since implementation now exists; module-level pytestmark skipif guard remains for import-absent environments

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PropPricingEngine importable and tested; ready for Phase 16 plans 04-05 (live win probability, API wiring)
- price_vs_line() provides the +EV edge signal needed by bet_selector integration
- backtest() ROI sign is data-dependent (simulated on residuals); larger holdout will sharpen signal

---
*Phase: 16-tier-6-models-live-win-probability*
*Completed: 2026-04-24*
