"""tests/test_w023_ingame_vac_ast.py — W-023 CV_INGAME_VAC_AST gate tests.

Covers:
  * default-OFF is byte-identical (no vac_ast field, no scaling) — the hard gate.
  * HARD-OFF in playoffs (game_id prefix "004") even when flag is ON.
  * When ON + game_date + regular season: vac_ast field attached to all rows.
  * AST projected_final scaled up 1.25x when vac_ast >= 3 (< 6).
  * AST projected_final scaled up 1.50x when vac_ast >= 6.
  * Non-AST stats: vac_ast field attached but projected_final unchanged.
  * When vac_ast < 3: AST projected_final unchanged.
  * When game_date absent: no-op (vac_ast=0.0 default, no scaling).
  * Only remaining delta is scaled (current_stat is never altered).
  * When remaining <= 0: no scaling (projected_final already at floor).
  * ingame_vac_ast_enabled() in intel_selection reflects the env flag.
  * belt-and-suspenders: bad inputs never raise.
"""
from __future__ import annotations

import importlib
import os
from typing import Dict, List
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snap(game_id: str = "0022500100", game_date: str = "2026-01-15") -> dict:
    return {
        "game_id": game_id,
        "game_date": game_date,
        "period": 3,
        "clock": "12:00",
        "home_team": "OKC",
        "away_team": "NYK",
        "home_score": 78,
        "away_score": 72,
        "players": [
            {"player_id": 1001, "name": "Star Guard", "team": "OKC",
             "min": 24.0, "pts": 20, "reb": 3, "ast": 5,
             "fg3m": 2, "stl": 1, "blk": 0, "tov": 2, "pf": 2},
        ],
    }


def _make_rows(current: float = 5.0, projected: float = 9.0,
               stat: str = "ast", pid: int = 1001) -> List[Dict]:
    return [{
        "player_id": pid,
        "name": "Star Guard",
        "team": "OKC",
        "stat": stat,
        "current": current,
        "projected_final": projected,
        "period": 3,
        "foul_factor": 1.0,
        "blow_factor": 1.0,
        "projection_source": "cycle_88_linear",
    }]


def _fake_lookup(pid: int, date: str, vac_ast: float) -> dict:
    """Mock vac_ast lookup keyed (player_id, YYYY-MM-DD)."""
    return {(pid, date): {"vac_ast": vac_ast, "vac_ast_share": 0.25}}


# ---------------------------------------------------------------------------
# Import the function under test
# ---------------------------------------------------------------------------

from src.prediction.live_engine import _apply_ingame_vac_ast  # noqa: E402
import src.prediction.intel_selection as isel  # noqa: E402


# ---------------------------------------------------------------------------
# Gate 1: default-OFF is byte-identical
# ---------------------------------------------------------------------------

def test_default_off_no_field_added(monkeypatch):
    """With CV_INGAME_VAC_AST unset, rows are returned unchanged."""
    monkeypatch.delenv("CV_INGAME_VAC_AST", raising=False)
    snap = _make_snap()
    rows = _make_rows()
    original_pf = rows[0]["projected_final"]
    result = _apply_ingame_vac_ast(snap, rows)
    # vac_ast field must NOT be added when the flag is OFF
    assert "vac_ast" not in result[0]
    # projected_final must be unchanged
    assert result[0]["projected_final"] == original_pf


def test_default_off_sweep(monkeypatch):
    """Sweep many (stat, pid, pf, vac_ast) combinations: flag OFF is always a no-op."""
    monkeypatch.delenv("CV_INGAME_VAC_AST", raising=False)
    for stat in ("ast", "pts", "reb", "fg3m"):
        for pf in (2.0, 5.0, 10.0, 20.0):
            rows = _make_rows(current=1.0, projected=pf, stat=stat)
            original = rows[0]["projected_final"]
            result = _apply_ingame_vac_ast(_make_snap(), rows)
            assert "vac_ast" not in result[0]
            assert result[0]["projected_final"] == original


# ---------------------------------------------------------------------------
# Gate 2: HARD-OFF in playoffs
# ---------------------------------------------------------------------------

def test_hard_off_in_playoffs_004_prefix(monkeypatch):
    """HARD-OFF: even with flag ON and valid vac_ast data, playoffs are no-op."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0042500401")
    rows = _make_rows(stat="ast", current=5.0, projected=9.0)
    original_pf = rows[0]["projected_final"]
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=8.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    # Playoff guard fires before any lookup
    assert "vac_ast" not in result[0]
    assert result[0]["projected_final"] == original_pf


def test_playoff_prefix_004_all_forms(monkeypatch):
    """Various 004* game_id forms all trigger the playoff guard."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    for gid in ("0042500401", "0042500317", "004xxxx"):
        snap = _make_snap(game_id=gid, game_date="2026-06-03")
        rows = _make_rows(stat="ast", current=3.0, projected=8.0)
        result = _apply_ingame_vac_ast(snap, rows)
        assert "vac_ast" not in result[0], f"Playoff guard failed for game_id={gid}"
        assert result[0]["projected_final"] == 8.0


# ---------------------------------------------------------------------------
# Gate 3: no game_date → no-op with vac_ast=0.0 default
# ---------------------------------------------------------------------------

def test_no_game_date_attaches_zero(monkeypatch):
    """When game_date absent from snap, vac_ast=0.0 is attached but no scaling."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap()
    del snap["game_date"]  # remove date
    rows = _make_rows(stat="ast", current=5.0, projected=9.0)
    result = _apply_ingame_vac_ast(snap, rows)
    # vac_ast=0.0 default attached (schema consistency)
    assert result[0].get("vac_ast") == 0.0
    # No scaling when date unknown
    assert result[0]["projected_final"] == 9.0


def test_none_game_date_attaches_zero(monkeypatch):
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap()
    snap["game_date"] = None
    rows = _make_rows(stat="ast", current=5.0, projected=9.0)
    result = _apply_ingame_vac_ast(snap, rows)
    assert result[0].get("vac_ast") == 0.0
    assert result[0]["projected_final"] == 9.0


# ---------------------------------------------------------------------------
# Core firing: vac_ast attaches + AST scales
# ---------------------------------------------------------------------------

def test_vac_ast_attached_to_all_stats(monkeypatch):
    """vac_ast field is attached to every row (all stats), not just AST."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = []
    for stat in ("ast", "pts", "reb", "fg3m"):
        rows.append({
            "player_id": 1001, "stat": stat,
            "current": 2.0, "projected_final": 8.0,
            "projection_source": "cycle_88_linear",
        })
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=4.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    for r in result:
        assert r.get("vac_ast") == 4.0, f"vac_ast missing on stat={r['stat']}"


def test_ast_scales_1_25x_when_vac_ast_3_to_6(monkeypatch):
    """AST projected_final scales by 1.25x when 3 <= vac_ast < 6."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    current, projected = 5.0, 9.0  # remaining = 4.0
    rows = _make_rows(stat="ast", current=current, projected=projected)
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=4.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    # remaining=4.0, mult=1.25 -> new_pf = 5.0 + 4.0*1.25 = 10.0
    assert abs(result[0]["projected_final"] - (current + (projected - current) * 1.25)) < 1e-6


def test_ast_scales_1_50x_when_vac_ast_ge_6(monkeypatch):
    """AST projected_final scales by 1.50x when vac_ast >= 6."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    current, projected = 3.0, 7.0  # remaining = 4.0
    rows = _make_rows(stat="ast", current=current, projected=projected)
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=7.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    # remaining=4.0, mult=1.50 -> new_pf = 3.0 + 4.0*1.50 = 9.0
    expected = current + (projected - current) * 1.50
    assert abs(result[0]["projected_final"] - expected) < 1e-6


def test_ast_no_scale_when_vac_ast_below_3(monkeypatch):
    """AST projected_final unchanged when vac_ast < 3."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=3.0, projected=8.0)
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=2.9)):
        result = _apply_ingame_vac_ast(snap, rows)
    assert result[0]["projected_final"] == 8.0
    assert result[0]["vac_ast"] == 2.9


def test_non_ast_stats_not_scaled(monkeypatch):
    """Non-AST stats get vac_ast attached but projected_final unchanged."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    for stat in ("pts", "reb", "fg3m", "stl", "blk", "tov"):
        rows = _make_rows(stat=stat, current=2.0, projected=8.0)
        with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
                   _fake_lookup(1001, "2026-01-15", vac_ast=8.0)):
            result = _apply_ingame_vac_ast(snap, rows)
        assert result[0]["projected_final"] == 8.0, f"Non-AST stat {stat} was scaled"
        assert result[0]["vac_ast"] == 8.0


# ---------------------------------------------------------------------------
# Remaining-delta-only scaling
# ---------------------------------------------------------------------------

def test_current_never_scaled(monkeypatch):
    """current_stat is never altered — only the remaining projection."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    current, projected = 6.0, 9.0  # remaining = 3.0
    rows = _make_rows(stat="ast", current=current, projected=projected)
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    new_pf = result[0]["projected_final"]
    # current must be unchanged (not in the row dict, but projected_final >= current)
    assert new_pf >= current
    # Only remaining scaled: new_pf = current + remaining*1.25
    expected = current + (projected - current) * 1.25
    assert abs(new_pf - expected) < 1e-6


def test_no_scale_when_remaining_zero_or_negative(monkeypatch):
    """When projected_final <= current (player past projection), no scaling."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=8.0, projected=8.0)  # remaining=0
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    assert result[0]["projected_final"] == 8.0  # unchanged


def test_no_scale_when_pf_below_current(monkeypatch):
    """remaining < 0 (floor case) — no scaling."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=10.0, projected=9.0)  # remaining=-1
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    assert result[0]["projected_final"] == 9.0  # unchanged


# ---------------------------------------------------------------------------
# Missing player in lookup → vac_ast=0.0, no scaling
# ---------------------------------------------------------------------------

def test_player_not_in_lookup_gets_zero_vac_ast(monkeypatch):
    """Player not in the lookup: vac_ast=0.0, projected_final unchanged."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=3.0, projected=9.0, pid=9999)
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=8.0)):  # different pid
        result = _apply_ingame_vac_ast(snap, rows)
    assert result[0].get("vac_ast") == 0.0
    assert result[0]["projected_final"] == 9.0


# ---------------------------------------------------------------------------
# projection_source tagging
# ---------------------------------------------------------------------------

def test_projection_source_tagged(monkeypatch):
    """projection_source gets '+vac_ast' appended when scaling fires."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=3.0, projected=9.0)
    rows[0]["projection_source"] = "cycle_88_linear"
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    assert "+vac_ast" in result[0].get("projection_source", "")


def test_projection_source_not_duplicated(monkeypatch):
    """'+vac_ast' is only added once per row."""
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = _make_rows(stat="ast", current=3.0, projected=9.0)
    rows[0]["projection_source"] = "cycle_88_linear+vac_ast"  # already tagged
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    src = result[0].get("projection_source", "")
    assert src.count("+vac_ast") == 1


# ---------------------------------------------------------------------------
# intel_selection.ingame_vac_ast_enabled() reflects the env flag
# ---------------------------------------------------------------------------

def test_ingame_vac_ast_enabled_false_by_default(monkeypatch):
    monkeypatch.delenv("CV_INGAME_VAC_AST", raising=False)
    importlib.reload(isel)
    assert isel.ingame_vac_ast_enabled() is False


def test_ingame_vac_ast_enabled_true_when_set(monkeypatch):
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    importlib.reload(isel)
    try:
        assert isel.ingame_vac_ast_enabled() is True
    finally:
        monkeypatch.delenv("CV_INGAME_VAC_AST", raising=False)
        importlib.reload(isel)


def test_ingame_vac_ast_distinct_from_intel_vac_ast(monkeypatch):
    """CV_INGAME_VAC_AST and CV_INTEL_VAC_AST are independent flags."""
    monkeypatch.setenv("CV_INTEL_VAC_AST", "1")
    monkeypatch.delenv("CV_INGAME_VAC_AST", raising=False)
    importlib.reload(isel)
    try:
        assert isel.vac_ast_enabled() is True        # pregame flag ON
        assert isel.ingame_vac_ast_enabled() is False  # live flag OFF
    finally:
        monkeypatch.delenv("CV_INTEL_VAC_AST", raising=False)
        importlib.reload(isel)


# ---------------------------------------------------------------------------
# Belt-and-suspenders: bad inputs never raise
# ---------------------------------------------------------------------------

def test_empty_rows(monkeypatch):
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, [])
    assert result == []


def test_none_player_id(monkeypatch):
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = [{"player_id": None, "stat": "ast", "current": 3.0, "projected_final": 9.0,
             "projection_source": "cycle_88_linear"}]
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    # No crash; projected_final unchanged (pid_key is None)
    assert result[0]["projected_final"] == 9.0


def test_none_projected_final(monkeypatch):
    monkeypatch.setenv("CV_INGAME_VAC_AST", "1")
    snap = _make_snap(game_id="0022500100", game_date="2026-01-15")
    rows = [{"player_id": 1001, "stat": "ast", "current": 3.0, "projected_final": None,
             "projection_source": "cycle_88_linear"}]
    with patch("src.prediction.live_engine._VAC_AST_INGAME_CACHE",
               _fake_lookup(1001, "2026-01-15", vac_ast=5.0)):
        result = _apply_ingame_vac_ast(snap, rows)
    # No crash; None projected_final left as-is
    assert result[0]["projected_final"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
