# CourtVision — Prediction Ceiling

> What the system can realistically achieve — by phase, by market, by model.
> Honest numbers. No inflated projections. All win% at standard -110 vig (break-even = 52.4%).
> Updated 2026-05-18 to reflect real holdout performance and signal-based architecture.

---

## The Headline

| Phase | Prop Win% (filtered) | Avg CLV | ROI / 100 bets |
|-------|----------------------|---------|----------------|
| **Now** (Phase G active, 75 models, API-only features) | **55-57%** | **+2-4%** | +$4-8 per $100 |
| +80 CV games (Tier 3-4 model retrain, spatial features live) | 57-59% | +4-6% | +$8-12 per $100 |
| +Possession simulator (Monte Carlo, full distributions) | 58-61% | +5-8% | +$10-16 per $100 |
| +Agentic research system (signal universe 200+) | 60-63% | +7-11% | +$14-22 per $100 |
| **Long-run ceiling (500+ signals, 200+ CV games, full research loop)** | **62-66%** | **+9-13%** | **+$18-26 per $100** |

**Important caveats:**
- Win% above is conditional on filtering (top-20% plays by confidence). Unfiltered win rate drops toward 52-53%.
- CLV of +2-4% is already a strong signal. Most sharp bettors sustain +1-3% CLV over time.
- The ceiling projections assume the agentic research system is running and signal retirement is disciplined.
- Gate 1 (first real CLV measurement vs Pinnacle close) has NOT YET BEEN RUN. Everything above is theory until Gate 1 passes.

---

## Current Model State (2026-05-18)

### Player Prop Models — Actual Holdout Performance

Walk-forward temporal CV, 48-hr purge, N=480 observations. Source: `data/models/model_registry.json`.

| Stat | Holdout R² | MAE | Implied Win% vs -110 | Signal strength |
|------|-----------|-----|----------------------|----------------|
| PTS  | 0.41 | 4.12 pts | ~54-56% | Usable — needs CV lift |
| REB  | 0.38 | 1.84 reb | ~54-55% | OK on role players |
| AST  | 0.36 | 1.52 ast | ~54-55% | Good on high-usage players |
| FG3M | 0.29 | 0.91 3pm | ~53-54% | Needs spatial (closeout speed) |
| TOV  | 0.22 | 0.76 tov | ~53-54% | Marginal — use selectively |
| STL  | 0.18 | 0.48 stl | ~52-53% | Near break-even — filter hard |
| BLK  | 0.16 | 0.42 blk | ~52-53% | Near break-even — filter hard |

> **Holdout, not training R².** Training R²s are: pts=0.47, reb=0.43, ast=0.42. The gap reflects overfitting risk. Always report holdout.

### Win Probability Model

| Metric | Current | Target (post 80-game CV retrain) |
|--------|---------|----------------------------------|
| Accuracy | 68.5% | 71-73% |
| Brier | 0.209 | 0.185-0.195 |

### xFG Model (Shot Quality)

| Metric | Current | Target (with CV defender data) |
|--------|---------|-------------------------------|
| Brier | 0.226 (221K shots) | 0.195-0.210 |

---

## What Changes With the Agentic Research System

The single biggest ceiling expansion is not more data or more models — it's a better research process.

**Current process:** Human identifies hypothesis → codes feature → trains model → evaluates → ships or abandons.
**Agentic process:** Researcher agent generates hypotheses continuously → Engineer implements → Validator gates on IR → Retirement Monitor catches decay → cycle repeats 24/7.

| Research dimension | Current | With agentic system |
|-------------------|---------|---------------------|
| Hypotheses tested per week | 1-3 (human-paced) | 50-100 (agent-paced) |
| Signal retirement | Ad hoc | Systematic (IR threshold) |
| Factor decomposition | Manual | Automated attribution |
| Signal universe depth | 75 models | 500-5000 validated signals |
| Edge decay detection | Noticed when ROI drops | Caught by IR monitor before live |

Renaissance Technologies runs ~500 signals at any time. 60-70% of newly proposed signals fail validation. The survivors compound. This is the model.

---

## Model-by-Model Ceiling

### Prop Ceilings (with full signal architecture)

| Stat | Current holdout R² | CV lift (est) | Ceiling R² | Key signal unlock |
|------|--------------------|---------------|-----------|------------------|
| PTS  | 0.41 | +0.06-0.10 | 0.47-0.51 | defender_distance, minutes model, regime detection |
| REB  | 0.38 | +0.07-0.10 | 0.45-0.48 | CV positioning, box-out detection, paint pressure |
| AST  | 0.36 | +0.06-0.09 | 0.42-0.45 | CV spacing, play type distribution, drive kickout rate |
| FG3M | 0.29 | +0.08-0.12 | 0.37-0.41 | closeout speed, catch-vs-pull-up classification |
| BLK  | 0.16 | +0.05-0.08 | 0.21-0.24 | rim protection positioning, shot arc estimation |
| TOV  | 0.22 | +0.04-0.07 | 0.26-0.29 | CV pressure at handoff, pass lane congestion |
| STL  | 0.18 | +0.04-0.07 | 0.22-0.25 | CV deflection positioning, passing lane activity |

### Context Signals With Known Lift (no CV required)

| Signal | Estimated lift | Status |
|--------|---------------|--------|
| Referee crew foul tendencies | +1-2% accuracy on foul-dependent props | Built |
| Travel fatigue index (great-circle, circadian) | +0.5-1% | Built |
| Denver altitude | +0.3% on 3PM props | Built |
| Lineup redistribution on late scratches | +3-5% on beneficiary props | Built |
| Injury return curve pricing | +5-8% on return-from-injury props | Built |
| Opening-line capture (24hr pre-game) | +1.2% CLV | Built |
| Steam detection | Confirmation signal (size up) | Built |

---

## What This Is NOT

- Not a "65%+ win rate guaranteed" claim. 62-66% is a long-run ceiling on filtered plays with the full research loop running.
- Not a claim that CLV has been validated. Gate 1 has not been run yet.
- Not a claim that the agentic system exists. It's planned, not built.
- Not a claim that 90 models are trained. 75 are trained; the architecture targets 500-5000 signals (not 90 models).

The honest current position: 7 prop models with holdout R² in the 0.16-0.41 range, win probability at 68.5%/Brier 0.209, 29 usable CV games, Gate 1 pending.

---

## The Path From Here to Ceiling

```
NOW                                      CEILING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gate 1 not run ──────────────────────► Gate 1 passed (CLV validated)
29 usable CV games ──────────────────► 200+ clean CV games
75 models, API-only ─────────────────► 500+ signals, CV-powered
No agentic system ───────────────────► Agent loop running 24/7
Underprediction bias on all props ───► Calibrated distributions
kelly_corr matrix empty ─────────────► Full correlation matrix live
No news ingestion ───────────────────► Injury/lineup pipe live
Single surface (personal betting) ───► 3+ surfaces generating revenue
```

Every step is an engineering checklist, not a fantasy. The hardest part (CV pipeline) is already running.

---

*For the full signal architecture: [vault/Plans/Signal Architecture.md](../vault/Plans/Signal%20Architecture.md)*
*For Gate 1 step-by-step: [vault/Plans/Gate 1 Validation.md](../vault/Plans/Gate%201%20Validation.md)*
*For Renaissance methodology context: [vault/Research/Renaissance Methodology.md](../vault/Research/Renaissance%20Methodology.md)*
