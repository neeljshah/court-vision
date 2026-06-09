# CourtVision — Prediction Ceiling

> What the system can realistically achieve — by phase, by market, by model.
> Honest numbers. No inflated projections. All win% at standard -110 vig (break-even = 52.4%).
> Reframed 2026-06-09 toward honest intelligence tiers. The betting "Now" read is **break-even-minus-vig** vs efficient closing lines; the ceiling is **funnel depth + basketball understanding**, not a printed ROI (see [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)).

---

## The Headline

The honest ceiling is about **basketball understanding and funnel depth**, not a printed ROI. Against efficient closing lines today the betting edge is roughly break-even-minus-vig; the headroom lives in how deep the intelligence funnel goes, not in bet sizing on an efficient market.

| Tier | What unlocks it | Betting read | Intelligence read |
|------|-----------------|--------------|-------------------|
| **Now** (MEASURED) | leak-free prop MAE · 80-artifact intel · agentic loop | **Break-even-minus-vig** vs real closes; **AST ~+4–5%** durable | funnel live end-to-end; CV features wired (SHAP≈0 today) |
| +Pinnacle Gate 1 (Oct 2026) | first real sharp-close CLV archive | first *true* edge measurement vs sharp closes | — |
| +80 CV games live | spatial features actually move the model | CV moat converts plumbing → measured lift (unproven) | per-player behavioral signal at scale |
| +Possession sim + real SGP capture | joint pricing on live markets | same-game-parlay edge (if any) becomes measurable | full-distribution game understanding |
| +Agentic loop at scale (500+ signals) | larger validated signal universe | more durable selections survive the refute-gate | deepest tier of automated understanding |

**Important caveats:**
- The honest **Now** read: vs real DK/FD/MGM/Pinnacle **closing** lines the market is efficient — break-even-minus-vig overall, with **assists ~+4–5% ROI** the one durable, book-robust edge (breaks in playoffs; size conservative). The earlier "+18.38% / +8.94pp CLV / $18.38 per $100" was a **market-follow grading artifact**, retracted ([JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md)).
- The forward tiers are **directional headroom, not forecasts.** Real sharp-close CLV cannot be measured until Oct 2026; zero real money placed by design.
- The leverage is **funnel depth** (DATA→SIGNALS→MODELS→ENGINES→PREDICTIONS→INTELLIGENCE) and the agentic loop that re-validates every stage — not better sizing on an efficient market.

---

## Current Model State (2026-05-25)

> **Post-in-play-system shift (cycles 103-110, improve_loop R7):** The pregame ceiling outlined below is now augmented by the in-play prediction architecture — residual heads stacked on base models, endQ1/endQ2 period-specific projection layers, learned Q4 minutes trajectory (`minute_trajectory.py`, PTS -0.2312 MAE), and live quantile bands calibrated to 80% empirical coverage. On a 550-game retro the endQ3 in-play system beats pregame by -43% to -55% MAE across 7/7 stats, and in-play betting wins 7/7 stats at threshold 1.0. Pregame still hits the architecture/feature ceiling; remaining gains there are DATA-bound (live injury feed, real sportsbook lines, CV defender_distance at scale, lineup projection).

### Player Prop Models — Actual Holdout Performance

Walk-forward temporal CV, N=99,818 observations. Source: `data/models/model_registry.json`.

| Stat | MAE | Model | Signal strength |
|------|-----|-------|----------------|
| PTS  | 4.62 | sqrt+Huber blend | Usable — needs CV lift |
| REB  | 1.90 | LGB-q50 | OK on role players |
| AST  | 1.36 | multitask MLP | Good on high-usage players |
| FG3M | 0.89 | XGB-q50 | Needs spatial (closeout speed) |
| TOV  | 0.89 | XGB-q50 | Marginal — use selectively |
| STL  | 0.72 | XGB-q50 | Near break-even — filter hard |
| BLK  | 0.44 | XGB-q50 | -16% session win |

> **Walk-forward MAE.** q50 quantile heads beat squared-error/Huber for skewed counts because prop O/U scores against the median.

### Win Probability Model (5-way NNLS stack)

| Metric | Current (WF) | Current (single-split) | Target (post 80-game CV retrain) |
|--------|-------------|------------------------|----------------------------------|
| Accuracy | 0.7094 | 0.717 | 0.73+ |
| Brier | 0.193 | 0.188 | 0.180 |

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
| Signal universe depth | 85 models | 500-5000 validated signals |
| Edge decay detection | Noticed when ROI drops | Caught by IR monitor before live |

Renaissance Technologies runs ~500 signals at any time. 60-70% of newly proposed signals fail validation. The survivors compound. This is the model.

---

## Model-by-Model Ceiling

### Prop Ceilings (with full signal architecture)

| Stat | Current holdout MAE | CV lift (est) | Ceiling MAE | Key signal unlock |
|------|---------------------|---------------|-------------|------------------|
| PTS  | 4.62 MAE | -0.15 to -0.25 | 4.37-4.47 MAE | defender_distance, minutes model, regime detection |
| REB  | 1.90 MAE | -0.08 to -0.12 | 1.78-1.82 MAE | CV positioning, box-out detection, paint pressure |
| AST  | 1.36 MAE | -0.06 to -0.10 | 1.26-1.30 MAE | CV spacing, play type distribution, drive kickout rate |
| FG3M | 0.89 MAE | -0.05 to -0.08 | 0.81-0.84 MAE | closeout speed, catch-vs-pull-up classification |
| BLK  | 0.44 MAE | -0.02 to -0.04 | 0.40-0.42 MAE | rim protection positioning, shot arc estimation |
| TOV  | 0.89 MAE | -0.04 to -0.07 | 0.82-0.85 MAE | CV pressure at handoff, pass lane congestion |
| STL  | 0.72 MAE | -0.03 to -0.05 | 0.67-0.69 MAE | CV deflection positioning, passing lane activity |

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
- Not a claim that 500 models are trained. 85 are trained; the architecture targets 500-5000 signals.

The honest current position: 7 prop models with walk-forward MAE locked in (PTS 4.62 / REB 1.90 / AST 1.36 / FG3M 0.89 / TOV 0.89 / STL 0.72 / BLK 0.44), win probability at 0.7094 acc / 0.193 Brier (WF), 29 usable CV games, Gate 1 pending.

---

## The Path From Here to Ceiling

```
NOW                                      CEILING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gate 1 not run ──────────────────────► Gate 1 passed (CLV validated)
29 usable CV games ──────────────────► 200+ clean CV games
85 models, API-only ─────────────────► 500+ signals, CV-powered
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

---

*Last verified: 2026-05-25*
