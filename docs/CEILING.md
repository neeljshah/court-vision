# CourtVision — Prediction Ceiling

> What the system can realistically achieve — by phase, by market, by model.
> Honest numbers. No inflated projections. All win% at standard -110 vig (break-even = 52.4%).
> The betting "Now" read is **break-even-minus-vig** vs efficient closing lines; the ceiling is
> **funnel depth + basketball understanding**, not a printed ROI.
> Cross-links: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) · [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## The Headline

**The model is at the data/feature ceiling.** Against efficient closing lines, break-even-minus-vig
is not a failure — it is the correct output of a rigorous validation framework applied to an
efficient market. The headroom lives in **data freshness, richer information substrate, and joint
structure** — not a smarter model on existing features.

| Tier | What unlocks it | Betting read | Intelligence read |
|------|-----------------|--------------|-------------------|
| **Now** (MEASURED) | Leak-free prop MAE · 80-artifact intel · agentic loop | **Break-even-minus-vig** vs real closes; **AST ~+4–5%** durable (not playoffs) | Funnel live end-to-end; CV features wired (SHAP ≈ 0 today) |
| +Pinnacle Gate 1 (Oct 2026) | First real sharp-close CLV archive | First *true* edge measurement vs sharp closes | — |
| +80 CV games live | Spatial features actually move the model | CV moat converts plumbing → measured lift (unproven) | Per-player behavioral signal at scale |
| +Possession sim + real SGP capture | Joint pricing on live markets | Same-game-parlay edge (if any) becomes measurable | Full-distribution game understanding |
| +Agentic loop at scale (500+ signals) | Larger validated signal universe | More durable selections survive the refute-gate | Deepest tier of automated understanding |

**Important caveats — read before quoting any number:**

- The honest **Now** read: vs real DK/FD/MGM/Pinnacle closing lines the market is efficient —
  break-even-minus-vig overall, with **assists ~+4–5% ROI** the one durable, book-robust edge
  (breaks in playoffs; size conservative).
- The **+18.38% / +8.94pp CLV** figures are retracted as market-follow grading artifacts.
  See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).
- The forward tiers are **directional headroom, not forecasts.** Real sharp-close CLV cannot be
  measured until Oct 2026; zero real money placed by design.

---

## Why the model is at the feature ceiling

Six independent experiments reached the same conclusion: adding more point features does not
beat the line. The ceiling is structural, not an implementation gap.

| Experiment | Result |
|---|---|
| 6 model architectures (LGB/XGB/MLP/Ridge/NN/Blend) | All converge to the same OOS MAE range |
| 4 signal levers (CV defender, lineup, scheme, vacated load) | All reject at the honest gate; individual lifts are single-fold artifacts |
| Full-season WF backtest, truncation-invariance proven | Season Brier 0.208 vs close 0.198; CLV ≈ 0; corr-with-outcome = 0.001 |
| PBP Finals replay (G1–G3) | Win-prob Brier 0.34–0.40 in-series (worse than coin flip) |
| CV SHAP audit | Every CV feature SHAP = 0.0 in production |
| Agentic loop (101,770-row gate) | Point-feature candidates correctly REJECT; loop idle on point-feature frontier |

**Remaining ceiling-raisers that the feature ceiling does NOT bind:**

1. **FRESHNESS / CLV** — betting openers before news moves lines (~58% ATS ceiling, graded);
   the model captures none of this (same-day speed edge, needs a live feed). Line-shopping adds
   ~+3.5% EV/bet (FD/MGM/DK softest). This is the #1 money lane.
2. **JOINT / SGP correlation pricing** — same-game parlay correlation structure is an underpriced
   market; requires real SGP price capture to grade.
3. **IN-GAME live re-pricing** — per-player projector validated as ship baseline (foul-out only);
   win-prob Brier Q1–Q3 needs improvement before the live betting layer is worth running.
4. **RICHER DATA SUBSTRATE** — shot-zone / on-court-5 / defender / assist-net, validated
   cross-season via `cluster_lab`; the V2 data frontier.

---

## Current Model State (2026-06-11)

### Player Prop Models — Leak-Free Walk-Forward MAE

Walk-forward temporal CV, ~51K held-out player-games/stat. Source: `data/cache/pregame_oof.parquet`.

| Stat | MAE | Notes |
|------|-----|-------|
| PTS  | **4.58** | Small ~-0.45 under-bias; CV lift unproven (SHAP=0) |
| REB  | **1.90** | Solid on role players |
| AST  | **1.34** | Best edge stat; ~+4–5% ROI durable (not playoffs) |
| FG3M | **0.88** | Needs spatial closeout speed to break ceiling |
| TOV  | 0.89 | Marginal — use selectively |
| STL  | 0.72 | Near break-even — filter hard |
| BLK  | 0.44 | -16% session win; high variance |

> These are competitive with published prop-model benchmarks. **This is the honest core accuracy
> claim — lead with it.** Do not quote the stale 4.62/1.36 figures from earlier runs.

### Win-Probability Model (5-way NNLS stack)

| Metric | Walk-forward | Season backtest | In-series (Finals G1–G3) |
|--------|-------------|-----------------|--------------------------|
| Accuracy | **0.709** | — | — |
| Brier | **0.193** | 0.208 (model) vs 0.198 (close) | 0.34–0.40 (worse than coin flip) |

The season backtest and in-series PBP replay are the cleanest market-efficiency proofs in the
system. "The model is well-calibrated but does not beat the market" is the correct and honest
output of the validation framework.

### xFG Model (Shot Quality)

| Metric | Current |
|--------|---------|
| Brier | 0.226 (221K shots) |

---

## What Changes With the Agentic Research System

The self-improving loop runs 24/7, but **the feature ceiling means it correctly rejects point
features**. The loop's real value is at the three open frontiers (joint, in-game, freshness).

| Research dimension | Current | With agentic system at scale |
|-------------------|---------|------------------------------|
| Hypotheses tested per week | 50–100 (LLM-free proposer running) | 500+ (broader frontier coverage) |
| Signal retirement | Systematic (IR threshold) | Faster (continuous monitoring) |
| Signal universe | ~85 models, point-feature ceiling hit | 500+ signals at open frontiers |
| Edge decay detection | IR monitor + held-out flag | Caught by IR monitor before live |

The LLM-free proposer (`src/loop/discovery.py`) enumerates feature transforms automatically;
the existing honest gate (expanding WF + null-shuffle z≥3 + BH-FDR) decides. Discovery is now
inexhaustible — the ceiling just needs to be attacked at the right frontier.

---

## Model-by-Model Ceiling With Unlocks

### Prop Ceilings (with full signal architecture)

| Stat | Current MAE | CV lift (est) | Ceiling MAE | Key signal unlock |
|------|-------------|---------------|-------------|------------------|
| PTS  | 4.58 | -0.15 to -0.25 | 4.33–4.43 | defender_distance, minutes model (requires 80 CV games + retrain) |
| REB  | 1.90 | -0.08 to -0.12 | 1.78–1.82 | CV positioning, box-out detection |
| AST  | 1.34 | -0.06 to -0.10 | 1.24–1.28 | CV spacing, drive kickout rate |
| FG3M | 0.88 | -0.05 to -0.08 | 0.80–0.83 | closeout speed, catch-vs-pull-up |
| BLK  | 0.44 | -0.02 to -0.04 | 0.40–0.42 | rim protection positioning |
| TOV  | 0.89 | -0.04 to -0.07 | 0.82–0.85 | CV pressure at handoff |
| STL  | 0.72 | -0.03 to -0.05 | 0.67–0.69 | passing lane activity |

*CV lift estimates are conditional on 80-game gate clearing AND SHAP confirming non-zero lift
in retrain. Current SHAP = 0 — these are the ceiling, not the current state.*

---

## What This Is NOT

- Not a "65%+ win rate guaranteed" claim. That ceiling requires: CV features validated, 500+
  signals running, real SGP price capture, and the agentic loop at scale.
- Not a claim that CLV has been validated. Gate 1 has not been run. First reading: Oct 2026.
- Not a claim that the agentic loop has produced positive results on point features. It
  correctly REJECTS on the current frontier — that is the correct behavior.
- Not a claim of any real-money edge. Zero real money placed, by design.

**The honest current position:** 7 prop models with walk-forward MAE locked in
(PTS 4.58 / REB 1.90 / AST 1.34 / FG3M 0.88), win-prob at 0.709 acc / 0.193 Brier (WF),
AST ~+4–5% the one durable edge, market efficient on all other closing-line props,
Gate 1 pending (Oct 2026).

---

## The Path From Here to Ceiling

```
NOW                                          CEILING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gate 1 not run (Oct 2026) ───────────────► Gate 1 passed (CLV validated vs Pinnacle)
~85 CV games, SHAP=0 ────────────────────► 80 CLEAN games + retrain, SHAP > 0
Season backtest: CLV ≈ 0 ────────────────► Freshness edge captured (live feed)
Point-feature ceiling hit ───────────────► V2 substrate (shot-zone/on-court-5/defender)
No real SGP price capture ───────────────► Joint/SGP correlation edge measurable
Win-prob Brier 0.34–0.40 in-series ──────► In-game live re-pricing validated
Polarity bug unpatched ──────────────────► Polarity fix + retrain cascade (+1.5–3.5pp CLV)
kelly_corr matrix empty ─────────────────► Full correlation matrix live
```

Every step is an engineering checklist, not a fantasy. The hardest part (validation framework)
is already running — and it already correctly caught the inflated numbers.

---

*For the full signal architecture: [vault/Plans/Signal Architecture.md](../vault/Plans/Signal%20Architecture.md)*
*For Gate 1 step-by-step: [vault/Plans/Gate 1 Validation.md](../vault/Plans/Gate%201%20Validation.md)*

*Last verified: 2026-06-11*
