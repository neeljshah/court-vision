"""Per-file test for build_formation_lineups_full.py -- runs the REAL builder
against a small real slice (30 matches) of the on-disk statsbomb corpus, plus
unit checks on formation formatting / home-away resolution with synthetic
data. Skips if the real corpus isn't present on this box (CI-safe).
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_build_formation_lineups_full.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from domains.soccer import build_formation_lineups_full as m

_HAVE_CORPUS = m._META_PATH.exists() and m._EVENTS_DIR.exists()


@pytest.mark.skipif(not _HAVE_CORPUS, reason="statsbomb full-pull corpus not present on this box")
def test_small_real_slice_produces_lineup_rows(tmp_path):
    meta = pd.read_parquet(m._META_PATH)
    cached = {p.stem for p in m._EVENTS_DIR.glob("*.json")}
    slice_ids = [int(mid) for mid in meta["match_id"] if str(mid) in cached][:30]
    assert len(slice_ids) >= 20, "expected >=20 real matches with cached events for the slice"

    out_path = tmp_path / "formation_lineups_full.parquet"
    progress_path = tmp_path / "progress.json"
    cov = m.build(out_path=out_path, progress_path=progress_path, match_ids=slice_ids)

    assert cov["matches_processed_this_run"] == len(slice_ids)
    assert cov["stopped_reason"] is None
    assert out_path.exists()
    df = pd.read_parquet(out_path)
    assert len(df) > 0
    assert set(["match_id", "match_date", "competition", "team_id", "team_name", "is_home",
                "formation", "player_id", "player_name", "jersey_number",
                "position_id", "position_name"]).issubset(df.columns)
    # every match with rows should have exactly one home + one away lineup
    per_match_sides = df.groupby("match_id")["is_home"].agg(lambda s: sorted(s.unique().tolist()))
    assert (per_match_sides.apply(lambda v: v == [0, 1])).all()
    # formation is a bare int reformatted with dashes, e.g. "4-4-2"
    assert df["formation"].str.match(r"^\d(-\d)+$").all()

    # re-run with the same slice -- resumable, zero new rows processed
    cov2 = m.build(out_path=out_path, progress_path=progress_path, match_ids=slice_ids)
    assert cov2["matches_processed_this_run"] == 0
    assert cov2["lineup_rows_total"] == cov["lineup_rows_total"]


def test_fmt_formation():
    assert m._fmt_formation(442) == "4-4-2"
    assert m._fmt_formation(4231) == "4-2-3-1"


def _starting_xi_event(team_id, team_name, formation):
    return {
        "type": {"name": "Starting XI"}, "team": {"id": team_id, "name": team_name},
        "tactics": {"formation": formation, "lineup": [
            {"player": {"id": 1, "name": "P One"}, "position": {"id": 1, "name": "Goalkeeper"}, "jersey_number": 1},
            {"player": {"id": 2, "name": "P Two"}, "position": {"id": 2, "name": "Right Back"}, "jersey_number": 2},
        ]},
    }


def test_match_lineups_resolves_home_away_by_name(tmp_path):
    events = [
        _starting_xi_event(10, "Home FC", 442),
        _starting_xi_event(20, "Away FC", 433),
    ]
    ev_path = tmp_path / "1.json"
    ev_path.write_text(json.dumps(events), encoding="utf-8")
    meta_row = {"match_date": "2020-01-01", "competition": "test", "home_team": "Home FC", "away_team": "Away FC"}
    rows = m._match_lineups(1, meta_row, ev_path)
    assert len(rows) == 4
    home_rows = [r for r in rows if r["is_home"] == 1]
    away_rows = [r for r in rows if r["is_home"] == 0]
    assert len(home_rows) == 2 and len(away_rows) == 2
    assert home_rows[0]["formation"] == "4-4-2"
    assert away_rows[0]["formation"] == "4-3-3"


def test_match_lineups_skips_unresolved_team_name(tmp_path):
    # team.name doesn't match either meta side -> that side's rows are dropped, not guessed
    events = [_starting_xi_event(10, "Unknown FC", 442), _starting_xi_event(20, "Away FC", 433)]
    ev_path = tmp_path / "1.json"
    ev_path.write_text(json.dumps(events), encoding="utf-8")
    meta_row = {"match_date": "2020-01-01", "competition": "test", "home_team": "Home FC", "away_team": "Away FC"}
    rows = m._match_lineups(1, meta_row, ev_path)
    assert len(rows) == 2
    assert all(r["is_home"] == 0 for r in rows)
