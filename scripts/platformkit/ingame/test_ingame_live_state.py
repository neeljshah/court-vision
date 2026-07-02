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


# --------------------------------------------------------------------------------------- #
# state_summary parity fix: _extract must emit the keys live_grade._state_summary and      #
# ingame_clv_per_segment._infer_segment read, so captured ticks carry real game state      #
# (score margin + period/inning/half/minute) instead of falling back to "live"/UNK.        #
# --------------------------------------------------------------------------------------- #
def _mlb_event(period=5, detail="Bottom 5th", hs="7", as_="1"):
    return {"id": "G1",
            "status": {"period": period, "type": {"state": "in",
                       "name": "STATUS_IN_PROGRESS", "shortDetail": detail}},
            "competitions": [{"competitors": [
                {"homeAway": "home", "score": hs, "team": {"abbreviation": "DET"}},
                {"homeAway": "away", "score": as_, "team": {"abbreviation": "CWS"}}]}]}


def test_extract_emits_score_and_segment_keys_mlb():
    st = S._extract("mlb", _mlb_event(), None, p0_provider=lambda s, g: None)
    assert st["home_score"] == 7.0 and st["away_score"] == 1.0   # margin available
    assert st["inning"] == 5 and st["half"] == "bottom"          # segment available


def test_extract_segment_fields_nba_and_soccer():
    nba = {"id": "G2", "status": {"period": 3, "clock": 300,
           "type": {"state": "in", "name": "STATUS_IN_PROGRESS", "shortDetail": "Q3"}},
           "competitions": [{"competitors": [
               {"homeAway": "home", "score": "70", "team": {"abbreviation": "BOS"}},
               {"homeAway": "away", "score": "66", "team": {"abbreviation": "NYK"}}]}]}
    st = S._extract("nba", nba, None, p0_provider=lambda s, g: None)
    assert st["period"] == 3 and st["home_score"] == 70.0
    soc = S._extract("soccer_intl", _wc_event(live=True, clock="57'"),
                     None, p0_provider=lambda s, g: None)
    assert soc["minute"] == 57


def test_state_summary_and_segment_roundtrip():
    # The real downstream chain: _extract -> live_grade._state_summary -> _infer_segment.
    from scripts.platformkit.ingame import live_grade as lg
    from scripts.platformkit.ingame import ingame_clv_per_segment as ps
    st = S._extract("mlb", _mlb_event(), None, p0_provider=lambda s, g: None)
    ss = lg._state_summary(st)
    assert "inning=5" in ss and "home_score" in ss and ss != "live"
    assert ps._infer_segment("mlb", ss) == "I5"
