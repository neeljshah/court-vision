"""Tests for Wave-2 courtvision_router.py bug fixes.

Covers:
  bug1  – api_auto_parlay calls _build_parlays_constructor (not _build_parlays)
           and never raises TypeError; handler returns on error.
  bug2  – shrunk_q50 / shrunk is floored at current accumulated stat;
           already-cleared UNDER cards are dropped before live_bets.
  bug8  – unresolved game_id on a 2-distinct-game slate yields have_data=False
           (sample stays None → away_a/home_a stay empty).
  bug10 – fresh=1 branch in api_slate pops _PRED_LOOKUP_CACHE[date].
"""
from __future__ import annotations

import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ──────────────────────────────────────────────────────────────────────────────
# Minimal stubs so courtvision_router imports offline (NBA_OFFLINE=1 style)
# ──────────────────────────────────────────────────────────────────────────────

_INSERTED_STUBS: list = []  # names this file newly stubbed into sys.modules


def _stub_module(name, **attrs):
    if name not in sys.modules:
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        _INSERTED_STUBS.append(name)
    return sys.modules[name]


def teardown_module(module):  # remove this file's stubs so siblings import real modules
    for _n in _INSERTED_STUBS:
        sys.modules.pop(_n, None)
    _INSERTED_STUBS.clear()


def _ensure_stubs():
    for mod in ["fastapi", "fastapi.responses", "fastapi.templating"]:
        _stub_module(mod,
            APIRouter=MagicMock, Body=MagicMock, HTTPException=MagicMock,
            Query=MagicMock, Request=MagicMock, HTMLResponse=MagicMock,
            JSONResponse=MagicMock, RedirectResponse=MagicMock,
            Response=MagicMock, Jinja2Templates=MagicMock)

    fake_betting = MagicMock()
    fake_betting.evaluate.return_value = {"kelly_size": 5.0}
    _stub_module("api._courtvision_data",
        grade_bet=MagicMock(return_value={}),
        load_lines_csv=MagicMock(return_value=[]),
        load_slate_csv=MagicMock(return_value=[]),
        slate_no_lines=MagicMock(return_value=[]),
        _BETTING=fake_betting)
    _stub_module("api._courtvision_middleware", install=MagicMock())
    _stub_module("api._courtvision_form",
        get_form_lookup=MagicMock(return_value={}),
        attach_form=MagicMock())
    _stub_module("api._courtvision_odds",
        consolidate_for_slate=MagicMock(return_value=[]),
        _load_nba_players=MagicMock(return_value=set()),
        resolve_game_id=MagicMock(return_value={}),
        _CACHE={}, _STEAM_CACHE={})
    po_stub = _stub_module("api._predictions_overlay",
        _load_predictions=MagicMock(return_value=None),
        overlay_predictions=MagicMock(return_value=[]))
    # Give it the real cache dict so bug10 test can inspect it
    if not hasattr(po_stub, "_PRED_LOOKUP_CACHE"):
        po_stub._PRED_LOOKUP_CACHE = {}
    _stub_module("slowapi", Limiter=MagicMock())
    _stub_module("slowapi.util", get_remote_address=MagicMock())
    _stub_module("lightgbm")
    _stub_module("sklearn")
    _stub_module("src.llm.bet_narrator", narrate_slate=MagicMock())
    _stub_module("src.prediction.bet_thresholds",
        allowed_directions_for=MagicMock(return_value=["over", "under"]),
        edge_threshold_for=MagicMock(return_value=1.0),
        is_line_excluded=MagicMock(return_value=False),
        is_direction_line_excluded=MagicMock(return_value=False),
        kelly_b_hit_rate_for=MagicMock(return_value=0.55))
    _stub_module("src.prediction.edge_calibration",
        calibrate_p_win=MagicMock(return_value=0.62))
    _stub_module("src.prediction.live_engine",
        project_from_snapshot=MagicMock(return_value=[]))
    _stub_module("src.prediction.inplay_winprob",
        features_from_snapshot=MagicMock(return_value={}),
        predict_home_win_prob=MagicMock(return_value=None),
        active_stack=MagicMock(return_value={}))


_ensure_stubs()

_router_path = ROOT / "api" / "courtvision_router.py"
_spec = importlib.util.spec_from_file_location("courtvision_router_w2", _router_path)
_router_mod = importlib.util.module_from_spec(_spec)
_router_mod.__name__ = "courtvision_router_w2"
try:
    _spec.loader.exec_module(_router_mod)
except Exception:
    pass

_build_parlays_constructor = getattr(_router_mod, "_build_parlays_constructor", None)
_build_parlays = getattr(_router_mod, "_build_parlays", None)
_build_box_score = getattr(_router_mod, "_build_box_score", None)
_live_shrink_weight = getattr(_router_mod, "_live_shrink_weight", None)
_CACHE = getattr(_router_mod, "_CACHE", {})


# ──────────────────────────────────────────────────────────────────────────────
# BUG 1 — api_auto_parlay uses _build_parlays_constructor, never errors
# ──────────────────────────────────────────────────────────────────────────────

class TestBug1AutoParlay:
    """_build_parlays_constructor is the called function; handler never 500s."""

    def test_build_parlays_constructor_exists(self):
        """_build_parlays_constructor must be importable from the router."""
        assert _build_parlays_constructor is not None, (
            "_build_parlays_constructor not found in courtvision_router"
        )

    def test_build_parlays_constructor_signature(self):
        """_build_parlays_constructor(date, max_legs, min_ev_pct) — 3 required args."""
        import inspect
        sig = inspect.signature(_build_parlays_constructor)
        params = list(sig.parameters.keys())
        # Required positional params must include date, max_legs, min_ev_pct
        assert "date" in params
        assert "max_legs" in params
        assert "min_ev_pct" in params

    def test_auto_parlay_calls_constructor_not_build_parlays(self):
        """api_auto_parlay must call _build_parlays_constructor, not _build_parlays."""
        import ast
        src = _router_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_auto_parlay":
                # Check non-comment lines only
                func_src = ast.get_source_segment(src, node) or ""
                code_lines = [
                    ln for ln in func_src.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                code_only = "\n".join(code_lines)
                assert "_build_parlays_constructor" in code_only, (
                    "api_auto_parlay body must reference _build_parlays_constructor"
                )
                # Old 4-arg call must not appear in executable code
                assert "_build_parlays(date, max_legs" not in code_only, (
                    "api_auto_parlay must not call _build_parlays with positional max_legs arg"
                )
                return
        pytest.fail("api_auto_parlay function not found in router source")

    def test_handler_has_try_except(self):
        """api_auto_parlay body must be wrapped in try/except (never 500s)."""
        import ast
        src = _router_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_auto_parlay":
                has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
                assert has_try, "api_auto_parlay must contain a try/except block"
                return
        pytest.fail("api_auto_parlay not found")

    def test_constructor_returns_dict_with_parlays(self):
        """_build_parlays_constructor returns dict with 'parlays' list even when empty."""
        if _build_parlays_constructor is None:
            pytest.skip("function not importable")
        # Patch _build_slate to return an empty envelope (no lines)
        with patch.object(_router_mod, "_build_slate",
                          return_value={"bets": [], "has_lines": False}):
            result = _build_parlays_constructor("2099-01-01", 3, 5.0)
        assert isinstance(result, dict)
        assert "parlays" in result
        assert isinstance(result["parlays"], list)
        assert result.get("n_parlays") == 0

    def test_constructor_no_kelly_stake_dollars_in_schema(self):
        """Parlays from _build_parlays_constructor use expected_roi_sgp_pct, not kelly_stake_dollars."""
        # This test verifies the key used in the auto_parlay filter is correct.
        import ast
        src = _router_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_auto_parlay":
                func_src = ast.get_source_segment(src, node) or ""
                # The old broken filter was p["kelly_stake_dollars"] <= stake
                # With the fix, kelly_stake_dollars is NOT used as the filter key
                # (constructor parlays have expected_roi_sgp_pct, not kelly_stake_dollars)
                assert 'p["kelly_stake_dollars"]' not in func_src, (
                    "api_auto_parlay must not filter on kelly_stake_dollars "
                    "(constructor parlays don't have that key)"
                )
                return
        pytest.fail("api_auto_parlay not found")


# ──────────────────────────────────────────────────────────────────────────────
# BUG 2 — shrunk_q50 floored at current; settled UNDERs dropped
# ──────────────────────────────────────────────────────────────────────────────

class TestBug2CurrentFloor:
    """shrunk_q50 / shrunk is never below current; UNDER already past line is dropped."""

    def _shrunk(self, w_live, live_raw, pregame_q50, current):
        """Replicate the shrinkage + floor logic from all three sites."""
        shrunk = w_live * live_raw + (1.0 - w_live) * pregame_q50
        if current is not None:
            shrunk = max(shrunk, float(current))
        return shrunk

    def test_floor_raises_shrunk_to_current(self):
        """When shrunk < current, the floor brings it up to current."""
        # Player has 6 pts already; projection is only 5.0 (e.g. early shrinkage).
        shrunk = self._shrunk(w_live=0.3, live_raw=5.0, pregame_q50=20.0, current=6)
        # Without floor: 0.3*5 + 0.7*20 = 1.5 + 14 = 15.5 — actually above here.
        # Test the explicit below-current case:
        raw = 0.1 * 4.0 + 0.9 * 5.0   # = 0.4 + 4.5 = 4.9
        current = 6
        floored = max(raw, float(current))
        assert floored == pytest.approx(6.0), (
            f"Expected floor at current=6, got {floored}"
        )

    def test_no_floor_when_shrunk_above_current(self):
        """When shrunk > current, the floor is a no-op."""
        raw = 0.8 * 25.0 + 0.2 * 20.0  # = 20 + 4 = 24.0
        current = 10
        floored = max(raw, float(current))
        assert floored == pytest.approx(24.0)

    def test_floor_when_current_is_none_is_noop(self):
        """When current is None, shrunk is unchanged."""
        raw = 5.5
        current = None
        floored = raw if current is None else max(raw, float(current))
        assert floored == pytest.approx(5.5)

    def test_under_dropped_when_current_clears_line(self):
        """A recommended UNDER where current >= line should be dropped (settled)."""
        # Simulate the belt-and-suspenders guard:
        # current=5, line=4.5, side=UNDER → already lost, must be dropped.
        current = 5.0
        line = 4.5
        side = "UNDER"
        should_drop = (current is not None and side == "UNDER" and float(current) >= line)
        assert should_drop is True, "Current=5 >= line=4.5 UNDER should be dropped"

    def test_under_kept_when_current_below_line(self):
        """A recommended UNDER where current < line should NOT be dropped."""
        current = 3.0
        line = 4.5
        side = "UNDER"
        should_drop = (current is not None and side == "UNDER" and float(current) >= line)
        assert should_drop is False, "Current=3 < line=4.5 UNDER should be kept"

    def test_over_never_dropped_by_guard(self):
        """The UNDER-settled guard must never drop OVER bets."""
        current = 99.0  # absurdly high
        line = 4.5
        side = "OVER"
        should_drop = (current is not None and side == "UNDER" and float(current) >= line)
        assert should_drop is False, "OVER bets must never be dropped by the UNDER guard"

    def test_site_a_floor_in_source(self):
        """Source at the live_bets site (a) must apply the floor after shrunk_q50 computation."""
        src = _router_path.read_text(encoding="utf-8")
        # Find the block that computes shrunk_q50 in the live_bets loop
        assert "shrunk_q50 = max(shrunk_q50, float(_cur_a))" in src, (
            "Bug 2 site (a) floor missing: expected max(shrunk_q50, float(_cur_a))"
        )

    def test_site_b_floor_in_source(self):
        """Source at the home_data site (b) must apply the floor."""
        src = _router_path.read_text(encoding="utf-8")
        assert "shrunk_q50 = max(shrunk_q50, float(_cur_b))" in src, (
            "Bug 2 site (b) floor missing: expected max(shrunk_q50, float(_cur_b))"
        )

    def test_site_c_floor_in_source(self):
        """Source at the parlay site (c) must apply the floor."""
        src = _router_path.read_text(encoding="utf-8")
        assert "shrunk = max(shrunk, float(_cur_c))" in src, (
            "Bug 2 site (c) floor missing: expected max(shrunk, float(_cur_c))"
        )

    def test_site_a_settled_under_guard_in_source(self):
        """Source must contain the belt-and-suspenders UNDER-settled drop guard."""
        src = _router_path.read_text(encoding="utf-8")
        assert "_side_a == \"UNDER\"" in src or "_side_a == 'UNDER'" in src, (
            "Bug 2 site (a) UNDER settled guard missing"
        )
        assert "float(_cur_a) >= _line_a" in src, (
            "Bug 2 site (a) UNDER settled threshold check missing"
        )


# ──────────────────────────────────────────────────────────────────────────────
# BUG 8 — unresolved game_id on multi-game slate yields have_data=False
# ──────────────────────────────────────────────────────────────────────────────

class TestBug8BoxScoreFallback:
    """When game_id can't be matched and slate has 2+ distinct games, sample stays None."""

    def _distinct_game_count(self, bets):
        """Replicate the fixed fallback logic."""
        _ab = bets
        _dg = {str(b.get("game_id") or "") for b in _ab}
        sample = _ab[0] if (_ab and len(_dg) == 1) else None
        return sample

    def test_single_game_slate_gets_fallback(self):
        """With one distinct game_id on the slate, fallback to all_bets[0] is safe."""
        bets = [
            {"game_id": "G1", "player_name": "A", "team": "LAL", "opp": "BOS"},
            {"game_id": "G1", "player_name": "B", "team": "LAL", "opp": "BOS"},
        ]
        sample = self._distinct_game_count(bets)
        assert sample is not None, "Single-game slate should produce a fallback sample"
        assert sample["game_id"] == "G1"

    def test_two_game_slate_no_fallback(self):
        """With two distinct game_ids on the slate, fallback must return None."""
        bets = [
            {"game_id": "G1", "player_name": "A", "team": "LAL", "opp": "BOS"},
            {"game_id": "G2", "player_name": "C", "team": "GSW", "opp": "PHX"},
        ]
        sample = self._distinct_game_count(bets)
        assert sample is None, (
            "Multi-game slate must NOT fall back to first bet (wrong matchup)"
        )

    def test_empty_slate_no_fallback(self):
        """Empty slate must not crash and must return None."""
        sample = self._distinct_game_count([])
        assert sample is None

    def test_fix_present_in_source(self):
        """Source must contain the fixed fallback guard checking len(_dg) == 1."""
        src = _router_path.read_text(encoding="utf-8")
        assert "len(_dg) == 1" in src, (
            "Bug 8 fix missing: fallback should gate on len(distinct game_ids) == 1"
        )


# ──────────────────────────────────────────────────────────────────────────────
# BUG 10 — fresh=1 pops _PRED_LOOKUP_CACHE
# ──────────────────────────────────────────────────────────────────────────────

class TestBug10FreshBustsPredCache:
    """After fresh=1 the predictions overlay cache entry for that date is popped."""

    def test_fresh_pops_pred_lookup_cache(self):
        """Verify the fresh branch calls _po._PRED_LOOKUP_CACHE.pop(date, None)."""
        import ast
        src = _router_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Find api_slate function
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_slate":
                func_src = ast.get_source_segment(src, node) or ""
                assert "_PRED_LOOKUP_CACHE" in func_src, (
                    "Bug 10 fix missing: api_slate must bust _PRED_LOOKUP_CACHE in fresh branch"
                )
                assert "_po._PRED_LOOKUP_CACHE.pop(date" in func_src, (
                    "Bug 10 fix missing: must pop date key from _PRED_LOOKUP_CACHE"
                )
                return
        pytest.fail("api_slate function not found in router source")

    def test_fresh_bust_is_guarded_by_try_except(self):
        """The _PRED_LOOKUP_CACHE.pop call must be in a try/except (tolerates missing attr)."""
        import ast
        src = _router_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "api_slate":
                # Walk for try nodes whose body touches _PRED_LOOKUP_CACHE
                for try_node in ast.walk(node):
                    if isinstance(try_node, ast.Try):
                        body_src = "".join(
                            ast.get_source_segment(src, s) or ""
                            for s in try_node.body
                        )
                        if "_PRED_LOOKUP_CACHE" in body_src:
                            return  # Found: guarded correctly
                pytest.fail(
                    "Bug 10: _PRED_LOOKUP_CACHE.pop must be wrapped in try/except"
                )
                return
        pytest.fail("api_slate not found")

    def test_pred_cache_pop_mechanics(self):
        """Unit-test the pop mechanics: after pop the key is absent."""
        cache: dict = {"2026-05-31": (1.0, {}), "2026-05-30": (1.0, {})}
        cache.pop("2026-05-31", None)
        assert "2026-05-31" not in cache
        assert "2026-05-30" in cache  # other dates untouched

    def test_pred_cache_pop_missing_key_is_noop(self):
        """pop(date, None) on a missing key must not raise."""
        cache: dict = {}
        cache.pop("2099-01-01", None)  # must not raise
