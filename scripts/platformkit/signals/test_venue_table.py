"""Focused tests for the static, RUNTIME-available NBA venue table."""
from __future__ import annotations

from datetime import date

import pytest

from scripts.platformkit.signals import venue_table as VT


# Canonical NBA schedule home-team identifiers.  The visible worktree has no
# standalone schedule file, so this is the complete league identifier set that
# an NBA schedule corpus must resolve.
NBA_HOME_TEAM_IDS = {
    1610612737, 1610612738, 1610612739, 1610612740, 1610612741, 1610612742,
    1610612743, 1610612744, 1610612745, 1610612746, 1610612747, 1610612748,
    1610612749, 1610612750, 1610612751, 1610612752, 1610612753, 1610612754,
    1610612755, 1610612756, 1610612757, 1610612758, 1610612759, 1610612760,
    1610612761, 1610612762, 1610612763, 1610612764, 1610612765, 1610612766,
}


def test_distance_identity_and_denver_miami_reference_pair():
    denver = VT.lookup(1610612743, date(2026, 1, 1))
    miami = VT.lookup(1610612748, "2026-01-01")
    assert VT.great_circle_km(denver, denver) == 0.0
    assert abs(VT.great_circle_km(denver, miami) - 2780.0) <= 2780.0 * 0.02


def test_every_nba_home_team_resolves_to_a_runtime_row():
    unresolved = [team_id for team_id in NBA_HOME_TEAM_IDS
                  if not _resolves(team_id)]
    assert unresolved == []
    assert len(VT.VENUES) == len(NBA_HOME_TEAM_IDS)


def test_coordinate_elevation_and_runtime_tag_bounds():
    assert VT.runtime_columns_are_tagged()
    assert set(VT.RUNTIME_COLUMNS) == set(VT.VenueRow.__dataclass_fields__)
    for venue in VT.VENUES:
        assert -90.0 <= venue.lat <= 90.0
        assert -180.0 <= venue.lon <= 180.0
        assert -500.0 <= venue.elevation_m <= 4000.0


def test_lookup_rejects_unknown_team_and_invalid_date():
    with pytest.raises(KeyError):
        VT.lookup(0, date(2026, 1, 1))
    with pytest.raises(ValueError):
        VT.lookup(1610612743, "not-a-date")


def _resolves(team_id: int) -> bool:
    try:
        return VT.lookup(team_id, date(2026, 1, 1)).team_ids == (team_id,)
    except KeyError:
        return False
