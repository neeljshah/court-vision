"""Per-file test for domains.basketball_nba.ingest_pbp_foul_states (no network)."""
from __future__ import annotations

from domains.basketball_nba import ingest_pbp_foul_states as M


def _payload():
    """Two periods of plays with attributable fouls; home id=H, away id=A."""
    header = {"competitions": [{"competitors": [
        {"homeAway": "home", "id": "H"}, {"homeAway": "away", "id": "A"}]}]}
    plays = [
        {"homeScore": 2, "awayScore": 0, "period": {"number": 1},
         "clock": {"displayValue": "11:00"}, "type": {"text": "Made Shot"}},
        {"homeScore": 2, "awayScore": 0, "period": {"number": 1},
         "clock": {"displayValue": "10:00"}, "type": {"text": "Shooting Foul"},
         "team": {"id": "A"}},
        {"homeScore": 2, "awayScore": 0, "period": {"number": 1},
         "clock": {"displayValue": "09:00"}, "type": {"text": "Personal Foul"},
         "team": {"id": "A"}},
        {"homeScore": 5, "awayScore": 4, "period": {"number": 2},
         "clock": {"displayValue": "06:00"}, "type": {"text": "Loose Ball Foul"},
         "team": {"id": "H"}},
        {"homeScore": 9, "awayScore": 4, "period": {"number": 4},
         "clock": {"displayValue": "00:01"}, "type": {"text": "Made Shot"}},
    ]
    return {"header": header, "plays": plays}


def test_home_away_ids():
    assert M.home_away_ids(_payload()) == ("H", "A")


def test_foul_trajectory_cumulative_and_leakfree():
    traj = M.parse_foul_trajectory(_payload())
    # sorted by DECREASING seconds_remaining (chronological)
    srs = [r["seconds_remaining"] for r in traj]
    assert srs == sorted(srs, reverse=True)
    last = traj[-1]
    # away committed 2 fouls, home committed 1 over the game
    assert last["away_fouls"] == 2 and last["home_fouls"] == 1
    # cumulative is monotone non-decreasing in chronological order
    assert all(b["home_fouls"] >= a["home_fouls"]
               for a, b in zip(traj, traj[1:]))
    assert all(b["away_fouls"] >= a["away_fouls"]
               for a, b in zip(traj, traj[1:]))


def test_unattributed_foul_dropped():
    p = _payload()
    p["plays"].append({"homeScore": 9, "awayScore": 4, "period": {"number": 4},
                       "clock": {"displayValue": "00:01"},
                       "type": {"text": "Technical Foul"}, "team": {"id": "ZZZ"}})
    traj = M.parse_foul_trajectory(p)
    # traj sorted by DECREASING sr, so the final cumulative state is the LAST entry
    assert traj[-1]["home_fouls"] + traj[-1]["away_fouls"] == 3  # unknown id not counted


def test_grid_states_schema_and_label():
    pay = _payload()
    states = M.fetch_game_states("evt1", "20251022", http_get=lambda url: pay)
    assert states, "should produce grid states"
    cols = {"event_id", "seconds_remaining", "home_margin", "home_fouls",
            "away_fouls", "foul_diff", "home_win", "home_final", "away_final"}
    assert cols <= set(states[0])
    # home won (9 > 4)
    assert all(s["home_win"] == 1 for s in states)
    # foul_diff = away - home, and foul state never decreases across the grid
    fd = [s["away_fouls"] - s["home_fouls"] for s in states]
    assert all(s["foul_diff"] == s["away_fouls"] - s["home_fouls"] for s in states)
    tot = [s["home_fouls"] + s["away_fouls"] for s in states]
    assert tot == sorted(tot)  # cumulative non-decreasing through the game


def test_tie_game_dropped():
    pay = _payload()
    pay["plays"][-1] = {"homeScore": 4, "awayScore": 4, "period": {"number": 4},
                        "clock": {"displayValue": "00:01"}, "type": {"text": "Made Shot"}}
    assert M.fetch_game_states("evt2", "20251022", http_get=lambda url: pay) == []
