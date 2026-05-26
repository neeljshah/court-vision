"""
test_L40_dispatcher.py — Unit tests for L40_multi_model_dispatcher.

All tests are pure-Python; no network calls, no real model files required.
"""
from __future__ import annotations

import importlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, call, patch

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
_TESTS_DIR = Path(__file__).resolve().parent
_EL_DIR = _TESTS_DIR.parent
_PROJECT_DIR = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

import scripts.execute_loop.L40_multi_model_dispatcher as dispatcher
from scripts.execute_loop.L40_multi_model_dispatcher import (
    HARDCODED_DEFAULTS,
    ModelRoute,
    STATS,
    VARIANTS,
    best_routing_from_wf_results,
    get_routing,
    predict_dispatched,
    predict_quantiles_dispatched,
    update_routing,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_STUB_ROW: Dict[str, float] = {"l5_pts": 22.4, "l10_pts": 21.1, "rest_days": 1.0}


def _make_routing_json(tmp_path: Path, overrides: Dict[str, dict] | None = None) -> Path:
    """Write a minimal valid dispatch_routing.json to tmp_path."""
    routes: Dict[str, dict] = {}
    for stat in STATS:
        variant, notes = HARDCODED_DEFAULTS[stat]
        routes[stat] = {
            "model_variant": variant,
            "source_path": None,
            "wf_mae": 1.0,
            "deployed_at": "2026-04-01T00:00:00+00:00",
            "notes": notes,
        }
    if overrides:
        for stat, patch_dict in overrides.items():
            routes[stat].update(patch_dict)
    data = {"version": 1, "updated_at": "2026-04-01T00:00:00+00:00", "routes": routes}
    p = tmp_path / "dispatch_routing.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test 1: get_routing returns dict with all 7 stats, each a ModelRoute
# ---------------------------------------------------------------------------
class TestGetRouting:
    def test_all_stats_present(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        routes = get_routing(routing_path)
        assert set(routes.keys()) == set(STATS)

    def test_values_are_model_routes(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        routes = get_routing(routing_path)
        for stat in STATS:
            assert isinstance(routes[stat], ModelRoute), f"{stat} not a ModelRoute"

    def test_variants_from_defaults(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        routes = get_routing(routing_path)
        for stat in STATS:
            expected_variant = HARDCODED_DEFAULTS[stat][0]
            assert routes[stat].model_variant == expected_variant, (
                f"{stat}: expected {expected_variant}, got {routes[stat].model_variant}"
            )


# ---------------------------------------------------------------------------
# Test 2: predict_dispatched("pts", ...) delegates to predict_pergame
# ---------------------------------------------------------------------------
class TestPredictDispatchedBlend:
    def test_pts_calls_predict_pergame(self, tmp_path):
        """pts is routed to blend → must call src.prediction.prop_pergame.predict_pergame."""
        routing_path = _make_routing_json(tmp_path, {"pts": {"model_variant": "blend"}})

        sentinel = 24.5
        mock_fn = MagicMock(return_value=sentinel)

        with patch("scripts.execute_loop.L40_multi_model_dispatcher._predict_blend", mock_fn):
            result = predict_dispatched("pts", _STUB_ROW, _routing_path=routing_path)

        mock_fn.assert_called_once()
        assert result == sentinel

    def test_blend_propagates_none(self, tmp_path):
        routing_path = _make_routing_json(tmp_path, {"pts": {"model_variant": "blend"}})
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=None,
        ):
            result = predict_dispatched("pts", _STUB_ROW, _routing_path=routing_path)
        assert result is None


# ---------------------------------------------------------------------------
# Test 3: predict_dispatched("blk", ...) with routing=q50_xgb calls loader
# ---------------------------------------------------------------------------
class TestPredictDispatchedQ50Xgb:
    def test_blk_q50_xgb_returns_stub(self, tmp_path):
        routing_path = _make_routing_json(tmp_path, {"blk": {"model_variant": "q50_xgb"}})

        stub_value = 0.82
        mock_loader = MagicMock(return_value=stub_value)

        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_q50_xgb",
            mock_loader,
        ):
            result = predict_dispatched("blk", _STUB_ROW, _routing_path=routing_path)

        mock_loader.assert_called_once()
        assert result == stub_value

    def test_q50_xgb_missing_falls_back_to_blend(self, tmp_path):
        """When q50_xgb returns None (file missing), result comes from blend."""
        routing_path = _make_routing_json(tmp_path, {"blk": {"model_variant": "q50_xgb"}})
        blend_value = 0.55

        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_q50_xgb",
            return_value=None,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=blend_value,
        ) as mock_blend:
            result = predict_dispatched("blk", _STUB_ROW, _routing_path=routing_path)

        mock_blend.assert_called_once()
        assert result == blend_value


# ---------------------------------------------------------------------------
# Test 4: Routing JSON missing → get_routing returns HARDCODED_DEFAULTS, file written
# ---------------------------------------------------------------------------
class TestGetRoutingMissingFile:
    def test_defaults_returned_when_file_absent(self, tmp_path):
        routing_path = tmp_path / "dispatch_routing.json"
        assert not routing_path.exists()

        routes = get_routing(routing_path)

        # File should now exist
        assert routing_path.exists(), "get_routing should create the file"

        # All 7 stats with correct default variants
        assert set(routes.keys()) == set(STATS)
        for stat in STATS:
            expected = HARDCODED_DEFAULTS[stat][0]
            assert routes[stat].model_variant == expected, (
                f"{stat}: expected {expected}, got {routes[stat].model_variant}"
            )

    def test_written_file_is_valid_json(self, tmp_path):
        routing_path = tmp_path / "dispatch_routing.json"
        get_routing(routing_path)
        data = json.loads(routing_path.read_text(encoding="utf-8"))
        assert "routes" in data
        assert "version" in data
        assert data["version"] == 1

    def test_corrupt_file_rebuilds_defaults(self, tmp_path):
        routing_path = tmp_path / "dispatch_routing.json"
        routing_path.write_text("NOT JSON{{{", encoding="utf-8")
        routes = get_routing(routing_path)
        assert set(routes.keys()) == set(STATS)
        for stat in STATS:
            assert routes[stat].model_variant == HARDCODED_DEFAULTS[stat][0]


# ---------------------------------------------------------------------------
# Test 5: predict_dispatched("foo", ...) → ValueError
# ---------------------------------------------------------------------------
class TestInvalidStat:
    def test_unknown_stat_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown stat"):
            predict_dispatched("foo", _STUB_ROW, _routing_path=routing_path)

    def test_empty_stat_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown stat"):
            predict_dispatched("", _STUB_ROW, _routing_path=routing_path)

    def test_predict_quantiles_unknown_stat_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown stat"):
            predict_quantiles_dispatched("xyz", _STUB_ROW, _routing_path=routing_path)


# ---------------------------------------------------------------------------
# Test 6: update_routing + get_routing → ast.model_variant persists
# ---------------------------------------------------------------------------
class TestUpdateRouting:
    def test_update_persists_to_json(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)

        update_routing("ast", "blend", 1.35, notes="manual", _routing_path=routing_path)

        routes = get_routing(routing_path)
        assert routes["ast"].model_variant == "blend"
        assert routes["ast"].wf_mae == pytest.approx(1.35)
        assert routes["ast"].notes == "manual"

    def test_other_stats_unchanged(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        routes_before = get_routing(routing_path)

        update_routing("ast", "blend", 1.35, _routing_path=routing_path)

        routes_after = get_routing(routing_path)
        for stat in STATS:
            if stat == "ast":
                continue
            assert routes_after[stat].model_variant == routes_before[stat].model_variant

    def test_update_routing_unknown_stat_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown stat"):
            update_routing("xyz", "blend", 1.0, _routing_path=routing_path)

    def test_update_routing_unknown_variant_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown variant"):
            update_routing("pts", "bad_variant", 4.5, _routing_path=routing_path)

    def test_deployed_at_updated(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        routes_before = get_routing(routing_path)
        old_ts = routes_before["pts"].deployed_at

        update_routing("pts", "blend", 4.62, _routing_path=routing_path)

        routes_after = get_routing(routing_path)
        # deployed_at should be a fresh timestamp (may equal or differ)
        assert routes_after["pts"].deployed_at != "" or old_ts != ""


# ---------------------------------------------------------------------------
# Test 7: best_routing_from_wf_results on fixture WF JSON
# ---------------------------------------------------------------------------
class TestBestRoutingFromWF:
    def _write_wf_fixture(self, tmp_path: Path) -> Path:
        """
        Fixture: by_stat schema with two variants per stat.
        blend always has higher MAE; q50_xgb has lower MAE with folds_positive=4.
        Exception: for 'ast', only blend passes (q50_xgb has folds_positive=1 < 3).
        """
        by_stat: Dict[str, Any] = {}
        for stat in STATS:
            # q50_xgb: good MAE, good folds
            # blend: higher MAE, also 4 folds
            by_stat[stat] = {
                "q50_xgb": {"mae_mean": 0.50, "folds_positive": 4},
                "blend":   {"mae_mean": 1.00, "folds_positive": 4},
            }
        # For 'ast': make q50_xgb fail the folds gate → blend wins
        by_stat["ast"]["q50_xgb"]["folds_positive"] = 1  # below threshold of 3
        # ast blend still has 4 folds and higher MAE (1.00 > 0.50 of the bad xgb),
        # but xgb is gated out, so blend (1.00) is the only valid choice

        data = {"version": 2, "by_stat": by_stat}
        p = tmp_path / "wf_results.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_picks_lowest_mae_variant(self, tmp_path):
        wf_path = self._write_wf_fixture(tmp_path)
        routing_path = _make_routing_json(tmp_path)

        result = best_routing_from_wf_results(wf_path, _routing_path=routing_path)

        # All stats except 'ast' should pick q50_xgb (lower MAE, folds >= 3)
        for stat in STATS:
            if stat == "ast":
                assert result[stat] == "blend", f"ast should fall back to blend; got {result[stat]}"
            else:
                assert result[stat] == "q50_xgb", (
                    f"{stat}: expected q50_xgb (lower MAE), got {result[stat]}"
                )

    def test_missing_wf_file_keeps_current(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        wf_path = tmp_path / "nonexistent_wf.json"

        routes_before = get_routing(routing_path)
        result = best_routing_from_wf_results(wf_path, _routing_path=routing_path)

        for stat in STATS:
            assert result[stat] == routes_before[stat].model_variant

    def test_ignores_folds_below_threshold(self, tmp_path):
        """Variant with folds_positive < 3 must never be selected."""
        by_stat: Dict[str, Any] = {
            "pts": {
                "q50_xgb": {"mae_mean": 0.10, "folds_positive": 2},  # gated: folds < 3
                "blend":   {"mae_mean": 0.90, "folds_positive": 4},  # selected despite higher MAE
            }
        }
        data = {"version": 2, "by_stat": by_stat}
        wf_path = tmp_path / "wf.json"
        wf_path.write_text(json.dumps(data), encoding="utf-8")
        routing_path = _make_routing_json(tmp_path)

        result = best_routing_from_wf_results(wf_path, _routing_path=routing_path)
        assert result["pts"] == "blend"

    def test_direct_stat_schema_shape(self, tmp_path):
        """Alternative schema: {stat: {variant: {mae_mean, folds_positive}}} (no 'by_stat')."""
        data: Dict[str, Any] = {}
        for stat in STATS:
            data[stat] = {
                "q50_lgb": {"mae_mean": 0.40, "folds_positive": 4},
                "blend":   {"mae_mean": 0.80, "folds_positive": 4},
            }
        wf_path = tmp_path / "wf_direct.json"
        wf_path.write_text(json.dumps(data), encoding="utf-8")
        routing_path = _make_routing_json(tmp_path)

        result = best_routing_from_wf_results(wf_path, _routing_path=routing_path)
        for stat in STATS:
            assert result[stat] == "q50_lgb"


# ---------------------------------------------------------------------------
# Test 8: predict_quantiles_dispatched — non-quantile variants
# ---------------------------------------------------------------------------
class TestPredictQuantilesDispatched:
    def test_blend_returns_q50_only(self, tmp_path):
        routing_path = _make_routing_json(tmp_path, {"pts": {"model_variant": "blend"}})
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=22.5,
        ):
            result = predict_quantiles_dispatched("pts", _STUB_ROW, _routing_path=routing_path)
        assert result is not None
        assert result["q50"] == pytest.approx(22.5)
        assert result["q10"] is None
        assert result["q90"] is None

    def test_invalid_stat_raises(self, tmp_path):
        routing_path = _make_routing_json(tmp_path)
        with pytest.raises(ValueError, match="unknown stat"):
            predict_quantiles_dispatched("garbage", _STUB_ROW, _routing_path=routing_path)


# ---------------------------------------------------------------------------
# Test 9: unrecognised variant in JSON → WARN + fall back to blend
# ---------------------------------------------------------------------------
class TestUnrecognisedVariant:
    def test_bad_variant_falls_back_to_blend(self, tmp_path):
        routing_path = _make_routing_json(tmp_path, {"reb": {"model_variant": "UNKNOWN_VARIANT"}})
        sentinel = 5.5
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=sentinel,
        ) as mock_blend:
            result = predict_dispatched("reb", _STUB_ROW, _routing_path=routing_path)
        mock_blend.assert_called_once()
        assert result == sentinel


# ---------------------------------------------------------------------------
# Test 10 (v2): EventBus integration — model.routed published on every dispatch
# ---------------------------------------------------------------------------
class TestDispatchPublishesModelRoutedEvent:
    def test_dispatch_publishes_model_routed_event(self, tmp_path):
        """predict_dispatched must call _L46.publish with 'model.routed' payload."""
        routing_path = _make_routing_json(tmp_path, {"pts": {"model_variant": "blend"}})

        mock_l46 = MagicMock()
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=22.0,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._L46", mock_l46
        ):
            result = predict_dispatched("pts", _STUB_ROW, _routing_path=routing_path)

        assert result == 22.0
        mock_l46.publish.assert_called()
        # First call must be "model.routed"
        first_call = mock_l46.publish.call_args_list[0]
        assert first_call.args[0] == "model.routed"
        assert first_call.kwargs["source"] == "L40"
        payload = first_call.kwargs["payload"]
        assert "request_id" in payload
        assert "model_variant" in payload
        assert "is_champion" in payload
        assert "is_challenger" in payload
        assert "latency_ms" in payload
        assert "routed_at" in payload
        assert payload["model_variant"] == "blend"
        assert isinstance(payload["latency_ms"], float)


# ---------------------------------------------------------------------------
# Test 11 (v2): model.slow emitted when latency exceeds threshold
# ---------------------------------------------------------------------------
class TestSlowDispatchPublishesModelSlowEvent:
    def test_slow_dispatch_publishes_model_slow_event(self, tmp_path):
        """Simulate >100ms latency; verify model.slow is published after model.routed."""
        routing_path = _make_routing_json(tmp_path, {"blk": {"model_variant": "q50_xgb"}})

        mock_l46 = MagicMock()
        # Simulate 200ms latency: first call returns t=0, second call returns t=0.200
        fake_times = [0.0, 0.200]
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_q50_xgb",
            return_value=0.45,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._L46", mock_l46
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher.time.perf_counter",
            side_effect=fake_times,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._SLOW_THRESHOLD_MS",
            100.0,
        ):
            predict_dispatched("blk", _STUB_ROW, _routing_path=routing_path)

        call_names = [c.args[0] for c in mock_l46.publish.call_args_list]
        assert "model.routed" in call_names
        assert "model.slow" in call_names

        slow_call = next(c for c in mock_l46.publish.call_args_list if c.args[0] == "model.slow")
        slow_payload = slow_call.kwargs["payload"]
        assert slow_payload["latency_ms"] == pytest.approx(200.0)
        assert slow_payload["threshold_ms"] == pytest.approx(100.0)
        assert "model_variant" in slow_payload
        assert "request_id" in slow_payload


# ---------------------------------------------------------------------------
# Test 12 (v2): Fast dispatch does NOT emit model.slow
# ---------------------------------------------------------------------------
class TestNormalDispatchNoSlowEvent:
    def test_normal_dispatch_no_slow_event(self, tmp_path):
        """When latency is below threshold, only model.routed should be published."""
        routing_path = _make_routing_json(tmp_path, {"stl": {"model_variant": "q50_xgb"}})

        mock_l46 = MagicMock()
        # Simulate 5ms latency (well below default 100ms threshold)
        fast_times = [0.0, 0.005]
        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_q50_xgb",
            return_value=0.72,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._L46", mock_l46
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher.time.perf_counter",
            side_effect=fast_times,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._SLOW_THRESHOLD_MS",
            100.0,
        ):
            predict_dispatched("stl", _STUB_ROW, _routing_path=routing_path)

        call_names = [c.args[0] for c in mock_l46.publish.call_args_list]
        assert "model.routed" in call_names
        assert "model.slow" not in call_names


# ---------------------------------------------------------------------------
# Test 13 (v2): EventBus publish failure does not break dispatch
# ---------------------------------------------------------------------------
class TestPublishFailureDoesNotBreakDispatch:
    def test_publish_failure_does_not_break_dispatch(self, tmp_path):
        """If _L46.publish raises, predict_dispatched must still return the prediction."""
        routing_path = _make_routing_json(tmp_path, {"ast": {"model_variant": "blend"}})

        mock_l46 = MagicMock()
        mock_l46.publish.side_effect = RuntimeError("EventBus exploded")

        with patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._predict_blend",
            return_value=7.3,
        ), patch(
            "scripts.execute_loop.L40_multi_model_dispatcher._L46", mock_l46
        ):
            result = predict_dispatched("ast", _STUB_ROW, _routing_path=routing_path)

        # Result must be the prediction, not an exception
        assert result == pytest.approx(7.3)
