"""Per-file test for claims_formation.py -- synthetic match lookup + event
files, hand-computed formation-pairing math, edge_claimed=False, n-floor.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_claims_formation.py -q
"""
from __future__ import annotations

import json

from domains.soccer import claims_formation as cf


def _write_event_file(tmp_path, match_id: int, home_id: int, away_id: int,
                       home_formation: int, away_formation: int):
    events = [
        {"type": {"name": "Starting XI"}, "team": {"id": home_id}, "tactics": {"formation": home_formation}},
        {"type": {"name": "Starting XI"}, "team": {"id": away_id}, "tactics": {"formation": away_formation}},
        {"type": {"name": "Pass"}, "team": {"id": home_id}},  # non-Starting-XI noise, must be ignored
    ]
    (tmp_path / f"{match_id}.json").write_text(json.dumps(events), encoding="utf-8")


def _lookup_entry(home_id, away_id, home_score, away_score):
    return {
        "home_team": {"home_team_id": home_id}, "away_team": {"away_team_id": away_id},
        "home_score": home_score, "away_score": away_score, "match_date": "2020-01-01",
    }


def test_fmt_formation():
    assert cf._fmt_formation(4231) == "4-2-3-1"
    assert cf._fmt_formation(433) == "4-3-3"


def test_pairing_hand_computed_wins_draws_goals(tmp_path):
    # 3 matches of pairing 4-3-3 (home) vs 4-4-2 (away): 2 home wins, 1 draw
    lookup = {
        1: _lookup_entry(10, 20, 2, 0),  # home win, total goals 2
        2: _lookup_entry(10, 20, 1, 0),  # home win, total goals 1
        3: _lookup_entry(10, 20, 1, 1),  # draw, total goals 2
    }
    for mid, meta in lookup.items():
        _write_event_file(tmp_path, mid, meta["home_team"]["home_team_id"],
                           meta["away_team"]["away_team_id"], 433, 442)

    source = cf.build_source(match_lookup=lookup, events_dir=tmp_path)
    assert len(source) == 3
    assert set(source["pairing"]) == {"4-3-3_vs_4-4-2"}

    ranking, n_considered, n_excluded = cf._rank(source, "is_home_win")
    assert n_considered == 1
    assert n_excluded == 1  # n=3 < MIN_N=10, excluded
    assert ranking == []  # below floor -> nothing ranked

    draw_ranking, _, _ = cf._rank(source, "is_draw")
    # verify math directly on the source (not gated by the demo's floor)
    assert source["is_home_win"].mean() == 2 / 3
    assert source["is_draw"].mean() == 1 / 3
    assert source["total_goals"].mean() == (2 + 1 + 2) / 3


def test_n_floor_ranks_only_pairings_with_enough_matches(tmp_path):
    lookup = {}
    for i in range(cf.MIN_N):  # exactly MIN_N matches of one pairing -> clears the floor
        lookup[i] = _lookup_entry(10, 20, 1, 0)
        _write_event_file(tmp_path, i, 10, 20, 433, 442)
    # one lone match of a different pairing -> stays below the floor
    lookup[100] = _lookup_entry(10, 20, 0, 0)
    _write_event_file(tmp_path, 100, 10, 20, 4231, 352)

    source = cf.build_source(match_lookup=lookup, events_dir=tmp_path)
    ranking, n_considered, n_excluded = cf._rank(source, "is_home_win")
    assert n_considered == 2
    assert n_excluded == 1
    assert len(ranking) == 1
    assert ranking[0]["pairing"] == "4-3-3_vs_4-4-2"
    assert ranking[0]["n"] == cf.MIN_N


def test_edge_claimed_false_on_every_claim(tmp_path):
    lookup = {i: _lookup_entry(10, 20, 1, 0) for i in range(cf.MIN_N)}
    for i in range(cf.MIN_N):
        _write_event_file(tmp_path, i, 10, 20, 433, 442)
    source = cf.build_source(match_lookup=lookup, events_dir=tmp_path)
    for col in ("is_home_win", "is_draw", "total_goals"):
        ranking, n_considered, n_excluded = cf._rank(source, col)
        claim = cf._claim(f"test_{col}", "q", col, col, tmp_path / "src.parquet",
                           ranking, n_considered, n_excluded)
        assert claim["edge_claimed"] is False
