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
| **Edge researcher** | [MARKET_EFFICIENCY_PROOF](MARKET_EFFICIENCY_PROOF.md) -> [quant-methodology](quant-methodology.md) -> [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md) -> [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md) |
| **Operator / deployer** | [PRODUCTION_RUNBOOK](PRODUCTION_RUNBOOK.md) -> [operations/data-pipeline](operations/data-pipeline.md) -> [LIVE_OPERATOR_RUNBOOK](LIVE_OPERATOR_RUNBOOK.md) -> [DEPLOY_RAILWAY](DEPLOY_RAILWAY.md) |
| **Curious how AI built it** | [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) |

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
| **1. DATA** | Keyless, leak-free, as-of-stamped ingest across 5 sports (ESPN, MLB StatsAPI, Sackmann, football-data) + prediction markets (Kalshi, Polymarket) + DFS prop feeds (Underdog, PrizePicks, FanDuel, DraftKings) | [DATA](DATA.md) - [data_schema](data_schema.md) - [operations/data-pipeline](operations/data-pipeline.md) |
| **2. SIGNALS** | Leak-safe per-entity features + priors: team ratings (Elo / EW-Poisson / serve-hold), per-player per-exposure rates, ~190-feature NBA prop stack, 48 atlases, playstyle archetypes | [signal-inventory](signal-inventory.md) - [models/feature-inventory](models/feature-inventory.md) - [INTELLIGENCE](INTELLIGENCE.md) - [PLAYER_INTELLIGENCE](PLAYER_INTELLIGENCE.md) |
| **3. MODELS** | One calibrated win-probability per sport (the anchor) + per-player count distributions (Poisson / Negative-Binomial, dispersion-calibrated) | [ML_MODELS](ML_MODELS.md) - [models/model-registry](models/model-registry.md) - [models/calibration](models/calibration.md) |
| **4. ENGINES** | JointDistribution (coherent score matrix) + possession Monte-Carlo sim (emergent teammate correlation) + the live repricer (conditions on realized state) | [architecture/possession-simulator](architecture/possession-simulator.md) - [LIVE_ENGINE_V2](LIVE_ENGINE_V2.md) |
| **5. PREDICTIONS** | One seam -> the full market surface (ML / totals / spreads / 1X2 / BTTS / correct-score / prop ladders / SGP), pregame and in-game | [PREDICTOR_PLATFORM](PREDICTOR_PLATFORM.md) - [PREDICTOR_QUICKSTART](PREDICTOR_QUICKSTART.md) - [scoreboard](scoreboard.md) |
| **6. EXECUTION** | Line-shopping across books -> Shin-devig -> EV -> tier floors (A/B/C) -> CLV-flat-unit + capped quarter-Kelly, units only, never $; below floor = no bet; paper-only | [EXECUTION_GUIDE](EXECUTION_GUIDE.md) - [BETTING](BETTING.md) - [architecture/execution-engine](architecture/execution-engine.md) - [risk-framework](risk-framework.md) - [decisions](decisions.md) |
| **7. SELF-IMPROVE** | Autonomous discovery -> 5-gate ratchet -> reject-ledger -> recalibration, replication-gated, versioned artifacts + auto-rollback | [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) |

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
- [INGAME_PROOF](INGAME_PROOF.md) -- the one measured calibration win: in-game conditioning sharpens the win-prob forecaster (calibration, not a dollar edge)
- [CALIBRATION_DIAGRAM](CALIBRATION_DIAGRAM.md) -- reliability table + Murphy Brier decomposition (self-checked), worked on the pre-conditioning baseline
- [EVAL_PLATFORM_MAPPING](EVAL_PLATFORM_MAPPING.md) -- the existing gates mapped to the eval primitives Braintrust/Galileo/Arize productize
- [CEILING](CEILING.md) -- the realistic bounds on edge claims
- [CALIBRATION_RECORD](CALIBRATION_RECORD.md) -- per-sport calibration audit
- [RECEIPTS](../RECEIPTS.md) -- append-only receipts ledger: every calibration number read verbatim from a machine artifact, verdicts include losses

### Evidence pages (claim -> receipt -> reproduce, one per claim family)
- [evidence/README](evidence/README.md) -- **the evidence hub**: all pages grouped (honesty / calibration-market / engineering / frontier), each with its strongest receipt, plus the one-command `check_all.py` proof
- [evidence/retraction-story](evidence/retraction-story.md) -- the flagship: the instruments that refuted my own headline numbers
- [evidence/ingame-conditioning](evidence/ingame-conditioning.md) -- the one measured calibration win, market-comparison losses stated plainly
- [evidence/agent-fleet-direction](evidence/agent-fleet-direction.md) -- directing an agent fleet under fail-closed gates (~91% agent-authored, disclosed)
- [evidence/devig-stack](evidence/devig-stack.md) -- four devig methods from scratch; the Shin-devigged close as the honest yardstick
- [evidence/leak-instruments](evidence/leak-instruments.md) -- the leakage-catching instruments (walk-forward guard, truncation invariance, multi-corpus gate, ship gate)
- [evidence/cv-pipeline](evidence/cv-pipeline.md) -- broadcast video to court coordinates on a consumer GPU, with the not-demonstrated list stated
- [evidence/calibration-decomposition](evidence/calibration-decomposition.md) -- our Brier gap vs the market decomposed (reliability vs resolution) + the ranked worst-bucket list
- [evidence/mcp-live-demo](evidence/mcp-live-demo.md) -- three real MCP envelopes captured live: receipt-backed answers, the caveat ladder, and the system disclosing when the market is sharper
- [evidence/market-disagreement](evidence/market-disagreement.md) -- when we disagree with the market, who wins -- bucketed by disagreement size, over time
- [ANALYTICS_CATALOG](ANALYTICS_CATALOG.md) -- every analytic the system computes: artifact path, chart, honest caveat, in one catalog
- [ATLAS](ATLAS.md) -- the card-atlas gallery: 1,549 floor-gated `DESCRIPTIVE_ONLY` entity cards across 7 packs (NBA players/teams, MLB pitching/batters, calibration, tennis, soccer), served by the MCP `atlas_card` resolver
- [evidence/industry-metrics](evidence/industry-metrics.md) -- the industry player-metric landscape mapped: three honest approximations built, RAPM-family declared out of reach
- [evidence/player-props](evidence/player-props.md) -- the 7-stat projection stack measured two ways, each number bound to its label
- [evidence/answer-engine](evidence/answer-engine.md) -- the fail-closed answer engine: one resolver per question, refusals measured (125/125 edge-language refused)
- [evidence/data-layer](evidence/data-layer.md) -- keyless, leak-safe, self-auditing data platform (statcast 693k, claims corpus 103k, matchup matrix 291k)
- [evidence/possession-simulator](evidence/possession-simulator.md) -- possession Monte Carlo whose teammate correlation emerges from mechanics, graded by state cell
- [evidence/operations-reliability](evidence/operations-reliability.md) -- unattended systems that fail visibly: sentinels, watchdog, and the health readout that honestly reports RED
- [evidence/knowledge-engine](evidence/knowledge-engine.md) -- sports folklore in, preregistered verdicts out: 50.4% survival over 256 testable mechanisms, nulls published
- [evidence/execution-honesty](evidence/execution-honesty.md) -- the paper-execution stack with no path to a real order, whose audit publishes its own nulls
- [evidence/novel-analytics](evidence/novel-analytics.md) -- frontier measurements with adversarial prior-art checks attached: information-arrival, overreaction spectrum, mechanism survival, comeback atlas, kernel transfer -- honest INCREMENTAL verdicts included
- [evidence/ai-engineering](evidence/ai-engineering.md) -- the five 2026 AI-eng hiring skills mapped to committed artifacts: evals, fail-closed answers, MCP, guardrails, cost-aware routing
- [evidence/entity-atlas](evidence/entity-atlas.md) -- 1,549 per-entity analytics cards with declared floors and manifest-verified counts, served fail-closed by the atlas_card resolver
- [evidence/true-intelligence](evidence/true-intelligence.md) -- the counterfactual/context/microstructure/forward-graded/cross-sport wave: what-if, why, when, who-grades-the-graders, with not_buildable verdicts shown beside the wins (fwd scoreboard 121 verified vs 134 null-or-worse)
- [evidence/analytical-depth](evidence/analytical-depth.md) -- the recorded-analytics inventory as evidence: 23 modules, the claims-corpus generated-vs-validated split, the Statcast base, tick microstructure, fail-closed QA coverage
- [evidence/novel-analytics](evidence/novel-analytics.md) -- uniquely-auditable measurements: five market-microstructure/calibration analytics, each with its honest prior-art verdict (2 INCREMENTAL, 1 ALREADY_DONE, 1 N/A) and the market beating our in-game model stated in numbers

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
- [signal-inventory](signal-inventory.md) -- 48 atlases + trained-signal catalog
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

### How AI built this (the factory)
- [BUILT_WITH_CLAUDE](BUILT_WITH_CLAUDE.md) -- the Opus-orchestrator / Sonnet-executor pipeline in depth

### Research
- [research/validation-methodology](research/validation-methodology.md) -- the CLV-over-ROI validation doctrine (the one public research note)

*(Other internal research -- competitive landscape, market microstructure, edge taxonomy, the organization-sprint and betting-product folders -- is kept LOCAL-ONLY and gitignored, so it is intentionally not linked from this public index.)*

---

## Contributing
- [CONTRIBUTING](../CONTRIBUTING.md) -- dev setup, branch/PR workflow, ML ship-gate, repo hygiene

---

*Honesty rail (applies to every linked doc): all prediction numbers are calibration / sharpness,
never a dollar edge; candidate prop edges are tiered HYPOTHESIS -> CALIBRATION-PROVEN -> CLV-PROVEN
and proven only by forward CLV. Truth-source: [JOB_EVIDENCE_PACKET](JOB_EVIDENCE_PACKET.md).*
