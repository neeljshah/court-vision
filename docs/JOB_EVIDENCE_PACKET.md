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
discipline.

**The honest headline finding (§3):** against real closing lines I found the market is
efficient — the model is about break-even-minus-vig, with assists the one small, durable
edge. That is a sophisticated and honest result, and I have the harnesses that prove it.

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
| 430-module codebase with explicit research-vs-runtime separation | `src/` contains 430 Python modules; ~130 in `src/prediction/` are a research surface with only ~12 load-bearing in the live deployment graph | "Designed a 430-module codebase and explicitly separated a large experiment surface from a small load-bearing deployment graph — judgment about what is actually in production." |
| Dual-backend persistence (PostgreSQL-first, transparent SQLite fallback) + idempotent migrations | `database/schema.sql` (12 core tables, PG dialect); `src/data/db.py` auto-translates PG SQL to SQLite; `src/data/migrations.py` tracks applied files | "Designed a relational schema on PostgreSQL with a zero-config SQLite fallback that auto-translates PG SQL, behind a unified cursor interface and idempotent migration runner." |
| Production alerting subsystem (Slack/Discord) | `scripts/execute_loop/L22_alerting.py` (669 LOC): token-bucket rate limiting, atomic-write dead-letter queue, per-channel circuit breaker, EventBus integration; 15 tests pass | "Engineered a Slack/Discord alerting layer with rate limiting, atomic-write retry queue, and per-channel circuit breakers." |
| Transactional P&L ledger | `src/betting/pnl_ledger.py` (562 LOC): place/settle/void, cross-platform file locking with stale-lock recovery, atomic writes, ROI/win-rate/Sharpe aggregation | "Designed a transactional P&L ledger with cross-platform file locking, atomic writes, and automatic settlement from game logs." |
| Multi-book scraper fleet with genuine API reverse-engineering | `scripts/draftkings_scraper.py` et al.: curl_cffi browser impersonation, live-vs-pregame contamination gate | "Reverse-engineered scrapers/WebSocket feeds for 6+ sportsbooks with browser-fingerprint impersonation and a live/pregame contamination guard." *(Caveat: DK/Caesars/MGM are IP-blocked in production; live coverage is a subset. See §4.)* |
| Cross-book arbitrage / line-shopping detector streamed over SSE | `api/_courtvision_odds.py::cross_book_spread` (implied-prob de-vig, freshness gating, tiered confidence); `scripts/arb_emitter_daemon.py` → `/sse/live_edges` | "Implemented a cross-book arbitrage detector (de-vig, freshness gating, capture-skew tiering) that streams opportunities to the dashboard over SSE." |
| Risk-management surfaces (auto kill-switch + ops/health dashboard) | Live `/api/risk/status` returns an auto-engaged drawdown kill-switch; `/health/ops` aggregates scraper lag, CLV hit-rate, drift flags, freshness | "Added operational guardrails: a drawdown-triggered kill switch and an ops/health dashboard so an automated system can fail safe." |
| Real CI/CD + multi-target deploy packaging | 3 GitHub Actions workflows (test+coverage gate, scheduled scrape); 5 Dockerfiles; `railway.json`, `fly.toml`, `nixpacks.toml`, `Procfile` | "Set up CI/CD on GitHub Actions and containerized the system into 5 purpose-built Docker images deployable to Railway/Fly." |

### C. ML / validation methodology (the senior-grade differentiator)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Walk-forward (expanding-window) CV with assertion-level per-fold leak guard + overfit-gap CI gate | `src/prediction/walk_forward_backtester.py` asserts `max_train_date < min_test_date` every fold; `scripts/run_walk_forward.py --gate` exits 1 on overfit | "Built a walk-forward CV harness with an assertion-level leakage guard on every fold and a CI gate that fails the build on overfitting." |
| Truncation-invariance leak test for streaming features | `tests/test_ingame_leak_free.py`: re-featurizes a truncated event stream and asserts past rows are byte-identical; passes | "Wrote property-based leakage tests that catch lookahead bias by asserting truncation invariance — a feature at time T is identical with or without future events." |
| Full-season walk-forward proving market efficiency | Season backtest (truncation-invariance PROVEN, 2025-26 season): well-calibrated (Brier 0.208 vs close 0.198) but does not beat the close; spread/total pregame CLV ≈ 0 (corr-with-outcome = 0.001). The cleanest market-efficiency proof in the system. | "I ran a full-season leak-free backtest that proved the model is well-calibrated but does not beat sharp closing lines — the honest finding a validation framework is *supposed* to produce." |
| Shin (1992) insider-trading de-vig model from scratch (+ 3 other methods), production-wired | `src/prediction/devig.py` (numerically-stable bisection solver); 7 tests; `POST /api/devig` defaults to `shin` | "Implemented four de-vig methods from scratch — including the Shin (1992) model via a stable bisection solver — and verified the output matches published theory." |
| Multi-corpus calibration acceptance gate (must beat raw on ≥2 independent corpora) | `scripts/validate_calibration_multicorpus.py` + tests (min-sample filter, least-intervention tie-break, strict train-before-eval guard) | "Designed a calibration-acceptance protocol that only ships a calibration if it beats raw on ≥2 independent OOS corpora — preventing single-window overfit from masquerading as a durable gain." |
| Append-only shadow-logging + overnight settlement (anti-survivorship-bias) | `src/prediction/shadow_logger.py` (logs passed AND blocked bets); `src/prediction/settlement.py` (scores vs final box scores) | "Built shadow-logging that records every bet the engine evaluated — including rejected ones — and a settlement engine, creating a counterfactual dataset to calibrate thresholds against real outcomes." |
| Fractional-Kelly sizing with correlation penalty, drawdown breaker, isotonic-calibrated input | `src/prediction/betting_portfolio.py::kelly_corr` (quarter-Kelly, persisted prop-correlation matrix shrink, drawdown halt, cap, isotonic win-prob override) | "Implemented fractional-Kelly bankroll management wired to calibrated probabilities — correlation-aware, drawdown-gated, capped." |
| Self-caught overfit, hard-corrected | `src/prediction/prop_cv_split.py` documents a leaky grid-search (train R² ~0.79 vs honest holdout ~0.06 on stl/blk) and applies corrective regularization that takes precedence over the stale tuned params | "Caught a real leakage-driven overfit in my own pipeline — 0.79 CV R² vs 0.06 leak-free holdout — and hard-coded the corrective regularization so the mistake can't silently reappear." |
| Written validation doctrine (CLV over ROI, null hypothesis, no K-fold on time series) | `docs/research/validation-methodology.md` | "Documented a disciplined methodology that treats beating the sharp closing line (CLV, significance-tested) as the proof of edge above noisy ROI, and bans K-fold CV on time-ordered data." |
| 4-sport real-data edge hunt: pregame MATCHES the Shin-devigged close within noise on team-strength markets across 6 independent corpora (NBA/MLB moneyline, soccer O/U); totals/ATP trail only by the freshness gap | `scripts/platformkit/edge_hunt_scoreboard.py`, `scripts/platformkit/beat_the_close_scoreboard.py`, `docs/MARKET_EFFICIENCY_PROOF.md` (recorded table reproduces `docs/research/organization-sprint/EDGE-HUNT-RESULTS.md`) | "Ran a real-data forecasting edge hunt across four sports and six independent corpora and showed my own calibrated model MATCHES the efficient closing line within noise on team-strength markets -- the honest best case for an efficient market. Calibration/sharpness, not a $ edge." |
| Every candidate signal REJECTED across >=2 independent corpora; positive full-sample lifts SIGN-FLIP across calendar halves = caught overfit signature | `scripts/platformkit/edge_hunt_schedule.py` (NBA H1/H2 sub-corpora output), `scripts/platformkit/hunt_line_movement.py` (MLB NL/AL CLV-capture), `scripts/platformkit/edge_hunt_scoreboard.py` | "Scored every schedule/fatigue/totals/CLV candidate through the real leak-free gate; all rejected on >=2 corpora, and I caught my own signals that looked positive full-sample then reversed sign out-of-sample -- the overfit signature. The market is efficient on price; the self-audit is the result." |
| In-game conditioning is the one measured calibration win (NBA Brier 0.209 -> 0.159, MLB 0.241 -> 0.126), scoped real-corpus-only, edge_claimed=False | `scripts/platformkit/ingame_scoreboard.py`, `scripts/platformkit/proof_nba/ingame_accuracy.py`, `scripts/platformkit/proof_mlb/ingame_accuracy.py` | "The one measured win is in-game conditioning -- fusing the pregame rating prior with the realized mid-game state sharpens the win-prob forecaster (calibration, not a $ edge; a live book sees the score too). Scoped honestly: real-corpus OOS is the win, the committed synthetic fixture prints no-improvement." |

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
| LLM-free inexhaustible signal proposer | `src/loop/discovery.py` enumerates feature transforms → cheap statistical screen → existing honest gate decides (no LLM required); wired into `orchestrator._run_discovery_arm` (flag `CV_LOOP_DISCOVERY`) | "Extended the discovery loop with an LLM-free proposer that generates thousands of candidate transforms from residuals — the gate still decides; discovery is just never exhausted." |
| Multi-agent orchestration playbook | `.claude/commands/workday-loop.md` (298 lines): model-tier routing, parallel branch-isolated execution, protected-file guardrails, atomic crash-safe state, self-stocking queue | "Authored the orchestration playbook for a cost-aware multi-agent coding loop — planner orchestrates, executors implement in parallel branch-isolated batches — that runs unattended without corrupting the repo." |

### F. Intelligence / data-engineering layer

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| 291,625-pair player-vs-player matchup matrix from 2,214 raw tracking files across 3 seasons | `data/cache/coverage_faced_allseasons.parquet` (verified 291,625 rows); `scripts/intel/build_coverage_allseasons.py` | "Built a 291K-row player-vs-player matchup database from 2,214 raw per-game tracking files across three seasons." |
| Idempotent single-writer knowledge graph (690 nodes) | 660 player + 30 team notes with marker-delimited folds; `scripts/intel/outcome/fold_outcome_impact.py` | "Designed an idempotent single-writer fold to merge ~80 derived artifacts into a 690-node knowledge graph without duplication on re-run." |
| 1,249 per-player dossiers (28 statistical categories, archetype-labeled) | Dossiers populated from 80-artifact intelligence layer; showcase + honest scope: `docs/PLAYER_INTELLIGENCE.md` | "Generated 1,249 per-player statistical dossiers covering 28 categories (form, matchup, clutch, situational, etc.) with archetype labels and scheme tags." |
| Leak-safe as-of feature builders with confound flagging | `scripts/intel/outcome/build_player_availability.py` (expanding shift(1), schedule-confound downgrade); metadata bakes in "descriptive not causal, not a betting edge" | "Wrote point-in-time-correct builders using strict expanding-window shift(1) joins, and documented the statistical limitations in each artifact's metadata." |
| Adversarial self-audit caught a real attribution bug and scoped its blast radius | `docs/_audits/HARDENING_SWEEP_INTEL_ARTIFACT_BUILDERS_2026-06-02.md` — defender-team tricode inversion confirmed LATENT (no live consumer) | "Ran an adversarial audit of my own pipeline that surfaced an attribution bug, then traced its full blast radius to prove it was confined to an unused offline field." |
| Player-level possession Monte Carlo whose teammate correlation *emerges* correct (no hand-tuned ρ-matrix) | `src/sim/basketball_sim.py` (shared scoring pie sampled from real stint minutes; measured teammate-ρ ≈ −0.10 vs. realized, fixing a prior simulator's +0.65); `src/sim/sgp_from_sim.py` prices same-game parlays off the joint samples with a `validate_joint_calibration` harness | "Built a possession-by-possession simulator where teammates compete for a shared scoring pie, so the correct negative teammate correlation emerges from the mechanics instead of a hand-tuned matrix — validated the joint structure and explicitly do **not** claim a betting edge." |
| Full-season win-probability PBP replay validation | `scripts/team_system/pbp_replay.py` replayed Finals G1–G3 through the in-game projector: per-player projector = ship baseline (foul-out only); pooled win-prob Brier Q1–Q3 **0.34–0.40** (worse than coin flip) = clean in-series proof that there is no pregame playoff edge | "Ran a PBP replay validation that produced an honest negative result — win-prob Brier worse than a coin flip in-series, the cleanest proof that the market is efficient on playoff games." |

### G. Autonomy layer + the answer-engine oracle (newest sprint)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Forward self-shadowing of the loop's own provisional verdicts (M09) | `scripts/platformkit/autoloop/shadow_settle_job.py`; `data/cache/intel_claims/shadow/shadow_settle_ledger.jsonl` | "Built a job that forward-settles the discovery loop's own not-yet-confirmed verdicts against real outcomes as they resolve -- closing the loop between 'looks promising' and 'held up out of sample' without a human checking in." |
| Zero-LLM self-proposal cycle (M10) -- the other previously-missing autonomy stage | `scripts/platformkit/autoloop/propose_gate_job.py` | "Wired a self-proposal stage that generates and gates new candidate hypotheses on a schedule with no LLM call and no human trigger. Self-shadow (M09) + self-propose (M10) were the two explicitly-flagged missing autonomy stages; both are now live." |
| Self-probing data-acquisition frontier + a data-completeness auditor | `scripts/platformkit/data_frontier/frontier_probe_job.py`, `profile_completeness.py`; live artifact `data/frontend/ops/profile_completeness.json` -- e.g. NBA: 61 attributes audited across 6 windows, 505-player active universe, 0 all-null attributes | "Built an auditor that measures its own per-attribute/per-window/per-sport data completeness, and a probe job that acts on the gaps it finds -- the system reports what it doesn't know yet instead of silently degrading." |
| Failsafe sentinel layer (disk, exceptions, heartbeats, tamper-evidence) | `scripts/platformkit/ops_sentinel/{guard_integrity,disk_space,exception_burst,heartbeat_coverage,wedge_restarter}.py` | "Added sentinels that watch the watchers -- disk pressure, exception bursts, stalled heartbeats, and hash-based tamper-evidence on the invariant-enforcing code itself -- so an unattended overnight run fails visibly instead of silently." |
| One-command system-liveness harness, fixed to never paper over a real problem | `scripts/platformkit/proof_harness/system_proof.py`. A live run on this box this session returned `OVERALL: RED` -- 1/45 heartbeats RED (`m41_public_splits`), 8 census-drift entries + 1 missing store, 6 autonomy jobs PENDING-RESTART -- and reported all of it plainly instead of a decorative green (the immediately-preceding commit, `2eedc37e`, is the fix that stopped it from doing so) | "Built a single command that composes the existing gates/sentinels/ledgers into one health readout, then fixed a real bug where a down section could still roll up green. Verified today: it correctly reports RED with the specific failing subsystems named." |
| 4-sport answer-engine oracle: an effect graph assembled from zero new claims | `scripts/platformkit/answers/effect_graph.py` + `resolver_registry.py`; live artifact `data/frontend/ops/effect_graph.json` -- 555 nodes / 296 edges across NBA/MLB/soccer/tennis, every edge a verbatim row copied from an already-adjudicated ledger | "Built a queryable 'what affects what' graph over everything the system has proven or disproven, composed entirely from existing ledger rows (no new statistics computed), plus a resolver registry that maps every supported question type to exactly one deterministic source and refuses anything unregistered rather than improvising an answer." |
| Anti-folklore receipts -- every mechanism answer cites its own local test, live-verified this session | `scripts/platformkit/answers/contract_client.py`. Ran: `python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba` -> `CONFIRMED_LOCAL effect=-1.73 n=4732 p=0.0056 ... source: domains/basketball_nba/knowledge/validation_ledger.jsonl` | "Built a deterministic answer client that reproduces the resolver's own numbers byte-for-byte instead of letting a model free-associate a plausible-sounding basketball belief -- every mechanism answer carries its verdict, sample size, p-value, and source file, live-verified in this audit." |
| Knowledge engine fully drained across all 4 sports -- zero open hypotheses left | `domains/{basketball_nba,mlb,soccer,tennis}/knowledge/validation_ledger.jsonl` -- 197 combined rows as of 2026-07-10 HEAD-committed count (ledger keeps growing under the live autoloop cycle, so a working-tree count will read higher): NBA 23 (10 confirmed/10 null/3 not-testable); MLB 61 (23 confirmed/20 null/11 not-testable/4 failed-replication/1 artifact/1 reject/1 provisional); soccer 43 (12 confirmed/22 null/8 not-testable/1 provisional); tennis 70 (44 confirmed/22 null/4 not-testable) | "Closed out every open mechanism hypothesis across four sports, not most of them -- 89 confirmed, 74 honest NULLs, and 34 not-testable/other out of 197; a large NULL share is the expected shape of a real audit." |
| Interaction-factory candidate composition, all adjudicated | `data/cache/intel_claims/interaction_factory_ledger.jsonl` -- 146 rows counted directly: 70 NULL, 47 NOT_TESTABLE, 12 provisional survivors, 6 failed-replication, 5 replication-blocked, 4 killed, 2 REPLICATED | "Ran a factory that composes confirmed single-mechanism findings into two-way interaction candidates and adjudicated all 146 of them -- the large NULL/NOT_TESTABLE majority is the gate doing its job, not a shortfall." |
| Entry-timing study -- another honest market-efficiency finding | `scripts/platformkit/execution/entry_timing/`; live artifact `data/frontend/ops/timing_policy.json` -- across NBA/MLB moneyline/spread/total (900-1,645 drift events per market checked), no pre-close entry horizon shows an information edge over the contemporaneous price; policy set to `last_pregame_tick` everywhere | "Tested whether entering a paper position earlier than the closing tick captures any value, on real drift-event data, and found it does not on any market tested -- the market is efficient on entry timing too, not just price level." |
| Order-lifecycle executor -- built and tested with no path to a live order | `scripts/platformkit/execution/executor/{lifecycle.py,mock_exchange.py,dryrun.py}`. `lifecycle.py`'s own header: `"DOUBLE-GATED LIVE PATH -- no real order is placeable from this module"` (an env flag that intentionally is not documented, plus a second independent gate) | "Built the order-lifecycle plumbing (mock exchange, dry-run/live parity harness) fully tested end-to-end behind two independent gates, so the code exists and is proven without any path to placing a real order -- a deliberate boundary, not an unfinished one." |
| Cross-sport simulator state-cell heatmap -- a prioritized improvement queue, not a vague TODO | `scripts/platformkit/benchmarks/sim_heatmap/build_heatmap.py`; `data/frontend/ops/sim_heatmap_{nba,mlb,soccer,tennis}.json` (per-state-bucket CRPS-vs-market + a ranked worst-bucket list) | "Built a benchmark that buckets the simulator's forecast quality by game state and ranks the worst-performing buckets across all 4 sports, turning 'improve the sim' into a ranked, data-driven backlog." |
| The reject ledger as an honesty exhibit at scale | `scripts/platformkit/reject_ledger.py` -- 513 recorded REJECT/DEFER verdicts across NBA/MLB signal candidates, counted directly from `python -m scripts.platformkit.reject_ledger show` | "513 candidate signals that did not survive the gate, each with its reason and source, in one append-only file -- the negative-result count dwarfs the positive one, which is the expected shape of honest signal discovery." |
| Live in-game settlement joins at real scale | `scripts/platformkit/ingame/ticker_settlement_join.py`; joined corpora on disk counted directly: `data/cache/ingame_grade_joined/mlb/` = 178 ticker files / 67,519 rows, `.../soccer_intl/` = 48 ticker files / 8,700 rows, each row carrying model_prob + market_prob + outcome + close_source together | "Fixed a join bug that had kept model, market, outcome, and close-price on separate files, and verified the repaired join now produces two real multi-thousand-row corpora with all four fields present on every row." |
| 6 new keyless acquisition pipelines, honestly staged (some live, some PENDING-RESTART) | `scripts/platformkit/data_frontier/{bbref_advanced,understat_xg,statsbomb_open_full,savant_bat_tracking,milb_statsapi,an_public_splits}.py`. Some already producing data on disk (e.g. `data/cache/bbref_advanced_extended.parquet` = 1,470 rows); others are wired but not yet picked up by the running daemon, and the shipping commits say so explicitly (e.g. `37d0a7da "MiLB statsapi pipeline ... M12 daily seam (PENDING-RESTART)"`, `47a88a7e "Action Network public-splits capture ... m41 daily spec (PENDING-RESTART)"`) | "Added 6 new keyless data-acquisition pipelines; the commits themselves flag which ones need a daemon restart to arm rather than claiming they're live before they are." |
| Settlement-truth hardening: 3 root-caused integrity gaps in the paper ledger | `c1417777` (a 3rd props settle path never stamped `close_source` on 96/96 recent rows -- forward-fixed, historical rows left as-is), `099476ac` (dedup wrappers checked-then-appended outside the lock -- TOCTOU race; fixed with a shared `ledger_lock()` + `append_row_if_new`, proven by a real 2-OS-subprocess race test in `scripts/platformkit/test_clv_ledger_io.py`), `0d01a0e7` (forward-only snapshot-then-diff score-drift audit; fresh measure 76/436 settled MLB rows mismatch the live resolver read, the 76 stable while settled rows grew 397->436 with zero *new* mismatches -- quarantine-flagged, not re-settled; the audit itself notes the historical pattern is intermittent, not one clean fix boundary) | "Root-caused three separate settlement-integrity gaps in my own paper-trading ledger -- a silent write-path bypass, a check-then-append race, and post-settlement score drift -- fixed each forward-only with a concurrency test proving the race is actually closed, and flagged the historically-affected rows for quarantine instead of silently rewriting settled history." |
| Knowledge-ledger dedupe audit + repair: 42% duplicate pollution found and fixed | `docs/research/ledger_dedupe_audit_2026-07-10.md` (audit: 135 of 321 rows were exact-content duplicates across the 4-sport `validation_ledger.jsonl` files, cascading into 94 of 296 duplicate edges in the live `effect_graph.json` answer-engine artifact); fix `78d503ee` (content-identical dup guard added to the shared `io_atomic.append_jsonl_atomic` writer + a one-time squash 321->186 rows, with a `.pre_squash_2026-07-10.bak` kept per sport ledger) | "Audited my own append-only knowledge ledger, found 42% of rows were exact-content duplicates from a missing guard at the shared writer, then fixed the writer and ran a one-time documented squash with backups on disk rather than a silent rewrite -- verified afterward that the ledgers kept growing under live concurrent writers with zero new duplicates." |
| Literature-to-verdict research loop: 21 hypotheses seeded and closed same-session | Round 1: `e500a0d6` seeds 12 UNTESTED rows (3/sport, cited sources) -> closed by `dd8a59cc`+`000922c9`+`7c080a76`+`d25aa98f`. Round 2: `1bc7d622` seeds 9 more -> closed by `95a35ae2`+`46377c9d`+`ab8dfccc`+`7ec6ce94`. Verdicts recorded in `domains/{basketball_nba,mlb,soccer,tennis}/knowledge/validation_ledger.jsonl` with source, effect size, p-value per row | "Ran a literature-to-verdict loop twice in one overnight session -- seed a hypothesis from a cited external source, validate it locally against real leak-free data, record the verdict -- closing 21 hypotheses across four sports, with the honest majority landing NULL/REJECTED/NOT_TESTABLE rather than cherry-picked positives." |
| Autonomy layer restart-verified twice, not just present in code | Both restarts followed the same sanctioned procedure (read the stop flag, kill only the live supervisor PID, let the watchdog relaunch, verify) and landed all_ready 44/44 procs; the runtime job-report `data/frontend/ops/autoloop_report.json` (ts 2026-07-10T07:57:28Z) shows a `maintenance` block covering 12 scheduled job categories plus a separate `execution` key -- every category dispatched, some recording an honest watermark/cadence skip rather than a forced run -- alongside `data/frontend/ops/post_restart_verify.json` | "Verified my own autonomy layer isn't just code that exists -- restarted the live supervisor twice with a sanctioned single-PID kill-and-relaunch procedure, then pulled the actual job-report artifact and confirmed every scheduled maintenance and execution category was dispatched with a real timestamp (watermark-skips recorded as skips, not dressed up as runs)." |

### H. The Proof Room: receipt-backed public evidence layer (2026-07-15)

| Accomplishment | Proof artifact | Honest recruiter phrasing |
|---|---|---|
| Snapshot exporter that publishes the system's evidence as a static, scrubbed, receipt-backed bundle | `scripts/platformkit/showcase/` (SPEC.md contract + `export_snapshot.py` + 8 room builders); verified live run: 11/11 files, lint clean | "Built an evidence-publication layer where every headline number carries a receipt -- the claim, an honesty label, the source artifact path, its sha256, and the as-of date -- so a reviewer can trace any number on the public surface back to the file that produced it." |
| Fail-closed honesty linter the bundle cannot ship without passing | `scripts/platformkit/showcase/lint_bundle.py` + `tests/platformkit/showcase/` (25 tests). During the first real export it fail-closed the bundle 3 times on the system's OWN disclaimers (banned tokens inside honesty notes) before shipping | "Wrote a linter that blocks the public bundle on any dollar-edge language, any of my own retracted numbers, or any receipt missing its label -- and it caught my own copy three times on the first real run, which is the point." |
| Fact-claims corpus presented with the corpus/sample split instead of a flattering conflation | `data/cache/intel_claims/` -- 102,847 generated claim rows across 101 family files; 50 validation sidecars re-checked a 715-claim sample, 689 verified. An earlier "52,343 verified claims" figure has NO surviving artifact and is not claimed | "The claims corpus is 102,847 generated fact-claims with a 715-claim re-validated sample (689 verified) -- I present the generated/validated split explicitly because 'verified' should never silently mean 'generated'." |
| Replay room degrades honestly instead of fabricating model overlays | `scripts/platformkit/showcase/rooms/replay.py` -- the market price series (venue slugs) and the prediction log (ESPN ids) genuinely do not join today; replays ship market-ticks-only with the gap documented as v2 work | "Where a data join wasn't achievable, the public artifact says so and ships the honest subset -- no fabricated model lines on the chart." |
| Single-concept public repos distilled from the system | `github.com/neeljshah/walkforward-guard` (leak-guard harness whose demo plants two real leak classes and exits nonzero on catching them) and companions | "Distilled individual competencies into standalone repos with tests -- the validation-infrastructure repo's demo deliberately plants leaks and proves the guard catches them." |

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

### Win-probability model

- 5-way NNLS stack: **0.709 acc / 0.193 Brier** (3-fold walk-forward).
- Full-season season backtest (2025-26, leak-free WF, truncation-invariance proven): Brier **0.208** (model) vs Brier **0.198** (closing line) — well-calibrated but does not beat the market. Spread/total CLV ≈ 0 (explains 0.13%/0.29% of the move; corr-with-outcome = 0.001).
- **PBP Finals replay (G1–G3):** win-prob Brier **0.34–0.40** in-series — worse than a coin flip. Cleanest proof that the playoff market is efficient.

### Betting edge vs real closing lines — "the market is efficient"

- Against real DraftKings/FanDuel/MGM **closing** lines, the model is **roughly
  break-even-minus-vig overall** (~-2% to -5%; -2.00% unfiltered from `gate1_full_analysis.json`).
  The market is efficient on closing lines.
- **The one genuinely positive, repeatable stat is assists (AST): ~+4–5% ROI**, positive on
  three independently-sourced line corpora. Stress-tested — selection skill, not under-bias
  artifact; positive in both over/under directions; beats a blind-under baseline by ~12pp.
  **Book-robust but regime-dependent — breaks in the playoffs.** Size on the conservative number.
- **The honest framing:** "Against real closing lines I found the market is efficient — the
  model is about break-even-minus-vig, with assists the one small, durable edge. That is a
  sophisticated and honest result, and I have the harnesses that prove it."

### In-game (end-of-Q3) projection MAE lift — leak-clean

- End-of-Q3 residual heads cut prediction MAE substantially vs the pre-game baseline,
  **confirmed leak-free** (the heads use a clean 14-feature schema and do **not** share the
  Q4-feature leak that contaminates the separate win-probability model). Corroborated by two
  independent walk-forward harnesses (~46% pooled MAE reduction; ~26% over a naive carry-forward
  in-game baseline, walk-forward validated).
- **Honest framing:** most of the ~46% lift is *mechanical* (three of four quarters of box
  score are observed). Over a naive carry-forward baseline the learned-head value-add is ~26%.
  State it that way.
- **Quote the MAE lift alone. Never bundle it with the endQ3 Brier** (that model has a Q4 leak).

### In-game win-probability Brier — honest leak-free number

- The famous **endQ3 Brier 0.1191 "inside Pinnacle's range" is leak-inflated and mis-sourced.**
  Two features computed from 4th-quarter data caused the end-of-Q3 model to peek at the quarter
  it predicts. The cited source file actually reports 0.1354, not 0.1191.
- **Honest version: the leak-free walk-forward endQ3 Brier is ~0.141** (after removing the two
  Q4-derived features). A controlled A/B showed the leak inflated it by ~4% relative.
  **Frame this as a leak you caught in your own pipeline**, not as a competitive number.

### The self-caught leaks ARE the strength

Frame every item above as evidence of senior judgment:

- Built three independent reproducible harnesses that **debunked his own flagship "+18.38% ROI"**
  and root-caused it to specific lines of code (the grader bet the market's devigged favorite —
  the model was never read — priced at a flat -110 fiction, with in-sample-tuned filters).
- Found and quantified a **Q4 lookahead leak** in his own win-prob features.
- Caught a **0.79-CV-vs-0.06-holdout overfit** and hard-corrected it.
- The `docs/KNOWN_LIMITATIONS.md` openly states per-player CV attribution is ~4% accurate and
  "CV signal at scale — SHAP ≈ 0 in production today."
- Ran a **full-season walk-forward + PBP replay** that produced two clean negative results (market
  efficiency), then documented those negative results as the system's most credible outputs.
- Ran a **4-sport / 6-corpus real-data edge hunt** (the newest, cleanest market-efficiency self-audit):
  the calibrated model MATCHES the devigged close within noise on team-strength markets and EVERY
  candidate signal rejected across >=2 corpora -- including signals that looked positive full-sample
  then SIGN-FLIPPED out-of-sample (the overfit signature I caught). See `docs/MARKET_EFFICIENCY_PROOF.md`,
  reproduced by `scripts/platformkit/edge_hunt_scoreboard.py`. These are calibration/sharpness numbers
  only (Brier/BSS vs the close), edge_claimed=False -- no $ claim and none of the retracted figures.

**The pitch:** "I build ambitious systems and then build the instruments to disprove my own
hype. Here is exactly what works and exactly what I have not yet validated." That is a rare and
high-value senior-engineering signal — especially for a candidate without a degree.

---

## 4. Do-not-claim list (never put these in front of a recruiter)

These numbers are inflated, leaked, artifactual, or unverifiable. A probing recruiter who runs
the repo will catch each one — which is disqualifying for a no-degree candidate. Drop them.

| Do NOT claim | Why it fails | Say instead |
|---|---|---|
| **"+18.38% ROI on 1,535 walk-forward bets vs real closing lines"** (also +15.04% flat, and per-stat splits BLK +26% / STL +17% / etc.) | **Market-follow artifact, confirmed at the source-code level.** The grader picks bet direction from `devig(over_odds, under_odds)` — the market's own lean — and never reads the model (the eval CSV has no prediction column); prices at a flat -110 fiction; filters tuned in-sample on the same file. At real odds ~-4%; the model's own number is -2.00%. | "Roughly break-even-minus-vig vs real closing lines; assists ~+4–5% is the one durable edge." |
| **"endQ3 in-play Brier 0.1191, inside Pinnacle's range"** | **Leak-inflated AND mis-sourced.** Fed two Q4-derived features (peeks at the predicted quarter); cited file actually reports 0.1354. | "Leak-free walk-forward endQ3 Brier ~0.141, after I removed a Q4 feature leak I found in my own pipeline." |
| **"+54.57% ROI / 78.11% hit on 55,073 in-play bets"** | Graded against an **L5 line proxy**, not real closing lines. A model-quality ceiling, not a tradeable result. | "On a soft L5 proxy the in-play backtest hits 78%/+54% — I treat that strictly as a model-quality ceiling, never as realized edge." |
| **"Aggregate CLV +8.94pp"** | Circular — computed on the same model-unused, devig-direction corpus. No real Pinnacle-close CLV exists yet; first reading dated Oct 2026. Full-season backtest shows CLV ≈ 0 vs real closes. | Don't quote a CLV figure. "Real closing-line CLV can't be measured yet; I built the methodology that will measure it." |
| **"Re-ID accuracy ~91%, homography RMSE ~4.2px, 28 FPS, ball-valid 87%"** | **Unbacked.** The referenced benchmark test does not exist. | Present as roadmap targets, never achieved metrics. Cite the **self-consistency tracking-quality gates** instead. |
| **"Tracks 10 players at 15 fps"** | Observed ~1.6–2.6 tracked players/frame (max 4) on real broadcast footage; ~7–11 fps. | "The detector finds all 10 players; the tracker maintains up to ~5–6 stable slots on the calibration clip; reliable 10-player broadcast tracking is not yet demonstrated." |
| **"Position accuracy ±12–18 inches" / "0 ID switches" / "track stability 1.0"** | No ground-truth labels exist; `evaluate.py` returns `self_evaluation: True`, not validated MOT metrics. | "Outputs court coordinates via homography; positional accuracy and MOT metrics are not yet benchmarked against labeled ground truth." |
| **"CV features are a predictive moat / edge sportsbooks lack"** | **Zero measured predictive value today** — every CV feature SHAP importance = 0.0 in production prop models; `cv_lift_report.json` is `has_cv_data: false`. | "CV-derived features are wired in as a potential future edge; they don't yet move the model (SHAP ~0). Credible thesis and complete plumbing, not a demonstrated advantage." |
| **"I trained a deep re-ID model"** | The shipped OSNet weights are **ImageNet-pretrained, not NBA-fine-tuned**; production appearance model is the HSV histogram. | "I reimplemented the OSNet architecture in PyTorch and run it with ImageNet-pretrained weights." |
| **"Built over 13 months"** | **Not supported by git** — history spans ~3 months (2026-03-09 to 2026-05-31). | "An intensive ~3-month solo build (1,470 commits, Mar–May 2026)." Drop the 13-month figure entirely. |
| **"Solo-built / I wrote 1,470 commits"** (implied hand-typed) | **~91% of commits are agent-authored** (GSD Executor); ~54% carry a Claude co-author trailer. | "Solo human architect/director of an agentic build pipeline. The engineering judgment, ship/reject decisions, and validation methodology are mine." |
| **"70 iterations / 29 ships / 41 reverts" as a code-artifact or ledger count** | Only ~39 iter files on disk; exactly one revert doc exists; no machine-checkable ledger backs the 29/41 split. | "Ran a documented iteration campaign; most candidates were correctly rejected by the gate, by design." |
| **"All ~7,400 tests pass / full suite is green"** | **Not currently true** — ~97–98% pass locally with a documented tail (DB/GPU/optional-dep/version drift), a few real logic-drift failures, and a native pyarrow segfault on Windows. CI enforces only a 30% coverage floor. | "~7,400 tests, ~97–98% passing, with a documented tail tracked in KNOWN_LIMITATIONS. Core betting-math and in-play subsets pass clean." |
| **"Run my verify scripts to reproduce the headlines"** | `verify_production_mae.py` **crashes** with an 85-vs-129 feature mismatch; `verify_winprob.py` reads an uncommitted cache and **fails from a fresh clone**. | "I built a self-auditing verification harness; closing the fresh-clone reproducibility gap is known work." |
| **Any "quant alpha / P&L track record" framing** | There is **no verified leak-free profitable edge.** Zero real money placed. | Apply as an ML-infra/modeling/CV hire. "I built the full quant toolchain — devig, Kelly, CLV, calibration, walk-forward backtesting — and ran the validation that proved the apparent edge was an artifact." |

**Pre-outreach housekeeping (status as of 2026-06-11):**

1. **the-odds-api key** — scripts that hard-code it are now in `.gitignore`. **Still a manual step:** rotate the key and move it to `.env` (`os.environ`), since prior revisions remain in git history.
2. **Personal phone number** — both files untracked from the public repo (kept local, gitignored) as of 2026-06-07. Prior revisions remain in git history; a full history scrub is a separate, destructive step not taken here.
3. **Public docs reconciliation** — README and PUBLIC_EVIDENCE.md front the retraction explicitly. CLAUDE.md has been reconciled with the honest numbers.

---

**Contact:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

*Audit basis: independent verification in conda env `basketball_ai` (Python 3.10, CUDA, RTX
4060) — pipeline run on real video, FastAPI app booted to count routes, ~170+ tests executed,
schemas/artifacts read directly, headline graders read line-by-line. No repo files were edited
during the audit. Last reconciled: 2026-06-11.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
