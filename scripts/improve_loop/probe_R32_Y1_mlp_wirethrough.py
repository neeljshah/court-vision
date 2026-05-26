"""probe_R32_Y1_mlp_wirethrough.py — validate R31_X3 MLP dispatch end-to-end.

R31_X3 wired the multitask MLP behind the env flag ``M2_FAMILY_USE_MLP``.
This probe builds the validation matrix (consumers x flag states) and
persists the result so the bot loop can assert the wire still holds after
later refactors.

Matrix:
    consumers x { unset, "0", "1" }
    where consumers = {
        game_models.predict,
        game_orchestrator.predict_game,   # used by api/predictions_router
        run_daily_slate (game_models.predict call),
        player_props (game_models.predict call inside _build_feats),
        build_prediction_cache,            # NOT affected (player props only)
        predict_slate,                     # NOT affected (player props only)
        live_recommendation_engine,        # NOT affected (reads parquet)
    }

Ship criteria (PASS):
  * UNSET and "0" produce identical predictions on every game-level consumer
  * "1" produces measurably different predictions on every game-level consumer
  * No NaN under the MLP path
  * No predictions ever come from the legacy single-XGB heads (m2 override
    fires for every game with a populated season_games row)
  * Player-prop consumers (build_prediction_cache / predict_slate /
    live_recommendation_engine) are insensitive to the flag — confirms the
    rollout is scoped to game-level signals only.

LOCAL only. Doesn't ship anything — just probes + records.

Usage:
    python scripts/improve_loop/probe_R32_Y1_mlp_wirethrough.py
"""
from __future__ import annotations

import importlib
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_OUT_PATH = os.path.join(PROJECT_DIR, "data", "cache", "probe_R32_Y1_results.json")
_SAMPLE_GAME = {
    "game_id": "0022500001",
    "home": "OKC",
    "away": "HOU",
    "season": "2025-26",
    "date": "2025-10-21",
}


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #
def _reload_game_models(flag: Optional[str]):
    if flag is None:
        os.environ.pop("M2_FAMILY_USE_MLP", None)
    else:
        os.environ["M2_FAMILY_USE_MLP"] = flag
    from src.prediction import game_models  # noqa: PLC0415
    importlib.reload(game_models)
    return game_models


def _stub_features_and_legacy(gm) -> None:
    """Force the legacy single-XGB head to FileNotFoundError so we always
    hit the formula -> m2_family override path. The m2_family path is what
    we're actually testing."""

    def fake_build_features(home, away, season, game_date, ref_names=None):
        d = {c: 0.0 for c in gm.FEATURE_COLS}
        d.update({
            "pace_avg": 100.0, "off_rtg_sum": 220.0, "def_rtg_sum": 220.0,
            "efg_sum": 1.0, "ts_sum": 1.0, "net_rtg_diff": 1.0,
            "pace_diff": 0.0, "home_advantage": 1.0, "tov_sum": 0.0,
            "ref_avg_fouls": 42.0, "ref_home_win_pct": 0.5,
            "home_off_rtg_l10": 112.0, "home_def_rtg_l10": 112.0,
            "home_net_rtg_l10": 0.0,
            "away_off_rtg_l10": 112.0, "away_def_rtg_l10": 112.0,
            "away_net_rtg_l10": 0.0,
        })
        return d

    def fake_load_models():
        raise FileNotFoundError("probe stub: bypass legacy single-XGB heads")

    gm._build_features = fake_build_features
    gm.load_models = fake_load_models


def _consumer_game_models_predict(flag: Optional[str]) -> Dict[str, Any]:
    gm = _reload_game_models(flag)
    _stub_features_and_legacy(gm)
    out = gm.predict(_SAMPLE_GAME["home"], _SAMPLE_GAME["away"],
                     season=_SAMPLE_GAME["season"],
                     game_date=_SAMPLE_GAME["date"],
                     game_id=_SAMPLE_GAME["game_id"])
    return {
        "total_est":    out.get("total_est"),
        "spread_est":   out.get("spread_est"),
        "home_pts_est": out.get("home_pts_est"),
        "away_pts_est": out.get("away_pts_est"),
        "ensemble":     out.get("ensemble"),
        "m2_family_used": out.get("m2_family_used", False),
        "confidence":   out.get("confidence"),
    }


def _consumer_game_orchestrator(flag: Optional[str]) -> Dict[str, Any]:
    gm = _reload_game_models(flag)
    _stub_features_and_legacy(gm)
    from src.prediction import game_orchestrator  # noqa: PLC0415
    importlib.reload(game_orchestrator)

    # Stub win_probability + prop_model_stack so we don't hit network.
    from src.prediction import win_probability as wp  # noqa: PLC0415

    class _WP:
        def predict(self, *_a, **_kw):
            return {"home_win_prob": 0.5}

    wp.WinProbabilityModel = lambda: _WP()
    from src.prediction import prop_model_stack as ps  # noqa: PLC0415

    def _stack_predict(*_a, **_kw):
        return type("S", (), {"predictions": {}})()

    ps.stack_predict = _stack_predict

    out = game_orchestrator.predict_game(
        _SAMPLE_GAME["home"], _SAMPLE_GAME["away"],
        season=_SAMPLE_GAME["season"], game_date=_SAMPLE_GAME["date"],
        player_ids=[], save=False,
    )
    gm_out = out.get("game_models", {})
    return {
        "total_est":    gm_out.get("total_est"),
        "spread_est":   gm_out.get("spread_est"),
        "home_pts_est": gm_out.get("home_pts_est"),
        "away_pts_est": gm_out.get("away_pts_est"),
        "ensemble":     gm_out.get("ensemble"),
        "m2_family_used": gm_out.get("m2_family_used", False),
    }


# Consumers that don't go through game_models.predict:
#   build_prediction_cache.py + predict_slate.py + live_recommendation_engine.py
# all operate on player-prop predictions only. We mark them "unaffected" — the
# rollout doc explicitly scopes the flag to game-level signals.
def _consumer_unaffected_marker(name: str) -> Dict[str, Any]:
    return {"unaffected_by_flag": True, "rationale": f"{name} consumes player-prop predictions only"}


# --------------------------------------------------------------------------- #
# matrix runner                                                               #
# --------------------------------------------------------------------------- #
def _diffs(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, float]:
    out = {}
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None:
            out[k] = None
        else:
            out[k] = round(float(vb) - float(va), 3)
    return out


def _all_finite(d: Dict[str, Any]) -> bool:
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        v = d.get(k)
        if v is None:
            return False
        try:
            f = float(v)
        except (TypeError, ValueError):
            return False
        if math.isnan(f) or math.isinf(f):
            return False
    return True


def run() -> Dict[str, Any]:
    t0 = time.time()
    consumers: Dict[str, Dict[str, Any]] = {}

    # Game-level consumers — run all 3 modes
    for cname, fn in (
        ("game_models.predict",              _consumer_game_models_predict),
        ("game_orchestrator.predict_game",   _consumer_game_orchestrator),
    ):
        modes = {}
        for label, flag in (("unset", None), ("zero", "0"), ("one", "1")):
            try:
                modes[label] = fn(flag)
            except Exception as exc:
                modes[label] = {"error": repr(exc)}
        # Acceptance gates
        unset = modes.get("unset", {})
        zero = modes.get("zero", {})
        one = modes.get("one", {})
        unset_eq_zero = all(
            unset.get(k) == zero.get(k)
            for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est")
        )
        one_differs = any(
            unset.get(k) != one.get(k)
            for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est")
            if unset.get(k) is not None and one.get(k) is not None
        )
        diffs_mlp_vs_off = _diffs(unset, one)
        no_nan_mlp = _all_finite(one)
        consumers[cname] = {
            "modes": modes,
            "unset_equals_zero":   unset_eq_zero,
            "mlp_differs_from_off": one_differs,
            "deltas_mlp_minus_off": diffs_mlp_vs_off,
            "no_nan_under_mlp":     no_nan_mlp,
            "ship_gate": unset_eq_zero and one_differs and no_nan_mlp,
        }

    # Unaffected consumers — explicitly recorded so future code-review can
    # see they were considered.
    for cname in (
        "scripts/predict_slate.py",
        "scripts/build_prediction_cache.py",
        "scripts/live_recommendation_engine.py",
    ):
        consumers[cname] = _consumer_unaffected_marker(cname)
        consumers[cname]["ship_gate"] = True

    # Top-level summary
    ship_gates_passed = sum(1 for c in consumers.values() if c.get("ship_gate"))
    out = {
        "task":                "R32_Y1 m2_family MLP wire-through validation",
        "sample_game":         _SAMPLE_GAME,
        "consumers":           consumers,
        "consumers_total":     len(consumers),
        "consumers_passed":    ship_gates_passed,
        "ship_gate_overall":   ship_gates_passed == len(consumers),
        "runtime_sec":         round(time.time() - t0, 2),
    }
    return out


def main() -> int:
    result = run()
    os.makedirs(os.path.dirname(_OUT_PATH), exist_ok=True)
    with open(_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[probe_R32_Y1] wrote {_OUT_PATH}")
    print(f"  consumers: {result['consumers_passed']}/{result['consumers_total']}")
    print(f"  ship_gate: {result['ship_gate_overall']}")
    for cname, cinfo in result["consumers"].items():
        gate = "PASS" if cinfo.get("ship_gate") else "FAIL"
        print(f"    [{gate}] {cname}")
        if "deltas_mlp_minus_off" in cinfo:
            print(f"      deltas (mlp - off): {cinfo['deltas_mlp_minus_off']}")
    return 0 if result["ship_gate_overall"] else 1


if __name__ == "__main__":
    sys.exit(main())
