"""Per-file test for the S84 NBA lineup-at-tick screen (tick-time as-of guard + coverage)."""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.eval_gate import s84_nba_lineup_at_tick as S


def _sub(elapsed, team, player, side, order=0):
    return {"elapsed": float(elapsed), "order": order, "team": team, "player": player,
            "kind": "substitution", "sub": side}


def test_clock_and_elapsed():
    assert S.parse_clock("PT7M2.00S") == pytest.approx(422.0)
    assert S.parse_clock("PT00M00.00S") == pytest.approx(0.0)
    assert S.parse_clock("nonsense") == -1.0
    assert S.elapsed_of(1, 720.0) == pytest.approx(0.0)
    assert S.elapsed_of(2, 360.0) == pytest.approx(1080.0)
    assert S.elapsed_of(5, 300.0) == pytest.approx(2880.0)   # OT tips at 48:00


def test_guard_raises_on_same_tick_and_later_events():
    tick = 600.0
    with pytest.raises(S.AsOfViolation):
        S.assert_strictly_before([_sub(tick, "ATL", 1, "in")], tick, "same tick")
    with pytest.raises(S.AsOfViolation):
        S.assert_strictly_before([_sub(tick + 1.0, "ATL", 1, "in")], tick, "later")
    S.assert_strictly_before([_sub(tick - 0.1, "ATL", 1, "in")], tick, "before")   # no raise


def test_lineup_at_ignores_a_substitution_on_the_tick_itself():
    starters = {"ATL": frozenset({1, 2, 3, 4, 5}), "BOS": frozenset({6, 7, 8, 9, 10})}
    subs = [_sub(300.0, "ATL", 5, "out", 0), _sub(300.0, "ATL", 11, "in", 1),
            _sub(600.0, "BOS", 10, "out", 2), _sub(600.0, "BOS", 12, "in", 3)]
    early = S.lineup_at(subs, starters, 600.0)
    assert early["ATL"] == frozenset({1, 2, 3, 4, 11})       # 300s sub applied
    assert early["BOS"] == frozenset({6, 7, 8, 9, 10})       # 600s sub is NOT (same tick)
    late = S.lineup_at(subs, starters, 600.1)
    assert late["BOS"] == frozenset({6, 7, 8, 9, 12})
    assert all(len(v) == 5 for v in late.values())


def test_starters_inferred_from_first_appearance(tmp_path):
    """A player whose first action is a non-sub, or a sub he leaves on, was on the floor."""
    actions = []
    for i, pid in enumerate([1, 2, 3, 4, 5]):
        actions.append({"clock": "PT11M%02d.00S" % (59 - i), "period": 1, "teamTricode": "ATL",
                        "actionType": "2pt", "subType": "", "personId": pid})
    for i, pid in enumerate([6, 7, 8, 9]):
        actions.append({"clock": "PT10M%02d.00S" % (59 - i), "period": 1, "teamTricode": "BOS",
                        "actionType": "3pt", "subType": "", "personId": pid})
    # BOS starter 10 never records an action -- he is only ever substituted OUT.
    actions.append({"clock": "PT08M00.00S", "period": 1, "teamTricode": "BOS",
                    "actionType": "substitution", "subType": "out", "personId": 10})
    actions.append({"clock": "PT08M00.00S", "period": 1, "teamTricode": "BOS",
                    "actionType": "substitution", "subType": "in", "personId": 11})
    path = tmp_path / "0022400001.json"
    path.write_text(json.dumps({"game": {"gameId": "0022400001", "actions": actions}}),
                    encoding="ascii")
    subs, starters = S.game_events(str(path))
    assert starters == {"ATL": frozenset({1, 2, 3, 4, 5}), "BOS": frozenset({6, 7, 8, 9, 10})}
    assert len(subs) == 2
    floor = S.lineup_at(subs, starters, S.elapsed_of(1, 0.0))
    assert floor["BOS"] == frozenset({6, 7, 8, 9, 11})       # 10 out, 11 in
