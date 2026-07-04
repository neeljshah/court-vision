"""Per-file test: scripts/platformkit/ingame/test_tennis_capture_bridge.py
Run: python -m pytest scripts/platformkit/ingame/test_tennis_capture_bridge.py -q

DOWNSTREAM proof for the ingame_live_state tennis fix: inplay_capture_loop's
_scan_live_by_legs bridges a Kalshi-keyed tennis market to its live ESPN state by
TEAM/PLAYER name (home_display/away_display). Before the fix those fields were '' for
every tennis competitor (athlete-shaped, not team-shaped) so a live tennis match could
never bind to its Kalshi market. This proves the real consumer now gets named
competitors + a sane state dict end-to-end, using the same trimmed real-payload
tennis fixture as test_ingame_live_state.py / test_settled_finals.py (verified live
2026-07-03 against site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard).

READ-ONLY test: does not modify inplay_capture_loop.py (over-LOC-cap file --
additive-only per repo rule). No network: http_get is injected.
"""
from __future__ import annotations

from scripts.platformkit.ingame import inplay_capture_loop as loop


def _tennis_match(*, live=True, match_id="179877",
                  home_name="Zsombor Piros", away_name="Ivan Ivanov"):
    status = ({"period": 1, "type": {"name": "STATUS_IN_PROGRESS", "state": "in",
                                     "completed": False}} if live else
              {"period": 2, "type": {"name": "STATUS_FINAL", "state": "post",
                                     "completed": True}})
    home_ls = [{"value": 6.0, "winner": True}]
    away_ls = [{"value": 3.0, "winner": False}]
    return {
        "id": match_id, "date": "2026-06-22T10:05Z", "status": status,
        "competitors": [
            {"id": "13489", "type": "athlete", "homeAway": "away", "winner": False,
             "linescores": away_ls, "athlete": {"displayName": away_name}},
            {"id": "3110", "type": "athlete", "homeAway": "home", "winner": True,
             "linescores": home_ls, "athlete": {"displayName": home_name}},
        ],
    }


def _tennis_payload(matches):
    return {"events": [{"id": "188-2026", "name": "Wimbledon",
                        "groupings": [{"grouping": {"slug": "mens-singles"},
                                      "competitions": matches}]}]}


def test_scan_live_by_legs_binds_tennis_match_by_player_name(monkeypatch):
    payload = _tennis_payload([_tennis_match()])
    real_live_states = loop._ls.live_states
    monkeypatch.setattr(loop._ls, "live_states",
                        lambda sport, **kw: real_live_states(sport, http_get=lambda url: payload))
    # A Kalshi tennis market's legs are labelled by player display name.
    legs = {"Zsombor Piros": 0.62, "Ivan Ivanov": 0.38}
    st = loop._scan_live_by_legs("tennis", legs)
    assert st is not None
    assert st["home_display"] == "Zsombor Piros" and st["away_display"] == "Ivan Ivanov"
    # sane state dict: leak-free keys present, honest None for the clock-free field.
    assert st["state_diff"] == 1.0  # 1 set won vs 0
    assert st["frac_elapsed"] is None
    assert st["sport"] == "tennis" and st["game_id"] == "179877"


def test_scan_live_by_legs_no_match_when_legs_dont_align(monkeypatch):
    payload = _tennis_payload([_tennis_match()])
    real_live_states = loop._ls.live_states
    monkeypatch.setattr(loop._ls, "live_states",
                        lambda sport, **kw: real_live_states(sport, http_get=lambda url: payload))
    legs = {"Some Other Player": 0.5, "Another One": 0.5}
    assert loop._scan_live_by_legs("tennis", legs) is None
