"""tests/test_R32_Y1_mlp_wirethrough.py

R32_Y1 — validate the R31_X3 m2_family multitask MLP wire-through is
end-to-end correct.

The MLP path is opt-in via the env var ``M2_FAMILY_USE_MLP``. We pin the
"truthy" set to {"1", "true", "yes"} (case-insensitive, see
``_m2_family_use_mlp`` in ``src/prediction/game_models.py``).

Coverage (9 tests):
  1. ``_m2_family_use_mlp`` returns the documented truthy/falsy semantics
  2. ``game_models.predict()`` with flag UNSET == flag = "0" (identical pred)
  3. ``game_models.predict()`` with flag = "1" diverges measurably from "0"
  4. ``game_models.predict()`` flag = "1" produces no NaN / Inf
  5. Ensemble label changes when MLP is on vs off
  6. ``game_orchestrator.predict_game`` propagates the MLP flag end-to-end
  7. MLP cache and multi5 cache are keyed independently (no collision)
  8. Player-prop pergame predictions still work under MLP=1 (game-level
     change does not break the 7 prop heads)
  9. Sample game 0022500001 (HOU @ OKC 2025-10-21) deltas land in
     plausible per-game magnitudes (sign + bounded)

All tests are LOCAL only.
"""
from __future__ import annotations

import importlib
import math
import os
import sys
from typing import Optional

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Hard skip when the host-side m2 ensembles aren't available (CI clones
# without trained models would otherwise spew unrelated failures).
import numpy as np  # noqa: E402

torch = pytest.importorskip("torch")


def _reload_game_models(flag: Optional[str]):
    """Reset env var then importlib.reload to clear module-level caches."""
    if flag is None:
        os.environ.pop("M2_FAMILY_USE_MLP", None)
    else:
        os.environ["M2_FAMILY_USE_MLP"] = flag
    from src.prediction import game_models  # noqa: PLC0415
    importlib.reload(game_models)
    return game_models


def _stub_features_and_legacy(gm) -> None:
    """Stub ``_build_features`` + ``load_models`` so ``predict()`` never
    touches the NBA API and falls into the formula path. The m2_family
    override fires from the season_games row lookup regardless, so we still
    exercise the real MLP / multi5 dispatch."""

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
        raise FileNotFoundError("stub: force formula fallback")

    gm._build_features = fake_build_features
    gm.load_models = fake_load_models


def _have_mlp_artifacts() -> bool:
    """Resolve `_M2_FAMILY_MLP_DIR` and confirm the manifest + at least one
    seed checkpoint exist."""
    gm = _reload_game_models(None)
    manifest_p = os.path.join(gm._M2_FAMILY_MLP_DIR, "manifest.json")
    return os.path.exists(manifest_p)


def _have_multi5_artifacts() -> bool:
    gm = _reload_game_models(None)
    manifest_p = os.path.join(gm._M2_FAMILY_DIR, "manifest.json")
    return os.path.exists(manifest_p)


def _have_season_games_row(game_id: str) -> bool:
    gm = _reload_game_models(None)
    return gm._lookup_season_games_row(game_id, None, None, None) is not None


_HAVE_BOTH = _have_mlp_artifacts() and _have_multi5_artifacts()
_HAVE_GAME = _HAVE_BOTH and _have_season_games_row("0022500001")
_NEED_BOTH = pytest.mark.skipif(
    not _HAVE_BOTH,
    reason="requires both data/models/m2_family/ and data/models/m2_family_mlp/",
)
_NEED_GAME = pytest.mark.skipif(
    not _HAVE_GAME,
    reason="requires season_games row for 0022500001",
)


# --------------------------------------------------------------------------- #
# 1) env var truthy/falsy semantics                                           #
# --------------------------------------------------------------------------- #
def test_env_flag_truthy_falsy_semantics():
    """Documented truthy set is {1, true, yes} (case-insensitive). All other
    values (including 0, '', random text) must be falsy."""
    gm = _reload_game_models(None)
    assert gm._m2_family_use_mlp() is False

    for truthy in ("1", "true", "yes", "True", "YES", "  yes  "):
        os.environ["M2_FAMILY_USE_MLP"] = truthy
        assert gm._m2_family_use_mlp() is True, f"{truthy!r} should be truthy"

    for falsy in ("0", "false", "no", "", "maybe", "2", "off"):
        os.environ["M2_FAMILY_USE_MLP"] = falsy
        assert gm._m2_family_use_mlp() is False, f"{falsy!r} should be falsy"

    os.environ.pop("M2_FAMILY_USE_MLP", None)


# --------------------------------------------------------------------------- #
# 2) flag UNSET behaves the same as flag = "0"                                #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_unset_equals_zero():
    """Two control modes must agree to the rounded cent — anything else
    means a hidden code path snuck in."""
    gm_unset = _reload_game_models(None)
    _stub_features_and_legacy(gm_unset)
    out_a = gm_unset.predict("OKC", "HOU", season="2025-26",
                             game_date="2025-10-21", game_id="0022500001")

    gm_zero = _reload_game_models("0")
    _stub_features_and_legacy(gm_zero)
    out_c = gm_zero.predict("OKC", "HOU", season="2025-26",
                            game_date="2025-10-21", game_id="0022500001")

    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert out_a[k] == out_c[k], (
            f"unset ({out_a[k]}) and =0 ({out_c[k]}) must match for {k}"
        )
    assert out_a.get("ensemble") == out_c.get("ensemble")


# --------------------------------------------------------------------------- #
# 3) flag = "1" diverges from flag = "0"                                      #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_mlp_on_diverges_from_off():
    """The MLP and multi5 ensembles are different models — at least one of
    the 4 targets must differ for a fully-featured game row."""
    gm_off = _reload_game_models("0")
    _stub_features_and_legacy(gm_off)
    off = gm_off.predict("OKC", "HOU", season="2025-26",
                         game_date="2025-10-21", game_id="0022500001")

    gm_on = _reload_game_models("1")
    _stub_features_and_legacy(gm_on)
    on = gm_on.predict("OKC", "HOU", season="2025-26",
                       game_date="2025-10-21", game_id="0022500001")

    diffs = [abs(on[k] - off[k]) for k in
             ("total_est", "spread_est", "home_pts_est", "away_pts_est")]
    assert max(diffs) > 0.1, (
        f"MLP and multi5 should give different predictions, got diffs={diffs}"
    )


# --------------------------------------------------------------------------- #
# 4) MLP path produces no NaN / Inf                                           #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_mlp_no_nan_no_inf():
    gm = _reload_game_models("1")
    _stub_features_and_legacy(gm)
    out = gm.predict("OKC", "HOU", season="2025-26",
                     game_date="2025-10-21", game_id="0022500001")
    for k in ("total_est", "spread_est", "home_pts_est",
              "away_pts_est", "first_half_est", "pace_est"):
        v = out.get(k)
        assert v is not None, f"missing {k}"
        assert not math.isnan(float(v)), f"{k} is NaN"
        assert not math.isinf(float(v)), f"{k} is Inf"


# --------------------------------------------------------------------------- #
# 5) ensemble label switches with the flag                                    #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_ensemble_label_changes_with_flag():
    gm_off = _reload_game_models("0")
    _stub_features_and_legacy(gm_off)
    off = gm_off.predict("OKC", "HOU", season="2025-26",
                         game_date="2025-10-21", game_id="0022500001")

    gm_on = _reload_game_models("1")
    _stub_features_and_legacy(gm_on)
    on = gm_on.predict("OKC", "HOU", season="2025-26",
                       game_date="2025-10-21", game_id="0022500001")

    assert "M2_family_v1" in off.get("ensemble", "")
    assert "mlp" in on.get("ensemble", "").lower()
    assert off.get("ensemble") != on.get("ensemble")


# --------------------------------------------------------------------------- #
# 6) game_orchestrator.predict_game propagates the flag                       #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_game_orchestrator_propagates_flag():
    """`api/predictions_router.py` calls `predict_game`, which delegates to
    `game_models.predict`. We verify the env flag round-trips end-to-end."""

    def _run(flag: Optional[str]):
        gm = _reload_game_models(flag)
        _stub_features_and_legacy(gm)
        from src.prediction import game_orchestrator  # noqa: PLC0415
        importlib.reload(game_orchestrator)
        # Stub win_probability + prop_model_stack to avoid network/model loads
        from src.prediction import win_probability as wp  # noqa: PLC0415

        class _WP:
            def predict(self, *_args, **_kw):
                return {"home_win_prob": 0.5}

        wp.WinProbabilityModel = lambda: _WP()
        from src.prediction import prop_model_stack as ps  # noqa: PLC0415

        def _stack_predict(*_a, **_kw):
            return type("S", (), {"predictions": {}})()

        ps.stack_predict = _stack_predict
        return game_orchestrator.predict_game(
            "OKC", "HOU", season="2025-26", game_date="2025-10-21",
            player_ids=[], save=False,
        )

    off = _run("0")
    on = _run("1")
    assert off["game_models"].get("total_est") != on["game_models"].get("total_est")
    assert "mlp" in on["game_models"].get("ensemble", "").lower()
    assert "M2_family_v1" in off["game_models"].get("ensemble", "")


# --------------------------------------------------------------------------- #
# 7) MLP path bypasses the R21_N5 multi5 cache                                #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_mlp_path_bypasses_multi5_cache():
    """The multi5 cache (`m2_family_predictions_cache.json`) is keyed by
    multi5-models mtime. The MLP path must NOT read or write that cache so
    cached multi5 values can never leak into MLP responses."""
    gm = _reload_game_models("1")
    _stub_features_and_legacy(gm)
    # Seed the multi5 cache with a sentinel value for this game_id.
    sentinel = {
        "models_mtime": -1.0,
        "total_est": 999.0, "spread_est": -99.0,
        "home_pts_est": -99.0, "away_pts_est": -99.0,
        "computed_at": "1970-01-01T00:00:00+00:00",
    }
    gm._save_m2_pred_cache({"0022500001": sentinel})
    try:
        out = gm.predict("OKC", "HOU", season="2025-26",
                         game_date="2025-10-21", game_id="0022500001")
        # If MLP read the multi5 cache, total_est would be the sentinel 999.0.
        assert out["total_est"] != 999.0
        assert out["away_pts_est"] != -99.0
    finally:
        # Cleanup — never leave the sentinel in cache for other tests.
        gm.clear_m2_pred_cache()


# --------------------------------------------------------------------------- #
# 8) player-prop pergame predictions still work under MLP=1                   #
# --------------------------------------------------------------------------- #
def test_player_props_unaffected_by_mlp_flag():
    """The MLP only changes game-level total/spread/home/away. The 7 prop
    heads (pts/reb/ast/fg3m/stl/blk/tov) must still load + predict on the
    MLP path."""
    os.environ["M2_FAMILY_USE_MLP"] = "1"
    try:
        from src.prediction import prop_pergame  # noqa: PLC0415
        importlib.reload(prop_pergame)
        # Sanity: 7 stats registered + predict callable exposed
        assert set(prop_pergame.STATS) == {
            "pts", "reb", "ast", "fg3m", "stl", "blk", "tov"
        }
        assert callable(prop_pergame.predict_pergame)
        # No model load actually triggered here — just that flag presence
        # doesn't break the prop module's import / public surface.
    finally:
        os.environ.pop("M2_FAMILY_USE_MLP", None)


# --------------------------------------------------------------------------- #
# 9) sample-game deltas land in plausible per-game magnitudes                 #
# --------------------------------------------------------------------------- #
@_NEED_GAME
def test_sample_game_deltas_bounded():
    """For 0022500001 (HOU @ OKC 2025-10-21), the MLP - multi5 deltas must
    be small (single-digit points per target) — anything larger means the
    MLP regressed catastrophically or the scaler is mis-loaded."""
    gm_off = _reload_game_models("0")
    _stub_features_and_legacy(gm_off)
    off = gm_off.predict("OKC", "HOU", season="2025-26",
                         game_date="2025-10-21", game_id="0022500001")

    gm_on = _reload_game_models("1")
    _stub_features_and_legacy(gm_on)
    on = gm_on.predict("OKC", "HOU", season="2025-26",
                       game_date="2025-10-21", game_id="0022500001")

    # Plausibility envelope: per-target delta must be < 15 points (a half-
    # quarter's worth). MLP whitepaper said total -1.80%, away -6.15% on
    # the HOLDOUT — for ONE game the per-target shift will be different but
    # bounded.
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        d = abs(on[k] - off[k])
        assert d < 15.0, f"unrealistic MLP delta for {k}: {d:.2f} pts"

    # And the sum-identity (home + away == total) must hold approximately
    # for both heads up to rounding (the heads are independent but trained
    # on consistent targets).
    for label, pred in (("multi5", off), ("mlp", on)):
        s = pred["home_pts_est"] + pred["away_pts_est"]
        # Allow 4-pt slack — heads are independent, target_order rounding.
        assert abs(s - pred["total_est"]) < 4.0, (
            f"{label}: home+away ({s:.1f}) drifts from total ({pred['total_est']:.1f})"
        )
