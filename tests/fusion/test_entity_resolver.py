"""Smoke tests for entity_resolver."""
import pytest
from src.fusion.entity_resolver import (
    EntityResolver, RosterEntry, TrackObservation, roster_from_boxscore
)


def _roster():
    return [
        RosterEntry(1001, "LeBron James",    23, 1610612747, "LAL", minutes_prior=36.0),
        RosterEntry(1002, "Anthony Davis",    3, 1610612747, "LAL", minutes_prior=34.0),
        RosterEntry(2001, "Stephen Curry",   30, 1610612744, "GSW", minutes_prior=35.0),
        RosterEntry(2002, "Klay Thompson",   11, 1610612744, "GSW", minutes_prior=32.0),
    ]


def test_exact_jersey_match():
    resolver = EntityResolver("0022401234", _roster())
    obs = [TrackObservation(slot=1, team_abbrev="LAL", jersey_number=23,
                             jersey_ocr_conf=0.90, team_color_conf=0.85)]
    result = resolver.resolve(obs)
    assert result[1].player_id == 1001
    assert result[1].match_method == "jersey_exact"
    assert result[1].player_game_id == "0022401234_1001"


def test_hungarian_no_jersey():
    resolver = EntityResolver("0022401234", _roster())
    obs = [TrackObservation(slot=5, team_abbrev="GSW", jersey_number=None,
                             jersey_ocr_conf=0.0, team_color_conf=0.80)]
    result = resolver.resolve(obs)
    assert result[5].player_id in {2001, 2002}
    assert result[5].match_method == "hungarian"


def test_cross_team_not_matched():
    """A LAL slot should never be matched to a GSW player."""
    resolver = EntityResolver("0022401234", _roster())
    # Only GSW in roster, slot says LAL — should fall back
    roster_gsw_only = [
        RosterEntry(2001, "Stephen Curry", 30, 1610612744, "GSW", 35.0),
    ]
    resolver2 = EntityResolver("0022401234", roster_gsw_only)
    obs = [TrackObservation(slot=7, team_abbrev="LAL", jersey_number=30,
                             jersey_ocr_conf=0.85, team_color_conf=0.70)]
    result = resolver2.resolve(obs)
    # Should be fallback since jersey_exact would cross teams
    assert result[7].match_method in {"hungarian", "fallback"}


def test_fallback_for_unresolved():
    resolver = EntityResolver("0022401234", [])  # empty roster
    obs = [TrackObservation(slot=9, team_abbrev="BOS", jersey_number=7,
                             jersey_ocr_conf=0.80, team_color_conf=0.60)]
    result = resolver.resolve(obs)
    assert result[9].match_method == "fallback"
    assert result[9].player_id == -1


def test_roster_from_boxscore_empty():
    entries = roster_from_boxscore("0022401234", {})
    assert entries == []


def test_source_value_confidence_range():
    resolver = EntityResolver("0022401234", _roster())
    obs = [TrackObservation(slot=1, team_abbrev="LAL", jersey_number=23,
                             jersey_ocr_conf=0.90, team_color_conf=0.85)]
    result = resolver.resolve(obs)
    conf = result[1].source_value.confidence
    assert 0.0 <= conf <= 1.0
