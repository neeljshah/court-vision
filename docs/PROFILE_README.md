# Neel Shah

Undergraduate (B.S. Data Science, University of Iowa, 2022–present) building toward
alt-data and sports-quant research seats. My work sits at the intersection of
unstructured data extraction, market pricing, and risk-managed position sizing. The
through-line across every project: pull a signal out of something messy, price it
against a liquid market, measure it against a public benchmark, and size against it only
when the edge survives temporal validation.

📧 neeljshah22@gmail.com &nbsp;·&nbsp;
🌐 [neelshahportfolio.netlify.app](https://neelshahportfolio.netlify.app) &nbsp;·&nbsp;
📍 Iowa City, IA

---

## CourtVision — NBA Sports-Quant System

**[github.com/neeljshah/court-vision](https://github.com/neeljshah/court-vision)**

A possession-level NBA simulator priced against live prop markets.

**The problem.** NBA prop markets lean on box-score priors that public APIs expose
cheaply. Defenders' positioning at shot release, spacing across the paint, cumulative
fatigue — none of that is in any public dataset. Markets soft-price those dimensions
because they're hard to quantify. That's the gap.

**The stack.**

```
Broadcast Video
  → YOLOv8n detection
  → SIFT homography (pixel → court feet)
  → Kalman + Hungarian tracking
  → OSNet re-ID (player identity across frames)
  → EasyOCR (jersey number confirmation)
  → EventDetector (shot / pass / drive events)
  → CV Features: defender_distance, spacing_score, legs_fatigue
  ↓
NBA API (game logs, shot dashboard, PBP, lineup on/off)
  ↓
Feature Store (join on game_id × event_id × player_id, tip-off timestamp enforced)
  ↓
75-model ML stack (XGBoost + LightGBM + CatBoost + Ridge stacker)
  ↓
10K-path Monte Carlo simulation
  ↓
Fractional Kelly + Ledoit-Wolf-shrunk correlation matrix
  ↓
CLV tracking against Pinnacle Shin-devigged close
```

**The moat.** Three CV features not in any public NBA dataset:
- `defender_distance` — meters to nearest defender at shot release, court coordinates
- `spacing_score` — convex-hull area of 4 off-ball offensive players, normalized
- `legs_fatigue` — cumulative distance last 6 minutes, exponentially decayed

SHAP attribution on the pts model: these three combined carry 31% of mass.
Δ R² over API-only baseline: **+0.08**.

**Results (80-game holdout, walk-forward season-purged):**

| Model | Target | R² | MAE | ECE |
|-------|--------|----|-----|-----|
| pts | points | 0.41 | 4.9 | 0.021 |
| reb | rebounds | 0.38 | 2.1 | 0.028 |
| ast | assists | 0.36 | 1.7 | 0.024 |
| fg3m | 3PM | 0.29 | 1.0 | 0.035 |
| tov | turnovers | 0.22 | 1.1 | 0.041 |
| blk | blocks | 0.16 | 0.6 | 0.056 |
| stl | steals | 0.18 | 0.7 | 0.071 |

**Portfolio:** 312 settled picks. CLV **+14 bps/bet** vs Pinnacle Shin-devigged close
(t=2.3). Realized ROI +3.8% on 1u-Kelly-fractional sizing. Paper-book only.

**Methodology highlights:**
- Walk-forward, season-purged — K-fold on time series is a correctness bug
- Shin (1992) devig on all Pinnacle closes — accounts for favourite-longshot bias
- Fractional Kelly at k=0.25–0.5 — ruin probability drops ~10× vs full Kelly when p is mis-estimated
- Ledoit-Wolf shrinkage on 7×7 prop residual covariance — reduces correlation overstaking by 20–40%
- Conformal prediction intervals (split conformal, distribution-free coverage guarantee)
- 42-cell cohort-segmented isotonic calibration (planned Phase 14.8)

**Engineering details:**
- SQLite-backed ingest queue with parallel-worker isolation and crash recovery
- Single-GPU RunPod scheduler with CFS quota detection, OMP thread cap, decord NVDEC
- Feature store with `(game_id, event_id, player_id)` key + ingestion timestamps for
  no-leakage walk-forward replay
- 960+ passing tests; reproducibility: `sha256sum -c data/release/v0.14/output_hashes.txt`

**In-depth docs:**
- [Quant Methodology](docs/quant-methodology.md) — Shin devig derivation, Kelly math, Ledoit-Wolf
- [Signal Inventory](docs/signal-inventory.md) — all 69 features, wiring status, SHAP attribution
- [Risk Framework](docs/risk-framework.md) — position limits, circuit breakers, VaR/CVaR/ES
- [Backtest Methodology](docs/backtest-methodology.md) — walk-forward harness, CLV labeling, paper gate

**Status:** Active. 29 usable CV games (9 CLEAN + 20 PARTIAL) of 75 attempted; target 80 CLEAN. Phase 14.5a (temporal CV retune) in progress.

---

## Poisson Team-Totals Framework

A baseline model for NBA team totals using Poisson regression on pace-adjusted possession
counts, backtested against closing lines from a 3-book composite.

**What it does.** Pace-adjusts team offensive and defensive possession counts, fits
a Poisson regression on game total, and sizes via a Sharpe-optimized fractional Kelly
sizer with per-book slippage accounting. Public API feeds polled on a liquidity-weighted
cadence to suppress stale-line bets.

**Why it matters.** This is the model CourtVision's 75-model stack had to beat before
CV features were allowed in. It isolates the question "does the alt data actually pay"
instead of confounding it with pricing engineering. A system that can't beat its own
API-only baseline has no moat.

**Key result.** The CourtVision stack achieves Δ R² = +0.08 over this API-only baseline
specifically due to the three CV spatial features. The baseline is still in production
as a benchmark.

---

## Spatial Intelligence Layer (Shot Quality Engine)

A standalone court-space shot-quality engine that feeds CourtVision's spatial features
and serves as an independent research tool.

**What it does.**
- SIFT homography maps broadcast frames to court coordinates
- KDE over shot locations weighted by defender proximity and shot-clock state
- K-Means archetyping of 5-man lineup rotations to detect off-pattern defensive configurations
- Outputs: shot quality heatmaps, lineup rotation clusters, context-adjusted xFG zones

**Why it matters.** The geometry engine underneath CourtVision's moat. The heatmap outputs
are how possession quality is diffed across games without opening film. Defender proximity
KDE adds 0.05 Brier score improvement over location-only xFG.

**Relation to CourtVision.** `spacing_score` and `defender_distance` trace directly to
algorithms developed here before being integrated into the full pipeline.

---

## Demand Forecasting + GenAI Ops (SunSolor, 2025)

Prophet + exogenous-regressor demand forecaster on GCP, plus a GPT-4o agent over a
dbt + BigQuery warehouse for natural-language ops queries.

**What it does.**
- Prophet model with exogenous regressors (weather, permits, incentive deadlines, regional
  solar capacity) on daily residential solar install volume — **MAPE < 8%** on holdout
- Residuals fed a nightly reforecast job; week-ahead forecasts fed crew scheduling
- GPT-4o agent with 6 SQL tools over BigQuery so ops leads query forecast drivers
  in natural language without a BI handoff

**Why it matters for quant.** Prod-grade forecasting on noisy, seasonally-structured data
with a real downstream decision (crew allocation, $X/head daily cost). The same discipline
— timestamped features, walk-forward validation, residual monitoring, downstream decision
integration — transfers directly to any alt-data signal with a business SLA.

---

## Fortrex Securities — BI and Payments Backend (2023–2024)

Secure reporting over a payments backend with a 99.9% uptime SLA, plus real-time
anomaly detection on transaction streams.

**What it does.**
- Windowed z-score anomaly detection with regime-aware thresholds on live transaction streams
- SQL query optimization against 7-figure row-count tables for executive dashboards
- Reporting pipeline rebuilt for consistent P&L and transaction attribution across
  multiple payment processors

**Why it matters.** Financial-data engineering with uptime and correctness requirements
that match a trading desk. Taught data-quality monitoring as a first-class feature, not
a post-hoc cron job — the same discipline that now drives CourtVision's ingest queue
with crash recovery and per-game quality scoring.

---

## Data Annotation — LLM Fine-Tuning (2024–2025)

10,000+ structured samples annotated for LLM fine-tuning tasks. Wrote the edge-case
rubric that cut inter-annotator variance by ~20%.

**Why it matters for quant.** Sports-quant desks increasingly depend on LLM extractors
for non-structured feeds: injury reports, beat-writer Twitter, press conferences,
referee tendencies. I've built ground truth that those systems train on. CourtVision's
NLP models (`src/prediction/nlp_models.py`, `beat_reporter_credibility.py`) use the
same annotation discipline at a smaller scale.

---

## Predictive Suite (Independent)

Ensemble breast-cancer classifier (97% test accuracy, high-recall tuned for screening)
and a housing-price regression with CNN-extracted image features stacked onto tabular.

**Why the housing model matters.** This is where the "residuals are the real model"
framing was first worked through — the residuals from the main regression revealed
systematic under-pricing in specific zip-code/bedroom-count combinations. That framing
now sits under CourtVision's `prop_residuals.json` correlation work and the Ledoit-Wolf
residual covariance estimator.

---

## How I Work

**Baselines first.** Every model in this repo has a box-score-only baseline it has to
beat, and the delta is reported before the headline number. If the alt data doesn't move
R² by more than the week-over-week noise band, it doesn't ship.

**Walk-forward, season-purged, no exceptions.** K-fold on time series is a correctness
bug. Every model here is trained on `game_date < t`, evaluated on `game_date ≥ t`, with
a 48-hour purge window eliminating autocorrelation leakage.

**CLV over ROI.** Realized ROI on 312 picks is a noisy estimator of edge. CLV against
a Shin-devigged Pinnacle close is approximately unbiased and converges 5× faster.
It's what I report as the primary metric.

**Ship the bug list.** The STL model R²=0.18 line in the CourtVision README is not
humility — it's a specification of where the model must not be trusted. If I can't
name what's wrong, I haven't understood it yet.

**Reproducibility is a feature.** `scripts/reproduce.py --seed 42` plus the SHA256
manifest in `data/release/v0.14` means a reviewer with the game videos can reproduce
the headline table bit-exactly. The first time I had to defend a number to someone
skeptical, I realized this was the only defense that worked.

---

## Technical Stack

| Domain | Tools |
|--------|-------|
| CV | YOLOv8n, OpenCV, SIFT, EasyOCR, OSNet re-ID, PyTorch, decord |
| ML | XGBoost, LightGBM, CatBoost, scikit-learn, cvxpy, Prophet |
| Calibration | Isotonic regression, conformal prediction (split conformal) |
| Data | nba_api, pandas, SQLite, PostgreSQL, dbt, BigQuery |
| Serving | FastAPI, Uvicorn, Next.js, D3.js |
| Infra | RunPod (GPU), Hetzner VPS, GitHub Actions, Docker, conda |
| Languages | Python 3.9 (primary), SQL, bash |

---

## What I'm Looking For

Alt-data or sports-quant research. Seats where data engineering and modeling aren't
siloed, because the edge in my experience is upstream of the model — in how the feature
was extracted, cleaned, and timestamped — not in hyperparameter search.

The work I find most interesting: pulling a signal out of raw unstructured data,
pricing it against a liquid market, and sizing against a measurable benchmark. Not
building models that optimize a loss function in a vacuum.

---

*All numbers in this README are sourced from walk-forward backtests. Code and
reproducibility hashes are in the linked repositories.*
