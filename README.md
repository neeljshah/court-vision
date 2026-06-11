# CourtVision

**Broadcast video → court coordinates → signals → models → engines → predictions → intelligence.**

An AI-native sports intelligence system that converts a raw NBA broadcast feed into calibrated
player-game predictions, a 690-node knowledge graph, and a self-improving research loop —
all on a single consumer GPU at ~$0.10–0.13 per game.

Built by **[Neel Shah](https://neelshahportfolio.netlify.app)** — solo human architect and
director of an agentic build pipeline. Engineering judgment, ship/reject decisions, and
validation methodology are mine; most code was written by planner→executor model agents under
hard statistical gates. Intensive ~3-month build, 1,470 commits (Mar–May 2026).

Open to **ML / computer-vision / data / founding-engineer** roles →
[neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

**430 Python modules · 7 prop heads (q10/q50/q90) · 80-artifact intelligence layer ·
291K-pair matchup matrix · 690-node knowledge graph · ~99 FastAPI endpoints ·
~7,400 tests · 9 watchdog'd daemons · ~$0.10–0.13/game CV pipeline**

---

> **One honesty note, because it is the most important signal in the repo.** The same
> person who built this system also built the harnesses that caught — and publicly retracted —
> his own inflated headline numbers (+18.38% ROI, endQ3 Brier 0.119). Both were measurement
> artifacts; both are documented in detail below, not buried. The defensible results are the
> **CV pipeline, the prediction accuracy, the validation rigor, and the intelligence layer** —
> not a betting edge. Full audited account: **[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)**.

---

## The funnel

```
┌────────────────────────────────────────────────────────────────────────────┐
│  1. DATA        Broadcast video + NBA Stats API + live betting lines        │  ← widest
│                 CV tracking → ~150 cols/game @ ~$0.10–0.13/game             │
├────────────────────────────────────────────────────────────────────────────┤
│  2. SIGNALS     60+ engineered features · 80-artifact intelligence layer    │
│                 · self-improving signal-discovery loop (gated)              │
├────────────────────────────────────────────────────────────────────────────┤
│  3. MODELS      7 prop heads (q10/q50/q90) · win-prob NNLS stack            │
│                 · in-play snapshot heads (endQ1/Q2/Q3) — walk-forward gated │
├────────────────────────────────────────────────────────────────────────────┤
│  4. ENGINES     Possession Monte Carlo · Shin devig · decision engine       │
│                 · correlation-aware Kelly · shadow logger · 9 daemons       │
├────────────────────────────────────────────────────────────────────────────┤
│  5. PREDICTIONS Calibrated projections + win prob + EV + sized bets + SGPs  │
│                 surfaced over ~99-endpoint FastAPI + live trading desk       │
├────────────────────────────────────────────────────────────────────────────┤
│  6. INTELLIGENCE 1,249 player dossiers · 30 scheme cards · grounded AI chat │  ← narrowest,
│   (the apex)    · agentic loop that discovers, validates, ships, retires    │    most refined
└────────────────────────────────────────────────────────────────────────────┘
        ▲                                                                 │
        └──────────  the agentic loop feeds back and improves every stage ┘
```

Read top-to-bottom: a data-refinement pipeline. Read the feedback arrow: a self-improving
research system. The intelligence layer at the bottom also re-validates and re-ships everything above it.

---

## 1 · DATA — turning a TV feed into structured court data

Point CourtVision at any NBA broadcast and it produces structured, court-coordinate data
on every player, the ball, every shot, every possession, and every event — at
**~$0.10–0.13 per full game** on a single consumer GPU, versus six- to seven-figure annual
licensing for Sportradar / Second Spectrum on the same broadcast feed. That cost delta is
the moat thesis.

### The CV pipeline

```
Broadcast video
  → YOLOv8n detection            players, ball, rim, referee, shoot/made events
  → SIFT homography              image pixels → 94 × 50 ft court coordinates
  → Kalman + Hungarian tracking  6D constant-velocity motion + globally-optimal ID assignment
  → OSNet re-ID (512-dim)        recover identities through occlusion / scene cuts
  → EasyOCR                      jerseys, scoreboard clock + period + score
  → EventDetector                shots, passes, dribbles, screens, drives, closeouts, rebounds
  → Per-frame writer             CSV / SQLite / Postgres
  → NBA API enrichment           real player IDs, official PBP labels
```

The tracking math is implemented from primitives: a 6D constant-velocity Kalman filter plus
Hungarian assignment over a blended IoU+appearance cost
([`src/tracking/advanced_tracker.py`](src/tracking/advanced_tracker.py)), a custom-trained
single-class ball detector exported PyTorch→ONNX→TensorRT, and a broadcast-hardened
homography with inlier gating, EMA smoothing, drift re-anchoring, and replay/scene-cut
suspension. Every accelerated component has a graceful CPU fallback — runs identically on
a laptop or a GPU server.

### What it produces (per game)

| Output | Granularity | Contents |
|--------|-------------|----------|
| `tracking_data.csv` | per frame × player (~60 cols) | court x/y (raw+normalized+feet), velocity/accel/heading, ball pos+possession flag, defender distance, team spacing + convex-hull area, paint counts, drive/fast-break flags, shot-clock estimate, lineup ID, play type, homography-valid flag |
| `shot_log.csv` | one row per shot (~25 cols) | shooter+team, court x/y+zone, defender distance+identity, spacing at release, made/missed, contest angle, closeout speed, fatigue proxy, catch-and-shoot flag |
| `possessions.csv` | one row per possession (~25 cols) | team, duration, avg spacing+pressure, drive attempts, play type, result, pass/screen/drive/cut counts |
| `events_log.csv` | one row per event (~17 cols) | screens/cuts/drives/closeouts/rebounds with player+defender IDs, court coords |
| `scoreboard_log.csv` · `ball_tracking.csv` · `stats.json` | OCR / per-frame / aggregates | game+shot clock, score, period, ball position, per-player totals |

**~150 distinct columns** of structured per-frame and per-event data from raw video, mirrored
to SQLite/PostgreSQL and enriched against the NBA Stats API. Current status: ~240 games
tracked end-to-end; **17,254 `cv_features` rows / 241 games / 252 distinct resolved NBA player
IDs** in `data/nba_ai.db`.

### The other two data sources

- **NBA Stats API + cdn.nba.com** — 569 gamelogs, ~221K shots, ~3.6K PBP sequences across
  30 seasons; live boxscore + PBP for in-play.
- **Betting lines** — The Odds API + custom scrapers (Pinnacle / Bovada / FanDuel / PrizePicks
  live; DK / Caesars / MGM IP-blocked in production, browser-fingerprint impersonation attempted
  with a live/pregame contamination guard).

**Load-bearing:**
[`src/pipeline/unified_pipeline.py`](src/pipeline/unified_pipeline.py) ·
[`src/tracking/advanced_tracker.py`](src/tracking/advanced_tracker.py) ·
[`src/tracking/osnet_reid.py`](src/tracking/osnet_reid.py) ·
[`src/tracking/ball_detect_track.py`](src/tracking/ball_detect_track.py)

Deep dive: [docs/CV_TRACKING.md](docs/CV_TRACKING.md)

---

## 2 · SIGNALS — turning data into questions the models can't guess

### Engineered features

[`src/features/feature_engineering.py`](src/features/feature_engineering.py) builds 60+
pregame features — pace, team total, lineup on/off, rest/travel, referee tendencies, altitude —
plus the **CV bridge** that joins behavioral tracking features (defender distance at release,
spacing entropy, fatigue from cumulative movement, paint dwell %, contested-shot rate) onto
each player-game.

### The 80-artifact intelligence layer

Between raw tracking and the models sits a derived layer of **80 parquet/json artifacts**
(`data/intelligence/`, gitignored — regenerable, encodes the moat). Highlights: a
**26,335-pair player similarity matrix**, defensive scheme tags for all 30 teams, position×scheme
and archetype×scheme interaction tables with significance tests, lineup chemistry
(4,760 rows / 1,175 lineups), clutch / quarter / shot-clock / possession-type splits, matchup
deviations, coaching adjustments, a game-similarity retrieval index, per-game CV-quality and
per-player confidence curves, and underneath it all a **291,625-pair player-vs-player matchup
matrix** built from 2,214 raw tracking files across three seasons, folded into a **690-node
idempotent knowledge graph** (660 player + 30 team notes, single-writer, no duplication on
re-run).

Full manifest with per-artifact row counts and schemas: [docs/INTELLIGENCE.md](docs/INTELLIGENCE.md)

### The self-improving signal-discovery loop

[`src/loop/`](src/loop/) runs a two-arm daemon. **ARM A** mines residuals into hypotheses,
instantiates a leaf `signals/<name>.py`, and ships it only behind a hard statistical gate
([`src/loop/gate.py`](src/loop/gate.py)): expanding walk-forward (all folds must improve) +
null-shuffle permutation control (z ≥ 3) + ablation-vs-full marginal lift +
Benjamini-Hochberg FDR across the hypothesis family. **ARM B** writes new `intel/*.py` atlas
sections back into the player profiles, REAL-vs-unknown fields explicitly marked. **Most
candidates are correctly rejected — that is the design.**

> **Honest caveat:** In today's production prop models, CV-derived features carry SHAP
> importance ≈ 0 (`cv_lift_report.json` → `has_cv_data: false`). The plumbing is complete
> and the thesis is credible, but CV features do not yet move the model. Stated as a roadmap
> item, not a current advantage.

---

## 3 · MODELS — calibrated predictions, walk-forward gated

Every model is validated walk-forward, point-in-time, behind a leak guard. The numbers below
are the **leak-free** ones, after self-audit.

### Prop projections — walk-forward MAE @ q50

Seven per-stat models (PTS / REB / AST / FG3M / STL / BLK / TOV), each emitting
q10/q50/q90 quantile heads. Quantile regression at q50 beats squared-error blends here
because sportsbook O/U lines score against the median, not the mean.

| Stat | MAE @ q50 | Recipe |
|------|----------:|--------|
| PTS  | 4.58 | sqrt + Huber XGB/LGB + 5-seed MLP, NNLS-stacked |
| REB  | 1.90 | log1p LGB quantile q50 |
| AST  | 1.34 | log1p XGB+LGB + multitask MLP, NNLS-stacked |
| FG3M | 0.88 | log1p XGB quantile q50 |
| TOV  | 0.89 | log1p XGB quantile q50 |
| STL  | 0.72 | log1p XGB quantile q50 |
| BLK  | 0.44 | log1p XGB quantile q50 |

Source: `data/cache/pregame_oof.parquet` (~51K held-out player-games/stat, byte-identical
to the calibration frame, monotonic non-overlapping folds). Competitive with published
prop-model benchmarks. **This is the honest core accuracy claim.**

### Win probability — 5-way NNLS stack

XGB + LGB + LR + MLP + NB over N=2,455 games: **70.9% ± 2.5pp accuracy / 0.193 Brier**
(3-fold walk-forward). The stack picks members by validation, not mandate — NNLS weighted
LGB 0.66 / NB 0.16 / LR 0.12 / MLP 0.03 and zeroed XGB autonomously.
Source: `data/models/win_prob_metrics.json`.

### In-play snapshot heads — endQ1 / Q2 / Q3

Per-snapshot LightGBM heads on thousands of game-snapshots, expanding-window walk-forward.

- **In-game MAE lift:** at end-of-Q3 the residual heads cut prediction MAE ~46% vs the
  pre-game baseline (240 held-out records, confirmed leak-free). Most of that is mechanical —
  three quarters of box score are observed. Over a naive carry-forward baseline the
  **learned-head value-add is ~26%**, walk-forward validated.
- **In-game win-prob Brier:** the leak-free endQ3 Brier is **~0.141** after removing two
  Q4-derived features that let the end-of-Q3 model peek at the quarter it predicts.
  (The retracted "0.119" was that leak — see the discipline section.)

### Validation infrastructure — the senior-grade differentiator

Walk-forward expanding CV with an **assertion-level per-fold leak guard**
(`assert max_train_date < min_test_date` every fold) + CI overfit gate; a
**truncation-invariance leak test** (re-featurize a truncated event stream, assert past rows
are byte-identical); a **multi-corpus calibration acceptance gate** (a calibration ships only
if it beats raw on ≥ 2 independent OOS corpora); and a documented self-catch of a
**0.79-CV-vs-0.06-holdout overfit** that was hard-corrected.

Methodology: [docs/ML_MODELS.md](docs/ML_MODELS.md) · validation doctrine:
[docs/research/validation-methodology.md](docs/research/validation-methodology.md)

---

## 4 · ENGINES — turning predictions into decisions

Models emit point + interval predictions. The engines turn distributions into prices and
sized decisions, and log everything for counterfactual calibration.

- **Possession Monte Carlo** ([`src/sim/basketball_sim.py`](src/sim/basketball_sim.py)) —
  simulates a game one possession at a time. Each possession is used by exactly one of five
  on-court players (a shared scoring pie drawn from real stint minutes), so teammates compete
  for the same possessions and the correct slightly-negative teammate correlation **emerges
  from the mechanics** (measured ρ ≈ −0.10 vs. realized, fixing a prior simulator's +0.65
  against a real −0.01). A vectorized `fast_sim` path rolls thousands of games; the same
  samples price **same-game parlays** off the true joint distribution (`sgp_from_sim.py`).
  Structure validated; no betting edge claimed.

- **Line evaluator** — Shin (1992) insider-trading devig via a numerically-stable bisection
  solver (+ additive / multiplicative / power), a multi-book line scanner, and a cross-book
  arbitrage detector streamed over SSE. `POST /api/devig` defaults to `shin`.

- **Decision engine** ([`src/prediction/decision_engine.py`](src/prediction/decision_engine.py))
  — gate chain (projection-sane, min-edge, multi-book consensus) → per-quarter EV floor →
  S/A/B/C tier classification.

- **Correlation-aware Kelly** ([`src/prediction/betting_portfolio.py`](src/prediction/betting_portfolio.py))
  — fractional Kelly-B sized off isotonic-calibrated probabilities, Ledoit-Wolf-shrunk
  prop-correlation penalty, drawdown breaker, hard cap.

- **Shadow logger + settlement** — every bet the engine evaluates is logged, **passed AND
  blocked, with a `gate_blocked_by` reason**; settlement joins the log to official finals
  nightly. This append-only counterfactual dataset is what makes filter calibration a
  re-derived result instead of guesswork. Anti-survivorship-bias by construction.

- **Execution stack** — 9 long-running daemons (in-play projection, auto-place/settle, CLV
  tracker, bankroll monitor, middle-finder, multi-book scraper, lineup ingest, dashboard)
  under a watchdog/registry supervisor; a transactional P&L ledger with cross-platform file
  locking; Slack/Discord alerting with rate limiting + per-channel circuit breakers;
  a drawdown kill-switch + ops/health dashboard.

---

## 5 · PREDICTIONS — the narrow end of the funnel

What comes out: per-player **q10/q50/q90 projections**, **win probabilities**, **EV** at
every book, **correlation-sized bets**, **2-/3-leg parlays and SGPs**, and a **live in-play
projection panel** — all surfaced over a FastAPI serving layer of **~99 endpoints across
12 routers** (REST + WebSocket + SSE), a server-rendered trading-desk dashboard
(18 Jinja templates), and a companion Next.js live frontend.

### The honest betting read

> **Against real closing lines, the market is efficient.** Re-graded against real
> DraftKings / FanDuel / MGM **closing** lines at real odds, the prop edge is roughly
> **break-even-minus-vig overall** (≈ −2% to −5%). The one genuinely positive, repeatable
> result is **assists (AST): ~+4–5% ROI**, positive across three independently-sourced line
> corpora, shown to be selection skill (positive in both directions, beats a blind-under
> baseline by ~12pp) — but **regime-dependent: the edge breaks in the playoffs.**

That finding is *stronger* than a fake ROI: it demonstrates the ability to tell a real edge
from a measurement artifact.

The in-play backtest (78% hit / +54% ROI on 55,073 calibrated bets) is real **but settles
against a soft L5 line proxy, not real closing lines** — a model-quality ceiling, not a
tradeable result. First real Pinnacle closing-line CLV reading: **October 2026**. Zero real
money has been placed, by design.

---

## 6 · INTELLIGENCE — the apex (and the loop that builds the rest)

The narrowest, most refined stage. The funnel doesn't end at a number — it ends at
*understanding*, and that understanding loops back to improve every stage above it.

- **1,249 per-player dossiers** (up to 28 statistical categories each, archetype-labeled,
  scheme-tagged) + **30 per-team scheme cards** (defensive-intensity z-scores, tempo/spacing
  profile, matchup notes).

- **Grounded AI chat surface** — `ai_chat_facts.json` (pre-extracted player + team facts)
  + `ai_chat_index.json` (topic → artifact routing) let an LLM answer basketball questions
  grounded in the intelligence layer instead of hallucinating.

- **The agentic system that builds all of the above.** Opus orchestrates, plans, and reviews;
  Sonnet executors implement in parallel branch-isolated batches; Haiku searches. A
  multi-agent coordination protocol runs unattended ~24-hour ship cycles without corrupting
  the repo. This is the system that autonomously discovers, validates, ships, and retires
  prediction signals under the same hard gate that rejects most of them.

**This is "the AI."** Stages 1–5 are the substrate; stage 6 is the part that *understands
the game* and rewrites the substrate. The feedback arrow in the funnel diagram is not
decoration — it's the product.

---

## The discipline — I built the instruments that caught my own hype

The single strongest signal in this repo is not a metric. It's that the validation harnesses
were built to *refute* the headlines, and when a famous number didn't survive, the honest
version was written down and the inflated one retired.

| Retracted headline | What actually happened | The honest version |
|---|---|---|
| **+18.38% ROI** on 1,535 walk-forward bets | Market-follow grading artifact — the grader picked bet direction from the market's own devigged favorite and never read the model (no prediction column in the eval), priced at a flat −110 fiction, with in-sample-tuned filters | **Break-even-minus-vig vs real closes; AST ~+4–5% the one durable edge.** Own reproduce command returns −2.00%. |
| **endQ3 Brier 0.119**, claimed "Pinnacle-class" | Two Q4-derived features leaked the predicted quarter into the end-of-Q3 model | **Leak-free endQ3 Brier ~0.141** — a leak I caught, not a competitive number |
| **+54.57% in-play ROI** | Graded against an L5 line proxy, not real closing lines | **Model-quality ceiling only**; first real CLV Oct 2026 |
| **"Built over 13 months"** | Git history spans ~3 months | **Intensive ~3-month build, 1,470 commits** (Mar–May 2026) |
| **"Solo-built, 1,470 commits"** (implied hand-typed) | ~91% agent-authored under direction | **Solo human architect/director of an agentic pipeline** — judgment, ship/reject, and validation are mine |

Three reproducible harnesses (`run_gate1_full_analysis.py`, `gate1_filtered_vs_vegas.py`,
`reconcile_edge_source.py`) debunked the flagship number and root-caused it to specific
lines of code.

Full adversarial audit, with every claim's proof artifact and a complete do-not-claim list:
**[docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)**

Open limitations tracked openly in **[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)**:
per-player CV attribution is early; the shipped OSNet runs ImageNet-pretrained weights
(production appearance model is the HSV histogram); a `sim_win_prob` polarity inversion is
documented and patch-gated; the fresh-clone repro path has a known feature-count drift in
the verify scripts.

---

## What's genuinely hard here

Most sports-prediction repos pick one hard thing. This system stacks several:

1. **Broadcast CV at consumer-GPU cost.** There is no ground truth, no clean feed, no stable
   camera. The homography drifts, the scoreboard flickers, IDs fragment across occlusions.
   Hardening this to ship-grade required ~10 documented sentinel-leak guards in the feature
   extractor, each tied to a specific observed failure mode.

2. **Leak-free time-series validation at scale.** Random K-fold leaks through residuals on
   any grouped time series. The harness enforces per-fold date ordering at the assertion
   level, plus a 48-hour same-team purge, plus a truncation-invariance property test. Most
   published sports-ML benchmarks don't do all three.

3. **Correct teammate correlation without a hand-tuned matrix.** Prior simulators hard-coded
   a correlation matrix (one published at +0.65 vs. a real −0.01). The possession-level
   Monte Carlo model gets the right sign *because* teammates share a scoring pie — it's a
   structural consequence, not a parameter.

4. **A self-improving loop with a gate that genuinely rejects.** An agent loop that only ever
   ships is just automated overfit. The gate here runs permutation controls, Benjamini-Hochberg
   FDR, and all-folds-must-improve walk-forward. The loop's most important outputs are the
   honest REJECTs.

5. **Multi-agent coordination without corruption.** Parallel executor agents on shared state
   is a known failure mode. The coordination log, range pre-assignment, and crash-safe
   checkpoint protocol are engineering work that doesn't appear in any commit message but
   shows up in the zero file-conflict count across 23+ shared-branch commits.

---

## Platform direction — kernel + adapter architecture

CourtVision is being generalized into a **domain-agnostic, multi-sport forecasting and
decision engine**. The architecture is a sport-agnostic `kernel/` paired with
`domains/<sport>/` adapters: adding a new sport means writing only the adapter.

A June 2026 audit of the 430-module codebase found that **~38% of the code is already
sport-agnostic kernel** — the honest validation gate, the walk-forward harness, calibration,
Kelly/CLV/devig math, the Monte Carlo simulation framework, the two-arm discovery loop,
the brain/flags registry, and the serving scaffolds. The NBA codebase becomes the reference
`domains/nba/` adapter. The kernel-level honest-edge discipline (accuracy ≠ edge, CLV > ROI,
nothing un-gated) is baked into the kernel as invariants — no domain adapter can weaken the gate.

The first second-domain proof-of-concept targets tennis. More detail (public-safe):
[docs/PLATFORM.md](docs/PLATFORM.md)

---

## Engineering snapshot

| | |
|--|--|
| **CV pipeline** | YOLOv8n + from-scratch Kalman/Hungarian tracker + OSNet re-ID + SIFT homography + EventDetector, ~$0.10–0.13/game |
| **Modules** | 430 Python modules across `src/`, `scripts/`, `api/`, `tests/` |
| **Prop models** | 7 heads (q10/q50/q90) · walk-forward MAE: PTS 4.58 / REB 1.90 / AST 1.34 / FG3M 0.88 |
| **Win probability** | 5-way NNLS stack · 70.9% acc / 0.193 Brier |
| **Intelligence** | 80-artifact layer · 291,625-pair matchup matrix · 690-node knowledge graph · 1,249 dossiers · 30 scheme cards |
| **Serving** | FastAPI ~99 endpoints / 12 routers (REST+WS+SSE) · 18-template trading desk · Next.js frontend |
| **Execution** | 9 watchdog'd daemons · transactional P&L ledger · Slack/Discord alerting · kill-switch + ops dashboard |
| **Persistence** | PostgreSQL-first schema (12 core tables) with transparent SQLite fallback + idempotent migrations |
| **Tests** | ~7,400 collected, ~97–98% pass (documented tail) · 3 GitHub Actions workflows · 5 Dockerfiles |
| **Agentic loop** | Opus planner + parallel Sonnet executors, branch-isolated, crash-safe state, hard ship gates |

### Discipline indicators

- Every candidate signal ships behind a walk-forward gate (all folds improve) + null-shuffle
  permutation (z ≥ 3) + ablation + Benjamini-Hochberg FDR. Most are correctly rejected.
- Quantile bands, not point estimates — q10/q50/q90 calibrated toward 80% empirical coverage.
- Shin (1992) bisection devig — sharp-book-correct, not the symmetric power-sum most public
  sports-ML code uses.
- Walk-forward season-purged validation with a 48-hour same-team purge.
- pkl integrity check after every retrain (`booster.num_feature() == meta['n_features_in_']`)
  — caught a silent ValueError that had been zeroing REB predictions.
- Multi-agent coordination log: parallel sessions on ~24-hour cycles, zero file conflicts
  across 23+ shared-branch commits.

---

## Tech stack

**ML / data:** Python 3.9, PyTorch 2.0.1 + CUDA 11.8, XGBoost, LightGBM, scikit-learn
(Isotonic + NNLS), NumPy, pandas, Optuna

**CV:** YOLOv8n (Ultralytics), OpenCV, SIFT homography, OSNet re-ID (torchreid), EasyOCR

**Serving:** FastAPI, uvicorn, SSE for live events, SQLite + parquet feature store,
Next.js, Railway / Fly deploy

**Data:** nba_api (box / PBP / lineups), cdn.nba.com live feeds, The Odds API,
custom Pinnacle / Bovada / FanDuel / PrizePicks scrapers

**Infra:** RunPod (RTX 3090), Backblaze B2, Docker, GitHub Actions CI

**Quant:** walk-forward CV (season-purged + 48hr same-team purge), Shin devig,
fractional Kelly-B, per-stat isotonic edge calibration, Ledoit-Wolf shrinkage,
NNLS stacking, shadow-logged settlement

**AI agents:** Claude Code — Opus orchestrator + parallel Sonnet executors, coordination
handshake, multi-wave autonomous loops with hard ship gates

---

## Quickstart

```bash
git clone <repo> && pip install -r requirements.txt

# Source-of-truth metrics (committed JSON):
#   data/models/quantile_pergame_metrics.json   prop MAE @ q50
#   data/models/win_prob_metrics.json           win-prob acc / Brier

# Real-Vegas Gate 1 — re-grade vs real DK/FD/MGM/BetRivers closes
python scripts/run_gate1_full_analysis.py        # → ~-2.00% unfiltered (market efficient)

# In-game win-prob OOS validation (exposes the in-sample leakage)
python scripts/oos_validate_inplay_2026_05_27.py

# In-play paper-ceiling backtest, L5 proxy (~10-15 min) — read the L5 caveat
python scripts/run_backtest.py --n-games 50

# Trading desk dev server
uvicorn api.main:app --reload
#   /scan  /parlays  /clv  /live/<game_id>

# Full test suite
python -m pytest tests/ -q
```

> The verify scripts have a known fresh-clone feature-count drift (documented in
> [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)); the committed JSON is the
> source of truth for the numbers above.

---

## Repo map

| Path | Contents |
|------|----------|
| `src/tracking/` | YOLOv8, OSNet re-ID, SIFT homography, EventDetector, from-scratch tracker |
| `src/features/` | feature engineering (60+ features + CV bridge) |
| `src/prediction/` | ~130 modules — ~12 load-bearing, rest research/experiments/dormant |
| `src/sim/` | player-level possession Monte Carlo + SGP joint pricing |
| `src/loop/` | two-arm self-improving signal/intel discovery daemon + ship gate |
| `src/ingame/` | in-game state engine, routed ensemble, universal win-prob, projectors |
| `src/brain/` | feature-flag registry, control brain, discovery gate |
| `src/calibration/` | cohort calibrator, conformal prediction, multi-corpus gate |
| `src/pipeline/` | unified CV pipeline orchestrator |
| `src/ingest/` | SQLite queue, yt-dlp, B2 sync, parallel game ingest |
| `api/` | FastAPI serving — ~99 endpoints / 12 routers + Jinja trading desk |
| `webapp/` | Next.js live-v2 frontend |
| `scripts/` | training, probes, daemons, ops CLIs, intelligence builders |
| `tests/` | ~7,400 tests — walk-forward gates, leak tests, integration, E2E |
| `data/models/` | registered model artifacts + segment-filter dicts (large ones gitignored) |
| `data/intelligence/` | 80-artifact intelligence layer (gitignored; manifest in docs/INTELLIGENCE.md) |
| `data/shadow/` | per-game evaluation logs (passed + blocked bets) |
| `docs/` | deep-dives — start with JOB_EVIDENCE_PACKET.md |
| `ARCHITECTURE.md` | funnel + component status with live/planned flags |

---

## Deep-dives

| Document | What it covers |
|----------|----------------|
| [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) | Every claim's proof artifact + the do-not-claim list — **start here** |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Component-by-component funnel with live/planned status |
| [docs/CV_TRACKING.md](docs/CV_TRACKING.md) | CV pipeline internals, per-component caveats |
| [docs/ML_MODELS.md](docs/ML_MODELS.md) | Model recipes, validation methodology, walk-forward design |
| [docs/INTELLIGENCE.md](docs/INTELLIGENCE.md) | 80-artifact layer manifest with schemas and row counts |
| [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | Open gaps, bugs, and what is not yet demonstrated |
| [docs/PLATFORM.md](docs/PLATFORM.md) | Kernel + adapter multi-sport architecture direction |

---

## Contact

Solo-built (human-directed agentic pipeline). Available for senior ML / computer-vision /
data / founding-engineer roles.

- **Start here:** [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) — the honest, audited account
- **Portfolio:** [neelshahportfolio.netlify.app](https://neelshahportfolio.netlify.app)
- **Email:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

*The funnel is the system: broadcast video → court coordinates → signals → models → engines
→ predictions → intelligence, with an agentic loop that re-validates every stage. Numbers
throughout are the leak-free, audited figures; retracted headlines and their root causes are
documented in [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md) and
[docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).*
