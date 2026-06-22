"""Per-file test: scripts/platformkit/ingame/test_ingame_live_state.py
Run: python -m pytest scripts/platformkit/ingame/test_ingame_live_state.py -q

Covers the soccer_intl (World Cup) wiring added so the in-play day-trader can resolve a
live WC state: the fifa.world scoreboard URL, minutes-based frac_elapsed, and the additive
absolute-score + display-name fields the in-game model_fn needs. NO network: http_get is
injected with a canned ESPN scoreboard payload.
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_live_state as S


def _wc_event(*, live: bool, hs: str = "1", as_: str = "0", clock: str = "57'"):
    state = "in" if live else "pre"
    name = "STATUS_IN_PROGRESS" if live else "STATUS_SCHEDULED"
    return {
        "id": "760456",
        "status": {"displayClock": clock, "type": {"state": state, "name": name,
                                                   "shortDetail": clock}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": hs,
             "team": {"abbreviation": "ARG", "displayName": "Argentina"}},
            {"homeAway": "away", "score": as_,
             "team": {"abbreviation": "AUT", "displayName": "Austria"}},
        ]}],
    }


def test_soccer_intl_url_is_world_cup():
    assert S._scoreboard_url("soccer_intl", None) == (
        "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard")
    # club soccer still defaults to its own league (unchanged)
    assert "eng.1" in S._scoreboard_url("soccer", None)


def test_soccer_intl_frac_elapsed_from_display_clock():
    frac = S._frac_elapsed("soccer_intl", _wc_event(live=True, clock="45'"))
    assert frac is not None and abs(frac - 45.0 / 90.0) < 1e-6


def test_live_state_soccer_intl_extracts_scores_and_names():
    payload = {"events": [_wc_event(live=True, hs="2", as_="1", clock="80'")]}
    st = S.live_state("soccer_intl", http_get=lambda url: payload, p0=0.55)
    assert st is not None
    assert st["sport"] == "soccer_intl"
    assert st["home"] == "ARG" and st["away"] == "AUT"
    # additive fields the in-game model_fn consumes
    assert st["home_display"] == "Argentina" and st["away_display"] == "Austria"
    assert st["home_goals"] == 2.0 and st["away_goals"] == 1.0
    assert st["state_diff"] == 1.0
    assert abs(st["frac_elapsed"] - 80.0 / 90.0) < 1e-6
    assert st["p0"] == 0.55 and st["p0_source"] == "CALLER"


def test_live_state_skips_scheduled_game():
    payload = {"events": [_wc_event(live=False)]}
    # no in-progress event -> None (never fabricates a live state)
    assert S.live_state("soccer_intl", http_get=lambda url: payload) is None


def test_unknown_sport_returns_none():
    assert S.live_state("cricket", http_get=lambda url: {"events": []}) is None


def test_live_states_returns_all_in_progress():
    # two live + one scheduled -> only the two live states come back
    ev_live2 = _wc_event(live=True, hs="0", as_="0", clock="10'")
    ev_live2["id"] = "770099"
    ev_live2["competitions"][0]["competitors"][0]["team"] = {
        "abbreviation": "USA", "displayName": "United States"}
    ev_live2["competitions"][0]["competitors"][1]["team"] = {
        "abbreviation": "MEX", "displayName": "Mexico"}
    payload = {"events": [_wc_event(live=True), ev_live2, _wc_event(live=False)]}
    states = S.live_states("soccer_intl", http_get=lambda url: payload)
    assert len(states) == 2
    names = {(s["home"], s["away"]) for s in states}
    assert ("ARG", "AUT") in names and ("USA", "MEX") in names


def test_live_states_empty_when_none_live():
    payload = {"events": [_wc_event(live=False)]}
    assert S.live_states("soccer_intl", http_get=lambda url: payload) == []
