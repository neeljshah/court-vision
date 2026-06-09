"""P0.1 — tests for the n_min_per_season keystone floor + its cross_season.gate_x wiring.

The floor (ARCHITECTURE.md §2 / RED_A §A5) makes the honesty class a function of statistical
power, not season-label presence. These tests prove a thin second season (the 7.6k / 1.6k / 4-game
slivers the red-team flagged) is rejected, a real two-season corpus passes, and the wiring into
gate_x is additive (back-compatible) — no existing caller is affected.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "team_system"))

from loop.gate_nmin import (  # noqa: E402
    passes_n_min,
    classify_power,
    effective_season_count,
)


# --- the floor itself ------------------------------------------------------
def test_thin_second_season_fails_player_game():
    ok, reason = passes_n_min({"2024-25": 13643, "2025-26": 600}, "player_game")
    assert ok is False
    assert "600" in reason


def test_real_two_seasons_pass_player_game():
    ok, _ = passes_n_min({"2024-25": 13643, "2025-26": 9000}, "player_game")
    assert ok is True


def test_four_game_sim_lever_fails():
    ok, _ = passes_n_min({"2025-26": 4}, "sim_lever_games")
    assert ok is False


def test_classify_power_thin_is_single_season():
    assert classify_power({"2024-25": 13643, "2025-26": 600}, "player_game") == "single_season_effective"


def test_classify_power_real_is_cross_season():
    assert classify_power({"2024-25": 13643, "2025-26": 9000}, "player_game") == "cross_season"


def test_blank_season_keys_ignored():
    # 94%-unlabeled rows (blank key, RED_A §0) convey no season signal
    assert effective_season_count({"": 335405, "2024-25": 13643, "2025-26": 7630}) == 2
    assert effective_season_count({"": 100000, "  ": 50000}) == 0


def test_single_labeled_season_is_single_season_effective():
    assert classify_power({"2025-26": 50000}, "player_game") == "single_season_effective"


def test_unknown_grain_passes_floor():
    ok, reason = passes_n_min({"a": 1, "b": 2}, "novel_grain")
    assert ok is True and "no-floor" in reason


# --- the LIVE wiring in cross_season.gate_x --------------------------------
def test_gate_x_caps_thin_new_grain():
    import cross_season as cs
    res = cs.gate_x("player_game", feature="resid_x",
                    season_counts={"2024-25": 13000, "2025-26": 500})
    assert res["power_class"] == "single_season_effective"
    assert res["flag_allowed_on"] is False
    assert res["honesty_cap"] == "RESEARCH"


def test_gate_x_allows_real_two_season_grain():
    import cross_season as cs
    res = cs.gate_x("player_game", feature="resid_x",
                    season_counts={"2024-25": 13000, "2025-26": 9000})
    assert res["power_class"] == "cross_season"
    assert res.get("flag_allowed_on") is True


def test_gate_x_no_season_counts_is_backcompat():
    # existing callers that pass no season_counts get the original dict, unchanged (additive guarantee)
    import cross_season as cs
    res = cs.gate_x("lineup", feature="x")
    assert res["verdict"] == "N/A-no-substrate"
    assert "power_class" not in res
