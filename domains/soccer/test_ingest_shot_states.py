"""Per-file test for domains.soccer.ingest_shot_states (no network: fake payload)."""
from __future__ import annotations

from domains.soccer.ingest_shot_states import (
    build_shot_states,
    shot_events,
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
            {"play": {"type": {"text": "Shot On Target"},
                      "clock": {"displayValue": "10'"},
                      "participants": [{"athlete": {"displayName": "Home One"}}]}},
            {"play": {"type": {"text": "Goal"},
                      "clock": {"displayValue": "45'+3'"},
                      "participants": [{"athlete": {"displayName": "Home Two"}}]}},
            {"play": {"type": {"text": "Shot Off Target"},
                      "clock": {"displayValue": "60'"},
                      "participants": [{"athlete": {"displayName": "Away One"}}]}},
            # unattributable (player not in roster) -> dropped
            {"play": {"type": {"text": "Shot Blocked"},
                      "clock": {"displayValue": "70'"},
                      "participants": [{"athlete": {"displayName": "Ghost X"}}]}},
            # non-shot -> ignored
            {"play": {"type": {"text": "Foul"},
                      "clock": {"displayValue": "20'"}}},
        ],
    }


def test_shot_events_attribution_and_filtering():
    ev = shot_events(_payload())
    # 2 home (10', 48') + 1 away (60'); ghost + foul dropped
    sides = sorted(s for _, s, _ in ev)
    assert sides == ["away", "home", "home"]
    minutes = sorted(m for m, _, _ in ev)
    assert minutes == [10.0, 48.0, 60.0]
    # weights: on-target/goal = 0.30, off-target = 0.05
    ks = sorted(round(k, 2) for _, _, k in ev)
    assert ks == [0.05, 0.30, 0.30]


def test_build_shot_states_leakfree_cumulative():
    ev = shot_events(_payload())
    rows = build_shot_states("EVT", ev)
    assert len(rows) == 19            # full 5-min grid
    bym = {r["asof_idx"]: r for r in rows}
    # minute 5 (idx 1): no shots yet
    assert bym[1]["home_shots"] == 0 and bym[1]["away_shots"] == 0
    # minute 10 (idx 2): one home shot
    assert bym[2]["home_shots"] == 1 and bym[2]["away_shots"] == 0
    assert bym[2]["shot_diff"] == 1.0
    # minute 50 (idx 10): two home (10',48'), zero away
    assert bym[10]["home_shots"] == 2 and bym[10]["shot_diff"] == 2.0
    # minute 60 (idx 12): two home, one away -> diff 1
    assert bym[12]["away_shots"] == 1 and bym[12]["shot_diff"] == 1.0
    # xgproxy_diff at end = 0.30+0.30 (home) - 0.05 (away) = 0.55
    assert abs(bym[18]["xgproxy_diff"] - 0.55) < 1e-9
    # monotone non-decreasing cumulative counts (leak-free step)
    hs = [bym[i]["home_shots"] for i in range(19)]
    assert hs == sorted(hs)


def test_no_shots_yields_zero_rows():
    p = _payload()
    p["commentary"] = [{"play": {"type": {"text": "Foul"},
                                 "clock": {"displayValue": "20'"}}}]
    ev = shot_events(p)
    assert ev == []
    rows = build_shot_states("EVT", ev)
    assert all(r["home_shots"] == 0 and r["away_shots"] == 0 for r in rows)
