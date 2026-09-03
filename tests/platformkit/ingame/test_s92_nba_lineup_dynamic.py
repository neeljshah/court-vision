"""Per-file test for the S92 non-static NBA lineup terms (as-of guard, stints, history)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s84_nba_lineup_at_tick as S84
from scripts.platformkit.eval_gate import s92_nba_lineup_dynamic as S
from scripts.platformkit.eval_gate import s92_unit_ledger as L

HOME, AWAY = "ATL", "BOS"
STARTERS = {HOME: frozenset({1, 2, 3, 4, 5}), AWAY: frozenset({6, 7, 8, 9, 10})}


def _sub(elapsed, team, player, side, order=0):
    return {"elapsed": float(elapsed), "order": order, "team": team, "player": player,
            "kind": "substitution", "sub": side}


SUBS = [_sub(300.0, HOME, 5, "out", 0), _sub(300.0, HOME, 11, "in", 1),
        _sub(600.0, AWAY, 10, "out", 2), _sub(600.0, AWAY, 12, "in", 3)]


def _clock(elapsed):
    """Seconds elapsed in period 1 -> the feed's PT<M>M<S>S remaining-clock string."""
    remaining = 720.0 - elapsed
    return "PT%02dM%05.2fS" % (int(remaining // 60), remaining % 60)


def _game_json(tmp_path, name="0022400001"):
    """A synthetic one-period game: ten starters act, then ATL swaps 5 for 11 at 120s."""
    acts = []
    for i, pid in enumerate([1, 2, 3, 4, 5]):
        acts.append({"clock": _clock(1.0 + i), "period": 1, "teamTricode": HOME,
                     "actionType": "2pt", "subType": "", "personId": pid,
                     "scoreHome": 0, "scoreAway": 0})
    for i, pid in enumerate([6, 7, 8, 9, 10]):
        acts.append({"clock": _clock(10.0 + i), "period": 1, "teamTricode": AWAY,
                     "actionType": "2pt", "subType": "", "personId": pid,
                     "scoreHome": 0, "scoreAway": 0})
    acts.append({"clock": _clock(60.0), "period": 1, "teamTricode": HOME, "actionType": "3pt",
                 "subType": "", "personId": 1, "scoreHome": 5, "scoreAway": 0})
    for pid, side in ((5, "out"), (11, "in")):
        acts.append({"clock": _clock(120.0), "period": 1, "teamTricode": HOME,
                     "actionType": "substitution", "subType": side, "personId": pid,
                     "scoreHome": 5, "scoreAway": 0})
    acts.append({"clock": _clock(720.0), "period": 1, "teamTricode": AWAY, "actionType": "2pt",
                 "subType": "", "personId": 6, "scoreHome": 10, "scoreAway": 3})
    path = tmp_path / ("%s.json" % name)
    path.write_text(json.dumps({"game": {"gameId": name, "actions": acts}}), encoding="ascii")
    return str(path)


def test_minutes_so_far_is_as_of_and_a_later_sub_cannot_move_an_earlier_tick():
    """THE guard: appending a substitution AFTER the tick leaves that tick's feature identical."""
    at600 = S.minutes_so_far(SUBS, STARTERS, 600.0)
    assert at600[1] == pytest.approx(600.0) and at600[5] == pytest.approx(300.0)
    assert at600[11] == pytest.approx(300.0)          # entered at 300s
    assert at600[10] == pytest.approx(600.0)          # his 600s exit is NOT applied (same tick)
    assert 12 not in at600
    later = SUBS + [_sub(900.0, HOME, 1, "out", 9), _sub(900.0, HOME, 13, "in", 10)]
    assert S.minutes_so_far(later, STARTERS, 600.0) == at600
    after = S.minutes_so_far(later, STARTERS, 600.1)
    assert after[12] == pytest.approx(0.1) and after[10] == pytest.approx(600.0)
    with pytest.raises(S84.AsOfViolation):
        S84.assert_strictly_before([_sub(600.0, HOME, 1, "in")], 600.0, "same tick")


def test_unit_stints_books_seconds_and_a_signed_point_differential(tmp_path):
    stints = L.unit_stints(_game_json(tmp_path), HOME, AWAY)
    booked = {(unit, round(sec, 3)): pts for unit, sec, pts in stints}
    assert booked[(frozenset({1, 2, 3, 4, 5}), 120.0)] == 5      # home led 5-0 over stint one
    assert booked[(frozenset({6, 7, 8, 9, 10}), 120.0)] == -5    # the away side is its mirror
    assert booked[(frozenset({1, 2, 3, 4, 11}), 600.0)] == 2     # 10-3 close, 5-0 at the swap
    assert booked[(frozenset({6, 7, 8, 9, 10}), 600.0)] == -2
    assert sum(sec for _u, sec, _p in stints) == pytest.approx(2 * 720.0)


def test_unit_value_is_the_shrunk_net_rating():
    assert L.unit_value(0.0, 0.0) == 0.0
    assert L.unit_value(2880.0, 10.0) == pytest.approx(1000.0 / 300.0)   # 100 poss + 200 shrink
    assert L.unit_value(2880.0, -10.0) == pytest.approx(-1000.0 / 300.0)


def test_unit_history_uses_strictly_earlier_games_only(tmp_path, monkeypatch):
    """A game on the same date as the target must not reach the target's unit history."""
    pbp = {gid: _game_json(tmp_path, gid) for gid in ("0022400001", "0022400002", "0022400003")}
    meta = pd.DataFrame([{"game_id": "0022400001", "date": "2024-10-22", "home_team": HOME,
                          "away_team": AWAY},
                         {"game_id": "0022400002", "date": "2024-10-23", "home_team": HOME,
                          "away_team": AWAY},
                         {"game_id": "0022400003", "date": "2024-10-23", "home_team": HOME,
                          "away_team": AWAY}])
    path = tmp_path / "games.parquet"
    meta.to_parquet(path)
    monkeypatch.setattr(L, "GAMES", path)
    unit = frozenset({1, 2, 3, 4, 5})
    hist = L.unit_history({gid: {unit} for gid in pbp}, pbp)
    assert hist["0022400001"] == {}                              # nothing precedes the opener
    assert hist["0022400002"][unit] == pytest.approx(L.unit_value(120.0, 5.0))
    assert hist["0022400003"] == hist["0022400002"]              # same date -> same history
