"""Tests for scripts/multi_game_kelly.py — R18 K7."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from multi_game_kelly import (  # noqa: E402
    SLATE_CAP_DEFAULT,
    _load_slate_from_path,
    _per_game_exposure,
    solve_multi_game,
)


# --------- helpers --------- #
def _mk_bet(player, stat, side, stake, odds=-110, book="bov", line=10.5):
    return {
        "player": player, "stat": stat, "side": side, "book": book,
        "line": line, "odds": odds, "kelly_pct_used": stake / 10.0,
        "kelly_stake_$": stake,
    }


def _mk_slate(gid, bets):
    return {"game_id": gid, "label": gid, "ranked_bets": bets}


# --------- Test 1: single-game backward compat --------- #
def test_single_game_under_cap_is_identity():
    """One game, total exposure already under 25% — output bets are
    bit-for-bit identical (modulo the added _original side-fields)."""
    bets = [
        _mk_bet("A", "pts", "OVER", 50.0),
        _mk_bet("B", "reb", "UNDER", 50.0),
        _mk_bet("C", "ast", "OVER", 50.0),
    ]
    slate = _mk_slate("game1", bets)
    result = solve_multi_game([slate], bankroll=1000.0, slate_cap=0.25)
    assert result["n_games"] == 1
    assert result["slate_multiplier"] == 1.0
    assert result["cap_hit"] is False
    assert result["total_exposure_pre"] == pytest.approx(150.0)
    assert result["total_exposure_post"] == pytest.approx(150.0)
    # stakes preserved exactly
    out_bets = result["scaled_slates"][0]["ranked_bets"]
    for orig, scaled in zip(bets, out_bets):
        assert scaled["kelly_stake_$"] == orig["kelly_stake_$"]


def test_single_game_at_cap_is_identity():
    """One game, exposure exactly at 25% — still identity."""
    bets = [_mk_bet("A", "pts", "OVER", 250.0)]
    slate = _mk_slate("game1", bets)
    result = solve_multi_game([slate], bankroll=1000.0, slate_cap=0.25)
    assert result["slate_multiplier"] == 1.0
    assert result["cap_hit"] is False
    assert result["scaled_slates"][0]["ranked_bets"][0]["kelly_stake_$"] == 250.0


# --------- Test 2: two-game allocation --------- #
def test_two_game_allocation_under_cap():
    """Two games, each at 12% — total 24% under 25% cap, no scaling."""
    s1 = _mk_slate("g1", [_mk_bet("A", "pts", "OVER", 120.0)])
    s2 = _mk_slate("g2", [_mk_bet("B", "pts", "OVER", 120.0)])
    result = solve_multi_game([s1, s2], bankroll=1000.0, slate_cap=0.25)
    assert result["n_games"] == 2
    assert result["slate_multiplier"] == 1.0
    assert result["total_exposure_post"] == pytest.approx(240.0)


def test_two_game_allocation_over_cap_scales_uniformly():
    """Two games, each pre-scale at 20% — total 40%, scales to 25%.
    Multiplier = 25/40 = 0.625, every bet scaled by that exact factor."""
    s1 = _mk_slate("g1", [
        _mk_bet("A", "pts", "OVER", 100.0),
        _mk_bet("A", "reb", "OVER", 100.0),
    ])
    s2 = _mk_slate("g2", [
        _mk_bet("B", "pts", "OVER", 100.0),
        _mk_bet("B", "reb", "OVER", 100.0),
    ])
    result = solve_multi_game([s1, s2], bankroll=1000.0, slate_cap=0.25)
    assert result["cap_hit"] is True
    assert result["slate_multiplier"] == pytest.approx(0.625)
    assert result["total_exposure_post"] == pytest.approx(250.0, abs=0.5)
    # Each bet scaled to 62.50
    for sg in result["scaled_slates"]:
        for b in sg["ranked_bets"]:
            assert b["kelly_stake_$"] == pytest.approx(62.5, abs=0.01)
            assert b["kelly_stake_$_original"] == 100.0


# --------- Test 3: 25% cap enforcement --------- #
def test_cap_enforcement_three_games():
    """Three games each at 10% — total 30%, scales to 25%. m = 5/6."""
    slates = [
        _mk_slate(f"g{i}", [_mk_bet(f"P{i}", "pts", "OVER", 100.0)])
        for i in range(3)
    ]
    result = solve_multi_game(slates, bankroll=1000.0, slate_cap=0.25)
    assert result["cap_hit"] is True
    assert result["slate_multiplier"] == pytest.approx(5.0 / 6.0, abs=1e-6)
    assert result["total_exposure_post"] == pytest.approx(250.0, abs=0.5)
    # Total never exceeds the cap (even with rounding noise)
    assert result["total_exposure_post"] <= result["slate_cap_dollars"] + 1.0


def test_cap_enforcement_custom_cap():
    """Custom cap of 15% — three games at 10% each total 30% scales to 15%."""
    slates = [
        _mk_slate(f"g{i}", [_mk_bet(f"P{i}", "pts", "OVER", 100.0)])
        for i in range(3)
    ]
    result = solve_multi_game(slates, bankroll=1000.0, slate_cap=0.15)
    assert result["cap_hit"] is True
    assert result["total_exposure_post"] == pytest.approx(150.0, abs=0.5)


# --------- Test 4: zero-correlation default --------- #
def test_cross_game_correlation_default_is_zero():
    """Default cross_game_corr is 0 — games treated as independent."""
    s1 = _mk_slate("g1", [_mk_bet("A", "pts", "OVER", 50.0)])
    s2 = _mk_slate("g2", [_mk_bet("B", "pts", "OVER", 50.0)])
    result = solve_multi_game([s1, s2], bankroll=1000.0)
    assert result["cross_game_corr"] == 0.0


def test_nonzero_correlation_raises_not_implemented():
    """Non-zero cross-game correlation is reserved for future work."""
    s1 = _mk_slate("g1", [_mk_bet("A", "pts", "OVER", 50.0)])
    with pytest.raises(NotImplementedError):
        solve_multi_game([s1], bankroll=1000.0, cross_game_corr=0.3)


# --------- Test 5: slate-Kelly identity --------- #
def test_slate_kelly_identity_with_existing_C6_output():
    """If a single game's bets came out of the within-game C6 solver
    with total exposure already at the 25% cap, multi-game wrapper must
    leave them untouched (multiplier == 1.0). This is the smoke-test
    invariant for the SAS@OKC tonight case."""
    # mimic SAS@OKC live ranker output: 5 bets totaling $250 on $1000 bankroll
    bets = [
        _mk_bet("Wemby",     "blk", "UNDER", 50.0),
        _mk_bet("Keldon",    "reb", "OVER",  50.0),
        _mk_bet("Keldon",    "reb", "OVER",  50.0),
        _mk_bet("SGA",       "ast", "UNDER", 50.0),
        _mk_bet("JDub",      "pts", "OVER",  50.0),
    ]
    slate = _mk_slate("sas_okc_2026-05-26", bets)
    result = solve_multi_game([slate], bankroll=1000.0, slate_cap=0.25)
    assert result["slate_multiplier"] == 1.0
    assert result["cap_hit"] is False
    assert result["total_exposure_post"] == pytest.approx(250.0)
    for orig, scaled in zip(bets, result["scaled_slates"][0]["ranked_bets"]):
        assert scaled["kelly_stake_$"] == orig["kelly_stake_$"]


# --------- Test 6: input validation --------- #
def test_invalid_bankroll_raises():
    s = _mk_slate("g1", [_mk_bet("A", "pts", "OVER", 10.0)])
    with pytest.raises(ValueError):
        solve_multi_game([s], bankroll=0)
    with pytest.raises(ValueError):
        solve_multi_game([s], bankroll=-100)


def test_invalid_slate_cap_raises():
    s = _mk_slate("g1", [_mk_bet("A", "pts", "OVER", 10.0)])
    with pytest.raises(ValueError):
        solve_multi_game([s], bankroll=1000.0, slate_cap=0.0)
    with pytest.raises(ValueError):
        solve_multi_game([s], bankroll=1000.0, slate_cap=1.5)


def test_empty_slates_list():
    """Zero-game slate list — total exposure 0, multiplier defaults to 1."""
    result = solve_multi_game([], bankroll=1000.0)
    assert result["n_games"] == 0
    assert result["total_exposure_pre"] == 0.0
    assert result["total_exposure_post"] == 0.0
    assert result["slate_multiplier"] == 1.0


def test_load_slate_from_path_roundtrip():
    """Load a live_bet_ranker JSON via the loader and confirm shape."""
    payload = {
        "slate_id": "test_slate",
        "label": "Test Game",
        "ranked_bets": [
            _mk_bet("A", "pts", "OVER", 25.0),
            _mk_bet("B", "reb", "UNDER", 25.0),
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tf:
        json.dump(payload, tf)
        tf_path = tf.name
    try:
        slate = _load_slate_from_path(tf_path)
        assert slate["game_id"] == "test_slate"
        assert slate["label"] == "Test Game"
        assert len(slate["ranked_bets"]) == 2
        assert _per_game_exposure(slate) == pytest.approx(50.0)
    finally:
        os.unlink(tf_path)
