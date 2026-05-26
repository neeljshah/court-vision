# NBA Execute-Loop Demo (L48)

> **Started:** 2026-05-26T02:26:12.534133+00:00  
> **Finished:** 2026-05-26T02:26:12.537140+00:00  
> **Paper Mode Verified:** YES ✓

## Executive Summary

| Metric | Value |
|--------|-------|
| Bets Placed | 5 |
| DFS Lineups | 3 |
| Total Paper Stake | $500.00 |
| Simulated P&L | $278.35 |
| Simulated ROI | 55.67% |
| Win Rate | 80.0% |
| Avg Edge % | 5.70% |
| Total Kelly Stake | 8.865% of bankroll |
| Avg CLV (pp) | 0.0000 |

---

## Stage 1: Slate Ingest

*Load the NBA prop slate for today. Shows player pool: 10 players across 5 positions with DraftKings salaries.*

**Duration:** 0 ms

### Player Pool Sample

| # | Name | Team | Position | Salary |
|---|------|------|----------|--------|
| 1 | Alex Johnson | FAKEA | PG | $4,446 |
| 2 | Ben Carter | FAKEB | SG | $7,870 |
| 3 | Chris Davis | FAKEA | SF | $7,273 |
| 4 | Devon Evans | FAKEB | PF | $6,194 |
| 5 | Eli Foster | FAKEA | C | $6,165 |

---

## Stage 2: FPTS Distribution

*Monte Carlo FPTS distributions per player: mean projection, uncertainty bands (q10–q90), and per-stat breakdown.*

**Duration:** 1 ms

### Top-3 FPTS Projections

| Player | Mean FPTS | q10 | q90 | Bandwidth |
|--------|-----------|-----|-----|-----------|
| Jake Kim | 47.26 | 39.58 | 53.94 | 14.36 |
| Alex Johnson | 47.20 | 37.71 | 57.03 | 19.32 |
| Devon Evans | 33.22 | 21.65 | 42.12 | 20.47 |

**FPTS Mean Distribution (top 3)**
```
    33.2 | ##########           1
    36.7 |                      0
    40.2 |                      0
    43.8 | #################### 2
```

---

## Stage 3: Lineup Optimization

*LP + simulated-annealing lineup optimizer: 1 cash lineup (max-floor) + 2 GPP stacks (max-ceiling with ownership leverage).*

**Duration:** 0 ms

### Cash Optimal

- **Salary used:** $49,335 / $50,000
- **Expected FPTS:** 263.61

  - Jake Kim (C)
  - Alex Johnson (PG)
  - Devon Evans (PF)
  - Chris Davis (SF)
  - Frank Green (PG)
  - Eli Foster (C)
  - Henry Ingram (SF)
  - Ivan Jones (PF)

### GPP Stack A

- **Salary used:** $49,294 / $50,000
- **Expected FPTS:** 232.77

  - Alex Johnson (PG)
  - Devon Evans (PF)
  - Chris Davis (SF)
  - Frank Green (PG)
  - Eli Foster (C)
  - Henry Ingram (SF)
  - Ivan Jones (PF)
  - Gary Harris (SG)

### GPP Stack B

- **Salary used:** $52,718 / $50,000
- **Expected FPTS:** 207.47

  - Devon Evans (PF)
  - Chris Davis (SF)
  - Frank Green (PG)
  - Eli Foster (C)
  - Henry Ingram (SF)
  - Ivan Jones (PF)
  - Ben Carter (SG)
  - Gary Harris (SG)

---

## Stage 4: Cross-Exchange EV Scan

*Compare model-implied probabilities vs. quotes from Kalshi, Polymarket, and SportTrade. Rank opportunities by edge %.*

**Duration:** 0 ms

### Top-3 EV Opportunities

| Player | Stat | Line | Side | Model Prob | Book Prob | Edge % | Exchange |
|--------|------|------|------|-----------|-----------|--------|----------|
| Chris Davis | pts | 14.7 | over | 0.559 | 0.491 | **6.80%** | Kalshi |
| Devon Evans | fg3m | 18.1 | over | 0.601 | 0.538 | **6.27%** | Polymarket |
| Eli Foster | ast | 18.8 | over | 0.541 | 0.488 | **5.39%** | Kalshi |

---

## Stage 5: Kelly Sizing

*Fractional Kelly (1/4 Kelly) stake per opportunity. Returns fraction of bankroll to commit per bet.*

**Duration:** 0 ms

### Kelly Stakes per Opportunity

| Player | Stat | Odds | Kelly Fraction | Stake % |
|--------|------|------|---------------|---------|
| Chris Davis | pts | -130 | 0.00000 | 0.000% |
| Devon Evans | fg3m | -99 | 0.05160 | 5.160% |
| Eli Foster | ast | -117 | 0.00000 | 0.000% |
| Alex Johnson | reb | -87 | 0.03705 | 3.705% |
| Ben Carter | pts | -124 | 0.00000 | 0.000% |

**Stake % Distribution**
```
     0.0 | #################### 3
     1.0 |                      0
     2.1 |                      0
     3.1 | ######               1
     4.1 | ######               1
```

---

## Stage 6: Risk Budget Check

*L34 mean-variance portfolio budgeter: verifies total Kelly stake ≤ 30% open-position cap before submission.*

**Duration:** 1 ms

```json
{"total_kelly_pct": 8.865, "max_allowed_pct": 30.0, "status": "PASS", "within_budget": true, "source": "L34_variance_budgeter"}
```

---

## Stage 7: Paper Submit

*L05 submission engine in paper mode: simulates DFS lineup entry + exchange prop orders. All orders receive OK status.*

**Duration:** 0 ms

- Submitted: **8** items
- All OK: **True**

```
  [OK] dfs_lineup: Cash Optimal
  [OK] dfs_lineup: GPP Stack A
  [OK] dfs_lineup: GPP Stack B
  [OK] exchange_prop: Chris Davis pts
  [OK] exchange_prop: Devon Evans fg3m
  [OK] exchange_prop: Eli Foster ast
  [OK] exchange_prop: Alex Johnson reb
  [OK] exchange_prop: Ben Carter pts
```

---

## Stage 8: Settlement (simulated)

*Fake game outcomes drawn from model probabilities. Computes simulated P&L delta using paper-mode stake of $100/bet.*

**Duration:** 0 ms

```json
{"n_bets": 5, "wins": 4, "losses": 1, "win_rate": 0.8000, "simulated_pnl": $278.35}
```
> Note: paper-mode simulation only — no real money

---

## Stage 9: CLV Report

*L19 nightly CLV report: compares bet prices at placement vs. closing line to measure execution quality independent of outcomes.*

**Duration:** 0 ms

- **Date:** 2026-05-26
- **Avg CLV (pp):** 0.0000
- **Simulated Win Rate:** 80.0%
- **Source:** L19_clv_calculator

---

## Stage 10: Performance Summary

*End-to-end headline numbers: bets placed, total stake, simulated P&L, ROI, win rate, and CLV.*

**Duration:** 0 ms

*See Executive Summary table at top of report.*

---

*Generated by L48 DemoRunner — paper mode only — 2026-05-26T02:26:12.537140+00:00*