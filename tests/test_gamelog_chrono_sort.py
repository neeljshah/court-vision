"""Test the CV_GAMELOG_CHRONO_SORT gated fix in feature_assembler._gamelogs_for_player.

Bug (sweep TRACKING_CV, HIGH): game_date is 'Mon DD, YYYY'; the legacy LEXICOGRAPHIC sort
scrambles the Oct->Apr NBA season (Apr<Dec<Jan<Nov<Oct), so the L5/L10/L20 tail + last-game
read the wrong games. Default OFF = byte-identical legacy; ON = true chronological order.
"""
import json
import os
import pytest
from src.pipeline import feature_assembler as fa

# True chronological order by pts: 1(Oct)->2(Nov)->3(Dec)->4(Jan)->5(Apr, latest)
_DATA = [
    {"game_date": "Jan 05, 2025", "pts": 4},
    {"game_date": "Oct 24, 2024", "pts": 1},
    {"game_date": "Apr 13, 2025", "pts": 5},
    {"game_date": "Dec 25, 2024", "pts": 3},
    {"game_date": "Nov 15, 2024", "pts": 2},
]


@pytest.fixture()
def _gamelog_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_NBA_CACHE", str(tmp_path))
    pid, season = 999999, "2024-25"
    with open(tmp_path / f"gamelog_full_{pid}_{season}.json", "w", encoding="utf-8") as fh:
        json.dump(_DATA, fh)
    return pid, season


def test_legacy_off_is_lexicographic_wrong(_gamelog_dir, monkeypatch):
    monkeypatch.delenv("CV_GAMELOG_CHRONO_SORT", raising=False)
    pid, season = _gamelog_dir
    logs = fa._gamelogs_for_player(pid, season)
    # lexicographic ascending tail = "Oct 24, 2024" (pts 1) — the season START, the bug
    assert logs[-1]["pts"] == 1
    assert [g["pts"] for g in logs] == [5, 3, 4, 2, 1]  # Apr,Dec,Jan,Nov,Oct lexicographic


def test_fix_on_is_chronological(_gamelog_dir, monkeypatch):
    monkeypatch.setenv("CV_GAMELOG_CHRONO_SORT", "1")
    pid, season = _gamelog_dir
    logs = fa._gamelogs_for_player(pid, season)
    # true chronological tail = "Apr 13, 2025" (pts 5) — the actual most recent game
    assert logs[-1]["pts"] == 5
    assert [g["pts"] for g in logs] == [1, 2, 3, 4, 5]  # Oct->Nov->Dec->Jan->Apr


def test_iso_dates_also_sort_chronologically(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, "_NBA_CACHE", str(tmp_path))
    monkeypatch.setenv("CV_GAMELOG_CHRONO_SORT", "1")
    pid, season = 888888, "2024-25"
    iso = [{"game_date": "2025-01-05", "pts": 2}, {"game_date": "2024-10-24", "pts": 1}]
    with open(tmp_path / f"gamelog_full_{pid}_{season}.json", "w", encoding="utf-8") as fh:
        json.dump(iso, fh)
    logs = fa._gamelogs_for_player(pid, season)
    assert [g["pts"] for g in logs] == [1, 2]
