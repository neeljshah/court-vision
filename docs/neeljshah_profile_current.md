<div align="center">

# Neel J. Shah
### Quantitative Researcher · Alt-Data Extraction · Sports-Market Pricing

**Undergraduate (B.S. Data Science, University of Iowa, 2022–present) building toward alt-data and sports-quant research seats.**

[![Email](https://img.shields.io/badge/Email-neeljshah22%40gmail.com-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:neeljshah22@gmail.com)
[![Portfolio](https://img.shields.io/badge/Portfolio-neelshahportfolio.netlify.app-0A66C2?style=for-the-badge)](https://neelshahportfolio.netlify.app)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-neeljshah22-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/neeljshah22/)

</div>

---

> **Thesis.** Public sports markets are priced off box-score aggregates that every retail model uses. They don't see where defenders stand at catch, how contested a shot actually is, or how many minutes of transition defense a player has in his legs. I extract those signals from broadcast video, price positions against them, and benchmark fills against Pinnacle's closing line. The edge persists because the CV pipeline is non-trivial to build and data-hungry to validate — which keeps soft markets wider than sides or totals.

---

## CourtVision — NBA Sports-Quant System

**[github.com/neeljshah/court-vision](https://github.com/neeljshah/court-vision)**

A possession-level NBA simulator priced against live prop markets. Broadcast video in → fractional-Kelly-sized +EV positions out.

```
Broadcast Video (60fps)
  → YOLOv8n player/ball detection    (custom-trained ball detector)
  → SIFT homography                  (pixel coords → court feet)
  → Kalman + Hungarian tracking      (multi-object, occlusion-robust)
  → OSNet re-ID (512-dim)            (persistent player identity across frames)
  → EasyOCR jersey number            (disambiguation on re-ID collisions)
  → EventDetector                    (shots, passes, drives, screens)
  → CV Features ← THE MOAT          (defender_distance, spacing_score, legs_fatigue)
         │
NBA API (game logs, shot dashboard, PBP, lineup on/off, injury reports)
         │
Feature Store (keyed on game_id × event_id × player_id, ingestion timestamps
               preserved for no-leakage walk-forward replay at tip-off time)
         │
75-Model ML Stack
  Tier 1 (API only):  XGBoost + Ridge stacker → 7 prop models, win prob, game total
  Tier 2 (shot data): xFG v1, shot zone tendency, clutch efficiency
  Tier 3 (CV ≥20g):  xFG v2 w/ defender, play type, spacing rating
  Tier 4 (CV ≥50g):  fatigue curve, rebound positioning, closeout quality
  Tier 5 (NLP):       injury return, load management, DNP predictor (AUC 0.979)
         │
10,000-path Monte Carlo simulation
  (correlated residuals, tempo-aware, FoulTrouble/GarbageTime/Q4Usage wired)
         │
Fractional Kelly + Ledoit-Wolf-shrunk 7×7 correlation matrix
  (reduces correlated-prop overstaking by 20–40% vs naive Kelly)
         │
CLV tracking vs Pinnacle Shin-devigged close
```

### Results (80-game holdout, walk-forward season-purged)

| Model | Target | R² | MAE | ECE | vs API-only baseline |
|-------|--------|----|-----|-----|---------------------|
| pts | points | 0.47 | 4.9 | 0.021 | +0.08 Δ R² from CV features |
| reb | rebounds | 0.40 | 2.1 | 0.028 | — |
| ast | assists | 0.46 | 1.7 | 0.024 | — |
| fg3m | 3PM | 0.28 | 1.0 | 0.035 | — |
| tov | turnovers | 0.25 | 1.1 | 0.041 | — |
| blk | blocks | 0.18 | 0.6 | 0.056 | — |
| stl | steals | 0.09 | 0.7 | 0.071 | — |

**Portfolio:** 312 settled picks. CLV **+14 bps/bet** vs Pinnacle Shin-devigged close (t=2.3).
Realized ROI +3.8% on 1u fractional-Kelly sizing. Paper-book only — no live capital until
the Phase 19 gate passes (≥50 paper bets, CLV beat rate ≥55%, paper ROI ≥3%).

### The CV Moat

Three features that do not exist in any public NBA dataset:

- **`defender_distance`** — meters to nearest defender at shot release, computed in court
  coordinates post-homography. Correlates with shot quality above what shot_distance +
  shot_type already encodes.
- **`spacing_score`** — convex-hull area of the 4 off-ball offensive players, normalized
  to half-court. Proxy for how much the defense must respect perimeter threats.
- **`legs_fatigue`** — cumulative running distance over the last 6 minutes, exponentially
  decayed. Captures the "tired-legs late-game" effect invisible to box-score MIN.

SHAP attribution on the pts model: these three combined carry **31% of mass**.
Δ R² over API-only baseline: **+0.08**.

### Methodology

**Walk-forward, season-purged — always.** Train on `game_date < t`, evaluate on
`game_date ≥ t`. A 48-hour purge window drops same-team games from the training window,
eliminating autocorrelation leakage that K-fold silently introduces. The harness is in
[`src/prediction/prop_backtester.py`](https://github.com/neeljshah/court-vision/blob/master/src/prediction/prop_backtester.py).

**Shin (1992) devig.** Pinnacle closes are devigged with the Shin method before CLV is
computed. Simple power-sum devig over-corrects the favourite-longshot bias; Shin fits a
single insider-trading parameter *z* per market and yields the corrected probability:

$$p_{\text{true}} = \frac{p_{\text{observed}} - z}{1 - 2z}$$

On NBA game totals *z* ≈ 0.02–0.04; on illiquid alt-line props it exceeds 0.06.

**Fractional Kelly sizing.** Full Kelly optimizes expected log-wealth but produces ruin
under any mis-estimation of *p*. The system uses *k* ∈ [0.25, 0.5] × f* where *k* is
calibrated to market maturity. At *k* = 0.25, ruin probability under a 2% edge
mis-estimation drops roughly 10× vs full Kelly. Implemented in
[`src/prediction/betting_portfolio.py`](https://github.com/neeljshah/court-vision/blob/master/src/prediction/betting_portfolio.py).

**Ledoit-Wolf correlation shrinkage.** A 7×7 sample covariance matrix from N=80 games
is rank-deficient and amplifies spurious correlations (pts/reb share minute-driven
variance; sample ρ ≈ 0.55–0.70 vs true ρ materially lower). Ledoit-Wolf shrinks toward
a scaled identity, reducing naive Kelly overstaking on correlated prop legs by 20–40%.
One line: `sklearn.covariance.LedoitWolf().fit(prop_residuals)`.

**Conformal prediction intervals.** Each bet carries (lo_80, hi_80, lo_95, hi_95) from
a split conformal procedure on a held-out calibration set — distribution-free coverage
guarantee regardless of model misspecification.
[`src/prediction/conformal_props.py`](https://github.com/neeljshah/court-vision/blob/master/src/prediction/conformal_props.py).

**CLV over ROI.** On 312 picks, realized ROI has a standard error of ~3–4%. CLV against
Pinnacle's close is approximately unbiased and converges to the true edge ~5× faster.
It's the primary metric; ROI is a secondary check.

### Engineering

- **Ingest queue.** SQLite-backed parallel job queue with claim-race retry, per-game
  quality scoring, and `reset_stale_jobs.py` for pods that OOM mid-game.
- **GPU scheduler.** `scripts/launch_single_3090_pod.sh` automates CFS quota detection,
  OMP thread cap, decord NVDEC install, and H.264-only quarantine — taking a RunPod RTX
  3090 from 45 fps aggregate to 80 fps without code changes to the tracker. Two sessions
  were lost rediscovering this the hard way; the runbook is the forensic record.
- **Reproducibility.** `scripts/reproduce.py --seed 42` + SHA256 manifest at
  `data/release/v0.14/output_hashes.txt`. A reviewer with source videos reproduces the
  headline table bit-exactly.
- **960+ passing tests** across 13 complete phases. FastAPI serving 9 endpoints with
  in-process TTL cache. Phase 14.5 (temporal CV retune) active.

---

## Poisson Team-Totals Framework

A Poisson regression baseline for NBA team totals — the model CourtVision's 75-model
stack had to beat before CV features were allowed in.

**What it does.** Pace-adjusts possession counts, fits Poisson regression on game total,
and sizes via Sharpe-optimized fractional Kelly with per-book slippage accounting. Public
API feeds polled on a liquidity-weighted cadence to suppress stale-line bets. Backtested
against closing lines from a 3-book composite.

**Why it matters.** It isolates the question "does the alt data actually pay" without
confounding it with pricing engineering. Same market, same closing-line benchmark, no CV.
The Δ R² = +0.08 that CV features deliver is measured against this baseline specifically.

---

## Spatial Intelligence Layer (Shot Quality Engine)

A standalone court-space shot-quality engine — the geometry library underneath
CourtVision's moat features.

**What it does.**
- SIFT homography maps broadcast frames to court coordinates
- KDE over shot locations weighted by defender proximity and shot-clock state produces
  zone-level xFG estimates that outperform location-only models
- K-Means archetyping of 5-man lineup rotations detects when a team is running an
  off-pattern defensive configuration (the precursor to `spacing_score`)

**Standalone use.** Heatmap outputs diff possession quality across games without opening
film. This is where `defender_distance` and `spacing_score` were first developed before
integration into the full CV pipeline.

---

## Demand Forecasting + GenAI Ops (SunSolor, 2025)

Prophet + exogenous-regressor demand forecaster on GCP, plus a GPT-4o agent over a
dbt + BigQuery warehouse.

**What it does.**
- Prophet with exogenous regressors (weather, permits, incentive deadlines, regional
  solar capacity) on daily residential solar install volume — **MAPE < 8%** on holdout
- Residuals fed a nightly reforecast job; week-ahead output feeds crew scheduling
- GPT-4o agent with SQL tools over BigQuery so ops leads query forecast drivers in
  natural language without a BI handoff

**Relevance to quant.** Prod-grade forecasting on noisy, seasonally-structured data
with a real downstream decision (crew allocation). Same discipline as any alt-data
signal that has to hit a business SLA: timestamped features, walk-forward validation,
residual monitoring, downstream decision integration.

---

## Fortrex Securities — BI and Payments Data Engineering (2023–2024)

Reporting infrastructure over a payments backend with a 99.9% uptime SLA.

**What it does.**
- Windowed z-score anomaly detection with regime-aware thresholds on live transaction streams
- SQL optimization against 7-figure row-count tables for executive P&L dashboards
- Reporting pipeline rebuilt for consistent attribution across multiple payment processors

**Relevance.** Financial-data engineering with uptime and correctness requirements that
match a trading desk. Taught data-quality monitoring as a first-class feature — the same
discipline now in CourtVision's ingest queue and per-game quality scoring.

---

## Research Principles

- **Walk-forward, purged, always.** K-fold on time-ordered data is a correctness bug. Every model here trains on `game_date < t`, evaluates on `game_date ≥ t`, with a purge window sized to the label overlap. No exceptions.
- **Baselines first.** Every model has a cheap API-only baseline it must beat, and the delta is reported before the headline number. If the alt data doesn't move R² past the week-over-week noise band, it doesn't ship.
- **CLV over ROI.** Realized ROI on small samples is a noisy estimator of edge. CLV against a Shin-devigged closing line is approximately unbiased and converges ~5× faster.
- **Calibration ≠ accuracy.** Reliability diagrams and ECE on every probabilistic model. A model that is accurate but miscalibrated cannot be safely sized with Kelly.
- **Ship the bug list.** The STL model R²=0.09 line in the CourtVision README is not humility — it's a specification of where the model must not be trusted. If I can't name what's wrong, I haven't understood it.
- **Reproducibility is a feature.** SHA256 manifests, seeded Monte Carlo, and pinned data snapshots mean a reviewer can verify claims without trusting intermediate representations.
- **Costs modeled, not assumed.** Kelly fractions account for slippage and vig differential. CLV is measured net of Pinnacle's margin, not gross.

---

## Stack

| Domain | Tools |
|--------|-------|
| CV / tracking | YOLOv8n, OpenCV, SIFT, EasyOCR, OSNet re-ID, PyTorch, decord (NVDEC) |
| ML | XGBoost, LightGBM, CatBoost, scikit-learn, cvxpy (QP optimizer) |
| Calibration | Isotonic regression (cohort-segmented), conformal prediction |
| Time-series | Prophet + exogenous regressors, walk-forward harness |
| Data | nba_api, pandas, SQLite, PostgreSQL, dbt, BigQuery |
| Serving | FastAPI, Next.js, D3.js, WebSocket |
| Infra | RunPod GPU, Hetzner VPS, GitHub Actions, Docker, B2 |
| Languages | Python 3.9 (primary), SQL, bash |

---

## What I'm Looking For

Alt-data or sports-quant research. Seats where data engineering and modeling aren't
siloed, because the edge in my experience is upstream of the model — in how the feature
was extracted, cleaned, and timestamped — not in hyperparameter search. I work best when
the question is "does this signal actually price into the market" and the answer requires
building something non-trivial to find out.

**Open to:** quant research (sports, systematic, alt-data) · alt-data sourcing · any
context where the pipeline is as interesting as the model.

📧 [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com) · [linkedin.com/in/neeljshah22](https://www.linkedin.com/in/neeljshah22/) · [neelshahportfolio.netlify.app](https://neelshahportfolio.netlify.app)
