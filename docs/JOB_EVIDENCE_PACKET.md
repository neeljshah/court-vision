# Job Evidence Packet — Neel Shah

> **Repository layout note (2026-09-17).** The public repository is the evidence surface: the analytics site, the documentation, the evidence artifacts, the eval gate and the sport-blind kernel. The production engine, adapters, API, operational tooling and bulk corpora (`src/`, `api/`, `domains/`, most of `scripts/` and `tests/`, `data/`) are kept in a private repository; reviewers can request read access. A path cited below that is not in this tree resolves there at tag `pre-minimize-2026-09-17`.

> An honest, recruiter-facing summary of what this project demonstrates. Every claim
> below was independently verified against the code, tests, and data artifacts by an
> adversarial audit whose job was to *refute* the headlines, not confirm them. Where a
> famous number did not survive scrutiny, the honest version is stated and the inflated
> one is listed in the retired-figures section (section 4).
>
> The single strongest signal in this repo is not any metric. It is that the same person
> who built the system also built the instruments that caught his own overclaims, and
> documented the negative results in writing.

---

## 1. One-line pitch + who this is

> **For a trading desk or quant team:** the one-page version of this packet, in desk vocabulary
> (Brier against the devigged close and the live market, devig, CLV, execution controls, forward
> record), is [QUANT_BRIEF.md](QUANT_BRIEF.md). Every number there is transcribed from this packet,
> EVIDENCE.md, MARKET_EFFICIENCY_PROOF.md, GO_LIVE_GATES.md, or a memo linked beside it.

**Pitch:** Solo builder of an end-to-end computer-vision → ML → full-stack production
system who rigorously audits and disproves his own results — senior-grade engineering
discipline.

**The honest headline finding (§3):** against real closing lines I found the market is
efficient — the pregame model matches or trails the devigged close in Brier, and every candidate signal, including
my strongest (assists), was ultimately rejected or retracted by my own gates. That is a
sophisticated and honest result, and I have the harnesses that prove it.

He is a hands-on systems engineer with three years of data-science coursework at the University
of Iowa, who built a complete NBA broadcast-video
CV pipeline, a multi-output ML prediction stack, and a multi-service FastAPI/daemon
serving platform, mostly by architecting and directing an agentic build workflow (a
planner model orchestrating cheaper executor models under hard ship gates). What sets him
apart is not the surface area but the validation rigor: he built walk-forward CV with
assertion-level leak guards, truncation-invariance leak tests, a multi-corpus calibration
acceptance gate, and reproducible audit harnesses — and then used those harnesses to catch
and publicly document leaks and measurement artifacts in his *own* flagship numbers. The work is already mid-to-senior level in CV, ML engineering,
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
| Production alerting subsystem (Slack/Discord) | `scripts/execute_loop/L22_alerting.py` (669 LOC): token-bucket rate limiting, atomic-write dead-letter queue, per-channel circuit breaker, EventBus integration; 15 tests pass | "Engineered a Slack/Discord alerting layer with rate limiting, atomic-write retry queue, and per-channel circuit breakers." *(Caveat added 2026-09-17: `scripts/execute_loop/` is an early generated research tree that nothing in the running system imports and that is excluded from deploy; cite this row as code written and unit-tested, not as a live subsystem.)* |
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
| Full-season walk-forward proving market efficiency | Season backtest (truncation-invariance PROVEN, 2025-26 season): well-calibrated (Brier 0.208 vs close 0.198; CORRECTION 2026-09-14: unreproduced, no artifact; reproducible artifact `data/cache/kalshi_complete/own_lines_backtest_nba.json` gives 0.1735 vs 0.1666, n=743, TRAILS_CLOSE, see the Selected Metrics entry; SUPERSEDED 2026-09-24 by the recompute: n=372 scored, gap +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20 -- see the Corrections entry) but does not beat the close; spread/total pregame CLV ≈ 0 (corr-with-outcome = 0.001). The cleanest market-efficiency proof in the system. | "I ran a full-season leak-free backtest that proved the model is well-calibrated but does not beat sharp closing lines — the honest finding a validation framework is *supposed* to produce." |
| Shin (1992) insider-trading de-vig model from scratch (+ 3 other methods), production-wired | `src/prediction/devig.py` (numerically-stable bisection solver); 7 tests; `POST /api/devig` defaults to `shin` | "Implemented four de-vig methods from scratch — including the Shin (1992) model via a stable bisection solver — and verified the output matches published theory." |
| Multi-corpus calibration acceptance gate (must beat raw on ≥2 independent corpora) | `scripts/validate_calibration_multicorpus.py` + tests (min-sample filter, least-intervention tie-break, strict train-before-eval guard) | "Designed a calibration-acceptance protocol that only ships a calibration if it beats raw on ≥2 independent OOS corpora — preventing single-window overfit from masquerading as a durable gain." |
| Append-only shadow-logging + overnight settlement (anti-survivorship-bias) | `src/prediction/shadow_logger.py` (logs passed AND blocked bets); `src/prediction/settlement.py` (scores vs final box scores) | "Built shadow-logging that records every bet the engine evaluated — including rejected ones — and a settlement engine, creating a counterfactual dataset to calibrate thresholds against real outcomes." |
| Fractional-Kelly sizing with correlation penalty, drawdown breaker, isotonic-calibrated input | `src/prediction/betting_portfolio.py::kelly_corr` (quarter-Kelly, persisted prop-correlation matrix shrink, drawdown halt, cap, isotonic win-prob override) | "Implemented fractional-Kelly bankroll management wired to calibrated probabilities — correlation-aware, drawdown-gated, capped." |
| Self-caught overfit, hard-corrected | `src/prediction/prop_cv_split.py` documents a leaky grid-search (train R² ~0.79 vs honest holdout ~0.06 on stl/blk) and applies corrective regularization that takes precedence over the stale tuned params | "Caught a real leakage-driven overfit in my own pipeline — 0.79 CV R² vs 0.06 leak-free holdout — and hard-coded the corrective regularization so the mistake can't silently reappear." |
| Written validation doctrine (CLV over ROI, null hypothesis, no K-fold on time series) | `docs/research/validation-methodology.md` | "Documented a disciplined methodology that treats beating the sharp closing line (CLV, significance-tested) as the proof of edge above noisy ROI, and bans K-fold CV on time-ordered data." |
| 4-sport real-data study against the devigged close: pregame TRAILS the close on MLB moneyline (+0.0039 Brier, 95% CI [+0.0028, +0.0051], DM p 3.6e-12, n=13,992) and on soccer O/U 2.5 (+0.0076 Brier, 95% CI [+0.0059, +0.0092], DM p 1.1e-19, n=7,558); NBA moneyline is indistinguishable from the close at n=372 and underpowered (MDE 0.0152); totals/ATP trail by more (freshness). Corrected 2026-10-06 from DM_RECOMPUTE_2026-09-24: this row earlier said team-strength markets matched the close within noise; that reading came from a fixed-threshold label, not an interval | `scripts/platformkit/eval_gate/dm_recompute_pregame.py`, `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md`, `scripts/platformkit/edge_hunt_scoreboard.py`, `docs/MARKET_EFFICIENCY_PROOF.md` (recorded scoreboard table) | "Ran a real-data forecasting study across four sports and six independent corpora: my calibrated model trails the devigged close by small, interval-resolved margins on MLB moneyline and soccer O/U 2.5, is indistinguishable from it on NBA moneyline at an underpowered n=372, and every candidate signal was rejected. Calibration and sharpness only." |
| Every candidate signal REJECTED across >=2 independent corpora; positive full-sample lifts SIGN-FLIP across calendar halves = caught overfit signature | `scripts/platformkit/edge_hunt_schedule.py` (NBA H1/H2 sub-corpora output), `scripts/platformkit/hunt_line_movement.py` (MLB NL/AL CLV-capture), `scripts/platformkit/edge_hunt_scoreboard.py` | "Scored every schedule/fatigue/totals/CLV candidate through the real leak-free gate; all rejected on >=2 corpora, and I caught my own signals that looked positive full-sample then reversed sign out-of-sample -- the overfit signature. The market is efficient on price; the self-audit is the result." |
| In-game conditioning is the one measured calibration win (NBA Brier 0.209 -> 0.159, MLB 0.241 -> 0.126), scoped real-corpus-only, edge_claimed=False. **CONTEXT 2026-09-14 (Gate A-0, `docs/evidence/ingame/GATE_A0_2026-09-14.md`):** those gains are against a STATIC pregame prior; against the contemporaneous Kalshi in-play price on the same ticks the in-game models are BEHIND (MLB Brier 0.2377 vs 0.2067, delta +0.0310, CI [0.0170, 0.0454], 227 games; soccer_intl 0.2279 vs 0.1427, 51 games). Sharpness vs static, not vs the market. | `docs/INGAME_PROOF.md` (receipts), `scripts/platformkit/ingame_scoreboard.py`, `scripts/platformkit/proof_nba/ingame_accuracy.py`, `scripts/platformkit/proof_mlb/ingame_accuracy.py` | "The one measured win is in-game conditioning -- fusing the pregame rating prior with the realized mid-game state sharpens the win-prob forecaster (calibration, not a $ edge; a live book sees the score too). Scoped honestly: real-corpus OOS is the win, the committed synthetic fixture prints no-improvement." |

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
| Idempotent single-writer knowledge graph (690 nodes) | 660 player + 30 team notes with marker-delimited folds; `scripts/intel/outcome/fold_outcome_impact.py` | "Designed an idempotent single-writer fold to merge derived intelligence artifacts into a 690-node knowledge graph without duplication on re-run." |
| 1,249 per-player dossiers (28 statistical categories, archetype-labeled) | Dossiers populated from the 151-file intelligence layer (`data/intelligence/`, counted on disk); showcase + honest scope: `docs/PLAYER_INTELLIGENCE.md` | "Generated 1,249 per-player statistical dossiers covering 28 categories (form, matchup, clutch, situational, etc.) with archetype labels and scheme tags." |
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
| Fact-claims corpus presented with the generated/validated split instead of a flattering conflation | `data/cache/intel_claims/` -- 103,048 generated claim rows across 103 family files; 99 `*_validation.json` sidecars cover 101,865 rows: 101,864 VERIFIED / 0 MISMATCH / 1 UNVERIFIABLE. Tracked tally: `scripts/platformkit/analytics_showcase/out/claims_corpus_meta.json` (2026-07-22; re-summed from the sidecars 2026-09-01, identical; regenerate with `python -m scripts.platformkit.analytics_showcase.claims_corpus_meta`). VERIFIED = the claim's number recomputes from its declared source file + formula (provenance check, `claims_validator.py`), NOT predictive accuracy. Superseded figures with NO surviving artifact, not claimed: "52,343 verified claims", the README's former "101,089 VERIFIED claim rows", and this row's former "715-claim sample / 689 verified" | "The claims corpus is 103,048 generated fact-claims, 101,864 of which re-verify from their declared source + formula -- I present the generated/verified split explicitly, and 'verified' means the arithmetic reproduces, never that the claim predicts anything." |
| Replay room degrades honestly instead of fabricating model overlays | `scripts/platformkit/showcase/rooms/replay.py` -- the market price series (venue slugs) and the prediction log (ESPN ids) genuinely do not join today; replays ship market-ticks-only with the gap documented as v2 work | "Where a data join wasn't achievable, the public artifact says so and ships the honest subset -- no fabricated model lines on the chart." |
| Single-concept public repos distilled from the system | `github.com/neeljshah/walkforward-guard` (leak-guard harness whose demo plants two real leak classes and exits nonzero on catching them) and companions | "Distilled individual competencies into standalone repos with tests -- the validation-infrastructure repo's demo deliberately plants leaks and proves the guard catches them." |

---

## 3. Honest numbers (what survives leak-free scrutiny)

These are the metrics that hold up. Each is paired with what the *inflated* version
claimed, so the candidate can pre-empt the gap rather than be caught by it.

### Prediction accuracy (two measurements, labeled -- never mix their numbers)

- **Production-model chronological holdout (the public, re-runnable lead number):
  PTS MAE 4.83, REB 1.92, AST 1.39, FG3M 0.89, STL 0.71, BLK 0.44, TOV 0.89** --
  last-20%-by-date holdout, 20,354 player-game rows, scored through the production
  inference path by `scripts/verify_production_mae.py` (re-measured 2026-07-20; the
  script exits nonzero if any stat drifts more than 0.02 from these claims). Every
  public doc leads with this set under this label.
- Walk-forward OOF measurement (internal artifact, `data/cache/pregame_oof.parquet`,
  gitignored): PTS 4.58, REB 1.90, AST 1.34, FG3M 0.88, STL 0.71, BLK 0.515, TOV 0.88
  on ~51K held-out player-games per stat (50,954 rows/stat), with a small consistent
  PTS under-bias (~-0.45). OOF predictions are byte-identical to the calibration
  frame's (max abs diff 0.0 over 319,081 rows, monotonic non-overlapping holdout
  windows). Quote these only under this OOF label -- a 4.83/0.44 number must never be
  paired with the ~51K/OOF citation (they are different measurements; on the OOF frame
  BLK reads 0.515, not 0.44).
- Both measurements are leak-free and competitive with published prop-model benchmarks.
  **The holdout set is the honest core accuracy claim -- lead with it.**

### Win-probability model

- 5-way NNLS stack: **0.709 acc / 0.193 Brier** (3-fold walk-forward).
- Full-season season backtest (2025-26, leak-free WF, truncation-invariance proven): Brier **0.208** (model) vs Brier **0.198** (closing line) — well-calibrated but does not beat the market. **CORRECTION 2026-09-14:** the 0.208 / 0.198 pair has no artifact on disk and did not reproduce; the reproducible pregame artifact is `data/cache/kalshi_complete/own_lines_backtest_nba.json` (2026-07-18; n=743, held-out 372; MOV-Elo via `scripts/platformkit/proof_nba/ml_accuracy.py`): Brier **0.1735** model vs **0.1666** Shin-devigged close, gap +0.0069, 95% CI [-0.0036, +0.0175], verdict TRAILS_CLOSE (SUPERSEDED 2026-09-24 by docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md: n=372 scored, 95% CI [-0.0038, +0.0175], DM p 0.20, MATCHES_CLOSE under the written interval rule, underpowered, MDE 0.0152; note added 2026-10-06). The conclusion (matches or trails the close, never beats it) is unchanged; the earlier figures should not be quoted until re-derived with n and date. Spread/total CLV ≈ 0 (explains 0.13%/0.29% of the move; corr-with-outcome = 0.001).
- **PBP Finals replay (G1–G3):** win-prob Brier **0.34–0.40** in-series — worse than a coin flip. Cleanest proof that the playoff market is efficient.
- **Per-regime recalibration, honest keys (S212, 2026-09-04, fresh-process reproducible):** after-ECE with date-group train-only regime keys -- nba **0.022205**, mlb **0.009672**, soccer **0.009192**, tennis **0.016928**. Supersedes the earlier S05 screen (nba 0.024843 / mlb 0.008077 / soccer 0.009302 / tennis 0.008403), whose tercile key was fitted on the scored rows (leak; tennis was flattered about 2x). Calibration only; no market comparison implied. Artifact: docs/evidence/harness/S212_regime_key_clean_rerun_2026-09-04.md (landing 6226fb042).

### Pregame vs real closing lines — "the market is efficient"

- Against real DraftKings/FanDuel/MGM **closing** lines, the pregame model trails or matches the
  devigged close in Brier on every market tested (see EVIDENCE.md section A); no return figure is claimed.
  The market is efficient on closing lines.
- **RETRACTED (2026-07-21): the earlier "assists ~+4–5% ROI durable edge" claim is superseded
  and must not be quoted as a live result.** It was regime-dependent (broke in the playoffs)
  and, under the no-edge-claims rail, no dollar/ROI edge is claimed anywhere. The historical
  measurement remains in the gate artifacts (`gate1_full_analysis.json`) as a record of the
  stress-testing methodology, nothing more.
- **The honest framing:** "Against real closing lines I found the market is efficient — the
  pregame model matches or trails the devigged close in Brier. Every candidate signal, including my strongest (assists),
  was ultimately rejected or retracted by my own gates. That is a sophisticated and honest
  result, and I have the harnesses that prove it."

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
  This is a leak caught in the project's own pipeline, not a competitive number.

### The self-caught leaks ARE the strength

Every item above was caught by the project's own instruments:

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
  the calibrated model TRAILS the devigged close on MLB moneyline and soccer O/U 2.5 (95% CIs above zero) and is indistinguishable from it on NBA moneyline at an underpowered n=372 (corrected 2026-10-06 from DM_RECOMPUTE_2026-09-24; earlier text said it matched within noise), and EVERY
  candidate signal rejected across >=2 corpora -- including signals that looked positive full-sample
  then SIGN-FLIPPED out-of-sample (the overfit signature I caught). See `docs/MARKET_EFFICIENCY_PROOF.md`,
  reproduced by `scripts/platformkit/edge_hunt_scoreboard.py`. These are calibration/sharpness numbers
  only (Brier/BSS vs the close), edge_claimed=False -- no $ claim and none of the retracted figures.

**The pitch:** "I build ambitious systems and then build the instruments to disprove my own
hype. Here is exactly what works and exactly what I have not yet validated." That is a rare and
high-value senior-engineering signal.

---

<a id="4-do-not-claim-list-never-put-these-in-front-of-a-recruiter"></a>

## 4. Retired figures (retracted or unverifiable; not claimed anywhere in this repository)

These numbers are inflated, leaked, artifactual, or unverifiable. A probing recruiter who runs
the repo will catch each one. Do not cite them as current results.

| Do NOT claim | Why it fails | Say instead |
|---|---|---|
| **"+18.38% ROI on 1,535 walk-forward bets vs real closing lines"** (also +15.04% flat, and per-stat splits BLK +26% / STL +17% / etc.) | **Market-follow artifact, confirmed at the source-code level.** The grader picks bet direction from `devig(over_odds, under_odds)` — the market's own lean — and never reads the model (the eval CSV has no prediction column); prices at a flat -110 fiction; filters tuned in-sample on the same file. At real odds ~-4%; the model's own number is -2.00%. | "Roughly break-even-minus-vig vs real closing lines; every candidate edge, including assists, was ultimately rejected or retracted by my own gates." |
| **"endQ3 in-play Brier 0.1191, inside Pinnacle's range"** | **Leak-inflated AND mis-sourced.** Fed two Q4-derived features (peeks at the predicted quarter); cited file actually reports 0.1354. | "Leak-free walk-forward endQ3 Brier ~0.141, after I removed a Q4 feature leak I found in my own pipeline." |
| **"+54.57% ROI / 78.11% hit on 55,073 in-play bets"** | Graded against an **L5 line proxy**, not real closing lines. A model-quality ceiling, not a tradeable result. | "On a soft L5 proxy the in-play backtest hits 78%/+54% — I treat that strictly as a model-quality ceiling, never as realized edge." |
| **"Aggregate CLV +8.94pp"** | Circular — computed on the same model-unused, devig-direction corpus. No real Pinnacle-close CLV exists yet; first reading dated Oct 2026 (section 5: as of 2026-10-23 the forward paper series computes no markout or CLV). Full-season backtest shows CLV ≈ 0 vs real closes. | Don't quote a CLV figure. "Real closing-line CLV can't be measured yet; I built the methodology that will measure it." |
| **"Re-ID accuracy ~91%, homography RMSE ~4.2px, 28 FPS, ball-valid 87%"** | **Unbacked.** The referenced benchmark test does not exist. | Present as roadmap targets, never achieved metrics. Cite the **self-consistency tracking-quality gates** instead. |
| **"Tracks 10 players at 15 fps"** | Observed ~1.6–2.6 tracked players/frame (max 4) on real broadcast footage; ~7–11 fps. | "The detector finds all 10 players; the tracker maintains up to ~5–6 stable slots on the calibration clip; reliable 10-player broadcast tracking is not yet demonstrated." |
| **"Position accuracy ±12–18 inches" / "0 ID switches" / "track stability 1.0"** | No ground-truth labels exist; `evaluate.py` returns `self_evaluation: True`, not validated MOT metrics. | "Outputs court coordinates via homography; positional accuracy and MOT metrics are not yet benchmarked against labeled ground truth." |
| **"The tracker reliably follows players"** / any claim that tracking OUTPUT is trustworthy | **Measured on the research route, 2026-09-04, not asserted.** Through a validated homography on one WNBA clip, **10.5 pct of on-court same-ID steps are physically impossible** (above 40 ft/s; G267/G270). The cause is upstream of association: on an unconditioned blind sample of 72 retained detections, **only 43/72 = 0.597 are a player on the court of play, and 15/72 = 0.208 are not a person at all** (G273). Jump steps are enriched in non-person crops by **1.667x** against a measured 18/60 = 0.300 baseline, **p = 0.034, marginal** (G276b). **The 0.597 figure is LOCALISATION-BLIND and must not be read as 'the detection is on a player'** (resolved 2026-09-04): its criterion was a person visible anywhere in a 512x640 crop centred on the detection, i.e. within +/-256 px horizontally and +/-320 px vertically. Measured directly against sealed hand-located player positions, a detection sits a **median 243 px** from the nearest player's feet (within 50 px only 0.071 of the time, within 100 px 0.205). A player IS in the neighbourhood 0.705 of the time, which matches 0.597+0.125 and confirms both measurements are consistent. **Detector RECALL remains NOT established** at any tolerance on a population basis. **MECHANISM, measured 2026-09-04 (G287, unconditioned, on G273's own 72 sealed crops re-judged blind):** what lies under the detection's centre point is a **player's feet 15/72 = 0.208**, a player's body-not-feet 0.236, bare floor 0.236, a graphic or ticker 0.181 -- **and G288 confirmed all 13 of those are OVERLAY furniture, score bugs and lower-third tickers, which project inside the court rectangle and are accepted as on-court positions** -- and a non-player person 0.111. **So about one detection in five is on a player's feet and about two in five on a player somewhere.** **The decisive cross-tab: G273's 43 PLAYER verdicts split into 13 feet, 15 body-not-feet, 12 floor, 2 graphic and 1 basketball -- so 0.597 overstates the point-level 'on a player's feet' claim by 0.389.** Localisation is separately measured at a **median 172 px** from the paired player's feet, with mis-pairing ruled out at 0.089 (G286). **So 'physically impossible player motion' is the wrong phrase for the 10.5 pct figure: a substantial fraction of retained detector-box steps imply motion no object could perform BECAUSE a substantial fraction of retained detections are not on players.** The rate itself is unretracted and was separately shown robust to the 40 ft/s cut point (G279) and reproducible across detector draws to +0.0005 (G282). Scope: ONE clip, ONE camera shot (frames 19599-23399), ONE labeller, ONE non-deterministic detector draw; G274 could not replicate it in a second shot because that shot has no painted court. **And the span is measurably NOT representative of its own clip**: G278 found 51/61 = 0.836 of within-span frames show court geometry against 118/180 = 0.656 clip-wide (z = 2.662, nominal p = 0.0078), so **any clip-wide extrapolation of these figures is unsupported and the span must be quoted with them.** The DIRECTION of that effect is unknown -- tracking quality has never been measured in low-court-visibility footage, because no map exists there to measure it with. **MECHANISM IS NOT ESTABLISHED, measured 2026-09-04 (G289, exhaustive partition of all 4,090 implausible steps):** only **630/4,090 = 0.154** moved 20 px or less in the image, so projective amplification of small image moves is **REFUTED** as the mechanism; **3,460/4,090 = 0.846 are genuinely large image displacements**, 1,897 of them beyond 150 px, and **their cause remains unexplained**. Bimodal track ids account for **0.045** and were withdrawn as the mechanism; alternation is refuted (0.876 of large image jumps do not return within 5 frames); zero-image-motion mapping inconsistency is **0.004**. **A fourth candidate also failed (G292): at the two ends of 36 sampled jumps beyond 150 px, 29/72 = 0.403 of endpoints are on a player at all, against the unconditioned 32/72 = 0.444 (z = -0.506, nominal p = 0.613) -- so a large jump does NOT connect a person to broadcast furniture, and the re-anchoring story is unsupported. At 72 against 72 that test cannot see differences below roughly 20 points, so it means no LARGE difference, not no difference.** **So while it is measured that most retained detections are not on players, that fact has NOT been shown to ACCOUNT for the implausible steps -- no candidate yet explains more than 15 pct of them, and the two are separate findings that must not be stated as cause and effect.** **RATER ROBUSTNESS, measured 2026-09-04 (G291): the 0.597 crop-level figure does not survive an independent rater.** A second model (`gpt-6-astra`) re-judging the same 72 sealed crops under the same crop-level rule returned **60/72 = 0.833 PLAYER against 0.597**, raw agreement **47/72 = 0.653**, Cohen's kappa **0.283 (SE 0.079)**, exact McNemar **p = 0.0000763**, and **used NOT A PERSON zero times against the first rater's 15/72** (probability 4.96e-08 under that rate). G291's own diagnosis: the second rater counts players **anywhere in the crop**. A 512x640 crop is 26.7 pct x 59.3 pct of a 1080p frame and routinely holds several people, so **the crop-level rule was under-specified and 0.597 was never a well-defined quantity -- it must not be quoted as a detector property.** **Absolute crop-level LEVELS are not rater-robust; a comparison made inside ONE row from ONE pooled blind order is materially better protected because the same bias applies to both arms; a cross-row comparison is only partly protected even with the same model, which puts G280b-against-G273 in the weaker class.** **THE CENTRE-CROSS FIGURES HAVE NOW BEEN RATER-CHECKED CLEANLY (G297: a third model, `gpt-5.6-sol`, that had never seen these crops, verdicts sealed before un-blinding) AND THE ANSWER SPLITS BY CATEGORY.** Exact McNemar on each against G287: **footpoint on a player's FEET 0.208 against 0.181, discordant 10 versus 8, p = 0.815 -- REPRODUCES**; **footpoint on a BROADCAST GRAPHIC 0.181 against 0.194, discordant 1 versus 2, p = 1.000 -- REPRODUCES**; **player's BODY-not-feet 0.236 against 0.056, discordant 13 versus 0, p = 0.00024 -- DOES NOT**; **'on a player at all' 0.444 against 0.236, p = 0.00073 -- DOES NOT, and it fails ONLY because it inherits the body category.** **So the two figures quoted above -- about one detection in five on a player's FEET, and 0.181 on overlay furniture -- ARE rater-robust across two independent model raters and stand. The 'on a player at all' figure is NOT rater-robust and is WITHDRAWN as a detector property.** That split is coherent rather than lucky: whether a point sits on a foot, or on a score bug, is a crisp judgement, while whether a point near a torso-or-leg boundary is on the body or on the floor behind it is genuinely ambiguous -- and that is exactly the category that moved. **Stated honestly: p = 0.815 on the feet category is a NON-SIGNIFICANT DIFFERENCE at n = 72 with 10 versus 8 discordant pairs, NOT a proof of equality, and it cannot exclude a moderate difference.** Overall centre-cross agreement is Cohen's kappa **0.479 (SE 0.071)** against the crop-level **0.283 (SE 0.079)**, so **the well-posed rule fixes part of the problem and not all of it.** **AND MUCH OF IT IS THE CONFIGURATION, MEASURED 2026-09-04 (G298, three arms, same 15 frames, NO EYE LABELS -- recall against 143 hand-located feet, so it is immune to the rater problem above).** Production detects with **`yolov8n` at `imgsz=640` on 1920x1080** -- a 3x linear, **9x area downscale on the smallest model in the family** -- justified in a source comment asserting `yolov8x` is "only marginally better", **with no measurement anywhere in the repo.** At 100 px: **production 25/143 = 0.175; the SAME model at native 1920 gives 73/143 = 0.511; the LARGE model at 1920 gives 65/143 = 0.455.** **Input resolution alone adds +33.57 points. Added model capacity SUBTRACTS 5.59.** **So the comment was right about capacity and irrelevant: nobody had tested the downscale sitting next to it, and the input resolution is the dominant detector defect.** **THE GAIN IS NOT FREE, and this bounds the claim: the native-resolution arm emits 617 boxes against production's 112 -- 5.51x the boxes for 2.92x the matches -- so matched feet per emitted box FALLS from 0.2232 to 0.1183, roughly half as productive per box. That is a crude efficiency proxy, NOT precision, and PRECISION AT THE BETTER SETTING REMAINS UNMEASURED. No timing was measured either, so nothing here says the alternative is PRACTICAL, only that it detects more.** **NOTHING WAS ADOPTED: no production default was changed and `src/` was not touched -- this is a measurement of an alternative and the change is a human decision.** Scope: 143 located feet on 15 frames from ONE MODEL LOCATOR, so a detector finding players that locator missed is scored WRONG; one clip, one shot, on the span G278 measured friendlier than its own clip. **These figures come from the `scripts/platformkit` research route (G267 `route_sha256` names g196/g215 + `player_detection.py`), NOT from `unified_pipeline._compute_homography`, so they neither confirm nor refute the production hardening row above.** | "Tracking output quality is now measured rather than assumed, and it is poor. On the one clip with a validated map, about a tenth of on-court detector-box steps imply motion no object could perform -- and separately, most retained detections are not on players -- only about a fifth sit on a player's feet -- a figure that survived a clean check by a third rater -- while the broader 'on a player at all' rate did not survive it and is withdrawn. Those are two measured findings, not a cause and its effect: an exhaustive partition of every impossible step refuted the mapping explanation and left 85 pct of them with no established mechanism, and no candidate yet accounts for more than 15 pct. The crop-level precision figure also failed an independent-rater check (kappa 0.28), so I quote the unambiguous centre-point measurements and not that one. Single clip, single shot, on a span measurably friendlier than the clip; not a population claim." |
| **"Court calibration generalises across footage"** | **Falsified on the research route, 2026-09-04.** Seeded calibration works on `wnba__wnba_01` (5 px median / 19 px p90) but yields **NCAA 0/300, amateur 0 usable across 5 sources, soccer 0/1,195**. Causes are camera framing, occlusion and court decoration, not detector quality. Separately, **no hand-built signal detects an invalid court**: four independent families failed, and G274 produced **0.569 px RMS on a frame containing no court at all**. | "Calibration is hand-seeded per clip and does not generalise; sub-pixel reprojection residual is NOT evidence a map is valid. About two thirds of the one measured clip is court-geometry-bearing (upper bound 0.722, no measured floor), so the blocker is calibration validity, not footage availability." |
| **"CV features are a predictive moat / edge sportsbooks lack"** | **Zero measured predictive value today** — every CV feature SHAP importance = 0.0 in production prop models; `cv_lift_report.json` is `has_cv_data: false`. | "CV-derived features are wired in as a potential future edge; they don't yet move the model (SHAP ~0). Credible thesis and complete plumbing, not a demonstrated advantage." |
| **"I trained a deep re-ID model"** | The shipped OSNet weights are **ImageNet-pretrained, not NBA-fine-tuned**; production appearance model is the HSV histogram. | "I reimplemented the OSNet architecture in PyTorch and run it with ImageNet-pretrained weights." |
| **"Built over 13 months"** | **Not supported by git** — history spans ~6 months (2026-03-09 to 2026-09-07). | "An intensive solo build (5,504 commits, Mar–Sep 2026)." Drop the 13-month figure entirely. |
| **"Solo-built / I wrote 5,504 commits"** (implied hand-typed, the 2026-09-07 count) | **The large majority of commits are agent-authored** under direction. NOTE 2026-09-07: the identity-based recount no longer reproduces -- a history rewrite normalised every author to `Neel Shah` (5,504/5,504), so the old ~91% `GSD Executor` split is not re-derivable from `git log --format=%an` today; the still-derivable trailer figure is 1,333/5,504 = 24.2% carrying `Co-Authored-By: Claude`. | "Solo human architect/director of an agentic build pipeline. The engineering judgment, ship/reject decisions, and validation methodology are mine." |
| **"70 iterations / 29 ships / 41 reverts" as a code-artifact or ledger count** | Only ~39 iter files on disk; exactly one revert doc exists; no machine-checkable ledger backs the 29/41 split. | "Ran a documented iteration campaign; most candidates were correctly rejected by the gate, by design." |
| **"All ~7,400 tests pass / full suite is green"** | **Not currently true** — ~97–98% pass locally with a documented tail (DB/GPU/optional-dep/version drift), a few real logic-drift failures, and a native pyarrow segfault on Windows. CI enforces only a 30% coverage floor. | "~7,400 tests, ~97–98% passing, with a documented tail tracked in KNOWN_LIMITATIONS. Core betting-math and in-play subsets pass clean." |
| **"Run my verify scripts to reproduce the headlines"** | **AMENDED 2026-07-23:** the historical failures (`verify_production_mae.py` feature mismatch; `verify_winprob.py` uncommitted cache) were fixed 2026-07-20 (`eb95e13b8`), and fresh-clone reproducibility is now **measured, not assumed**: `check_all.py` passes 52/52 on a bare clone (8 data-dependent modules verify their committed artifacts in a labeled recorded-artifact mode) and runs green in public CI (`proof.yml`, first green run 2026-07-23; the first run honestly FAILED 46/52 on a path-portability bug, fixed in `03c4ce398` -- the red run stays in Actions history). | "Clone the repo and run `check_all.py` -- 52 module self-checks pass on a bare clone and in public CI ([REPRODUCE.md](../REPRODUCE.md)). The CI trail includes the first red run and its fix -- that is the discipline, not an embarrassment." |
| **Any "quant alpha / P&L track record" framing** | There is **no verified leak-free profitable edge.** Zero real money placed. | Apply as an ML-infra/modeling/CV hire. "I built the full quant toolchain — devig, Kelly, CLV, calibration, walk-forward backtesting — and ran the validation that proved the apparent edge was an artifact." |
| **"85 trained signals" / "0/85 candidate signals" / "80-artifact intelligence layer"** | **CORRECTED 2026-09-03 (S56).** No artifact holds 85 signals: 85 is the per-row `n_trials` multiplicity constant, while `scripts/platformkit/eval_gate/spa_catalog_report.txt` and `retro_correction_report.txt` both enumerate **60** catalog classes (NBA 16 / soccer 15 / tennis 15 / MLB 14), 0 surviving. The disjoint `data/registry/signal_registry.parquet` holds **86** rows (72 folded / 14 deferred, `coverage_pct` null 86/86, no market-relative verdict). `data/intelligence/` holds **151** files on disk and the 80-subset is not enumerable by any script. Memo: `docs/evidence/harness/SIGNAL_INVENTORY_REDTEAM_2026-09-03.md`. | "0 of 60 candidate signal classes survived the multiplicity correction; 86 registry signals carry no market-relative test; the intelligence layer is 151 files on disk." |
| **"A forward track record" / "N weeks of forward paper trading" / any forward-series Brier as a model verdict** (added 2026-10-19) | Through 2026-10-22 every scoreboard cell is INSUFFICIENT (1 to 6 games against the 30-game floor), 0 of 61 judged games passed qualification, 9 of 13 night receipts are PARTIAL, and the fitted arms scored ticks on two nights only (10-06 and 10-09), none since. Arm A is the venue mid's own Brier, not the model's. Section 5. | "A prospective, receipt-backed paper series has run since 2026-10-06. It has no calibration verdict yet, and the receipts say why: scorer wall time, laptop sleeps and recorder uptime." |
| **"Simulated fills" as execution quality or P&L** (added 2026-10-19) | fill_realism is `COUNTS ONLY` on unqualified tape with zero assumed latency. It reports no markout, no fee netting and no money figure. | "The fill-realism step counts which paper quotes would have been touched (188 at a 5 s quote life, 732 at 30 s, 10-08 to 10-22). It is a count, not a result." |
| **"The NBA season is pre-registered forward"** (added 2026-10-19) | No NBA-specific pre-registration document exists. NBA cells are scored under the general `PREREG_2026-10-07.json` seal (arm A and B_lag only so far, every cell INSUFFICIENT) and the fitted NBA arms are in warmup until about 20 regular-season games settle. Say "scored under the 2026-10-07 seal, fitted arms warmup", never "a pre-registered NBA season" or any NBA forward verdict. | "NBA is served and scored against the mid from the opener. A fitted NBA arm needs a new dated seal." |

**Pre-outreach housekeeping (status as of 2026-06-11):**

1. **the-odds-api key** — RESOLVED 2026-07-22 (user decision): the service is abandoned — the system uses its own odds feeds. No literal key exists in any tracked file (verified by git grep); the historical key remains only in old git revisions and is treated as dead. Optional 2-min step: deactivate the old key in the-odds-api account settings. This item no longer gates any launch.
2. **Personal phone number** — both files untracked from the public repo (kept local, gitignored) as of 2026-06-07. Prior revisions remain in git history; a full history scrub is a separate, destructive step not taken here.
3. **Public docs reconciliation** — README and PUBLIC_EVIDENCE.md front the retraction explicitly. CLAUDE.md has been reconciled with the honest numbers.

---

**Contact:** [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

*Audit basis: independent verification in conda env `basketball_ai` (Python 3.10, CUDA, RTX
4060) — pipeline run on real video, FastAPI app booted to count routes, ~170+ tests executed,
schemas/artifacts read directly, headline graders read line-by-line. No repo files were edited
during the audit. Last reconciled: 2026-06-11.*

---

## 5. Forward paper record 2026-10-06 .. 2026-10-22 (as of 2026-10-23)

PAPER ONLY. No order was placed, nothing here is a return figure, and every number below is
transcribed from a receipt under `docs/evidence/forward/` (path beside it; committed unless noted).
This section adds to the record. It does not replace any earlier text. The forward series is an
**operations and calibration record**. It is **not yet a verdict on the model**: no scored cell has
reached the sealed 30-game floor, and no game has passed qualification. That is the result so far,
and it is reported here as it stands. The 2026-10-19 version of this section covered 10-06 to 10-16
(113 games served, 9 night receipts with 2 COMPLETE and 7 PARTIAL, 0 of 44 judged games qualified);
those counts are the first rows of each table below, and they are still the dated canonical
`forward_window_counts` figure (as of 2026-10-19) in `docs/evidence/CANONICAL_FIGURES.json`.

**What the series is.** Each day a prospective schedule (`schedules/<D>_maker_forward.json`, rows
selected before the games start) names the games served on Kalshi in-game markets. The night after,
a paper night (`nights/<D>.json`, as_of D+1 06:00Z) runs six steps: qualification, fill_realism,
week, scoreboard, history and e. The sealed scoreboard
(`scoreboard/PREREG_2026-10-07.json`, file sha256 806fa58a..., effective 2026-10-07; nights before
that read `PREREG_2026-10-03.json`) scores arm A (the venue YES mid, **not** a devigged price), the fitted
arms B, C and D, and B_lag on Brier and log loss per sport, segment and target. Every cell is
INSUFFICIENT until it holds 30 games, and the scoring identity is frozen until a cell reaches that
floor.

**Games served per sport per day** (counted from `schedules/<D>_maker_forward.json`):

| Day | Served | mlb | nba | nfl | soccer | tennis | ncaaf |
|---|---|---|---|---|---|---|---|
| 10-06 | 3 | 2 | - | 1 | - | - | - |
| 10-07 | 7 | 3 | 4 | - | - | - | - |
| 10-08 | 19 | 2 | 6 | - | - | 11 | - |
| 10-09 | 19 | 1 | 3 | 1 | 2 | 12 | - |
| 10-10 | 26 | - | 3 | - | 7 | 7 | 9 |
| 10-11 | no schedule (laptop dark 10-10 01:56Z to 10-12 13:26Z; `daily/2026-10-12.md`) | | | | | | |
| 10-12 | 7 | 1 | 3 | - | 3 | - | - |
| 10-13 | 9 | 1 | 3 | 1 | 4 | - | - |
| 10-14 | 6 | 1 | 5 | - | - | - | - |
| 10-15 | 8 | 2 | 3 | - | - | - | 3 |
| 10-16 | 9 | 2 | 2 | 1 | 2 | - | 2 |
| 10-17, 10-18 | no schedule (laptop dark 10-16 03:56Z to 10-19 15:15Z, about 83 h; `daily/2026-10-19.md`) | | | | | | |
| 10-19 | 3 | - | - | - | 3 | - | - |
| 10-20 | 4 | 1 | 2 | - | - | - | 1 |
| 10-21 | 7 | - | 4 | - | 3 | - | - |
| 10-22 | 3 | - | 1 | - | - | - | 2 |
| **Total** | **130** | 16 | 39 | 4 | 24 | 30 | 17 |

Tennis left the served tuple from 10-11 by a recorded desk decision (`docs/operations/DESK_STATE.md`,
10-09 status). Every schedule file in this window is committed. The NBA rows through 10-16 are
preseason games (`season_type` 1 in the schedule rows); the 7 NBA rows from 10-20 on are
regular-season games (`season_type` 2).

**Nights** (from `nights/<D>.json`; 13 receipts, 4 COMPLETE, 9 PARTIAL, 4 calendar days without a night receipt):

| Night | Status | Reason (step status from the receipt) |
|---|---|---|
| 10-06 | PARTIAL | fill_realism and e KILLED at their step deadline |
| 10-07 | PARTIAL | qualification, fill_realism and e KILLED at their step deadline |
| 10-08 | PARTIAL | qualification KILLED at its memory ceiling; e KILLED at its deadline |
| 10-09 | PARTIAL | qualification, fill_realism and e KILLED at their step deadline |
| 10-10 | PARTIAL | qualification refused `undeclared_sport` (ncaaf); all 26 served games unsettled after the capture went dark (`daily/2026-10-12.md`) |
| 10-11 | missing | laptop dark, no schedule |
| 10-12 | COMPLETE | all six steps RAN |
| 10-13 | PARTIAL | scoreboard KILLED at its 900 s deadline, no scoreboard receipt (register row S824) |
| 10-14 | PARTIAL | scoreboard KILLED at its 900 s deadline, no scoreboard receipt |
| 10-15 | not run | laptop dark from 10-16 03:56Z; after the 10-19 relaunch, free RAM was 0.4 to 1.5 GB against the 2.5 GB night floor (`docs/operations/DESK_STATE.md`, 10-19 status) |
| 10-16 | COMPLETE | all six steps RAN, run after the 10-19 relaunch (as_of 2026-10-17T06:00Z; qualification 13 games judged, 0 qualified; week report INCOMPLETE) |
| 10-17, 10-18 | missing | no schedule (unrecoverable) |
| 10-19 | PARTIAL | qualification refused `step_budget_exceeded` (exit 3, no game judged); the other five steps RAN (run from 15:37Z 10-20) |
| 10-20 | PARTIAL | scoreboard exited 1 and wrote no receipt, and registry E was refused `caller_policy_not_prospective`: the checkout was a shallow clone (register row S832, below); qualification, fill_realism, week and history RAN (run from 14:53Z 10-22) |
| 10-21 | COMPLETE | all six steps RAN (run from 15:26Z 10-22); 6 of the 7 served games unsettled (`counts.unsettled_games` in `scoreboard/2026-10-21.json`) |
| 10-22 | COMPLETE | all six steps RAN (run from 15:42Z 10-23, after the desk was dark 00:05Z to 15:35Z 10-23); all 3 served games unsettled (`scoreboard/2026-10-22.json`) |

**Measurement gaps, stated plainly.** The desk was dark (no ticks; the host laptop off or asleep for
most of each interval) at least 10-10 01:56Z to 10-12 13:26Z, 10-16 03:56Z to 10-19 15:15Z, 10-20
00:26Z to 14:37Z, 10-21 04:56Z to 10-22 14:35Z and 10-23 00:05Z to 15:35Z (`daily/2026-10-12.md`,
`daily/2026-10-19.md`, `daily/2026-10-20.md`, `daily/2026-10-22.md`, `daily/2026-10-23.md`). The
cost: no schedule on 10-11, 10-17 or 10-18; night 10-15 never ran; and a served game that finished
while the desk was dark has no settlement, so it is not scored (6 of 7 on 10-21 and 3 of 3 on 10-22,
`counts.unsettled_games` in `scoreboard/<D>.json`). Separately, the main checkout was a shallow clone
from 17:18Z 10-20 until its repair on 10-22 (register row S832; commit bd95b24f4). Every
sealed-artifact prospectivity check refused on it, so night 10-20 has no scoreboard and no registry E
receipt. Its rerun is owed and had not run at this writing. These are gaps in the record, not results.

The scoreboard kills have a measured cause. The sealed scorer refits once per history row, so its
wall time grows about quadratically with the cumulative history: 1,443 s measured at 29k rows (`docs/operations/DESK_STATE.md`, 10-15 status; register row S825).
S824 (landed a6075f5c5, 10-15) raised the step deadline to 3,600 s as a stopgap. No scoreboard step
has been killed since: 25.7 s on 10-16, 65.5 s on 10-19, 18.6 s on 10-21 and 22.6 s on 10-22
(`nights/<D>.json`). Each of those steps records `no_fitted_arm: true`, so no fitted arm was trained
and these times do not yet test the refit cost. The real fix is S825, which is still **open** (register
`docs/evidence/HARNESS_GAPS_2026-09-03.md`). The earlier kills on 10-06 to 10-09 were memory and
time ceilings on qualification and fill_realism. They were bounded by S805 and S806 on 10-09; from
10-12 on both steps ran, and qualification refused once (`step_budget_exceeded`, 10-19).

**Scoreboard cells** (from `scoreboard/<D>.json`, outcome target; scoreboards exist for 10-06 to 10-10,
10-12, 10-16, 10-19, 10-21 and 10-22, and 10-13, 10-14 and 10-20 have none; every cell in every file is
**INSUFFICIENT**. The 95% interval is null in every cell except on 10-08, where the NBA arm A and
B_lag cells on 5 or 6 games carry one; those cells are INSUFFICIENT all the same):

- Games with arm A scored per night: 10-06 mlb 2, nfl 1; 10-07 mlb 3, nba 3; 10-08 mlb 2, nba 6;
  10-09 mlb 1, nba 1, nfl 1, soccer 2; 10-10 none (all unsettled); 10-12 mlb 1, soccer 3; 10-16
  mlb 1, nfl 1; 10-19 soccer 3; 10-21 nba 1; 10-22 none (all unsettled). Arm A is the market mid's
  own Brier. It describes the reference, not the model.
- The fitted arms B and C scored ticks on two nights only: 10-06 (mlb 2 games, nfl 1 game, under the
  earlier seal) and 10-09 (mlb 1 game). On every other night B, C and D scored zero ticks: the fitted
  arms were dark (fit `config_mismatch`, row S809, per the 10-09 status in `docs/operations/DESK_STATE.md`; `model_not_reconstructible` on 10-12 per `daily/2026-10-13.md`, and on every tick of the
  10-16, 10-19, 10-21 and 10-22 scoreboards). The desk reads the last four as no sport at the
  training floor of 20 settled games (register row S746; `daily/2026-10-23.md`). One or two games per
  cell carries no interval, so these per-night arm values are not quoted as model quality.
- Pooled C-minus-A on the outcome target, through 10-22 (`cumulative/2026-10-22.md`; the S721
  descriptive reader, a development population with no interval and no verdict; positive means C
  trails the mid), mlb only and unchanged since 10-14: seal 6abb1a85 4 games, Brier +0.2073 (log loss
  +1.2649); seal 801af61b 3 games, Brier -0.0648 (log loss -0.1665); seal 806fa58a 1 game, Brier
  +0.0283 (log loss +0.1925). All are INSUFFICIENT. The current seal has 1 of the 30 games its floor
  needs, and the reader now makes no projection (rate 0 under this seal). nba and soccer have 0
  C-and-A outcome games.
- Registry arm E (`cumulative/2026-10-22.md`): 967 ticks scored on 10-12 and 401 on 10-13, none
  since. Every E row was refused on 10-14 (`training_class_refused`) and on 10-16
  (`training_history_absent`); 10-19, 10-21 and 10-22 produced 0 E rows, and the 10-20 E step was
  refused (`caller_policy_not_prospective`, the shallow checkout). All INSUFFICIENT.

**Qualification** (from `qualification/<D>.json`; a receipt judges every selected game, served or
not): **0 PASS of 61 games judged** (10-06 0/3, 10-12 0/8, 10-13 0/14, 10-14 0/6, 10-16 0/13, 10-20
0/4, 10-21 0/9, 10-22 0/4). 10-07, 10-08 and 10-09 were killed before writing a receipt, 10-10 was
refused (`undeclared_sport`) and 10-19 was refused (`step_budget_exceeded`). All 61 failing games
carry COVERAGE_LOW and LINKAGE_INVALID. Other causes counted per game: STATE_GAP 51, DECISIONS_LOW
46, TAPE_INCOMPLETE 42, BOOK_CADENCE 35, RESERVATION_INVALID 33, NOT_LIVE 26 and STATE_STALE 23. No
game has qualified in any sport, to date (`cumulative/2026-10-22.md`). These are data-completeness
and linkage checks. A read-only replay of one game (LAD at MIL, 10-12;
`docs/evidence/harness/S831_PATH_PROOF_2026-10-22.md`, register row S831) traced part of COVERAGE_LOW
to the replay's own reservation rule: each RESERVATION_INVALID decision cuts the coverage credited to
the decision before it. Without those cuts that game would still cover 87.9 pct of its window, under
the 90 pct floor (arithmetic on the replay log, not a result); changing the rule needs a dated
re-seal, which has not happened. Other contributors in the period: overnight capture holes, laptop
sleeps, and a live shadow recorder that was **down 2026-10-13 01:08Z to 10-19 20:06Z and again from
00:49Z 10-20** (`daily/2026-10-20.md`), and that had **no heartbeat from 04:58Z 10-21 until its 19:55Z 10-23 relaunch**
(`daily/2026-10-22.md`, `daily/2026-10-23.md`; relaunched by the paper-desk watchdog before the 10-23 slate). Qualification grades the tape, not the model.

**Fill realism** (from `fill_realism/<D>.json`, mode `COUNTS ONLY` on unqualified tape; every receipt
from 10-14 on declares 1 unit and zero assumed latency): fills credited at a 5 s / 30 s quote life
were 10 / 77 (10-08), 3 / 20 (10-10), 35 / 111 (10-12), 36 / 139 (10-13), 22 / 105 (10-14), 24 / 61
(10-16), 24 / 49 (10-19), 20 / 108 (10-20), 3 / 25 (10-21) and 11 / 37 (10-22). The 10-08 to 10-22
totals are 188 / 732. The last seven days (10-16 to 10-22) sum to 82 / 280, which matches the last-7
count in `cumulative/2026-10-22.md`. These count simulated fills. They are not markouts, and no
fee-netted markout or P&L is computed from them.

**Feed latency** (`cumulative/2026-10-22.md`, S663 ledger): MLB statsapi receipt-minus-play-clock p50
was 15.5 to 19.5 s on the nights 10-06 to 10-20 that carry an MLB row. The NBA rows (ESPN scoreboard
feed) carry no p50 on any night; the 10-21 NBA ledger matched no play event and is flagged
UNDERPOWERED (`daily/2026-10-23.md`).

**NBA forward test from 2026-10-20.** The NBA regular season opened 2026-10-20. NBA games were
served on every scheduled day from 10-07 except 10-19, and NBA is scored under the current seal:
`PREREG_2026-10-07.json` (effective 2026-10-07, before the regular season) covers every served sport,
and the night-10-12 scoreboard holds NBA arm A (the mid) and B_lag cells over 3 games / 3,431 ticks,
all INSUFFICIENT (`docs/evidence/forward/scoreboard/2026-10-12.json`; readiness audit
`docs/evidence/forward/daily/NBA_READINESS_2026-10-19.md`). Seven regular-season games were served
from 10-20 to 10-22 (2, 4 and 1). One has scored cells: on 10-21, arm A and B_lag on 1 settled game,
every cell INSUFFICIENT; one game is not a result. The two 10-20 games are unscored because night
10-20 has no scoreboard (the shallow checkout), and the other four were unsettled because the desk
was dark when they finished. The fitted arms B / C / D are in warmup for NBA: their training uses
regular-season games only, so every NBA fit on disk is `fit_warmup` (`live_shadow_fit` nba 10-22,
`daily/2026-10-23.md`), and no NBA tick on 10-21 or 10-22 carries a B, C or D value; roughly 20
settled regular-season games are needed before a fitted NBA arm scores. NBA is not in
`model_optional_sports` (`mlb`, `nfl`, `soccer`), which governs arm D's model requirement, not whether
NBA is scored. No NBA-specific pre-registration document exists: the NBA forward series runs under
the sealed 2026-10-07 pre-registration, fitted arms warmup until the regular-season history exists.
The live shadow recorder had no heartbeat from 04:58Z 10-21 until its 19:55Z 10-23 relaunch, so the
opening regular-season week has no recorded in-game paper quotes in that interval (the late 10-20
games through the 10-23 afternoon); the newest shadow-fills receipt is `fills/2026-10-19.jsonl` (a partial day).

**Reading.** The desk wrote a prospective schedule on 14 of 17 calendar days and a night receipt on
13 of them, 4 COMPLETE. The receipts also record its operational limits: laptop uptime, scorer wall
time, a shallow checkout and recorder uptime. In the same period no cell reached its floor and no
game qualified. As of 2026-10-23 the forward series has no calibration verdict, either for or
against the model.

---

## Machine-readable figure list

Parsed by `scripts/platformkit/tracking/public_figures_check.py` (private tree); on the public tree
`scripts/platformkit/eval_gate/claim_consistency.py` enforces the same framing rule from
`docs/evidence/CANONICAL_FIGURES.json`. One figure per line, prefixed
`RETRACTED:` or `CORRECTED:`, the figure text first, then ` -- ` and the reason. A figure below
may appear on a public page (`README.md`, `EVIDENCE.md`, `docs/PUBLIC_EVIDENCE.md`) ONLY on a
line that also carries the word retracted, corrected, superseded or do-not-claim, or under a
markdown heading that does. Sources: `.claude/rules/no-edge-claims.md` and the 2026-09-14
correction in section 3 above.

RETRACTED: +18.38% -- pregame ROI, a market-follow grading artifact
RETRACTED: 0.119 -- endQ3 win-prob Brier, a Q4 feature leak
RETRACTED: +54% -- in-play ROI, an L5-proxy ceiling, not realized edge
RETRACTED: 78.11 -- in-play accuracy, the same L5-proxy ceiling
RETRACTED: 8.94 -- retracted inflated figure
RETRACTED: 54.57 -- retracted inflated figure
CORRECTED: 0.208 -- pregame model Brier; no artifact, did not reproduce; superseded 2026-09-14 by 0.1735 (n=743, TRAILS_CLOSE)
CORRECTED: 0.198 -- closing-line Brier of that same pair; superseded 2026-09-14 by 0.1666 (n=743, TRAILS_CLOSE)
SUPERSEDED 2026-09-24 (recompute, docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md): the same row reads n=372 scored (743 is the overlap; the first half is the fit), gap +0.0069, 95% CI [-0.0038, +0.0175], DM p 0.20, MATCHES_CLOSE under the written rule (CI includes 0) and underpowered (MDE 0.0152); MLB moneyline and soccer O/U 2.5 TRAIL the close with intervals excluding 0 (+0.0039 [+0.0028, +0.0051]; +0.0076 [+0.0059, +0.0092])


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
