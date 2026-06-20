"""Per-file test for domains.soccer.ingest_cardstate_states (no network: fake payload).

Covers the INCREMENT-3 gate contract: schema, leak-free red_diff step (0 before the card
minute, -/+1 after), drop-unattributable (never fabricate a side), and the second-yellow
red classification.
"""
from __future__ import annotations

from domains.soccer.ingest_cardstate_states import (
    build_card_states,
    card_events,
)


def _payload():
    return {
        "header": {"competitions": [{"competitors": [
            {"homeAway": "home", "team": {"id": "100"}},
            {"homeAway": "away", "team": {"id": "200"}},
        ]}]},
        "rosters": [
            {"team": {"id": "100"}, "roster": [
                {"athlete": {"displayName": "Home One"}},
                {"athlete": {"displayName": "Home Two"}},
            ]},
            {"team": {"id": "200"}, "roster": [
                {"athlete": {"displayName": "Away One"}},
            ]},
        ],
        "commentary": [
            # AWAY red card at min 40 -> red_diff = home_reds-away_reds = 0-1 = -1
            {"play": {"type": {"text": "Red Card"},
                      "clock": {"displayValue": "40'"},
                      "participants": [{"athlete": {"displayName": "Away One"}}]}},
            # HOME yellow at min 25
            {"play": {"type": {"text": "Yellow Card"},
                      "clock": {"displayValue": "25'"},
                      "participants": [{"athlete": {"displayName": "Home One"}}]}},
            # HOME substitution at min 60
            {"play": {"type": {"text": "Substitution"},
                      "clock": {"displayValue": "60'"},
                      "participants": [{"athlete": {"displayName": "Home Two"}}]}},
            # UNATTRIBUTABLE red card (taker not in either roster) -> DROPPED, never a side
            {"play": {"type": {"text": "Red Card"},
                      "clock": {"displayValue": "70'"},
                      "participants": [{"athlete": {"displayName": "Ghost X"}}]}},
            # non-card / non-shot -> ignored
            {"play": {"type": {"text": "Foul"},
                      "clock": {"displayValue": "20'"}}},
        ],
    }


def test_card_events_attribution_and_drop_unattributable():
    ev = card_events(_payload())
    kinds = sorted((round(m), sd, k) for m, sd, k, _ in ev)
    # away red @40, home yellow @25, home sub @60; ghost red @70 DROPPED, foul ignored
    assert kinds == [(25, "home", "yellow"), (40, "away", "red"), (60, "home", "sub")]
    # exactly ONE red survives (the ghost red is unattributable -> dropped)
    reds = [e for e in ev if e[2] == "red"]
    assert len(reds) == 1 and reds[0][1] == "away"


def test_red_diff_leakfree_step():
    ev = card_events(_payload())
    rows = build_card_states("EVT", ev)
    assert len(rows) == 19            # full 5-min grid
    bym = {r["asof_idx"]: r for r in rows}
    # away red @min40 (idx 8) -> red_diff (home-away) 0 for ticks<40, -1 for ticks>=40
    for idx in range(0, 8):           # minutes 0..35
        assert bym[idx]["red_diff"] == 0.0, f"leak: red_diff nonzero before card at idx {idx}"
    for idx in range(8, 19):          # minutes 40..90
        assert bym[idx]["red_diff"] == -1.0, f"red_diff should be -1 after away card at idx {idx}"
    # away got the red -> away_reds cumulative is 1 from idx 8, 0 before
    assert bym[7]["away_reds"] == 0 and bym[8]["away_reds"] == 1
    assert all(bym[i]["home_reds"] == 0 for i in range(19))


def test_yellow_and_sub_diffs_leakfree():
    rows = build_card_states("EVT", card_events(_payload()))
    bym = {r["asof_idx"]: r for r in rows}
    # home yellow @25 (idx 5): yellow_diff 0 before, +1 from idx 5
    assert bym[4]["yellow_diff"] == 0.0 and bym[5]["yellow_diff"] == 1.0
    # home sub @60 (idx 12): sub_count_diff 0 before, +1 from idx 12
    assert bym[11]["sub_count_diff"] == 0.0 and bym[12]["sub_count_diff"] == 1.0


def test_schema_columns_present():
    rows = build_card_states("EVT", card_events(_payload()))
    expect = {"game_id", "asof_idx", "red_diff", "yellow_diff", "sub_count_diff",
              "shot_zone_diff", "home_reds", "away_reds"}
    assert set(rows[0].keys()) == expect
    assert all(r["game_id"] == "EVT" for r in rows)


def test_second_yellow_counts_as_red():
    p = _payload()
    p["commentary"] = [
        {"play": {"type": {"text": "Second Yellow Card"},
                  "clock": {"displayValue": "55'"},
                  "participants": [{"athlete": {"displayName": "Home One"}}]}},
    ]
    ev = card_events(p)
    # a second-yellow sending-off is a RED (man-advantage), not a yellow
    assert len(ev) == 1 and ev[0][2] == "red" and ev[0][1] == "home"
    rows = build_card_states("EVT", ev)
    bym = {r["asof_idx"]: r for r in rows}
    # home sent off @55 (idx 11) -> red_diff = home_reds-away_reds = +1 from idx 11
    assert bym[10]["red_diff"] == 0.0 and bym[11]["red_diff"] == 1.0


def test_shot_zone_diff_from_fieldposition():
    p = _payload()
    p["commentary"] = [
        {"play": {"type": {"text": "Shot On Target"}, "fieldPositionX": 0.9,
                  "clock": {"displayValue": "30'"},
                  "participants": [{"athlete": {"displayName": "Home One"}}]}},
        {"play": {"type": {"text": "Shot Off Target"}, "fieldPositionX": 0.4,
                  "clock": {"displayValue": "50'"},
                  "participants": [{"athlete": {"displayName": "Away One"}}]}},
    ]
    rows = build_card_states("EVT", card_events(p))
    bym = {r["asof_idx"]: r for r in rows}
    # before any shot: 0
    assert bym[5]["shot_zone_diff"] == 0.0
    # after home shot (idx 6, min30): +0.9 ; after away shot (idx 10, min50): 0.9-0.4
    assert abs(bym[6]["shot_zone_diff"] - 0.9) < 1e-9
    assert abs(bym[10]["shot_zone_diff"] - 0.5) < 1e-9


def test_no_cards_yields_zero_diffs():
    p = _payload()
    p["commentary"] = [{"play": {"type": {"text": "Foul"},
                                 "clock": {"displayValue": "20'"}}}]
    ev = card_events(p)
    assert ev == []
    rows = build_card_states("EVT", ev)
    assert all(r["red_diff"] == 0.0 and r["yellow_diff"] == 0.0
               and r["sub_count_diff"] == 0.0 for r in rows)
