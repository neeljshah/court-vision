"""_gate_surfaces.py — Static surface/flag data for gate_coverage_report.py.

N-GATE-001 data module: pure list/dict constants + one accessor.
No imports beyond stdlib typing. No app boot. No torch.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Pre-existing flags (documented in flags.py; owned by other modules)
# ---------------------------------------------------------------------------

PREEXISTING_FLAGS: List[Tuple[str, str]] = [
    ("CV_LLM_CONTEXT",                "pre-existing — owned by src/ingame/"),
    ("CV_INGAME_SBS",                 "pre-existing — owned by src/ingame/sbs_shadow.py"),
    ("CV_LIVE_SIM",                   "pre-existing — owned by src/sim/live_game_simulator.py"),
    ("CV_AVAIL_PARQUET_FALLBACK",     "pre-existing — owned by src/prediction/availability.py"),
    ("CV_ENSEMBLE16_DECORR",          "pre-existing — owned by src/prediction/ (decorrelation layer)"),
    ("CV_ENGINE_RELIABILITY_WEIGHTS", "pre-existing — owned by src/prediction/ (engine weighting)"),
]

# ---------------------------------------------------------------------------
# Ad-hoc flags (found by grep; live outside flags.py)
# ---------------------------------------------------------------------------

ADHOC_FLAGS: List[Tuple[str, str, str]] = [
    # (name, owner_file, note)
    ("CV_ARCHETYPE_CORR",    "src/prediction/correlation_recal.py",
     "Playstyle correlation recalibration — gated, default-OFF; VERDICT in memory notes: accuracy-not-ROI"),
    ("CV_VAC_LOAD_FEATURE",  "src/prediction/prop_pergame.py",
     "Vacated-load feature gate — gated, default-OFF; VERDICT in memory notes: cross-season weaker than implied"),
    ("CV_QSHAPE_DECAY",      "scripts/predict_in_game.py + api/live_game_router.py",
     "Quarter-shape decay factor W-015 — gated, default-OFF; no formal ledger entry found"),
    ("CV_MIN_VAR",           "scripts/courtvision/build_cv_board.py (min_var_layer)",
     "Min-var joint-correction layer for DD/combo markets — VALIDATED per memory notes, no ledger entry"),
]

# ---------------------------------------------------------------------------
# Verdict display labels (used by emit_report)
# ---------------------------------------------------------------------------

VERDICT_LABEL: Dict[str, str] = {
    "SHIP": "SHIP",
    "REJECT": "REJECT",
    "DEFER": "DEFER",
    "VARIANCE_ONLY": "VARIANCE_ONLY",
    "NO_VERDICT": "NO VERDICT",
    "LEGACY_SHIPPED": "LEGACY-SHIPPED (pre-gate)",
    "VALIDATED_NOT_IN_LEDGER": "VALIDATED (not in ledger)",
    "SCOUTING_ONLY": "SCOUTING-ONLY",
    "UNKNOWN": "UNKNOWN",
}

# ---------------------------------------------------------------------------
# Prediction-surface catalogue (static enumeration — no app boot)
# ---------------------------------------------------------------------------

def _s(name: str, category: str, source: str, notes: str = "") -> Dict[str, Any]:
    return {"name": name, "category": category, "source": source, "notes": notes}


def enumerate_prediction_surfaces() -> List[Dict[str, Any]]:
    """Return all named prediction surfaces with category, source, and notes."""
    surfaces: List[Dict[str, Any]] = []

    # ── Core prop model surfaces (7 props × 3 quantiles = 21 cells) ──────────
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        for q in ("q10", "q50", "q90"):
            surfaces.append(_s(
                name=f"prop:{stat}:{q}",
                category="prop_quantile",
                source="src/prediction/prop_model_stack.py + api/main.py:/props/{player_id}",
                notes="7 stats × 3 quantiles; backed by stack_predict()",
            ))

    # ── Win-probability surface ───────────────────────────────────────────────
    surfaces.append(_s(
        name="win_prob:pregame",
        category="win_probability",
        source="api/main.py:/win-prob/{game_id} + api/models_router.py:/predictions/win",
        notes="XGBoost baseline; LiveWinProbInference when available",
    ))
    surfaces.append(_s(
        name="win_prob:ingame_live",
        category="win_probability",
        source="api/main.py:/ws/win-prob/{game_id} (WebSocket)",
        notes="Streamed per-possession via LiveWinProbInference; falls back to XGBoost",
    ))

    # ── 16-engine / multi-engine ensemble ────────────────────────────────────
    surfaces.append(_s(
        name="ensemble16:game_score_margin",
        category="game_level_ensemble",
        source="src/prediction/ (predict_ensemble16.py); api/predictions_router.py:/predictions/game",
        notes="16 heterogeneous engines fused; equal-weight Rung-0 is the default",
    ))

    # ── Possession Monte Carlo simulation ────────────────────────────────────
    surfaces.append(_s(
        name="mc_sim:team_score_win_prob",
        category="simulation",
        source="src/sim/basketball_sim.py; api/main.py:/simulate + /simulate_game",
        notes="Player-level possession MC; role-aware usage; defense-drives-predictions",
    ))
    surfaces.append(_s(
        name="mc_sim:player_stat_distribution",
        category="simulation",
        source="src/sim/basketball_sim.py; api/main.py:/over_prob",
        notes="Per-player stat distributions from MC simulation",
    ))

    # ── In-game live re-pricing heads ────────────────────────────────────────
    surfaces.append(_s(
        name="ingame:per_player_projection",
        category="ingame",
        source="api/live_game_router.py:/api/live/{game_id} + /live/{game_id}",
        notes=(
            "Pace-projected final from current actual + pregame q50; "
            "CV_QSHAPE_DECAY (W-015) shapes decay; default-OFF=byte-identical"
        ),
    ))
    surfaces.append(_s(
        name="ingame:game_state_router",
        category="ingame",
        source="src/ingame/ (CV_INGAME_STATE flag); src/brain/flags.py:CV_INGAME_STATE",
        notes="Unified GameState (P3.1); default-OFF; routes in-game layer through typed state",
    ))
    surfaces.append(_s(
        name="ingame:score_shrink",
        category="ingame",
        source="src/brain/flags.py:CV_INGAME_SHRINK",
        notes="Frozen-score shrink + RestOfGameSim at 30s poll; default-OFF; RMSE+bias gate",
    ))
    surfaces.append(_s(
        name="ingame:universal_win_prob",
        category="ingame",
        source="src/brain/flags.py:CV_INGAME_UNIVERSAL_WP",
        notes="Universal WP interface projected-final+time; default-OFF; 5-team fast path",
    ))

    # ── 372-market fan-out (market_intelligence.py) ──────────────────────────
    surfaces.append(_s(
        name="market_fanout:all_markets_372",
        category="market_intelligence",
        source="scripts/team_system/market_intelligence.py",
        notes=(
            "One sim → 372 markets (every stat/combo/DD/TD/longshot incl scenario); "
            "in-game re-price (--state); calibration-tier honesty audit tiers"
        ),
    ))
    surfaces.append(_s(
        name="market_fanout:min_var_layer",
        category="market_intelligence",
        source="scripts/courtvision/build_cv_board.py; min_var_layer.py (CV_MIN_VAR)",
        notes=(
            "Joint-corrected DD/combo markets; rank-remap fixes median-shift; "
            "CV_MIN_VAR env flag; VALIDATED per memory notes (cross-season data-blocked)"
        ),
    ))
    surfaces.append(_s(
        name="market_fanout:parlay_corr",
        category="market_intelligence",
        source="src/prediction/parlay_engine.py + correlation_recal.py (CV_ARCHETYPE_CORR)",
        notes="Parlay correlation pricing; CV_ARCHETYPE_CORR recalibrates rhos; default-OFF",
    ))

    # ── Shot probability (CV spatial) ────────────────────────────────────────
    surfaces.append(_s(
        name="shot_prob:xfg_v1",
        category="cv_spatial",
        source="api/models_router.py:/predictions/shot",
        notes="xFG v1 model (Brier 0.226, 221K shots); CV spatial features → shot probability",
    ))

    # ── Scouting / intelligence surfaces (not betting predictions) ───────────
    surfaces.append(_s(
        name="llm_scheme_prior:scouting",
        category="scouting_only",
        source="src/sim/scheme_prior.py (CV_LLM_SCHEME); src/brain/flags.py:CV_LLM_SCHEME",
        notes=(
            "LLM emits bounded multipliers on sim knobs; betting mode rejects leak_safe=false; "
            "REJECTED for betting number (redundant with sim); ships scouting-only"
        ),
    ))
    surfaces.append(_s(
        name="narration:template_engine",
        category="narration",
        source="src/brain/flags.py:CV_NARRATE",
        notes="Template narration engine; zero effect on predictions; lowest-priority phase",
    ))

    # ── Auxiliary prediction endpoints (from routers) ────────────────────────
    surfaces.append(_s(
        name="aux:injury_risk",
        category="auxiliary",
        source="api/predictions_router.py:/predictions/injury-risk",
        notes="Injury risk score + load management probability; scouting, not betting prediction",
    ))
    surfaces.append(_s(
        name="aux:breakout_score",
        category="auxiliary",
        source="api/predictions_router.py:/predictions/breakout",
        notes="Breakout potential score; scouting signal",
    ))
    surfaces.append(_s(
        name="aux:vacated_load_feature",
        category="prop_feature",
        source="src/prediction/prop_pergame.py (CV_VAC_LOAD_FEATURE)",
        notes=(
            "Vacated-load feature; gated CV_VAC_LOAD_FEATURE; improves accuracy but "
            "cross-season betting edge weaker than 2 corpora implied"
        ),
    ))

    return surfaces
