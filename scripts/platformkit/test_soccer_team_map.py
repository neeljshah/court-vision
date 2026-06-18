"""Per-file tests for scripts.platformkit.soccer_team_map (network-free).

  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_soccer_team_map.py -q
"""
from __future__ import annotations

from scripts.platformkit import soccer_team_map as stm

_PRESENT = ["FRA", "COL", "RSA", "GER", "SEN", "KOR"]


def test_opponent_in_match_picks_other_side():
    assert stm.opponent_in_match("France vs Senegal", "France") == "Senegal"
    assert stm.opponent_in_match("France vs Senegal", "Senegal") == "France"
    # alternate separators
    assert stm.opponent_in_match("France @ Senegal", "France") == "Senegal"
    assert stm.opponent_in_match("France v Senegal", "Senegal") == "France"


def test_opponent_in_match_ambiguous_or_bad_is_none():
    assert stm.opponent_in_match("France", "France") is None          # no separator
    assert stm.opponent_in_match(None, "France") is None
    # team matches neither side -> no guess
    assert stm.opponent_in_match("France vs Senegal", "Brazil") is None


def test_resolve_prefix_and_explicit_table():
    # clean prefix codes
    assert stm.resolve_team_abbr("France", _PRESENT) == "FRA"
    assert stm.resolve_team_abbr("Colombia", _PRESENT) == "COL"
    assert stm.resolve_team_abbr("Senegal", _PRESENT) == "SEN"
    # explicit (non-prefix) FIFA codes
    assert stm.resolve_team_abbr("South Africa", _PRESENT) == "RSA"
    assert stm.resolve_team_abbr("Germany", _PRESENT) == "GER"
    assert stm.resolve_team_abbr("South Korea", _PRESENT) == "KOR"


def test_resolve_unmappable_or_absent_is_none():
    # not present in the df universe -> None (never guess a missing abbr)
    assert stm.resolve_team_abbr("Brazil", _PRESENT) is None
    assert stm.resolve_team_abbr("Spain", _PRESENT) is None
    assert stm.resolve_team_abbr("", _PRESENT) is None
    assert stm.resolve_team_abbr("France", []) is None


def test_opponent_for_team_two_team_split():
    assert stm.opponent_for_team(["COL", "FRA"], "COL") == "FRA"
    assert stm.opponent_for_team(["COL", "FRA"], "FRA") == "COL"
    assert stm.opponent_for_team(["COL", "FRA"], "BRA") is None   # side absent
    assert stm.opponent_for_team(["COL"], "COL") is None          # not two teams


def test_opp_mult_for_line_unmappable_falls_back_to_one():
    # No df needed: opponent maps to nothing in the universe -> 1.0, no raise.
    cache = {}
    m = stm.opp_mult_for_line("France vs Brazil", "France", None, "2026-06-11",
                              "Shots", _PRESENT, cache)
    assert m == 1.0  # Brazil not in _PRESENT -> opponent-blind


def test_opp_mult_for_line_maps_and_caches(monkeypatch):
    # Force all_multipliers to a known map; assert the opponent (Senegal->SEN) is
    # resolved, the stat multiplier is returned, and the cache is populated/reused.
    calls = {"n": 0}

    def fake_all(df, opp, as_of):
        calls["n"] += 1
        assert opp == "SEN"
        return {"Shots": 1.4, "Saves": 0.8}

    import domains.soccer.team_defense as td
    monkeypatch.setattr(td, "all_multipliers", fake_all)
    cache = {}
    m1 = stm.opp_mult_for_line("France vs Senegal", "France", object(),
                               "2026-06-11", "Shots", _PRESENT, cache)
    assert abs(m1 - 1.4) < 1e-9
    # second call same (opp, as_of) must hit the cache (no extra all_multipliers).
    m2 = stm.opp_mult_for_line("France vs Senegal", "France", object(),
                               "2026-06-11", "Saves", _PRESENT, cache)
    assert abs(m2 - 0.8) < 1e-9
    assert calls["n"] == 1  # cached
