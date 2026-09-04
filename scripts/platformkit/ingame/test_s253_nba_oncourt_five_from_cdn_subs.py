"""Focused construct checks for the S253 CDN on-court-five reconstruction."""
from scripts.platformkit.ingame import nba_oncourt_five_from_cdn_subs as s253


def _boxscore():
    return {"game": {
        "homeTeam": {"teamId": 1, "players": [
            {"personId": player, "starter": "1"} for player in range(1, 6)
        ]},
        "awayTeam": {"teamId": 2, "players": [
            {"personId": player, "starter": "1"} for player in range(11, 16)
        ]},
    }}


def _action(team_id, person_id, sub_type, order):
    return {
        "actionType": "substitution", "teamId": team_id, "personId": person_id,
        "subType": sub_type, "timeActual": "2026-01-01T00:00:%02dZ" % order,
        "period": 1, "clock": "PT05M00.00S", "orderNumber": order,
    }


def test_replay_emits_complete_atomic_substitution_stamps():
    actions = [
        _action(1, 1, "out", 1), _action(1, 6, "in", 1),
        _action(2, 11, "out", 1), _action(2, 16, "in", 1),
    ]
    rows = s253.replay_game(_boxscore(), {"game": {"actions": actions}}, "game-1")
    assert len(rows) == 2
    assert rows[0]["tick_kind"] == "opening"
    assert rows[1]["tick_kind"] == "substitution"
    assert {rows[1]["home_player_%d" % index] for index in range(1, 6)} == {"2", "3", "4", "5", "6"}
    assert {rows[1]["away_player_%d" % index] for index in range(1, 6)} == {"12", "13", "14", "15", "16"}


def test_replay_rejects_in_out_imbalance_before_emitting_a_bad_tick():
    actions = [_action(1, 1, "out", 1)]
    try:
        s253.replay_game(_boxscore(), {"game": {"actions": actions}}, "game-1")
    except ValueError as error:
        assert str(error) == "substitution_in_out_imbalance"
    else:
        raise AssertionError("expected imbalance rejection")


def test_elapsed_seconds_handles_regulation_and_overtime_clocks():
    assert s253._elapsed_seconds(1, "PT10M00.00S") == 0.0
    assert s253._elapsed_seconds(4, "PT00M00.00S") == 2400.0
    assert s253._elapsed_seconds(5, "PT05M00.00S") == 2400.0
    assert s253._elapsed_seconds(5, "PT00M00.00S") == 2700.0
