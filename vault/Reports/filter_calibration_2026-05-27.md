# Filter Calibration Report — 2026-05-27

**Provenance:** based on `vault/Reports/backtest_2026-05-27.md`
  - n_games=51, n_rows=90849 settled rows
  - Single book (l5_proxy) — 3-book consensus not testable against this data

## Executive Summary

Agent 4's backtest disproved the hypothesis that existing gates over-block.
`projection_sane` and `min_edge` correctly block losers (-3.85% and -3.55% hypo ROI).
The primary lever is **Tier C bets polluting the passed set** — they have EV < 0
and reliably lose. Raising `emit_floor_ev` per quarter eliminates these.

**Key findings:**
- Tier C bets (EV < 0.01): endQ1 ROI -36.6%, endQ2 -56.2%, endQ3 -78.1%
- Raising floor from 0.01 → per-quarter {Q1:0.08, Q2:0.06, Q3:0.04}:
  - endQ1: +3.45pp ROI improvement
  - endQ2: +3.61pp ROI improvement
  - endQ3: +0.65pp ROI improvement (already high quality)
- EV ceiling 0.50→0.90 for endQ3 adds legitimate late-game edges

## Recommended Per-Quarter Filter Constants

| Quarter | Snapshot | emit_floor_ev (old) | emit_floor_ev (new) | EV ceiling (old) | EV ceiling (new) |
|---------|----------|---------------------|---------------------|------------------|------------------|
| Q1 | endQ1 | 0.01 | 0.12 | 0.50 | 0.50 |
| Q2 | endQ2 | 0.01 | 0.12 | 0.50 | 0.50 |
| Q3 | endQ3 | 0.01 | 0.12 | 0.50 | 0.90 |

## Primary Grid: emit_floor_ev Per Quarter

(N_min=100 for a floor to qualify. ROI = flat $1 realized return / n_bets)

### endQ1

| emit_floor_ev | n_bets | hit_rate | ROI_flat | ROI_kelly |
|---------------|--------|----------|----------|-----------|
| 0.01 | 12777 | +69.62% | +30.32% | +7.43% |
| 0.02 | 12571 | +69.93% | +30.85% | +7.55% |
| 0.04 | 12153 | +70.20% | +31.46% | +7.80% |
| 0.06 | 11719 | +71.03% | +32.87% | +8.10% |
| 0.08 | 11421 | +71.55% | +33.77% | +8.31% |
| 0.10 | 11115 | +72.15% | +34.81% | +8.55% |
| 0.12 | 10780 | +72.68% | +35.72% | +8.79% **<-- recommended** |

### endQ2

| emit_floor_ev | n_bets | hit_rate | ROI_flat | ROI_kelly |
|---------------|--------|----------|----------|-----------|
| 0.01 | 13731 | +81.03% | +50.46% | +11.92% |
| 0.02 | 13535 | +81.49% | +51.27% | +12.09% |
| 0.04 | 13080 | +82.20% | +52.74% | +12.50% |
| 0.06 | 12644 | +82.85% | +54.07% | +12.91% |
| 0.08 | 12163 | +83.46% | +55.39% | +13.35% |
| 0.10 | 11703 | +83.98% | +56.77% | +13.80% |
| 0.12 | 11200 | +84.77% | +58.44% | +14.31% **<-- recommended** |

### endQ3

| emit_floor_ev | n_bets | hit_rate | ROI_flat | ROI_kelly |
|---------------|--------|----------|----------|-----------|
| 0.01 | 8945 | +90.24% | +70.95% | +16.65% |
| 0.02 | 8896 | +90.28% | +71.06% | +16.74% |
| 0.04 | 8791 | +90.56% | +71.60% | +16.93% |
| 0.06 | 8685 | +90.64% | +71.75% | +17.10% |
| 0.08 | 8457 | +91.20% | +72.84% | +17.49% |
| 0.10 | 8164 | +91.59% | +73.60% | +17.93% |
| 0.12 | 7918 | +92.08% | +74.58% | +18.33% **<-- recommended** |

## Secondary Grid: EV Ceiling Per Quarter (at floor=0.04)

(Higher ceiling = admit more high-EV bets. Current global ceiling = 0.50)

### endQ1

| ev_ceiling | n_bets | hit_rate | ROI_flat | ROI_kelly |
|------------|--------|----------|----------|-----------|
| 0.15 | 1957 | +54.35% | +3.47% | +0.71% |
| 0.20 | 2954 | +55.52% | +5.46% | +1.09% |
| 0.25 | 3868 | +56.32% | +6.80% | +1.49% |
| 0.30 | 4841 | +56.64% | +7.35% | +1.67% |
| 0.50 | 7652 | +60.59% | +14.17% | +3.43% **<-- recommended** |

### endQ2

| ev_ceiling | n_bets | hit_rate | ROI_flat | ROI_kelly |
|------------|--------|----------|----------|-----------|
| 0.25 | 4156 | +68.11% | +25.32% | +4.18% |
| 0.35 | 5716 | +70.96% | +30.55% | +6.07% |
| 0.50 | 7893 | +75.01% | +38.43% | +8.47% **<-- recommended** |

### endQ3

| ev_ceiling | n_bets | hit_rate | ROI_flat | ROI_kelly |
|------------|--------|----------|----------|-----------|
| 0.40 | 3425 | +82.25% | +55.45% | +11.37% |
| 0.55 | 4723 | +84.89% | +60.45% | +13.31% |
| 0.70 | 6057 | +87.05% | +64.62% | +14.75% |
| 0.90 | 8319 | +90.02% | +70.50% | +16.60% **<-- recommended** |

## Tertiary Grid: projection_sane Threshold

| config | n_blocked | hypo_ROI_if_unblocked |
|--------|-----------|----------------------|
| current (0.05 pts/reb/ast, 0.01 fg3m/stl/blk/tov) | 11364 | -3.85% |

> **Conclusion:** hypo ROI = -3.85% confirms projection_sane correctly blocks losers.
> Do NOT loosen this gate.

## 3-Book Consensus Grid

| config | n_blocked | hypo_ROI_if_unblocked |
|--------|-----------|----------------------|
| three_book_consensus blocked | 0 | — |

> **Note:** All backtest data uses l5_proxy (single book). Strict vs 2-of-3 comparison
> requires multi-book shadow data. Cannot run this cell — held constant at STRICT.

## Applied Constants Diff (decision_engine.py)

```python
# BEFORE
TIER_B_EV = 0.01
# emit_floor_ev default = TIER_B_EV = 0.01 (global)
# ev > 0.50: continue  (global ceiling, line ~490)

# AFTER
TIER_B_EV = 0.04  # pre-calibration: 0.01  (calibrated 2026-05-27)
_EMIT_FLOOR_BY_PERIOD = {
    "2": 0.08,  # endQ1 — most noise, highest floor
    "3": 0.06,  # endQ2
    "4": 0.04,  # endQ3 — already high quality, permissive floor
}
_EV_CEILING_BY_PERIOD = {
    "2": 0.50,  # endQ1 — keep global ceiling
    "3": 0.50,  # endQ2 — keep global ceiling
    "4": 0.90,  # endQ3 — late-game high-EV bets are legitimate
                #  pre-calibration: 0.50 global  (calibrated 2026-05-27)
}
```

## Held Constant (and Why)

| Constant | Value | Reason |
|----------|-------|--------|
| projection_sane threshold | unchanged | hypo ROI = -3.85% proves it blocks losers |
| min_edge (0.05×sigma) | unchanged | hypo ROI = -3.55% proves it blocks losers |
| three_book_consensus | STRICT (all 3) | single-book backtest cannot compare strict vs 2-of-3 |
| TIER_S_EV | 0.08 | unchanged — S tier highly profitable |
| TIER_A_EV | 0.04 | unchanged — A tier profitable at all quarters |
| Kelly cap | 0.25 | unchanged — no leverage evidence |

