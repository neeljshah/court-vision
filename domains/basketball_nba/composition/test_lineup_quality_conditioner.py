"""Per-file test: as-of no-leak (a current-season profile value must NEVER
enter its own season's stints), composition math, segmenter game-state, and
season split. Synthetic frames only; no disk corpora touched.
Run: python -m pytest domains/basketball_nba/composition/test_lineup_quality_conditioner.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.composition import lineup_quality_conditioner as m


def _profiles(tmp_path):
    """Player 100 is elite ONLY in season_2025_26; league-average in
    season_2024_25. If its 2025-26 value leaked into a 2025-26 stint frame,
    load_player_composite('season_2024_25') would return a large composite."""
    rows = []
    for wid, val100 in [("season_2024_25", 0.0), ("season_2025_26", 999.0)]:
        for pid, val in [(100, val100), (101, 0.0), (102, 0.0), (103, 0.0), (104, 0.0),
                         (200, 0.0), (201, 0.0), (202, 0.0), (203, 0.0), (204, 0.0)]:
            for attr, _ in m.BASKET:
                rows.append({"entity_id": pid, "window": wid, "attribute": attr, "raw_value": val})
        # give a spread so std>0 in season_2024_25 (else z is dropped)
        rows.append({"entity_id": 900, "window": wid, "attribute": "gravity", "raw_value": 5.0})
        rows.append({"entity_id": 901, "window": wid, "attribute": "gravity", "raw_value": -5.0})
    p = tmp_path / "players.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def _teams(tmp_path):
    rows = []
    for wid in ["season_2024_25", "season_2025_26"]:
        for tid, nr in [(1, 5.0), (2, -5.0)]:
            for attr in ["net_rating_home", "net_rating_away"]:
                rows.append({"entity_id": tid, "window": wid, "attribute": attr, "raw_value": nr})
    p = tmp_path / "teams.parquet"
    pd.DataFrame(rows).to_parquet(p)
    return p


def _stints():
    # one game, one period: team1 lineup {100..104} vs team2 lineup {200..204}
    return pd.DataFrame([
        {"game_id": "G1", "team_id": 1, "period": 1, "lineup_key": "100,101,102,103,104",
         "n_on_court": 5, "start_s": 0.0, "end_s": 120.0, "elapsed_s": 120.0, "pts_for": 6, "pts_against": 4},
        {"game_id": "G1", "team_id": 2, "period": 1, "lineup_key": "200,201,202,203,204",
         "n_on_court": 5, "start_s": 0.0, "end_s": 120.0, "elapsed_s": 120.0, "pts_for": 4, "pts_against": 6},
    ])


def test_asof_no_leak(tmp_path):
    pp = _profiles(tmp_path)
    # prior window for 2025-26 is season_2024_25 -> player 100 must be ~neutral (0),
    # NOT its 999 value from season_2025_26. That would be same-season leak.
    comp, _ = m.load_player_composite("season_2024_25", pp)
    assert abs(comp.get(100, 0.0)) < 1e-6, "current-season value leaked into as-of composite"
    # sanity: the 2025-26 window DOES see the elite value (proves the fixture is real)
    comp26, _ = m.load_player_composite("season_2025_26", pp)
    assert comp26.get(100, 0.0) > 1.0


def test_prior_window_map():
    assert m.PRIOR_WINDOW["2025_26"] == "season_2024_25"
    assert m.PRIOR_WINDOW["2024_25"] == "season_2023_24"
    assert m.PRIOR_WINDOW["2023_24"] is None  # excluded, documented


def test_excluded_season_returns_none(tmp_path):
    assert m.build_frame("2023_24", stints_df=_stints(),
                         player_path=_profiles(tmp_path), team_path=_teams(tmp_path)) is None


def test_composition_math():
    # lineup composite = sum of member composites; missing player -> 0 (neutral)
    comp = {100: 2.0, 101: -1.0, 999: 100.0}
    assert m._lineup_comp("100,101,555", comp) == 1.0  # 2 + (-1) + 0(missing)


def test_segmenter_gamestate():
    seg = m.build_segments(_stints())
    assert len(seg) == 1
    r = seg.iloc[0]
    assert r["overlap_s"] == 120.0
    assert r["score_margin_start"] == 0.0          # first segment of game
    assert r["time_remaining"] == 720.0            # measured at segment start (abs_start=0)


def test_build_frame_composite_diff(tmp_path):
    seg = m.build_frame("2025_26", stints_df=_stints(),
                        player_path=_profiles(tmp_path), team_path=_teams(tmp_path))
    assert seg is not None and len(seg) == 1
    # all conditioning players are neutral in the prior (2024-25) window -> diff ~0
    assert abs(seg.iloc[0]["composite_diff"]) < 1e-6
    assert seg.iloc[0]["strength_diff"] == 10.0    # team1(+5) - team2(-5), prior window
