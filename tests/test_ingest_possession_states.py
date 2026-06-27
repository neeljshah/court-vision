"""Per-file test for domains.basketball_nba.ingest_possession_states (no network).

Asserts: (a) the FROZEN base schema + additive as-of detail cols are present;
(b) every detail column is leak-free / as-of-only (cumulative possessions monotone,
no *_final feature, pace divides by elapsed time); (c) the possession / scoring-run /
lead-change reconstruction is correct; (d) tie games are dropped.
"""
from __future__ import annotations

from domains.basketball_nba import ingest_possession_states as M


def _payload():
    """Home id 'H' wins 9-4. Plays: home scores twice (a 2-event run), away scores
    (flips lead, ends home run), away def rebound, a turnover, then home scores late.
    """
    plays = [
        # tip jump shot home makes -> home 2-0 (home run len 1); not a poss end on its own type text? scoringPlay True + 'shot'
        {"homeScore": 2, "awayScore": 0, "period": {"number": 1},
         "clock": {"displayValue": "11:00"}, "type": {"text": "Jump Shot"},
         "scoringPlay": True, "team": {"id": "H"}},
        {"homeScore": 4, "awayScore": 0, "period": {"number": 1},
         "clock": {"displayValue": "10:00"}, "type": {"text": "Layup Shot"},
         "scoringPlay": True, "team": {"id": "H"}},
        # away scores -> margin 4-2, lead stays home, but run flips to away len1
        {"homeScore": 4, "awayScore": 2, "period": {"number": 2},
         "clock": {"displayValue": "06:00"}, "type": {"text": "Jump Shot"},
         "scoringPlay": True, "team": {"id": "A"}},
        # away defensive rebound (possession-ending, no score change)
        {"homeScore": 4, "awayScore": 2, "period": {"number": 2},
         "clock": {"displayValue": "05:30"}, "type": {"text": "Defensive Rebound"},
         "scoringPlay": False, "team": {"id": "A"}},
        # home turnover (possession-ending)
        {"homeScore": 4, "awayScore": 2, "period": {"number": 3},
         "clock": {"displayValue": "04:00"}, "type": {"text": "Bad Pass Turnover"},
         "scoringPlay": False, "team": {"id": "H"}},
        {"homeScore": 9, "awayScore": 4, "period": {"number": 4},
         "clock": {"displayValue": "00:01"}, "type": {"text": "Made Shot"},
         "scoringPlay": True, "team": {"id": "H"}},
    ]
    return {"plays": plays}


def test_possession_trajectory_cumulative_and_leakfree():
    traj = M.parse_possession_trajectory(_payload())
    srs = [r["seconds_remaining"] for r in traj]
    assert srs == sorted(srs, reverse=True)  # DECREASING sr (chronological)
    # possessions_elapsed is cumulative non-decreasing in chronological order
    assert all(b["possessions_elapsed"] >= a["possessions_elapsed"]
               for a, b in zip(traj, traj[1:]))
    # 2 made FGs (home), away made FG, def rebound, turnover, late made FG = 6 poss ends
    assert traj[-1]["possessions_elapsed"] == 6


def test_scoring_run_sign_and_length():
    # traj is sorted DECREASING sr == chronological order top-to-bottom.
    chrono = M.parse_possession_trajectory(_payload())
    # after 2 home scores the run is +2 (home owns a 2-event run)
    assert chrono[1]["run_diff"] == 2.0
    # after away scores, the run flips to away len 1 -> -1
    assert chrono[2]["run_diff"] == -1.0


def test_grid_states_frozen_schema_and_additive_cols():
    states = M.fetch_game_states("evt1", "20251022", http_get=lambda url: _payload())
    assert states, "should produce grid states"
    frozen = {"game_id", "asof_idx", "state_diff", "frac_elapsed", "outcome"}
    additive = {"possessions_elapsed", "pace_so_far", "run_diff",
                "poss_since_lead_change"}
    assert frozen <= set(states[0])
    assert additive <= set(states[0])
    # home won 9-4
    assert all(s["outcome"] == 1 for s in states)
    # asof_idx is the per-game monotone grid index
    assert [s["asof_idx"] for s in states] == list(range(len(states)))
    # frac_elapsed in [0,1] and increases as the grid advances
    fracs = [s["frac_elapsed"] for s in states]
    assert all(0.0 <= f <= 1.0 for f in fracs)
    assert fracs == sorted(fracs)


def test_leakfree_no_final_on_per_tick_feature_and_pace_by_elapsed():
    states = M.fetch_game_states("evt1", "20251022", http_get=lambda url: _payload())
    # possessions_elapsed is cumulative non-decreasing across the as-of grid
    poss = [s["possessions_elapsed"] for s in states]
    assert poss == sorted(poss)
    # pace_so_far == possessions / elapsed-seconds (NEVER total game seconds) -- a
    # past-only rate. Reconstruct elapsed from frac_elapsed and verify.
    for s in states:
        elapsed = max(1.0, M._REG_SEC * s["frac_elapsed"])
        assert abs(s["pace_so_far"] - s["possessions_elapsed"] / elapsed) < 1e-6
    # no per-tick feature equals the final margin: state_diff is the as-of margin,
    # and the only *_final fields are diagnostics, never in the frozen feature set.
    assert "home_final" in states[0] and "away_final" in states[0]
    assert states[0]["state_diff"] != (states[0]["home_final"] - states[0]["away_final"])


def test_tie_game_dropped():
    pay = _payload()
    pay["plays"][-1] = {"homeScore": 4, "awayScore": 4, "period": {"number": 4},
                        "clock": {"displayValue": "00:01"}, "type": {"text": "Made Shot"},
                        "scoringPlay": True, "team": {"id": "H"}}
    assert M.fetch_game_states("evt2", "20251022", http_get=lambda url: pay) == []
