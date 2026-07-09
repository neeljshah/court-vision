"""Per-file test: v2 basket is a strict superset of v1's (same signs), exact
score-track lookup matches the naive last-action final score, and the exact
segment split reproduces a hand-computed 2-team synthetic game (no
apportionment error). Synthetic fixtures + one tiny real-shaped pbp dict;
no disk corpora touched except via monkeypatched paths.
Run: python -m pytest domains/basketball_nba/composition/test_lineup_quality_conditioner_v2.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.composition import lineup_quality_conditioner as v1
from domains.basketball_nba.composition import lineup_quality_conditioner_v2 as m


def test_basket_is_superset_of_v1_same_signs():
    v1_map = dict(v1.BASKET)
    v2_map = dict(m.BASKET)
    assert len(m.BASKET) == len(v1.BASKET) + 13
    for attr, sign in v1_map.items():
        assert v2_map[attr] == sign, f"{attr} sign changed between v1 and v2"
    assert len(v2_map) == len(m.BASKET), "duplicate attribute in v2 basket"


def _synthetic_game_json():
    """One period, one game: HOU(home)=1 vs OKC=2. Home scores +2 then +3
    (score 0->2->5); away stays 0. Clocks PT12M00S, PT11M00S, PT10M00S
    (elapsed 0s, 60s, 120s)."""
    actions = [
        {"period": 1, "clock": "PT12M00.00S", "scoreHome": 0, "scoreAway": 0, "actionNumber": 1},
        {"period": 1, "clock": "PT11M00.00S", "scoreHome": 2, "scoreAway": 0, "actionNumber": 2, "teamId": 1, "teamTricode": "HOU"},
        {"period": 1, "clock": "PT10M00.00S", "scoreHome": 5, "scoreAway": 0, "actionNumber": 3, "teamId": 1, "teamTricode": "HOU"},
    ]
    return {"game": {"actions": actions}}


def test_score_track_and_score_at_abs():
    times, scores = m._load_game_score_track(_synthetic_game_json())
    assert times == [0.0, 60.0, 120.0]
    # query mid-segment (abs=90) -> state as of the last event at/before 90 -> (2,0)
    assert m._score_at_abs(times, scores, 90.0) == (2, 0)
    # query at the exact final event -> (5,0)
    assert m._score_at_abs(times, scores, 120.0) == (5, 0)
    # before any event -> (0,0)
    assert m._score_at_abs(times, scores, -1.0) == (0, 0)


def test_build_segments_exact_no_apportionment(tmp_path, monkeypatch):
    """Team A (home) subs once mid-segment; a proportional (v1-style)
    apportionment of a whole-stint pts_for would smear points evenly across
    time, but the exact reconstruction must place ALL of the +2 in the first
    30s slice (before the sub) and the +3 in the second (after)."""
    game_id = "G1"
    stints = pd.DataFrame([
        {"game_id": game_id, "team_id": 1, "period": 1, "lineup_key": "10,11,12,13,14",
         "n_on_court": 5, "start_s": 0.0, "end_s": 60.0, "elapsed_s": 60.0, "pts_for": 2, "pts_against": 0},
        {"game_id": game_id, "team_id": 1, "period": 1, "lineup_key": "10,11,12,13,99",
         "n_on_court": 5, "start_s": 60.0, "end_s": 120.0, "elapsed_s": 60.0, "pts_for": 3, "pts_against": 0},
        {"game_id": game_id, "team_id": 2, "period": 1, "lineup_key": "20,21,22,23,24",
         "n_on_court": 5, "start_s": 0.0, "end_s": 120.0, "elapsed_s": 120.0, "pts_for": 0, "pts_against": 5},
    ])
    games_df = pd.DataFrame([{"game_id": game_id, "home_team": "HOU"}])
    monkeypatch.setitem(m._PBP_DIRS, "2025_26", tmp_path)
    (tmp_path / f"{game_id}.json").write_text(
        __import__("json").dumps(_synthetic_game_json()), encoding="utf-8")

    seg = m.build_segments_exact(stints, "2025_26", games_df=games_df)
    assert len(seg) == 2
    first, second = seg.iloc[0], seg.iloc[1]
    assert first["pts_a"] == 2 and first["pts_b"] == 0
    assert second["pts_a"] == 3 and second["pts_b"] == 0
    assert first["net"] == 2 and second["score_margin_start"] == 2


def test_validate_attribution_match(tmp_path, monkeypatch):
    game_id = "G1"
    stints = pd.DataFrame([{"game_id": game_id, "team_id": 1, "period": 1}])
    monkeypatch.setitem(m._PBP_DIRS, "2025_26", tmp_path)
    (tmp_path / f"{game_id}.json").write_text(
        __import__("json").dumps(_synthetic_game_json()), encoding="utf-8")
    box = pd.DataFrame([
        {"game_id": game_id, "team": "HOU", "is_home": 1.0, "pts": 5},
        {"game_id": game_id, "team": "OKC", "is_home": 0.0, "pts": 0},
    ])
    box_path = tmp_path / "box.parquet"
    box.to_parquet(box_path)
    monkeypatch.setattr(m, "_BOX_SRC", box_path)
    result = m.validate_attribution("2025_26", stints_df=stints)
    assert result["n_checked"] == 1 and result["n_match"] == 1 and result["match_rate"] == 1.0
