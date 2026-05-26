"""tests/test_R31_X6_lineup_backfill.py — R31_X6 backfill suite.

Verifies that scripts/backfill_lineups_2025_26.py:
  1. Writes a syntactically-valid lineup JSON file per team.
  2. Preserves the schema (lineup, minutes, net_rating, off_rating, ...).
  3. Is idempotent: a re-run with existing files leaves them untouched.
  4. Skips gracefully when a team has no API data.
  5. Sorts lineups by net_rating desc (matches the existing LAL/GSW files).
  6. Patch helper recomputes home/away_top_lineup_net_rtg in season_games.
  7. Probe reports n_teams_added correctly.
  8. _ALL_TEAMS list still has exactly 30 entries.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import backfill_lineups_2025_26 as bf  # noqa: E402
from scripts.improve_loop import probe_R31_X6_lineup_backfill as probe  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tmp_lineups_dir(monkeypatch, tmp_path):
    """Redirect the lineups directory to a temp folder for isolation."""
    d = tmp_path / "lineups"
    d.mkdir()
    monkeypatch.setattr(bf, "_LINEUPS_DIR", d)
    monkeypatch.setattr(probe, "_LINEUPS_DIR", d)
    return d


def _fake_lineup(net=10.0, mins=50.0, players=None):
    return {
        "lineup":     players or ["P. One", "P. Two", "P. Three", "P. Four", "P. Five"],
        "minutes":    mins,
        "net_rating": net,
        "off_rating": 110.0,
        "def_rating": 100.0,
        "pace":       100.0,
        "efg_pct":    0.55,
        "tov_pct":    0.13,
        "oreb_pct":   0.25,
        "ft_rate":    0.20,
        "plus_minus": 5.0,
    }


# --------------------------------------------------------------------------- #
# 1. Valid JSON written                                                        #
# --------------------------------------------------------------------------- #
def test_write_team_lineups_atomic_produces_valid_json(tmp_lineups_dir):
    rows = [_fake_lineup(net=15.0, mins=200.0),
            _fake_lineup(net=8.0,  mins=120.0)]
    out = bf.write_team_lineups_atomic("ATL", rows, season="2025-26")
    assert out.exists()
    with open(out, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert isinstance(loaded, list)
    assert len(loaded) == 2


# --------------------------------------------------------------------------- #
# 2. Schema preserved                                                          #
# --------------------------------------------------------------------------- #
def test_schema_matches_get_top_lineups_contract(tmp_lineups_dir):
    rows = [_fake_lineup()]
    out = bf.write_team_lineups_atomic("BOS", rows)
    with open(out, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    required = {"lineup", "minutes", "net_rating",
                "off_rating", "def_rating", "pace",
                "efg_pct", "tov_pct", "oreb_pct",
                "ft_rate", "plus_minus"}
    assert required.issubset(loaded[0].keys())
    assert isinstance(loaded[0]["lineup"], list)
    assert len(loaded[0]["lineup"]) == 5


# --------------------------------------------------------------------------- #
# 3. Sorted by net_rating desc                                                 #
# --------------------------------------------------------------------------- #
def test_lineups_sorted_by_net_rating_desc(tmp_lineups_dir):
    rows = [_fake_lineup(net=2.0), _fake_lineup(net=15.0), _fake_lineup(net=-3.0)]
    out = bf.write_team_lineups_atomic("CHA", rows)
    with open(out, "r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    ratings = [r["net_rating"] for r in loaded]
    assert ratings == sorted(ratings, reverse=True)
    assert ratings[0] == 15.0


# --------------------------------------------------------------------------- #
# 4. Top-N by minutes filtering                                                #
# --------------------------------------------------------------------------- #
def test_top_n_by_minutes_filters_and_caps():
    rows = [_fake_lineup(mins=10.0, net=20.0),
            _fake_lineup(mins=200.0, net=5.0),
            _fake_lineup(mins=150.0, net=2.0),
            _fake_lineup(mins=4.0,   net=99.0),
            _fake_lineup(mins=80.0,  net=1.0)]
    out = bf.top_n_by_minutes(rows, n=3, min_minutes=5.0)
    assert len(out) == 3                       # capped to N
    # All entries have minutes >= 5 (the mins=4 row was filtered)
    assert all(r["minutes"] >= 5.0 for r in out)
    # Sorted by minutes desc
    assert [r["minutes"] for r in out] == [200.0, 150.0, 80.0]


# --------------------------------------------------------------------------- #
# 5. Idempotency: pre-existing file is not overwritten when --force is false   #
# --------------------------------------------------------------------------- #
def test_missing_teams_reports_only_absent_teams(tmp_lineups_dir):
    bf.write_team_lineups_atomic("ATL", [_fake_lineup()])
    bf.write_team_lineups_atomic("BOS", [_fake_lineup()])
    missing = bf.missing_teams("2025-26")
    existing = bf.existing_teams("2025-26")
    assert "ATL" in existing
    assert "BOS" in existing
    assert "ATL" not in missing
    assert "BOS" not in missing
    assert "DET" in missing
    assert len(existing) + len(missing) == 30


def test_idempotent_existing_files_are_not_modified(tmp_lineups_dir, monkeypatch):
    # Seed an existing file
    seed_rows = [_fake_lineup(net=42.0, mins=300.0)]
    bf.write_team_lineups_atomic("ATL", seed_rows)
    seed_path = bf._team_file("ATL", "2025-26")
    seed_mtime = seed_path.stat().st_mtime

    # Make fetch_bulk return DIFFERENT data for ATL — if backfill respects
    # idempotency, this data should NOT overwrite the existing file.
    def fake_bulk(season="2025-26", min_minutes=5.0, top_n=10):
        return {"DET": [_fake_lineup(net=99.0, mins=99.0)]}

    monkeypatch.setattr(bf, "fetch_bulk", fake_bulk)
    summary = bf.run_backfill(season="2025-26", force=False, prefer_bulk=True)
    # ATL was already there — the backfill should NOT have touched it
    with open(seed_path, "r", encoding="utf-8") as fh:
        post = json.load(fh)
    assert post[0]["net_rating"] == 42.0
    assert summary["n_teams_added"] == 1   # only DET was added
    assert "DET" not in bf.missing_teams("2025-26")


# --------------------------------------------------------------------------- #
# 6. Empty bulk response on a target team is reported as api_error             #
# --------------------------------------------------------------------------- #
def test_missing_team_in_bulk_response_is_logged_not_crashed(
        tmp_lineups_dir, monkeypatch):
    def fake_bulk(season="2025-26", min_minutes=5.0, top_n=10):
        # Return only one team; the other 29 missing teams get logged
        return {"BOS": [_fake_lineup()]}

    monkeypatch.setattr(bf, "fetch_bulk", fake_bulk)
    summary = bf.run_backfill(season="2025-26", force=False, prefer_bulk=True)
    assert summary["n_teams_added"] == 1
    # All other targets should be listed as empty_bulk_response
    assert any("empty_bulk_response" in e for e in summary["api_errors"])
    # No crashes; missing teams stay missing
    assert len(bf.missing_teams("2025-26")) >= 28


# --------------------------------------------------------------------------- #
# 7. Patch season games regenerates top_lineup_net_rtg                         #
# --------------------------------------------------------------------------- #
def test_patch_season_games_overwrites_zeros(tmp_lineups_dir, tmp_path):
    # Seed a lineup file
    bf.write_team_lineups_atomic("LAL", [
        _fake_lineup(net=11.0, mins=200.0),
        _fake_lineup(net=3.0,  mins=400.0),
    ])
    bf.write_team_lineups_atomic("BOS", [
        _fake_lineup(net=7.5, mins=150.0),
    ])
    # Build a fake season_games payload with zeros
    fake_sg = tmp_path / "season_games_2025-26.json"
    payload = {
        "rows": [
            {"game_id": "g1", "home_team": "LAL", "away_team": "BOS",
             "home_top_lineup_net_rtg": 0.0, "away_top_lineup_net_rtg": 0.0},
            {"game_id": "g2", "home_team": "BOS", "away_team": "LAL",
             "home_top_lineup_net_rtg": 0.0, "away_top_lineup_net_rtg": 0.0},
        ]
    }
    fake_sg.write_text(json.dumps(payload), encoding="utf-8")
    res = bf.patch_season_games(season="2025-26", path=fake_sg)
    assert res["patched"] is True
    assert res["n_field_updates"] == 4   # 2 rows × 2 fields
    after = json.loads(fake_sg.read_text(encoding="utf-8"))
    # LAL's top lineup with >= 30 min is the higher of {11, 3} => 11.0
    assert after["rows"][0]["home_top_lineup_net_rtg"] == 11.0
    assert after["rows"][0]["away_top_lineup_net_rtg"] == 7.5
    # Idempotency: re-running yields zero field updates
    res2 = bf.patch_season_games(season="2025-26", path=fake_sg)
    assert res2["n_field_updates"] == 0


# --------------------------------------------------------------------------- #
# 8. Probe reports n_teams_added                                               #
# --------------------------------------------------------------------------- #
def test_probe_run_summary_shape(tmp_lineups_dir):
    # Start with 2 teams cached
    bf.write_team_lineups_atomic("LAL", [_fake_lineup()])
    bf.write_team_lineups_atomic("GSW", [_fake_lineup()])
    summary = probe.run(pre_teams=["LAL", "GSW"])
    assert summary["n_teams_with_data_before"] == 2
    assert summary["n_teams_with_data_after"] == 2  # no new files in test
    assert summary["n_teams_added"] == 0
    assert "verdict" in summary

    # Now add 28 more teams and assert delta is 28
    for t in bf._ALL_TEAMS:
        if t in ("LAL", "GSW"):
            continue
        bf.write_team_lineups_atomic(t, [_fake_lineup()])
    summary2 = probe.run(pre_teams=["LAL", "GSW"])
    assert summary2["n_teams_with_data_after"] == 30
    assert summary2["n_teams_added"] == 28
    assert summary2["ship_teams_ok"] is True


# --------------------------------------------------------------------------- #
# 9. _ALL_TEAMS stays at 30 (catches typo regressions)                         #
# --------------------------------------------------------------------------- #
def test_all_teams_list_has_exactly_30_entries():
    assert len(bf._ALL_TEAMS) == 30
    assert len(set(bf._ALL_TEAMS)) == 30   # no duplicates
    # All look like 3-letter abbreviations
    assert all(len(t) == 3 and t.isupper() for t in bf._ALL_TEAMS)


# --------------------------------------------------------------------------- #
# 10. classify integrates with existing lineup_data.get_top_lineups            #
# --------------------------------------------------------------------------- #
def test_files_consumable_by_lineup_data_get_top_lineups(tmp_lineups_dir,
                                                          monkeypatch):
    """The files we write must be readable by the legacy
    src.data.lineup_data.get_top_lineups so historical code paths keep
    working."""
    # Seed an ATL file with a clear winner
    bf.write_team_lineups_atomic("ATL", [
        _fake_lineup(net=12.0, mins=100.0,
                     players=["A. A", "B. B", "C. C", "D. D", "E. E"]),
        _fake_lineup(net=4.0, mins=60.0,
                     players=["F. F", "G. G", "H. H", "I. I", "J. J"]),
    ])
    # Point lineup_data's cache dir at our temp dir
    from src.data import lineup_data as ld
    monkeypatch.setattr(ld, "_CACHE_DIR", str(tmp_lineups_dir))
    top = ld.get_top_lineups("ATL", "2025-26", n=1, min_minutes=30.0)
    assert len(top) == 1
    assert top[0]["net_rating"] == 12.0
