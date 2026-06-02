# Job Evidence Packet — Neel Shah

> An honest, recruiter-facing summary of what this project demonstrates. Every claim
> below was independently verified against the code, tests, and data artifacts by an
> adversarial audit whose job was to *refute* the headlines, not confirm them. Where a
> famous number did not survive scrutiny, the honest version is stated and the inflated
> one is listed in the "Do Not Claim" section so it never reaches a recruiter.
>
> The single strongest signal in this repo is not any metric. It is that the same person
> who built the system also built the instruments that caught his own overclaims, and
> documented the negative results in writing.

---

## 1. One-line pitch + who this is

**Pitch:** Solo builder of an end-to-end computer-vision → ML → full-stack production
system who rigorously audits and disproves his own results — senior-grade engineering
discipline without a degree.

He is a self-taught, hands-on systems engineer who built a complete NBA broadcast-video
CV pipeline, a multi-output ML prediction stack, and a multi-service FastAPI/daemon
serving platform, mostly by architecting and directing an agentic build workflow (a
planner model orchestrating cheaper executor models under hard ship gates). What sets him
apart is not the surface area but the validation rigor: he built walk-forward CV with
assertion-level leak guards, truncation-invariance leak tests, a multi-corpus calibration
acceptance gate, and reproducible audit harnesses — and then used those harnesses to catch
and publicly document leaks and measurement artifacts in his *own* flagship numbers. He
has no CS degree, but the work is demonstrably mid-to-senior level in CV, ML engineering,
and backend/data-platform engineering, and his honesty-first methodology is the kind a
hiring manager actually wants.

---

## 2. Defensible evidence (the spine of the pitch)

Each item below is verifiable from the public repo. Proof artifacts are listed so a
recruiter or interviewer can check them directly.

### A. Computer-vision pipeline (mid-level CV Engineer)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| End-to-end broadcast-video → court-coordinate tracking pipeline, running on a single consumer RTX 4060 | Runs end-to-end and writes `data/tracking_data.csv` with per-track court coords + behavioral fields; `src/pipeline/unified_pipeline.py`, `src/tracking/advanced_tracker.py` | "Built a full CV tracking pipeline that converts NBA broadcast video into player court coordinates and behavioral features end-to-end, on a single consumer GPU." |
| Multi-object tracker implemented from primitives (not a black-box wrapper) | 6D constant-velocity Kalman filter + Hungarian assignment over a blended IoU+appearance cost, with a greedy fallback; `src/tracking/advanced_tracker.py` `_make_kf()` / `_assign()` | "Implemented the tracking math from scratch — Kalman filtering for motion prediction and the Hungarian algorithm for globally-optimal frame-to-frame ID assignment." |
| Custom-trained single-class ball detector, deployed across PyTorch/ONNX/TensorRT | `scripts/train_ball_yolo.py` (YOLOv8n fine-tune); weights `models/weights/yolov8n_ball.{pt,onnx,engine}` | "Trained a custom ball detector by fine-tuning YOLOv8n and exported it to ONNX and TensorRT for deployment." |
| Per-clip court homography from classical CV, with static-matrix fallback | `src/tracking/court_detector.py` (HSV masking, HoughLinesP, line-intersection cornering, `getPerspectiveTransform`); `tests/test_court_detector.py` 7/7 pass on synthetic courts | "Wrote a court-calibration module that recovers the camera-to-court homography from broadcast frames using classical CV, with unit tests on synthetic courts." |
| Broadcast-hardened homography (inlier gating, EMA smoothing, drift re-anchoring, replay/scene-cut suspension) | SIFT three-tier strategy + constants in `unified_pipeline.py`; `tests/test_homography_thresholds.py` verifies the 2-frame confirmation gate | "Hardened camera-tracking for messy broadcast footage so player trajectories aren't corrupted during graphics/replays." |
| OSNet-x0.25 re-ID network reimplemented from scratch in PyTorch, with a layered inference backend | `src/tracking/osnet_reid.py` (omni-scale blocks, depthwise-separable convs); fallback chain TensorRT → torchreid → standalone → MobileNetV2 → HSV histograms | "Reimplemented the OSNet omni-scale re-ID architecture in PyTorch with a multi-tier inference backend." *(Caveat: ships with ImageNet-pretrained weights, not NBA-fine-tuned; the production appearance model is the HSV histogram. See §4.)* |
| Graceful degradation across missing deps/hardware | Pipeline runs with torchreid/kornia/PyAV/PaddleOCR all absent (SIFT instead of LoFTR, EasyOCR instead of PaddleOCR, CSV instead of Postgres) | "Every accelerated component has a graceful CPU/CPU-lib fallback, so it runs on a laptop or a GPU server without code changes." |
| Feature layer hardened against silent data-corruption | `src/pipeline/tracking_feature_extractor.py`: pixel-vs-feet auto-rescale, physical-validity caps, phantom-slot filtering, ~10 documented sentinel-leak fixes (`Bug 30/31/34/...` comments) | "Hardened the feature layer against the silent-corruption failure modes broadcast CV is prone to, each guard tied to a specific observed artifact." |
| Re-ID resolves anonymous slots to real NBA player identities at scale | `data/nba_ai.db` `cv_features`: 17,254 rows / 241 games / 252 distinct real NBA player IDs | "Resolved anonymous CV tracker slots to real NBA player identities across 240+ games via jersey/color/re-ID." |

### B. System architecture & breadth (mid → senior backend / data-platform)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| FastAPI serving layer of ~99 endpoints across 12 routers (REST + WebSocket + SSE) | Booting `api.main:app` enumerates 99 distinct (method,path) routes, 2 WebSockets, 16 tag groups — counted at runtime, not by decorators | "Architected a FastAPI serving layer of ~99 endpoints across 12 routers (props, live win-prob, devig/EV, CLV, risk/kill-switch, multi-book line scan)." |
| Fleet of 9 real long-running daemons + watchdog/registry supervisor | All 9 files present, 371–868 LOC each, with genuine loop/scheduler logic; `daemon_watchdog.py` + `daemon_registry.json` | "Built a 9-daemon live execution loop (in-play projection, auto-place/settle, CLV, bankroll monitor, middle-finder, multi-book scraper, lineup ingest, dashboard) with a watchdog supervisor." |
| Dual-backend persistence (PostgreSQL-first, transparent SQLite fallback) + idempotent migrations | `database/schema.sql` (12 core tables, PG dialect); `src/data/db.py` auto-translates PG SQL to SQLite; `src/data/migrations.py` tracks applied files | "Designed a relational schema on PostgreSQL with a zero-config SQLite fallback that auto-translates PG SQL, behind a unified cursor interface and idempotent migration runner." |
| Production alerting subsystem (Slack/Discord) | `scripts/execute_loop/L22_alerting.py` (669 LOC): token-bucket rate limiting, atomic-write dead-letter queue, per-channel circuit breaker, EventBus integration; 15 tests pass | "Engineered a Slack/Discord alerting layer with rate limiting, atomic-write retry queue, and per-channel circuit breakers." |
| Transactional P&L ledger | `src/betting/pnl_ledger.py` (562 LOC): place/settle/void, cross-platform file locking with stale-lock recovery, atomic writes, ROI/win-rate/Sharpe aggregation | "Designed a transactional P&L ledger with cross-platform file locking, atomic writes, and automatic settlement from game logs." |
| Multi-book scraper fleet with genuine API reverse-engineering | `scripts/draftkings_scraper.py` et al.: curl_cffi browser impersonation, live-vs-pregame contamination gate | "Reverse-engineered scrapers/WebSocket feeds for 6+ sportsbooks with browser-fingerprint impersonation and a live/pregame contamination guard." *(Caveat: DK/Caesars/MGM are IP-blocked in production; live coverage is a subset. See §4.)* |
| Cross-book arbitrage / line-shopping detector streamed over SSE | `api/_courtvision_odds.py::cross_book_spread` (implied-prob de-vig, freshness gating, tiered confidence); `scripts/arb_emitter_daemon.py` → `/sse/live_edges` | "Implemented a cross-book arbitrage detector (de-vig, freshness gating, capture-skew tiering) that streams opportunities to the dashboard over SSE." |
| Risk-management surfaces (auto kill-switch + ops/health dashboard) | Live `/api/risk/status` returns an auto-engaged drawdown kill-switch; `/health/ops` aggregates scraper lag, CLV hit-rate, drift flags, freshness | "Added operational guardrails: a drawdown-triggered kill switch and an ops/health dashboard so an automated system can fail safe." |
| Real CI/CD + multi-target deploy packaging | 3 GitHub Actions workflows (test+coverage gate, scheduled scrape); 5 Dockerfiles; `railway.json`, `fly.toml`, `nixpacks.toml`, `Procfile` | "Set up CI/CD on GitHub Actions and containerized the system into 5 purpose-built Docker images deployable to Railway/Fly." |
| Explicit research-vs-runtime separation (judgment signal) | README documents that ~130 `src/prediction` modules are a research surface with only ~12 load-bearing in the deployment graph | "Explicitly separates a large experiment surface from a small load-bearing deployment graph — judgment about what is actually in production." |

### C. ML / validation methodology (the senior-grade differentiator)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Walk-forward (expanding-window) CV with assertion-level per-fold leak guard + overfit-gap CI gate | `src/prediction/walk_forward_backtester.py` asserts `max_train_date < min_test_date` every fold; `scripts/run_walk_forward.py --gate` exits 1 on overfit | "Built a walk-forward CV harness with an assertion-level leakage guard on every fold and a CI gate that fails the build on overfitting." |
| Truncation-invariance leak test for streaming features | `tests/test_ingame_leak_free.py`: re-featurizes a truncated event stream and asserts past rows are byte-identical; passes | "Wrote property-based leakage tests that catch lookahead bias by asserting truncation invariance — a feature at time T is identical with or without future events." |
| Shin (1992) insider-trading de-vig model from scratch (+ 3 other methods), production-wired | `src/prediction/devig.py` (numerically-stable bisection solver); 7 tests; `POST /api/devig` defaults to `shin` | "Implemented four de-vig methods from scratch — including the Shin (1992) model via a stable bisection solver — and verified the output matches published theory." |
| Multi-corpus calibration acceptance gate (must beat raw on ≥2 independent corpora) | `scripts/validate_calibration_multicorpus.py` + tests (min-sample filter, least-intervention tie-break, strict train-before-eval guard) | "Designed a calibration-acceptance protocol that only ships a calibration if it beats raw on ≥2 independent OOS corpora — preventing single-window overfit from masquerading as a durable gain." |
| Append-only shadow-logging + overnight settlement (anti-survivorship-bias) | `src/prediction/shadow_logger.py` (logs passed AND blocked bets); `src/prediction/settlement.py` (scores vs final box scores) | "Built shadow-logging that records every bet the engine evaluated — including rejected ones — and a settlement engine, creating a counterfactual dataset to calibrate thresholds against real outcomes." |
| Fractional-Kelly sizing with correlation penalty, drawdown breaker, isotonic-calibrated input | `src/prediction/betting_portfolio.py::kelly_corr` (quarter-Kelly, persisted prop-correlation matrix shrink, drawdown halt, cap, isotonic win-prob override) | "Implemented fractional-Kelly bankroll management wired to calibrated probabilities — correlation-aware, drawdown-gated, capped." |
| Self-caught overfit, hard-corrected | `src/prediction/prop_cv_split.py` documents a leaky grid-search (train R² ~0.79 vs honest holdout ~0.06 on stl/blk) and applies corrective regularization that takes precedence over the stale tuned params | "Caught a real leakage-driven overfit in my own pipeline — 0.79 CV R² vs 0.06 leak-free holdout — and hard-coded the corrective regularization so the mistake can't silently reappear." |
| Written validation doctrine (CLV over ROI, null hypothesis, no K-fold on time series) | `docs/research/validation-methodology.md` | "Documented a disciplined methodology that treats beating the sharp closing line (CLV, significance-tested) as the proof of edge above noisy ROI, and bans K-fold CV on time-ordered data." |

### D. Full-stack surfaces (founding-engineer / generalist breadth)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Server-rendered live trading-desk dashboard (FastAPI + Jinja) | `api/templates/` (18 templates); TestClient GETs return real HTML (`/tonight`=54KB, `/results`=38KB, etc.) | "Shipped a server-rendered live betting dashboard (slate, CLV, parlays, line-scanner, results), backed by the API." |
| Companion Next.js/React frontend | `webapp/` (Next.js app, `app/page.tsx` + 8 components, `vercel.json`) | "Built a lightweight Next.js/React live-v2 frontend." *(Secondary surface; lead with the FastAPI/Jinja dashboard. See §4.)* |
| Large, real test suite | ~7,400 tests collected across ~580 files; betting-math core (devig/CLV/calibration) and in-play subset run green | "Maintain a ~7,400-test pytest suite; the betting-math core and in-play subset pass clean." *(Do not claim 100% green — see §4.)* |

### E. Agentic discovery loop + orchestration (current-era senior signal)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Autonomous two-arm self-improvement daemon | `scripts/loop/run_loop.py` + `src/loop/`: checkpoint/resume, FDR budget, one-time held-out flag, per-hypothesis backoff; 166/168 tests pass | "Built an autonomous research daemon that mines residuals into hypotheses, validates each behind a statistical gate, and persists results — with checkpoint/resume and a one-time held-out budget." |
| Rigorous "ship gate" built to refute, not confirm | `src/loop/gate.py`: expanding walk-forward (all folds must improve), null-shuffle permutation control (z ≥ 3), ablation-vs-full-model, train-median impute, Benjamini-Hochberg FDR | "Wrote the validation gate that decides whether a candidate signal ships — walk-forward + permutation test + marginal-lift ablation + multiple-comparisons correction. Most candidates correctly get rejected." |
| Multi-agent orchestration playbook | `.claude/commands/workday-loop.md` (298 lines): model-tier routing, parallel branch-isolated execution, protected-file guardrails, atomic crash-safe state, self-stocking queue | "Authored the orchestration playbook for a cost-aware multi-agent coding loop — planner orchestrates, executors implement in parallel branch-isolated batches — that runs unattended without corrupting the repo." |

### F. Intelligence / data-engineering layer

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| 291,625-pair player-vs-player matchup matrix from 2,214 raw tracking files across 3 seasons | `data/cache/coverage_faced_allseasons.parquet` (verified 291,625 rows); `scripts/intel/build_coverage_allseasons.py` | "Built a 291K-row player-vs-player matchup database from 2,214 raw per-game tracking files across three seasons." |
| Idempotent single-writer knowledge graph (690 nodes) | 660 player + 30 team notes with marker-delimited folds; `scripts/intel/outcome/fold_outcome_impact.py` | "Designed an idempotent single-writer fold to merge ~80 derived artifacts into a 690-node knowledge graph without duplication on re-run." |
| Leak-safe as-of feature builders with confound flagging | `scripts/intel/outcome/build_player_availability.py` (expanding shift(1), schedule-confound downgrade); metadata bakes in "descriptive not causal, not a betting edge" | "Wrote point-in-time-correct builders using strict expanding-window shift(1) joins, and documented the statistical limitations in each artifact's metadata." |
| Adversarial self-audit caught a real attribution bug and scoped its blast radius | `docs/_audits/HARDENING_SWEEP_INTEL_ARTIFACT_BUILDERS_2026-06-02.md` — defender-team tricode inversion confirmed LATENT (no live consumer) | "Ran an adversarial audit of my own pipeline that surfaced an attribution bug, then traced its full blast radius to prove it was confined to an unused offline field." |

---

## 3. Honest numbers (what survives leak-free scrutiny)

These are the metrics that hold up. Each is paired with what the *inflated* version
claimed, so the candidate can pre-empt the gap rather than be caught by it.

### Prediction accuracy (leak-free walk-forward, ~51k held-out player-games per stat)

- **PTS MAE ~4.58, REB ~1.90, AST ~1.34, FG3M ~0.88**, with a small consistent under-bias
  (~-0.45 PTS). Computed directly from `data/cache/pregame_oof.parquet`; the OOF predictions
  are byte-identical to the calibration frame's predictions (max abs diff 0.0 over 319,081
  rows), and folds have monotonic non-overlapping holdout windows.
- These are competitive with published prop-model benchmarks. **This is the honest core
  accuracy claim — lead with it.**

### Betting edge vs real closing lines — "the market is efficient" (a sophisticated, honest finding)

- Against real DraftKings/FanDuel/MGM **closing** lines, the model is **roughly
  break-even-minus-vig overall** (whole book ~break-even on the coherent corpus; ~-2% to -5%,
  with a -2.00% unfiltered figure from `gate1_full_analysis.json`). The market is efficient
  on closing lines.
- **The one genuinely positive, repeatable stat is assists (AST): ~+4–5% ROI**, positive on
  three independently-sourced line corpora. Stress-tested and shown to be *selection skill*,
  not an under-bias artifact (positive in both over/under directions; beats a blind-under
  baseline by ~12pp; the flipped "anti-model" loses cleanly). It is **book-robust but
  regime-dependent** — durable core ~+5%, the higher gated figures are in-window peaks, and
  **the edge breaks in the playoffs.** Size on the conservative number.
- **The honest framing:** "Against real closing lines I found the market is efficient — the
  model is about break-even-minus-vig, with assists the one small, durable edge. That is a
  sophisticated and honest result, and I have the harnesses that prove it." This is *stronger*
  than a fake ROI because it shows the candidate can tell a real edge from a measurement
  artifact.

### In-game (end-of-Q3) projection MAE lift — leak-clean

- End-of-Q3 residual heads cut prediction MAE substantially vs the pre-game baseline,
  **confirmed leak-free** (the heads use a clean 14-feature schema and do **not** share the
  Q4-feature leak that contaminates the separate win-probability model). Corroborated by two
  independent walk-forward harnesses (`retro_inplay_mae.py` and `.planning/ingame/eval_routed.md`,
  240 held-out records → ~46% pooled MAE reduction; team-score ridge head ~52% total / ~64%
  margin MAE reduction).
- **Honest framing of the magnitude:** most of the ~46% lift vs pre-game is *mechanical*
  (three of four quarters of box score are observed). Over a naive carry-forward in-game
  baseline the learned-head value-add is **~26%**, validated walk-forward. State it that way.
- **Quote the MAE lift alone. Never bundle it with the endQ3 Brier** (the Brier model is
  leak-inflated; see below) — keep the clean MAE story away from the contaminated Brier.

### In-game win-probability Brier — honest leak-free number

- The famous **endQ3 Brier 0.1191 "inside Pinnacle's range" is leak-inflated and mis-sourced.**
  Two features (`halftime_pace_shift`, `trailing_team_q4_usg_hhi` in `build_quarter_features.py`)
  are computed from 4th-quarter data — the end-of-Q3 model peeks at the quarter it predicts.
  The cited source file actually reports 0.1354, not 0.1191.
- **Honest version:** the leak-free walk-forward endQ3 Brier is **~0.141** (after removing the
  two Q4-derived features). A controlled A/B showed the leak inflated it by ~4% relative.
  **Frame this as a leak you caught in your own pipeline**, not as a competitive number, and do
  not claim "Pinnacle-class."

### The self-caught leaks ARE the strength

Frame every item above as evidence of senior judgment:

- He built three independent reproducible harnesses (`run_gate1_full_analysis.py`,
  `gate1_filtered_vs_vegas.py`, `reconcile_edge_source.py`) that **debunked his own flagship
  "+18.38% ROI"** and root-caused it to specific lines of code (the grader bet the market's
  devigged favorite — the model was never read — and priced at a flat -110 fiction, with
  in-sample-tuned filters).
- He found and quantified a **Q4 lookahead leak** in his own win-prob features, and labels
  leaked-vs-honest metrics directly in code docstrings.
- He caught a **0.79-CV-vs-0.06-holdout overfit** and hard-corrected it.
- His `docs/KNOWN_LIMITATIONS.md` openly states per-player CV attribution is ~4% accurate and
  "CV signal at scale — unproven."

**The pitch:** "I build ambitious systems and then build the instruments to disprove my own
hype. Here is exactly what works and exactly what I have not yet validated." That is a rare and
high-value senior-engineering signal — especially for a candidate without a degree.

---

## 4. Do-not-claim list (never put these in front of a recruiter)

These numbers are inflated, leaked, artifactual, or unverifiable. A probing recruiter who runs
the repo will catch each one — which is disqualifying for a no-degree candidate. Drop them.

| Do NOT claim | Why it fails | Say instead |
|---|---|---|
| **"+18.38% ROI on 1,535 walk-forward bets vs real closing lines"** (also +15.04% flat, and per-stat splits BLK +26% / STL +17% / etc.) | **Market-follow artifact, confirmed at the source-code level.** The grader picks bet direction from `devig(over_odds, under_odds)` — the market's own lean — and never reads the model (the eval CSV has no prediction column); prices at a flat -110 fiction; filters tuned in-sample on the same file (ROI climbs +7.78%→+15.22% as filters stack). At real odds it is ~-4%; the model's own number is -2.00%. The repo's own "reproduce" command returns -2.00%, contradicting the headline. | "Roughly break-even-minus-vig vs real closing lines; assists ~+4–5% is the one durable edge." |
| **"endQ3 in-play Brier 0.1191, inside Pinnacle's range"** | **Leak-inflated AND mis-sourced.** Fed two Q4-derived features (peeks at the predicted quarter); the leak is in training, the OOS validators, AND the live serving path. Cited file actually reports 0.1354. | "Leak-free walk-forward endQ3 Brier ~0.141, after I removed a Q4 feature leak I found in my own pipeline." |
| **"+54.57% ROI / 78.11% hit on 55,073 in-play bets"** | Graded against an **L5 line proxy**, not real closing lines. A model-quality ceiling, not a tradeable result. | "On a soft L5 proxy the in-play backtest hits 78%/+54% — I treat that strictly as a model-quality ceiling, never as realized edge." |
| **"Aggregate CLV +8.94pp" / "+18.38% sits at the Kelly ROI ceiling"** | Circular — computed on the same model-unused, devig-direction corpus; Kelly stakes were synthesized from the same hit rate. No real Pinnacle-close CLV exists yet (first reading dated Oct 2026). | Don't quote a CLV figure. "Real closing-line CLV can't be measured yet; I built the methodology that will measure it." |
| **"Re-ID accuracy ~91%, homography RMSE ~4.2px, 28 FPS, ball-valid 87%"** | **Unbacked.** The referenced benchmark test does not exist; the only real benchmark reports lower/different values with no re-ID-accuracy or homography-RMSE measurement at all. | Present as roadmap targets, never achieved metrics. Cite the **self-consistency tracking-quality gates** instead, and call them that. |
| **"Tracks 10 players at 15 fps"** | Could not reproduce — observed ~1.6–2.6 tracked players/frame (max 4) on real broadcast footage; ~7–11 fps. | "The detector finds all 10 players; the tracker maintains up to ~5–6 stable slots on the calibration clip; reliable 10-player broadcast tracking is not yet demonstrated." |
| **"Position accuracy ±12–18 inches" / "0 ID switches" / "track stability 1.0"** | No ground-truth labels exist; these are estimates or self-consistency proxies (`evaluate.py` returns `self_evaluation: True`), not validated MOT metrics (no MOTA/IDF1). | "Outputs court coordinates via homography; positional accuracy and MOT metrics are not yet benchmarked against labeled ground truth." |
| **"CV features are a predictive moat / edge sportsbooks lack"** | **Zero measured predictive value today** — production prop models assign every CV feature SHAP importance = 0.0; `cv_lift_report.json` is `has_cv_data: false`. | "CV-derived features are wired in as a potential future edge; they don't yet move the model (SHAP ~0). Credible thesis and complete plumbing, not a demonstrated advantage." |
| **"I trained a deep re-ID model"** | The shipped OSNet weights are **ImageNet-pretrained, not NBA-fine-tuned**; in the runnable config OSNet is effectively random-initialized and the production appearance model is the HSV histogram. | "I reimplemented the OSNet architecture in PyTorch and run it with ImageNet-pretrained weights." |
| **"Built over 13 months"** | **Not supported by git** — history spans ~3 months (2026-03-09 to 2026-05-31). A recruiter checking the public GitHub sees <3 months; the claim collapses. | "An intensive ~3-month solo build (1,470 commits, Mar–May 2026)." Drop the 13-month figure entirely unless an artifact predating the repo can be shown. |
| **"Solo-built / I wrote 1,470 commits"** (implied hand-typed) | **91% of commits are agent-authored** (GSD Executor); ~54% carry a Claude co-author trailer. The work is heavily AI-agent-generated under direction. | "Solo human architect/director of an agentic build pipeline. The engineering judgment, ship/reject decisions, and validation methodology are mine." (The README already discloses this — keep that honesty front-and-center.) |
| **"70 iterations / 29 ships / 41 reverts" as a code-artifact or ledger count** | Only ~39 iter files on disk; exactly one revert doc exists; no machine-checkable ledger backs the 29/41 split. The autonomous daemon's ledger tells a different story (1 signal ship vs 9 reject/variance + 48 atlas ships). | "Ran a documented iteration campaign; most candidates were correctly rejected by the gate, by design." Cite the CHANGELOG as the source, not a hard split. |
| **"All ~7,400 tests pass / full suite is green"** | **Not currently true** — ~97–98% pass locally with a documented tail (DB/GPU/optional-dep/version drift), a few real logic-drift failures, and a native pyarrow segfault that blocks a clean one-shot full run on Windows. CI enforces only a 30% coverage floor. | "~7,400 tests, ~97–98% passing, with a documented tail tracked in KNOWN_LIMITATIONS. Core betting-math and in-play subsets pass clean." Never claim a coverage %. |
| **"Run my verify scripts to reproduce the headlines"** | `verify_production_mae.py` (the README's headline command) **crashes** with an 85-vs-129 feature mismatch; `verify_winprob.py` reads an uncommitted cache and **fails from a fresh clone**; training data is gitignored. | "I built a self-auditing verification harness (tolerance gates, drift reports, CI-oriented); closing the fresh-clone reproducibility gap is known work." Do not invite a live repro until fixed. |
| **Any "quant alpha / P&L track record" framing** | There is **no verified leak-free profitable edge.** Applying to quant roles on a P&L story would be caught immediately. | Apply as an ML-infra/modeling/CV hire. "I built the full quant toolchain — devig, Kelly, CLV, calibration, walk-forward backtesting — and ran the validation that proved the apparent edge was an artifact." |

**Pre-outreach action items flagged by the audit (not claims, but housekeeping):**

1. **Rotate the the-odds-api key** (it sits in 6 untracked, non-gitignored scripts; a blanket
   `git add -A` would publish it) and add those scripts to `.gitignore` or move the key to `.env`.
2. **Remove/parameterize the personal phone number + home city** hardcoded in
   `scripts/build_cv_resume.py:58` and `scripts/build_resume.py:58`.
3. **Reconcile the public docs** — `README.md`, `docs/PUBLIC_EVIDENCE.md`, and `CLAUDE.md`
   still headline +18.38% and endQ3 0.1191 with no caveat, while `docs/VS_VEGAS_ASSESSMENT.md`
   debunks them. The honesty docs must come *before* the inflated ones, or fix the inflated
   ones, before any recruiter sees the repo.

---

**Contact:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

*Audit basis: independent verification in conda env `basketball_ai` (Python 3.10, CUDA, RTX
4060) — pipeline run on real video, FastAPI app booted to count routes, ~170+ tests executed,
schemas/artifacts read directly, headline graders read line-by-line. No repo files were edited
during the audit.*
