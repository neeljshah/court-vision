"""
brain_system_spec.py -- curated spec of the CourtVision system funnel.

DATA module (no logic) consumed by brain_system_map.py to emit a navigable
Obsidian "system map": the whole pipeline as connected notes that bridge into
the existing sports intelligence brain. Grounded in CLAUDE.md Key Paths +
docs/PLATFORM.md. File references are for orientation only.

No edge claims: markets are efficient pregame; the product matches the devigged
close and measures calibration -- it does NOT claim a dollar edge.
"""
from __future__ import annotations

DISCLAIMER = (
    "Intelligence / calibration MAP -- markets are efficient pregame; this "
    "system matches the devigged close and measures calibration, it does NOT "
    "claim a $ edge."
)

# Ordered funnel stages: (key, title, one-line role).
STAGES = [
    ("00_Platform", "Platform",
     "Sport-blind kernel + per-sport adapters, the agentic loop, the API surface."),
    ("01_Data", "Data",
     "Raw inputs: CV tracking, multi-sport ingest, live feeds, corpora, DB."),
    ("02_Signals", "Signals",
     "Features + discovered signals + the leak-free validation gate."),
    ("03_Models", "Models",
     "Calibrated predictors: win-prob, prop models, recalibration."),
    ("04_Engines", "Engines",
     "Monte-Carlo possession sim + the in-game live engine."),
    ("05_Predictions", "Predictions",
     "Pregame (match the close) + in-game conditioning + scoreboards."),
    ("06_Execution", "Execution",
     "Kelly sizing, CLV ledger, prediction-market paper loop."),
    ("07_Intelligence", "Intelligence",
     "The multi-sport concept brain -- bridges into the sports graph."),
]

# stage_key -> [ (key, title, blurb, [files], [flows_to component keys]) ]
COMPONENTS: dict[str, list[tuple]] = {
    "00_Platform": [
        ("platform_kernel", "Platform Kernel",
         "Sport-blind validated machinery (loop, sim, validation, decision, brain, api) + domains/<sport> adapters.",
         ["kernel/", "domains/", "docs/PLATFORM.md"], ["ingest", "feature_engineering"]),
        ("improve_loop", "Improve Loop",
         "Agentic discover -> validate -> ship/REJECT loop that re-validates every funnel stage; honest rejects are successes.",
         ["src/loop/discovery.py", "src/loop/orchestrator.py"], ["signal_discovery"]),
        ("api_surface", "API Surface",
         "FastAPI (~99 endpoints, 12 routers) serving the live page + predictions.",
         ["api/main.py"], ["pregame", "in_game"]),
        ("validation_gate", "Validation Gate",
         "Fail-closed eval gate: golden-set, leak guard, walk-forward, freshness, ledger checks.",
         ["scripts/platformkit/", "tests/platform/"], ["calibration"]),
    ],
    "01_Data": [
        ("cv_tracking", "CV Tracking",
         "YOLOv8n -> SIFT homography -> Kalman+Hungarian -> OSNet 512-d re-ID -> EasyOCR -> EventDetector; per-possession tracking JSON.",
         ["src/pipeline/unified_pipeline.py", "src/tracking/osnet_reid.py", "src/tracking/advanced_tracker.py"],
         ["feature_engineering"]),
        ("ingest", "Ingest",
         "Multi-sport discover -> fetch -> process -> score game states (NBA API + per-sport adapters).",
         ["scripts/batch_season.py", "domains/basketball_nba/ingest_pbp_states.py", "domains/mlb/ingest_states.py"],
         ["feature_engineering", "corpora"]),
        ("live_feeds", "Live Feeds",
         "Live state via ESPN site.api (NBA hosts blocked), in-play odds feed + freshness guards.",
         ["scripts/platformkit/odds_provider/espn.py", "scripts/platformkit/odds_provider/inplay_feed.py"],
         ["live_engine"]),
        ("corpora", "Corpora",
         "Local league gamelogs, per-player CV parquets, snapshots (data/ -- gitignored, local-only).",
         ["data/cache/", "data/models/"], ["feature_engineering"]),
        ("database", "Database",
         "PostgreSQL schema for processed games + features.",
         ["database/schema.sql"], ["feature_engineering"]),
    ],
    "02_Signals": [
        ("feature_engineering", "Feature Engineering",
         "60+ leak-free features from tracking + box + game state; per-sport feature_spec.",
         ["src/features/feature_engineering.py", "domains/basketball_nba/feature_spec.py"],
         ["win_probability", "player_props", "possession_sim"]),
        ("signal_discovery", "Signal Discovery",
         "LLM-free signal proposer + orchestrator; proposes & screens candidate signals.",
         ["src/loop/discovery.py", "src/loop/orchestrator.py"], ["signal_catalog"]),
        ("signal_catalog", "Signal Catalog",
         "85 trained signals + the 80-artifact intelligence-layer manifest.",
         ["docs/INTELLIGENCE.md"], ["win_probability", "prop_stack"]),
        ("reject_ledger", "Reject Ledger",
         "Signal graveyard -- honest REJECTs as market-efficiency evidence (a null is a success).",
         ["scripts/platformkit/reject_ledger.py"], []),
    ],
    "03_Models": [
        ("win_probability", "Win Probability",
         "XGBoost team win-probability model.",
         ["src/prediction/win_probability.py"], ["possession_sim", "pregame"]),
        ("player_props", "Player Props",
         "7 per-stat prop models (PTS/REB/AST/FG3M/...).",
         ["src/prediction/player_props.py"], ["prop_stack"]),
        ("prop_stack", "Prop Stack",
         "Stacked prop ensemble + flag-gated bet policy.",
         ["src/prediction/prop_model_stack.py", "src/prediction/bet_policy.py"], ["pregame"]),
        ("calibration", "Calibration",
         "Isotonic / shin / Platt recalibration -- match the devigged close; calibration is the win, not $.",
         ["scripts/platformkit/"], ["pregame", "in_game", "calibration_scoreboard"]),
        ("model_registry", "Model Registry",
         "Versioned artifacts + temporal CV + drift assert (pkl n_features == meta count).",
         ["data/models/"], []),
    ],
    "04_Engines": [
        ("possession_sim", "Possession Sim",
         "Possession-level Monte-Carlo game simulation.",
         ["src/sim/basketball_sim.py", "src/sim/fast_sim.py"], ["pregame", "in_game"]),
        ("live_engine", "Live Engine",
         "In-game projection / state-conditioned re-pricing (WP withheld pre-Q3 by design).",
         ["src/prediction/live_engine.py"], ["in_game"]),
        ("bridge_model", "Bridge Model",
         "Translates CV-space behavior into public-feature space for non-CV games.",
         ["src/prediction/"], ["pregame"]),
    ],
    "05_Predictions": [
        ("pregame", "Pregame",
         "Pregame forecast -- matches the devigged close within noise (no edge claimed).",
         ["scripts/platformkit/"], ["betting_portfolio"]),
        ("in_game", "In-Game",
         "In-game conditioning: pregame prior + realized state -- the calibrated combinable edge.",
         ["src/prediction/live_engine.py"], ["betting_portfolio"]),
        ("calibration_scoreboard", "Calibration Scoreboard",
         "Per-sport Brier / ECE vs baselines (tuned vs baseline forecaster).",
         ["scripts/platformkit/"], []),
        ("cross_sport", "Cross-Sport",
         "One rating object scored out-of-sample across NBA/MLB/Soccer/Tennis.",
         ["scripts/platformkit/"], []),
    ],
    "06_Execution": [
        ("betting_portfolio", "Betting Portfolio",
         "Kelly sizing + CLV tracking -- a calibration/CLV instrument, NOT a $-edge product.",
         ["src/prediction/betting_portfolio.py"], ["clv_ledger"]),
        ("clv_ledger", "CLV Ledger",
         "Closing-line-value ledger for honest grading.",
         ["scripts/platformkit/clv_ledger.py"], []),
        ("pm_trading", "PM Trading",
         "Prediction-market paper loop (Kalshi / Polymarket).",
         ["scripts/platformkit/pm_trading/auto_loop.py", "scripts/platformkit/pm_trading/run_paper_today.py"], []),
    ],
    "07_Intelligence": [
        ("concept_brain", "Concept Brain",
         "The multi-sport concept graph: archetypes, mechanisms, schemes, drivers per sport.",
         ["vault/_Organized/"], []),
    ],
}

# stage_key -> [vault-relative targets in the EXISTING brain to bridge into].
BRIDGES: dict[str, list[str]] = {
    "07_Intelligence": [
        "_Organized/_Index/_Brain", "_Organized/NBA/_Digest", "_Organized/MLB/_Digest",
        "_Organized/Soccer/_Digest", "_Organized/Tennis/_Digest",
    ],
    "03_Models": [
        "_Organized/NBA/_Model_Card", "_Organized/MLB/_Model_Card", "_Organized/Tennis/_Model_Card",
    ],
    "05_Predictions": [
        "_Organized/_Index/_Calibration_Scoreboard", "_Organized/_Index/_Platform_Scoreboard",
    ],
    "02_Signals": [
        "_Organized/_Index/_Redundancy_Report", "_Organized/_Index/_Validated_Improvements",
    ],
}
