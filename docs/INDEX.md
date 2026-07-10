# Documentation Index -- the whole system, link by link

> **This is the map.** Land here from the [README](../README.md) and you can reach every
> aspect of the system by following links -- from the raw data feeds, through the models, the
> simulator, the calibration gates, the line-shopping and execution layer, the live in-game
> repricer, the autonomous self-improvement loop, and the agentic pipeline that built it all.
>
> Everything linked here is **tracked and published**. Honesty rails are non-negotiable: every
> prediction number is calibration / sharpness (Brier / RMSE / ECE), **never a dollar edge**, and
> the single truth-source for any number is
> [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

---

## Pick your path

| You are a... | Read in this order |
|--------------|--------------------|
| **Recruiter / quant reviewer** | [README](../README.md) -> [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md) -> [PREDICTOR_PLATFORM](PREDICTOR_PLATFORM.md) -> [PROOFS](PROOFS.md) -> [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) |
| **Engineer / architect** | [ARCHITECTURE](../ARCHITECTURE.md) -> [PLATFORM](PLATFORM.md) -> [architecture/system-overview](architecture/system-overview.md) -> [ML_MODELS](ML_MODELS.md) -> [API](API.md) |
| **Quant / methodology** | [quant-methodology](quant-methodology.md) -> [backtest-methodology](backtest-methodology.md) -> [research/validation-methodology](research/validation-methodology.md) -> [MARKET_EFFICIENCY_PROOF](MARKET_EFFICIENCY_PROOF.md) |
| **Edge researcher** | [research/edge-intelligence/README](research/edge-intelligence/README.md) -> [edge-theory](research/edge-intelligence/_framework/edge-theory.md) -> [proof-standards](research/edge-intelligence/_framework/proof-standards.md) -> [edge-ledger](research/edge-intelligence/_proof/edge-ledger.md) |
| **Operator / deployer** | [PRODUCTION_RUNBOOK](PRODUCTION_RUNBOOK.md) -> [operations/data-pipeline](operations/data-pipeline.md) -> [LIVE_OPERATOR_RUNBOOK](LIVE_OPERATOR_RUNBOOK.md) -> [DEPLOY_RAILWAY](DEPLOY_RAILWAY.md) |
| **Curious how AI built it** | [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) -> [research/ai-leverage-2026-06-16/00-README](research/ai-leverage-2026-06-16/00-README.md) -> [research/claude-org/01_official_best_practices](research/claude-org/01_official_best_practices.md) |

New to the vocabulary? Keep the [GLOSSARY](GLOSSARY.md) open in a tab (CLV, leak-free,
walk-forward, Shin devig, Brier, Kelly, devig, parity, ...).

---

## The whole system as one funnel

Every stage feeds the next; one calibrated win-probability anchors every market, and a single
seam propagates a model change coherently to moneyline, spread, total, props, and the in-game
reprice. Follow the links to go as deep as you want at any stage.

```
  DATA  ->  SIGNALS  ->  MODELS  ->  ENGINES  ->  PREDICTIONS  ->  EXECUTION  ->  SELF-IMPROVE
```

| Stage | What happens | Go deep |
|-------|--------------|---------|
| **1. DATA** | Keyless, leak-free, as-of-stamped ingest across 5 sports (ESPN, MLB StatsAPI, Sackmann, football-data) + prediction markets (Kalshi, Polymarket) + DFS prop feeds (Underdog, PrizePicks, FanDuel, DraftKings) | [DATA](DATA.md) - [data_schema](data_schema.md) - [operations/data-pipeline](operations/data-pipeline.md) - [research/edge-intelligence/_scrapers/data-acquisition](research/edge-intelligence/_scrapers/data-acquisition.md) |
| **2. SIGNALS** | Leak-safe per-entity features + priors: team ratings (Elo / EW-Poisson / serve-hold), per-player per-exposure rates, ~190-feature NBA prop stack, 44 atlases, playstyle archetypes | [signal-inventory](signal-inventory.md) - [models/feature-inventory](models/feature-inventory.md) - [INTELLIGENCE](INTELLIGENCE.md) - [PLAYER_INTELLIGENCE](PLAYER_INTELLIGENCE.md) |
| **3. MODELS** | One calibrated win-probability per sport (the anchor) + per-player count distributions (Poisson / Negative-Binomial, dispersion-calibrated) | [ML_MODELS](ML_MODELS.md) - [models/model-registry](models/model-registry.md) - [models/calibration](models/calibration.md) |
| **4. ENGINES** | JointDistribution (coherent score matrix) + possession Monte-Carlo sim (emergent teammate correlation) + the live repricer (conditions on realized state) | [architecture/possession-simulator](architecture/possession-simulator.md) - [LIVE_ENGINE_V2](LIVE_ENGINE_V2.md) - [research/project-deep-dive/08-nba-montecarlo-sim-ratings](research/project-deep-dive/08-nba-montecarlo-sim-ratings.md) - [research/project-deep-dive/11-live-ingame-layer](research/project-deep-dive/11-live-ingame-layer.md) |
| **5. PREDICTIONS** | One seam -> the full market surface (ML / totals / spreads / 1X2 / BTTS / correct-score / prop ladders / SGP), pregame and in-game | [PREDICTOR_PLATFORM](PREDICTOR_PLATFORM.md) - [PREDICTOR_QUICKSTART](PREDICTOR_QUICKSTART.md) - [scoreboard](scoreboard.md) |
| **6. EXECUTION** | Line-shopping across books -> Shin-devig -> EV -> tier floors (A/B/C) -> CLV-flat-unit + capped quarter-Kelly, units only, never $; below floor = no bet; paper-only | [EXECUTION_GUIDE](EXECUTION_GUIDE.md) - [BETTING](BETTING.md) - [architecture/execution-engine](architecture/execution-engine.md) - [risk-framework](risk-framework.md) - [decisions](decisions.md) |
| **7. SELF-IMPROVE** | Autonomous discovery -> 5-gate ratchet -> reject-ledger -> recalibration, replication-gated, versioned artifacts + auto-rollback | [research/project-deep-dive/06-eval-proving-spine](research/project-deep-dive/06-eval-proving-spine.md) - [research/ai-leverage-2026-06-16/blueprints/eval-gate](research/ai-leverage-2026-06-16/blueprints/eval-gate.md) - [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) |

---

## Full document tree

### Front door / orientation
- [README](../README.md) -- the funnel narrative end-to-end with honest numbers
- [ARCHITECTURE](../ARCHITECTURE.md) -- end-to-end technical map (root)
- [VISION](../VISION.md) -- the long-form thesis: what it is, what it is not
- [CLAUDE](../CLAUDE.md) / [AGENTS](../AGENTS.md) -- agent-onboarding (how an AI picks up the repo cold)
- [PROJECT_INDEX](PROJECT_INDEX.md) -- the older role-based doc hub (this INDEX supersedes it)
- [SYSTEM_OVERVIEW](SYSTEM_OVERVIEW.md) -- one-screen system summary
- [GLOSSARY](GLOSSARY.md) -- every term defined once
- [CHANGELOG](../CHANGELOG.md) -- version history

### Honesty truth-sources (read these before trusting any number)
- [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md) -- **the single truth-source**: every number's proof + the do-not-claim list
- [HONESTY_SYSTEM](HONESTY_SYSTEM.md) -- the discipline stack itself: lint -> gates -> independent validators -> preregistration -> retraction list -> ops detectors -> git guards, with a worked REJECT
- [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) -- open gaps, unproven claims, honest nulls
- [PROOFS](PROOFS.md) -- the provability index: every claim -> its runnable leak-free proof
- [MARKET_EFFICIENCY_PROOF](MARKET_EFFICIENCY_PROOF.md) -- the full-season walk-forward showing mainlines are efficient
- [CEILING](CEILING.md) -- the realistic bounds on edge claims
- [CALIBRATION_RECORD](CALIBRATION_RECORD.md) -- per-sport calibration audit

### Product / platform
- [PREDICTOR_PLATFORM](PREDICTOR_PLATFORM.md) -- full product: thesis, scorecards, architecture
- [PREDICTOR_QUICKSTART](PREDICTOR_QUICKSTART.md) / [PREDICTIONS_QUICKSTART](../PREDICTIONS_QUICKSTART.md) -- run a prediction in 60s
- [PLATFORM](PLATFORM.md) -- kernel + adapter multi-sport architecture
- [PLATFORM_TOOLING](PLATFORM_TOOLING.md) -- the platformkit CLI + proof-module surface
- [PLATFORM_HARNESS](PLATFORM_HARNESS.md) -- the platformkit build/test/gate harness underneath the CLI
- [PRODUCT_ONE_PAGER](PRODUCT_ONE_PAGER.md) -- one-page pitch
- [DEMO](DEMO.md) -- deterministic walkthrough (environment, CLIs, API, CV)
- [PRODUCT_DEMO](PRODUCT_DEMO.md) -- the 15-minute path: system health, prediction, oracle receipt, composed board, honesty ledgers
- [PUBLIC_EVIDENCE](PUBLIC_EVIDENCE.md) -- 60-second funnel scan
- [HIRE_PACKAGE](HIRE_PACKAGE.md) / [WORLD_CLASS_CASE](WORLD_CLASS_CASE.md) / [SELL-READINESS](SELL-READINESS.md) -- portfolio framing

### Methodology / validation
- [quant-methodology](quant-methodology.md) -- walk-forward CV, leak guards, multi-corpus gate
- [backtest-methodology](backtest-methodology.md) -- leak-free backtest construction
- [research/validation-methodology](research/validation-methodology.md) -- CLV-over-ROI doctrine, null discipline
- [risk-framework](risk-framework.md) -- decision-layer guardrails (kill-switch, drawdown)

### Architecture deep-dives
- [architecture/system-overview](architecture/system-overview.md) -- core systems + interconnects
- [architecture/possession-simulator](architecture/possession-simulator.md) -- the Monte-Carlo engine
- [architecture/execution-engine](architecture/execution-engine.md) -- bet selection + sizing
- [architecture/cv-pipeline](architecture/cv-pipeline.md) -- broadcast-video CV internals
- [architecture/dashboard-spec](architecture/dashboard-spec.md) -- front-end spec
- [architecture](architecture.md) -- alternate architecture narrative

### Models & signals
- [ML_MODELS](ML_MODELS.md) -- validated metrics (Brier / MAE / ECE) per sport + model
- [models/model-registry](models/model-registry.md) -- artifact inventory
- [models/calibration](models/calibration.md) -- Platt / isotonic / temperature / Shin devig
- [models/feature-inventory](models/feature-inventory.md) -- ~190-feature stack, per-feature WF result
- [models/BUILD_PROMPT](models/BUILD_PROMPT.md) -- the model-builder prompts
- [signal-inventory](signal-inventory.md) -- 44 atlases + trained-signal catalog
- [INTELLIGENCE](INTELLIGENCE.md) -- 80-artifact intelligence-layer manifest
- [PLAYER_INTELLIGENCE](PLAYER_INTELLIGENCE.md) -- per-player dossier showcase
- [MEMORY_GRAPH](MEMORY_GRAPH.md) -- the knowledge-graph structure

### Execution / betting
- [EXECUTION_GUIDE](EXECUTION_GUIDE.md) -- predictions -> sized bets (Kelly, CLV, gates)
- [BETTING](BETTING.md) -- line-shopping, arb, EV, CLV ledger, paper loop
- [decisions](decisions.md) -- decision-engine logic, tier floors, no-bet policy
- [label_strategy](label_strategy.md) -- prop labeling (reliable / thin / reject), CLV tiering
- [scoreboard](scoreboard.md) -- the live CLV / calibration scoreboard
- [PAPER_TRADING_STACK](PAPER_TRADING_STACK.md) -- the paper-trading ledger + fill-sim + analytics stack (never real money)

### Live / in-game
- [LIVE_ENGINE_V2](LIVE_ENGINE_V2.md) -- in-game repricer architecture
- [LIVE_ENGINE_V2_WEB](LIVE_ENGINE_V2_WEB.md) -- web surface for live predictions
- [LIVE_OPERATOR_RUNBOOK](LIVE_OPERATOR_RUNBOOK.md) / [operator_runbook](operator_runbook.md) -- live ops

### Data & outputs
- [DATA](DATA.md) -- sources, schemas, freshness
- [DATA_OUTPUTS](DATA_OUTPUTS.md) -- parquet snapshots, feature store, artifacts
- [data_schema](data_schema.md) -- parquet / feature-store schemas
- [DATA_DEPTH](DATA_DEPTH.md) -- the per-sport data census, the census->diff->factory loop, and the NBA lineup-reconstruction keystone
- [INGEST_PIPELINES](INGEST_PIPELINES.md) -- per-source ingest jobs, cadence, and keyless-capture recipes
- [SPORTS_COVERAGE](SPORTS_COVERAGE.md) -- per-sport matrix: data on disk, cadences, VERIFIED claims, vs-close verdict, biggest gap

### Serving / API / front-end
- [API](API.md) -- the FastAPI surface (endpoints, contracts)
- [ASK_SURFACES](ASK_SURFACES.md) -- the question-answering layer: ask() families, composers, trait profiles, paper analytics (VERIFIED claims only, honest UNANSWERABLE)
- [FRONTEND_OVERVIEW](FRONTEND_OVERVIEW.md) -- the dashboard surfaces

### Operations / deployment
- [PRODUCTION_RUNBOOK](PRODUCTION_RUNBOOK.md) -- launch, bootstrap, monitor, troubleshoot
- [DEPLOY_RAILWAY](DEPLOY_RAILWAY.md) -- Railway deploy
- [daily_workflow_cron](daily_workflow_cron.md) -- scheduled jobs
- [DAEMONS](DAEMONS.md) -- the always-on background daemons (governors, reapers, capture loops) and what each one guards
- [operations/](operations/data-pipeline.md) -- data-pipeline, deployment, full-game-production, RunPod runbooks, backfill

### Computer-vision lineage (origin, not the headline)
- [CV_TRACKING](CV_TRACKING.md) -- the broadcast-video CV pipeline internals
- [tracking_pipeline](tracking_pipeline.md) -- the tracking orchestrator
- [research/project-deep-dive/10-cv-tracking-pipeline](research/project-deep-dive/10-cv-tracking-pipeline.md) -- CV deep-dive

### Project deep-dive (end-to-end walkthrough, 13 chapters)
- [00-MASTER](research/project-deep-dive/00-MASTER.md) -- start of the guided tour
- [01-architecture-funnel](research/project-deep-dive/01-architecture-funnel.md) - [02-betting-frontend-serving](research/project-deep-dive/02-betting-frontend-serving.md) - [03-odds-prop-scrapers](research/project-deep-dive/03-odds-prop-scrapers.md) - [04-soccer-wc-prop-engine](research/project-deep-dive/04-soccer-wc-prop-engine.md) - [05-mlb-prop-engine](research/project-deep-dive/05-mlb-prop-engine.md) - [06-eval-proving-spine](research/project-deep-dive/06-eval-proving-spine.md) - [07-nba-prediction-models](research/project-deep-dive/07-nba-prediction-models.md) - [08-nba-montecarlo-sim-ratings](research/project-deep-dive/08-nba-montecarlo-sim-ratings.md) - [09-intelligence-signal-atlases](research/project-deep-dive/09-intelligence-signal-atlases.md) - [10-cv-tracking-pipeline](research/project-deep-dive/10-cv-tracking-pipeline.md) - [11-live-ingame-layer](research/project-deep-dive/11-live-ingame-layer.md) - [12-data-inventory-ops](research/project-deep-dive/12-data-inventory-ops.md)

### Edge-intelligence corpus (the brain's map of where edge can exist)
- [README](research/edge-intelligence/README.md) -- corpus index / spine
- [00-INTELLIGENCE-MASTER-PLAN](research/edge-intelligence/00-INTELLIGENCE-MASTER-PLAN.md) - [01-everything-needed-to-edge](research/edge-intelligence/01-everything-needed-to-edge.md)
- **Framework:** [edge-theory](research/edge-intelligence/_framework/edge-theory.md) - [proof-standards](research/edge-intelligence/_framework/proof-standards.md) - [cut-list-no-edge](research/edge-intelligence/_framework/cut-list-no-edge.md) - [data-to-edge-pipeline](research/edge-intelligence/_framework/data-to-edge-pipeline.md) - [intelligence-architecture](research/edge-intelligence/_framework/intelligence-architecture.md)
- **Methods:** [poisson-vs-negbin](research/edge-intelligence/_framework/methods/poisson-vs-negbin-for-counts.md) - [empirical-bayes-shrinkage](research/edge-intelligence/_framework/methods/empirical-bayes-shrinkage.md) - [shin-devig](research/edge-intelligence/_framework/methods/shin-devig.md) - [isotonic-when](research/edge-intelligence/_framework/methods/isotonic-calibration-when.md) - [kelly-sizing-correlation](research/edge-intelligence/_framework/methods/kelly-sizing-correlation.md) - [clv-computation](research/edge-intelligence/_framework/methods/clv-computation.md) - [walk-forward-leak-guards](research/edge-intelligence/_framework/methods/walk-forward-leak-guards.md) - [conformal-intervals](research/edge-intelligence/_framework/methods/conformal-intervals.md)
- **Inefficiency recipes:** [dfs-pickem-rigidity](research/edge-intelligence/_framework/inefficiencies/dfs-pickem-rigidity.md) - [live-ingame-lag](research/edge-intelligence/_framework/inefficiencies/live-ingame-lag.md) - [prediction-market-vs-book](research/edge-intelligence/_framework/inefficiencies/prediction-market-vs-book.md) - [stale-soft-line](research/edge-intelligence/_framework/inefficiencies/stale-soft-line.md) - [correlated-sgp](research/edge-intelligence/_framework/inefficiencies/correlated-sgp.md) - [same-day-freshness-gap](research/edge-intelligence/_framework/inefficiencies/same-day-freshness-gap.md) - [low-attention-niche](research/edge-intelligence/_framework/inefficiencies/low-attention-niche.md)
- **Proof / ledger:** [edge-ledger](research/edge-intelligence/_proof/edge-ledger.md) - [cut-vs-push-scorecard](research/edge-intelligence/_proof/cut-vs-push-scorecard.md)
- **Live:** [in-game-edge](research/edge-intelligence/_live/in-game-edge.md)
- **Scrapers:** [data-acquisition](research/edge-intelligence/_scrapers/data-acquisition.md) - [closing-line-and-clv](research/edge-intelligence/_scrapers/closing-line-and-clv.md) - and per-source deep specs (Underdog, PrizePicks, FanDuel, DraftKings, ESPN, MLB StatsAPI, Sackmann, football-data, SofaScore, Kalshi, Polymarket, The-Odds-API) under `research/edge-intelligence/_scrapers/deep/`
- **Wiring:** [wire-the-dead-funnel](research/edge-intelligence/_wiring/wire-the-dead-funnel.md) - [same-day-freshness](research/edge-intelligence/_wiring/same-day-freshness.md) - [nba-props-keyless](research/edge-intelligence/_wiring/nba-props-keyless.md)
- **Per sport** (each has: 00-edge-map, data-sources, markets-and-props, inefficiency-catalog, model-levers, get-to-edge-plan, deep/ archetypes + prop playbooks): [nba](research/edge-intelligence/nba/00-edge-map.md) - [mlb](research/edge-intelligence/mlb/00-edge-map.md) - [soccer_club](research/edge-intelligence/soccer_club/00-edge-map.md) - [soccer_intl](research/edge-intelligence/soccer_intl/00-edge-map.md) - [tennis](research/edge-intelligence/tennis/00-edge-map.md)

### How AI built this (the factory)
- [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) -- the Opus-orchestrator / Sonnet-executor pipeline in depth
- [research/ai-leverage-2026-06-16/00-README](research/ai-leverage-2026-06-16/00-README.md) -- the AI-leverage corpus index
- Briefs: [claude-mastery](research/ai-leverage-2026-06-16/01-claude-mastery.md) - [ai-engineering-playbook](research/ai-leverage-2026-06-16/02-ai-engineering-playbook.md) - [anthropic-agent-patterns](research/ai-leverage-2026-06-16/briefs/anthropic-agent-patterns.md) - [agentic-orchestration](research/ai-leverage-2026-06-16/briefs/agentic-orchestration.md) - [claude-skills](research/ai-leverage-2026-06-16/briefs/claude-skills.md) - [claude-mcp](research/ai-leverage-2026-06-16/briefs/claude-mcp.md)
- Blueprints: [claude-build-loop](research/ai-leverage-2026-06-16/blueprints/claude-build-loop.md) - [eval-gate](research/ai-leverage-2026-06-16/blueprints/eval-gate.md) - [mcp-and-ledger](research/ai-leverage-2026-06-16/blueprints/mcp-and-ledger.md)
- Org: [claude-org/01_official_best_practices](research/claude-org/01_official_best_practices.md) ... [10_cohesion_architecture](research/claude-org/10_cohesion_architecture.md)

### Other research
- [research/competitive-landscape](research/competitive-landscape.md) - [research/market-microstructure](research/market-microstructure.md) - [research/edge-taxonomy](research/edge-taxonomy.md) - [research/precedent-analysis](research/precedent-analysis.md) - [research/data-sources](research/data-sources.md)
- Sprint: [research/organization-sprint/SPRINT-SUMMARY](research/organization-sprint/SPRINT-SUMMARY.md) - [EVERY-MARKET-MAP](research/organization-sprint/EVERY-MARKET-MAP.md) - [EDGE-HUNT-RESULTS](research/organization-sprint/EDGE-HUNT-RESULTS.md)
- Betting product: [research/betting-product/01_competitor_teardown](research/betting-product/01_competitor_teardown.md) ... [04_freshness_arch](research/betting-product/04_freshness_arch.md)

---

## Contributing
- [CONTRIBUTING](../CONTRIBUTING.md) -- dev setup, branch/PR workflow, ML ship-gate, repo hygiene

---

*Honesty rail (applies to every linked doc): all prediction numbers are calibration / sharpness,
never a dollar edge; candidate prop edges are tiered HYPOTHESIS -> CALIBRATION-PROVEN -> CLV-PROVEN
and proven only by forward CLV. Truth-source: [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md).*
