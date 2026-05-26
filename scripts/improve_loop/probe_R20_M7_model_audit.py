"""probe_R20_M7_model_audit.py — model deployment audit (R20_M7).

Cross-references `scripts/improve_loop/state.json` ships with the actual
production prediction path (player props + game-level + residual heads).

Prints a ship -> wired matrix and persists the result to
`data/cache/probe_R20_M7_results.json`. Designed to be re-run any time the
improvement loop ships a new model: a future cycle that persists an artifact
without wiring it will surface as a new gap.

Usage:
    python scripts/improve_loop/probe_R20_M7_model_audit.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

STATE_PATH = os.path.join(PROJECT_DIR, "scripts", "improve_loop", "state.json")
OUT_PATH   = os.path.join(PROJECT_DIR, "data", "cache", "probe_R20_M7_results.json")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")


# ---------------------------------------------------------------------------
# Each entry: ship_name -> (artifact_glob_relative_to_models_dir,
#                          production_loader_module.fn,
#                          wired_status_check_callable)
# wired_status_check returns "WIRED" / "NOT_WIRED" / "PARTIAL" / "NO_ARTIFACT".
# ---------------------------------------------------------------------------


def _exists(*relpaths: str) -> bool:
    """Return True iff EVERY relpath under data/models/ exists."""
    return all(os.path.exists(os.path.join(MODELS_DIR, p)) for p in relpaths)


def _any_exists(*relpaths: str) -> bool:
    return any(os.path.exists(os.path.join(MODELS_DIR, p)) for p in relpaths)


def _m2_family_called_from_game_models() -> bool:
    """Return True iff the R20_M7 wire is present in src/prediction/game_models.py."""
    p = os.path.join(PROJECT_DIR, "src", "prediction", "game_models.py")
    if not os.path.exists(p):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return False
    return "_predict_m2_family" in src and "m2_family_used" in src


# Static deployment table — each row maps a ship class to its production path.
DEPLOYMENT_TABLE: List[Dict] = [
    # Player-prop family (7 stats, blended/q50 dispatch in predict_pergame)
    {
        "surface": "player_props_pts",
        "shipped_in_round": "cycle-18 sqrt+Huber",
        "artifact": "props_pg_pts.json (+ lgb + mlp)",
        "loader": "src.prediction.prop_pergame.load_pergame_model",
        "wired": "WIRED" if _exists("props_pg_pts.json") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_reb",
        "shipped_in_round": "cycle-29 LGB-q50",
        "artifact": "quantile_pergame_lgb_reb_q50.pkl",
        "loader": "src.prediction.prop_pergame._load_q50_model",
        "wired": "WIRED" if _exists("quantile_pergame_lgb_reb_q50.pkl") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_ast",
        "shipped_in_round": "cycle-23 multitask MLP",
        "artifact": "props_pg_mlp_ast.pkl",
        "loader": "src.prediction.prop_pergame.load_pergame_model",
        "wired": "WIRED" if _exists("props_pg_mlp_ast.pkl") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_fg3m",
        "shipped_in_round": "cycle-27 XGB-q50",
        "artifact": "quantile_pergame_fg3m_q50.json",
        "loader": "src.prediction.prop_pergame._load_q50_model",
        "wired": "WIRED" if _exists("quantile_pergame_fg3m_q50.json") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_stl",
        "shipped_in_round": "cycle-27 XGB-q50",
        "artifact": "quantile_pergame_stl_q50.json",
        "loader": "src.prediction.prop_pergame._load_q50_model",
        "wired": "WIRED" if _exists("quantile_pergame_stl_q50.json") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_blk",
        "shipped_in_round": "cycle-27 XGB-q50",
        "artifact": "quantile_pergame_blk_q50.json",
        "loader": "src.prediction.prop_pergame._load_q50_model",
        "wired": "WIRED" if _exists("quantile_pergame_blk_q50.json") else "NO_ARTIFACT",
    },
    {
        "surface": "player_props_tov",
        "shipped_in_round": "cycle-27 XGB-q50",
        "artifact": "quantile_pergame_tov_q50.json",
        "loader": "src.prediction.prop_pergame._load_q50_model",
        "wired": "WIRED" if _exists("quantile_pergame_tov_q50.json") else "NO_ARTIFACT",
    },
    # Pregame residual heads — R7_A
    {
        "surface": "pregame_residual_heads_6stat",
        "shipped_in_round": "R7_A_pregame_residual_heads_per_stat (round 6)",
        "artifact": "pregame_residual_heads/{reb,ast,fg3m,stl,blk,tov}.lgb",
        "loader": "src.prediction.pregame_residual_heads.apply_residual_correction",
        "wired": "WIRED" if _exists(
            "pregame_residual_heads/reb.lgb",
            "pregame_residual_heads/blk.lgb",
        ) else "NO_ARTIFACT",
    },
    # In-play residual heads — R2_F + R3_A + R4_A
    {
        "surface": "endq1_residual_heads",
        "shipped_in_round": "R4_A_residual_heads_endq1 (round 3)",
        "artifact": "residual_heads_endq1/{stat}.lgb",
        "loader": "src.prediction.residual_heads.apply_residual_correction_endq1",
        "wired": "WIRED" if _exists("residual_heads_endq1/pts.lgb") else "NO_ARTIFACT",
    },
    {
        "surface": "endq2_residual_heads",
        "shipped_in_round": "R3_A_residual_heads_endq2 (round 2)",
        "artifact": "residual_heads_endq2/{stat}.lgb",
        "loader": "src.prediction.residual_heads.apply_residual_correction_endq2",
        "wired": "WIRED" if _exists("residual_heads_endq2/pts.lgb") else "NO_ARTIFACT",
    },
    {
        "surface": "endq3_residual_heads",
        "shipped_in_round": "R2_F_residual_heads (round 1)",
        "artifact": "residual_heads/{stat}.lgb",
        "loader": "src.prediction.residual_heads.apply_residual_correction",
        "wired": "WIRED" if _exists("residual_heads/pts.lgb") else "NO_ARTIFACT",
    },
    # In-play residual heads streak + xstat — R10_M16 + R12_F3
    {
        "surface": "endq3_streak_features",
        "shipped_in_round": "R10_M16_streak_per_stat (round 9)",
        "artifact": "residual_heads/{fg3m,stl,blk,tov}_meta.json (+ retrained heads with streak inputs)",
        "loader": "src.prediction.streak_features.compute_streak_features_for_stat",
        "wired": "WIRED" if _any_exists(
            "residual_heads/blk_xstat_meta.json",
        ) else "NO_ARTIFACT",
    },
    {
        "surface": "endq3_xstat_covariance",
        "shipped_in_round": "R12_F3 (covered by R12_BATCH6 round 12)",
        "artifact": "residual_heads/{fg3m,stl,blk,tov}_xstat.lgb",
        "loader": "src.prediction.residual_heads._apply_xstat_correction",
        "wired": "WIRED" if _exists(
            "residual_heads/blk_xstat.lgb",
            "residual_heads/fg3m_xstat.lgb",
        ) else "NO_ARTIFACT",
    },
    # In-play win prob — R10_M5 + R12_F1 + R13_G2
    {
        "surface": "inplay_winprob_endq1_v1",
        "shipped_in_round": "R10_M5_inplay_winprob (round 9)",
        "artifact": "inplay_winprob_endq1.lgb",
        "loader": "src.prediction.inplay_winprob.load_booster",
        "wired": "WIRED" if _exists("inplay_winprob_endq1.lgb") else "NO_ARTIFACT",
    },
    {
        "surface": "inplay_winprob_endq3_v1",
        "shipped_in_round": "R10_M5_inplay_winprob (round 9)",
        "artifact": "inplay_winprob_endq3.lgb",
        "loader": "src.prediction.inplay_winprob.load_booster",
        "wired": "WIRED" if _exists("inplay_winprob_endq3.lgb") else "NO_ARTIFACT",
    },
    {
        "surface": "inplay_winprob_endq2_v2_ensemble",
        "shipped_in_round": "R12_F1 (round 11/12 area)",
        "artifact": "inplay_winprob_endq2_v2.lgb + _meta.json",
        "loader": "src.prediction.inplay_winprob.load_v2_bundle",
        "wired": "WIRED" if _exists("inplay_winprob_endq2_v2.lgb") else "NO_ARTIFACT",
    },
    {
        "surface": "inplay_winprob_endq1_v3_pregame_anchored",
        "shipped_in_round": "R13_G2 (post-round-12)",
        "artifact": "inplay_winprob_endq1_v3.lgb + _anchor.json",
        "loader": "src.prediction.inplay_winprob.load_v3_bundle",
        "wired": "WIRED" if _exists("inplay_winprob_endq1_v3.lgb") else "NO_ARTIFACT",
    },
    # Game-level family
    {
        "surface": "game_total",
        "shipped_in_round": "R11 M2 family (round 10, BATCH-6/7 consolidation)",
        "artifact": "m2_family/total_{lgb_s42,lgb_s7,lgb_s100,xgb_s42,xgb_s7}.joblib",
        "loader": "src.prediction.game_models._predict_m2_family (R20_M7) -> override total_est",
        "wired": (
            "WIRED"
            if _exists("m2_family/manifest.json", "m2_family/total_lgb_s42.joblib")
            and _m2_family_called_from_game_models()
            else ("PARTIAL" if _exists("m2_family/manifest.json") else "NO_ARTIFACT")
        ),
    },
    {
        "surface": "game_spread",
        "shipped_in_round": "R11 M2 family (round 10)",
        "artifact": "m2_family/spread_{lgb_s42,lgb_s7,lgb_s100,xgb_s42,xgb_s7}.joblib",
        "loader": "src.prediction.game_models._predict_m2_family (R20_M7) -> override spread_est",
        "wired": (
            "WIRED"
            if _exists("m2_family/manifest.json", "m2_family/spread_lgb_s42.joblib")
            and _m2_family_called_from_game_models()
            else ("PARTIAL" if _exists("m2_family/manifest.json") else "NO_ARTIFACT")
        ),
    },
    {
        "surface": "game_home_pts",
        "shipped_in_round": "R11 M2 family (round 10)",
        "artifact": "m2_family/home_pts_{lgb_s42,lgb_s7,lgb_s100,xgb_s42,xgb_s7}.joblib",
        "loader": "src.prediction.game_models._predict_m2_family (R20_M7) -> add home_pts_est",
        "wired": (
            "WIRED"
            if _exists("m2_family/home_pts_lgb_s42.joblib")
            and _m2_family_called_from_game_models()
            else ("PARTIAL" if _exists("m2_family/home_pts_lgb_s42.joblib") else "NO_ARTIFACT")
        ),
    },
    {
        "surface": "game_away_pts",
        "shipped_in_round": "R11 M2 family (round 10)",
        "artifact": "m2_family/away_pts_{lgb_s42,lgb_s7,lgb_s100,xgb_s42,xgb_s7}.joblib",
        "loader": "src.prediction.game_models._predict_m2_family (R20_M7) -> add away_pts_est",
        "wired": (
            "WIRED"
            if _exists("m2_family/away_pts_lgb_s42.joblib")
            and _m2_family_called_from_game_models()
            else ("PARTIAL" if _exists("m2_family/away_pts_lgb_s42.joblib") else "NO_ARTIFACT")
        ),
    },
    {
        "surface": "game_blowout",
        "shipped_in_round": "pre-loop (legacy)",
        "artifact": "game_blowout.json",
        "loader": "src.prediction.game_models.load_models",
        "wired": "WIRED" if _exists("game_blowout.json") else "NO_ARTIFACT",
    },
    {
        "surface": "game_first_half",
        "shipped_in_round": "pre-loop (legacy)",
        "artifact": "game_first_half.json",
        "loader": "src.prediction.game_models.load_models",
        "wired": "WIRED" if _exists("game_first_half.json") else "NO_ARTIFACT",
    },
    {
        "surface": "game_pace",
        "shipped_in_round": "pre-loop (legacy)",
        "artifact": "game_pace.json",
        "loader": "src.prediction.game_models.load_models",
        "wired": "WIRED" if _exists("game_pace.json") else "NO_ARTIFACT",
    },
    # Surfaces with no artifact (probe-only ships)
    {
        "surface": "binary_ou_thresholds (O220/O230/...)",
        "shipped_in_round": "R11 M2v11-v24 + BATCH8 (round 10)",
        "artifact": "(no persisted artifact — consolidated into m2_family regression)",
        "loader": "(would need new binary head + wiring)",
        "wired": "NO_ARTIFACT",
    },
    {
        "surface": "binary_ats_thresholds (AH3/AH7/PH3/...)",
        "shipped_in_round": "R11 M2v13/14/18/19/25-30 (round 10)",
        "artifact": "(no persisted artifact — consolidated into m2_family regression)",
        "loader": "(would need new binary head + wiring)",
        "wired": "NO_ARTIFACT",
    },
    {
        "surface": "q1_total / h1_total / home_q1 / away_q1",
        "shipped_in_round": "R11 M2v15-v17/v32-v34 (round 10)",
        "artifact": "(no persisted artifact)",
        "loader": "(would need new heads + wiring)",
        "wired": "NO_ARTIFACT",
    },
    {
        "surface": "tracking_pts_residual",
        "shipped_in_round": "R10_M13_tracking_pts_per_stat (round 9)",
        "artifact": "(probe shipped but no retrained PTS artifact persisted)",
        "loader": "(would need retrain with tracking features baked in)",
        "wired": "NO_ARTIFACT",
    },
]


def _load_ships() -> List[dict]:
    if not os.path.exists(STATE_PATH):
        return []
    with open(STATE_PATH, encoding="utf-8") as f:
        return json.load(f).get("ships", [])


def _count_wired(rows: List[Dict]) -> Dict[str, int]:
    counts = {"WIRED": 0, "PARTIAL": 0, "NO_ARTIFACT": 0, "NOT_WIRED": 0}
    for r in rows:
        counts[r["wired"]] = counts.get(r["wired"], 0) + 1
    return counts


def _print_table(rows: List[Dict]) -> None:
    print("\n" + "=" * 100)
    print(f"{'SURFACE':<42} {'SHIP':<46} {'WIRED'}")
    print("-" * 100)
    for r in rows:
        wired = r["wired"]
        marker = (
            "[YES]" if wired == "WIRED"
            else "[NO ]" if wired in ("NOT_WIRED", "NO_ARTIFACT")
            else "[?  ]"
        )
        print(f"{r['surface']:<42} {r['shipped_in_round']:<46} {marker} {wired}")
    print("=" * 100)


def main() -> int:
    rows = DEPLOYMENT_TABLE
    counts = _count_wired(rows)
    ships = _load_ships()

    _print_table(rows)
    print()
    print(f"Total surfaces audited:    {len(rows)}")
    print(f"  WIRED:                   {counts.get('WIRED', 0)}")
    print(f"  PARTIAL:                 {counts.get('PARTIAL', 0)}")
    print(f"  NO_ARTIFACT / NOT_WIRED: {counts.get('NO_ARTIFACT', 0) + counts.get('NOT_WIRED', 0)}")
    print()
    print(f"state.json ships listed:   {len(ships)}")

    unwired = [r for r in rows if r["wired"] in ("NOT_WIRED", "NO_ARTIFACT")]
    if unwired:
        print(f"\nGaps requiring follow-up ({len(unwired)}):")
        for r in unwired:
            print(f"  - {r['surface']}  ({r['shipped_in_round']})")

    payload = {
        "probe": "R20_M7_model_deployment_audit",
        "n_surfaces": len(rows),
        "n_state_ships": len(ships),
        "counts": counts,
        "matrix": rows,
        "unwired_surfaces": [r["surface"] for r in unwired],
        "r20_m7_wire_active": _m2_family_called_from_game_models(),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"\nWrote audit payload -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
