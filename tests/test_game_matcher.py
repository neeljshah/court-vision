"""
tests/test_game_matcher.py — Coverage tests for _LABEL_TO_ABBREV completeness
and the dropped-game WARN counter in game_matcher.py.

Validates:
  1. All 30 NBA abbreviations are reachable via _LABEL_TO_ABBREV values.
  2. The 9 previously-missing teams now resolve from their canonical tokens.
  3. _parse_teams returns (None, None) and increments _dropped_game_count when a
     label has no recognisable team tokens.
  4. _abbrev_from_full (in live_context) resolves every full NBA team name,
     including all 9 previously-missing teams.
"""
from __future__ import annotations

import importlib
import logging

import pytest

import src.data.game_matcher as gm
from src.prediction.live_context import _abbrev_from_full


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_30_ABBREVS = {
    "ATL", "BOS", "BKN", "CHA", "CHI",
    "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM",
    "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR",
    "SAC", "SAS", "TOR", "UTA", "WAS",
}

# The nine teams that were absent before FIX IN-8
PREVIOUSLY_MISSING = {
    "CHA": ("cha", "hornets", "charlotte"),
    "DET": ("det", "pistons", "detroit"),
    "HOU": ("hou", "rockets", "houston"),
    "LAC": ("lac", "clippers"),
    "MIN": ("min", "timberwolves", "wolves", "minnesota"),
    "NYK": ("nyk", "knicks"),
    "ORL": ("orl", "magic", "orlando"),
    "UTA": ("uta", "jazz", "utah"),
    "WAS": ("was", "wizards", "washington"),
}

# Full official team names as they appear in odds feeds
FULL_TEAM_NAMES = {
    "Atlanta Hawks": "ATL",
    "Boston Celtics": "BOS",
    "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL",
    "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW",
    "Houston Rockets": "HOU",
    "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC",
    "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN",
    "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC",
    "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA",
    "Washington Wizards": "WAS",
}


# ---------------------------------------------------------------------------
# 1. Map completeness — all 30 abbrevs present as values
# ---------------------------------------------------------------------------

def test_all_30_abbrevs_are_reachable():
    """Every NBA abbreviation must appear as a value in _LABEL_TO_ABBREV."""
    present = set(gm._LABEL_TO_ABBREV.values())
    missing = ALL_30_ABBREVS - present
    assert missing == set(), f"Abbreviations missing from map: {sorted(missing)}"


# ---------------------------------------------------------------------------
# 2. Previously-missing teams resolve from their canonical tokens
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("abbrev,tokens", PREVIOUSLY_MISSING.items())
def test_previously_missing_teams_resolve(abbrev: str, tokens: tuple):
    for tok in tokens:
        result = gm._LABEL_TO_ABBREV.get(tok)
        assert result == abbrev, (
            f"Token {tok!r} should map to {abbrev!r}, got {result!r}"
        )


# ---------------------------------------------------------------------------
# 3. _parse_teams warns + increments counter on unresolvable label
# ---------------------------------------------------------------------------

def test_dropped_game_counter_increments_on_unknown_label(caplog):
    """An unrecognised label should WARN and bump _dropped_game_count."""
    # Reload to reset module-level counter (tests may run in any order)
    importlib.reload(gm)

    before = gm._dropped_game_count
    with caplog.at_level(logging.WARNING, logger="src.data.game_matcher"):
        t1, t2 = gm._parse_teams("unknownteamA_unknownteamB_2026")

    assert t1 is None
    assert t2 is None
    assert gm._dropped_game_count == before + 1
    assert any("dropped" in r.message for r in caplog.records), (
        "Expected a WARNING containing 'dropped' for unresolvable label"
    )


def test_valid_label_does_not_increment_counter():
    """A properly-formed label should NOT increment the dropped counter."""
    importlib.reload(gm)
    before = gm._dropped_game_count
    t1, t2 = gm._parse_teams("nyk_sas_2026")
    assert t1 == "NYK"
    assert t2 == "SAS"
    assert gm._dropped_game_count == before, (
        "Counter should not increase for a fully-resolved label"
    )


# ---------------------------------------------------------------------------
# 4. _abbrev_from_full resolves all 30 official full team names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("full_name,expected", FULL_TEAM_NAMES.items())
def test_abbrev_from_full_all_teams(full_name: str, expected: str):
    result = _abbrev_from_full(full_name)
    assert result == expected, (
        f"_abbrev_from_full({full_name!r}) returned {result!r}, expected {expected!r}"
    )
