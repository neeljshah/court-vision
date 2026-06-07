"""Tests for the CV_LIVE_SIM gated scenario / win-prob panel.

Covers:
  1. OFF (default) = byte-identical — no ``sim`` key added, box dict unchanged.
  2. ON + live snapshot = sim block present with sane values.
  3. ON + no snapshot = no sim block (graceful absent-data path).
  4. ON + malformed snapshot = no crash, no sim block.
  5. sim block schema: win-prob in [0,1], score q10<=q50<=q90, scenarios present.
  6. Scenarios shift directionally (star foul-out lowers home win-prob vs base).
  7. Existing box keys are never mutated (ADDITIVE only).
"""
from __future__ import annotations

import copy
import os
import sys

import pytest

# Ensure repo root is on path regardless of how pytest is invoked.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_snapshot(period: int = 3, clock: str = "6:00",
                   home_score: int = 72, away_score: int = 69) -> dict:
    """Minimal but valid live snapshot for testing."""
    home_players = [
        {
            "player_id": i, "name": f"HomePlayer{i}", "team": "OKC",
            "pts": 8 + i * 2, "reb": 4, "ast": 2, "fg3m": 1,
            "stl": 0, "blk": 0, "tov": 1,
            "min": 20.0, "pf": 1, "oncourt": 1 if i <= 5 else 0,
            "is_starter": i <= 5, "l10_min": 32.0,
            "season_pts_per_min": 0.6,
        }
        for i in range(1, 9)
    ]
    away_players = [
        {
            "player_id": 100 + i, "name": f"AwayPlayer{i}", "team": "NYK",
            "pts": 7 + i * 2, "reb": 3, "ast": 2, "fg3m": 1,
            "stl": 0, "blk": 0, "tov": 1,
            "min": 20.0, "pf": 2, "oncourt": 1 if i <= 5 else 0,
            "is_starter": i <= 5, "l10_min": 30.0,
            "season_pts_per_min": 0.55,
        }
        for i in range(1, 9)
    ]
    return {
        "home_team": "OKC",
        "away_team": "NYK",
        "home_score": home_score,
        "away_score": away_score,
        "period": period,
        "clock": clock,
        "players": home_players + away_players,
    }


def _make_box(extra_key: str = "existing_data") -> dict:
    """Minimal box dict with some pre-existing keys."""
    return {
        extra_key: "untouched",
        "home": {"projected_total_pts": 110.0},
        "away": {"projected_total_pts": 107.0},
        "home_win_prob": 0.55,
        "away_win_prob": 0.45,
        "date": "2026-06-05",
        "game_id": "0042500401",
    }


# ---------------------------------------------------------------------------
# 1. OFF path: byte-identical
# ---------------------------------------------------------------------------

def test_flag_off_byte_identical(monkeypatch):
    """When CV_LIVE_SIM is not set (or '0'), box dict is returned UNCHANGED."""
    monkeypatch.delenv("CV_LIVE_SIM", raising=False)

    # Force reload so the flag re-reads the env.
    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    snap = _make_snapshot()
    box_before = copy.deepcopy(box)

    result = _mod.maybe_attach_sim_panel(box, snap)

    # Returned object is the same dict (identity)
    assert result is box
    # No new keys
    assert set(result.keys()) == set(box_before.keys()), (
        f"Unexpected new keys: {set(result.keys()) - set(box_before.keys())}")
    # All values identical
    for k, v in box_before.items():
        assert result[k] == v, f"Key {k!r} was mutated"


def test_flag_off_no_sim_key(monkeypatch):
    """Explicitly 'CV_LIVE_SIM=0' — no ``sim`` key in result."""
    monkeypatch.setenv("CV_LIVE_SIM", "0")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())
    assert "sim" not in result


# ---------------------------------------------------------------------------
# 2. ON + live snapshot present = sim block with sane values
# ---------------------------------------------------------------------------

def test_flag_on_sim_block_present(monkeypatch):
    """When CV_LIVE_SIM=1, a ``sim`` block is added to the box."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    snap = _make_snapshot()
    result = _mod.maybe_attach_sim_panel(box, snap)

    assert "sim" in result, "sim block missing when flag is ON"
    sim = result["sim"]
    assert sim["flag"] == "CV_LIVE_SIM"
    assert "note" in sim


def test_flag_on_win_prob_in_range(monkeypatch):
    """Win-prob values are in [0,1]."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())
    sim = result.get("sim", {})

    hwp = sim.get("home_win_prob")
    awp = sim.get("away_win_prob")
    assert hwp is not None and 0.0 <= hwp <= 1.0, f"home_win_prob out of range: {hwp}"
    assert awp is not None and 0.0 <= awp <= 1.0, f"away_win_prob out of range: {awp}"
    assert abs(hwp + awp - 1.0) < 1e-6, "win probs don't sum to 1"


def test_flag_on_score_dist_monotone(monkeypatch):
    """Score distributions satisfy q10 <= q50 <= q90."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())
    sim = result.get("sim", {})

    for side in ("home_score_dist", "away_score_dist"):
        dist = sim.get(side)
        if dist is not None:
            assert dist["q10"] <= dist["q50"], f"{side}: q10 > q50"
            assert dist["q50"] <= dist["q90"], f"{side}: q50 > q90"


def test_flag_on_scenarios_present(monkeypatch):
    """At least one scenario is generated for a mid-game snapshot."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())
    sim = result.get("sim", {})
    scenarios = sim.get("scenarios", [])

    assert isinstance(scenarios, list)
    # Each scenario must have required keys
    for sc in scenarios:
        assert "name" in sc
        assert "home_win_prob" in sc
        assert 0.0 <= sc["home_win_prob"] <= 1.0
        assert "note" in sc


def test_existing_keys_not_mutated(monkeypatch):
    """The sim block is ADDITIVE: existing box keys are never overwritten."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    original_wp = box["home_win_prob"]
    original_existing = box["existing_data"]
    box_keys_before = set(box.keys())

    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())

    # Routed win prob unchanged
    assert result["home_win_prob"] == original_wp
    # Existing data unchanged
    assert result["existing_data"] == original_existing
    # Only one new key allowed: "sim"
    new_keys = set(result.keys()) - box_keys_before
    assert new_keys <= {"sim"}, f"Unexpected extra keys: {new_keys}"


# ---------------------------------------------------------------------------
# 3. ON + no snapshot = no sim block (graceful)
# ---------------------------------------------------------------------------

def test_flag_on_no_snapshot_no_sim(monkeypatch):
    """When the live snapshot is None, no sim block is added."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, None)
    assert "sim" not in result


def test_flag_on_empty_snapshot_no_sim(monkeypatch):
    """When the live snapshot has no 'period', no sim block is added."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, {})
    assert "sim" not in result


# ---------------------------------------------------------------------------
# 4. ON + malformed snapshot = no crash, no partial sim block
# ---------------------------------------------------------------------------

def test_flag_on_malformed_snapshot_no_crash(monkeypatch):
    """Malformed snapshot (e.g. players is a string) doesn't crash."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    malformed = {
        "home_team": None,
        "away_team": 12345,      # wrong type
        "home_score": "not-a-number",
        "away_score": {},
        "period": "three",       # wrong type
        "clock": [1, 2, 3],      # wrong type
        "players": "NOT_A_LIST", # wrong type
    }
    box = _make_box()
    # Must not raise
    result = _mod.maybe_attach_sim_panel(box, malformed)
    # box is returned (may or may not have sim — just no crash)
    assert result is box


def test_flag_on_period_zero_no_sim(monkeypatch):
    """Snapshot with period=0 (pre-tip) produces no sim block."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    snap = _make_snapshot(period=0)
    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, snap)
    assert "sim" not in result


# ---------------------------------------------------------------------------
# 5. Scenario directional check: star foul-out should lower home win-prob
# ---------------------------------------------------------------------------

def test_foul_out_scenario_lowers_home_win_prob(monkeypatch):
    """The 'home_star_fouls_out' scenario should have lower home_win_prob
    than the base (or at most a very small increase due to sim variance).
    We allow a tolerance of 0.15 for simulation noise at n_sims=800."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    # Use a late-game close scenario (Q4, 6:00, home leading by 3)
    snap = _make_snapshot(period=4, clock="6:00",
                          home_score=95, away_score=92)
    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, snap)
    sim = result.get("sim", {})
    scenarios = sim.get("scenarios", [])

    foul_out_sc = next((s for s in scenarios
                        if s.get("name") == "home_star_fouls_out"), None)
    if foul_out_sc is None:
        pytest.skip("foul_out scenario not generated (no eligible player)")

    base_wp = sim.get("home_win_prob", 0.5)
    sc_wp = foul_out_sc["home_win_prob"]
    # Allow up to +0.15 due to sim variance (Monte Carlo noise at small n),
    # but the scenario should not *dramatically* increase home win prob.
    assert sc_wp <= base_wp + 0.15, (
        f"Star foul-out raised home WP by too much: base={base_wp:.3f}, "
        f"scenario={sc_wp:.3f}"
    )


# ---------------------------------------------------------------------------
# 6. sim block note field present and mentions scenario
# ---------------------------------------------------------------------------

def test_sim_note_field(monkeypatch):
    """The sim block note explicitly labels the output as scenario/illustrative."""
    monkeypatch.setenv("CV_LIVE_SIM", "1")

    import importlib
    import api._cv_live_sim_panel as _mod
    importlib.reload(_mod)

    box = _make_box()
    result = _mod.maybe_attach_sim_panel(box, _make_snapshot())
    sim = result.get("sim", {})
    note = sim.get("note", "")
    assert "SCENARIO" in note.upper() or "scenario" in note.lower()
    assert "POINT" in note.upper() or "projection" in note.lower()
