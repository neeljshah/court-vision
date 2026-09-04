"""Fixture-level reproduction of S282's fixed four-way namespace chain."""


def _fixed_four_way_census(checkpoint_game_ids, bridge_rows, foul_game_ids):
    """Classify each checkpoint game using S282's unmodified join chain."""
    bridge_by_event = {}
    for event_id, game_id in bridge_rows:
        bridge_by_event.setdefault(event_id, set()).add(game_id)

    result = {}
    for checkpoint_game_id in sorted(set(checkpoint_game_ids)):
        nba_game_ids = bridge_by_event.get(checkpoint_game_id, set())
        if not nba_game_ids:
            result[checkpoint_game_id] = ("NAMED-EXCLUDED", "NO_BRIDGE_EVENT_ID")
        elif len(nba_game_ids) != 1:
            result[checkpoint_game_id] = (
                "NAMED-EXCLUDED",
                "NON_UNIQUE_BRIDGE_EVENT_ID",
            )
        elif not next(iter(nba_game_ids)):
            result[checkpoint_game_id] = (
                "NAMED-EXCLUDED",
                "MISSING_BRIDGE_GAME_ID",
            )
        elif next(iter(nba_game_ids)) not in foul_game_ids:
            result[checkpoint_game_id] = (
                "NAMED-EXCLUDED",
                "NO_FOUL_STATE_GAME_ID",
            )
        else:
            result[checkpoint_game_id] = ("JOINED", "")
    return result


def test_s282_four_way_chain_fixture_has_three_complete_games_and_one_break_per_link():
    """Keep the fixed chain from being widened to inflate the cluster count."""
    census = _fixed_four_way_census(
        checkpoint_game_ids=[
            "401001",
            "401002",
            "401003",
            "401004",
            "401005",
            "401006",
        ],
        bridge_rows=[
            ("401001", "002001"),
            ("401002", "002002"),
            ("401003", "002003"),
            ("401005", ""),
            ("401006", "002006"),
        ],
        foul_game_ids={"002001", "002002", "002003", "002005"},
    )

    assert sum(status == "JOINED" for status, _ in census.values()) == 3
    assert census["401004"] == ("NAMED-EXCLUDED", "NO_BRIDGE_EVENT_ID")
    assert census["401005"] == (
        "NAMED-EXCLUDED",
        "MISSING_BRIDGE_GAME_ID",
    )
    assert census["401006"] == ("NAMED-EXCLUDED", "NO_FOUL_STATE_GAME_ID")
