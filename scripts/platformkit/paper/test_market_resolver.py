"""Per-file test: scripts.platformkit.paper.market_resolver (final-score resolution)."""
from __future__ import annotations

from scripts.platformkit.paper import market_resolver as mr

# Reds (home) beat Mets (away) 9-1 -> total=10, home margin=+8.
HOME, AWAY = "Cincinnati Reds", "New York Mets"
HS, AS = 9, 1


def r(group, sel, line=None, sport="mlb", h=HOME, a=AWAY, hs=HS, as_=AS):
    return mr.resolve(group, sel, line, sport, h, a, hs, as_)


def test_game_total_over_under_and_push():
    assert r("game total", "Over 6.5", 6.5) == "win"
    assert r("game total", "Under 6.5", 6.5) == "loss"
    # total==line -> push
    assert r("game total", "Over 10", 10) == "push"


def test_team_total():
    # Home (Reds) scored 9.
    assert r("team total", "Cincinnati Reds Over 3.5", 3.5) == "win"
    assert r("team total", "Cincinnati Reds Under 3.5", 3.5) == "loss"
    # Away (Mets) scored 1.
    assert r("team total", "New York Mets Over 3.5", 3.5) == "loss"


def test_run_line_and_spread():
    # Home -1.5: margin +8 -1.5 = +6.5 > 0 -> win.
    assert r("run line", "Cincinnati Reds -1.5", -1.5) == "win"
    # Away +1.5: -8 +1.5 = -6.5 -> loss.
    assert r("run line", "New York Mets +1.5", 1.5) == "loss"
    # Whole-number spread exact landing -> push.
    assert r("spread", "Cincinnati Reds -8", -8.0, sport="nba") == "push"


def test_segment_markets_are_ungradable():
    assert r("First 5 innings", "Cincinnati Reds ML") is None
    assert r("First half", "Cincinnati Reds ML", sport="nba") is None
    assert r("1st quarter", "Over 56.0", 56.0, sport="nba") is None


def test_soccer_1x2_and_double_chance():
    # Austria (home) 2, Jordan (away) 0 -> home win.
    h, a, hs, as_ = "Austria", "Jordan", 2, 0
    assert mr.resolve("1x2", "Austria", None, "soccer_intl", h, a, hs, as_) == "win"
    assert mr.resolve("1x2", "Draw", None, "soccer_intl", h, a, hs, as_) == "loss"
    assert mr.resolve("double chance", "Austria or Draw", None, "soccer_intl",
                      h, a, hs, as_) == "win"
    assert mr.resolve("double chance", "Jordan or Draw", None, "soccer_intl",
                      h, a, hs, as_) == "loss"


def test_btts_and_clean_sheet():
    h, a, hs, as_ = "Austria", "Jordan", 2, 0
    assert mr.resolve("both teams to score", "Yes", None, "soccer_intl",
                      h, a, hs, as_) == "loss"
    assert mr.resolve("both teams to score", "No", None, "soccer_intl",
                      h, a, hs, as_) == "win"
    assert mr.resolve("clean sheet", "Austria clean sheet", None, "soccer_intl",
                      h, a, hs, as_) == "win"
    assert mr.resolve("clean sheet", "Jordan clean sheet", None, "soccer_intl",
                      h, a, hs, as_) == "loss"


def test_winning_margin():
    h, a, hs, as_ = "Austria", "Jordan", 2, 0
    assert mr.resolve("winning margin", "home by 2", None, "soccer_intl",
                      h, a, hs, as_) == "win"
    assert mr.resolve("winning margin", "home by 1", None, "soccer_intl",
                      h, a, hs, as_) == "loss"
    assert mr.resolve("winning margin", "draw", None, "soccer_intl",
                      h, a, hs, as_) == "loss"


def test_unknown_market_is_ungradable():
    assert r("some exotic market", "whatever") is None
