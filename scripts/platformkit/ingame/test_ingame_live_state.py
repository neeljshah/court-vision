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


# --------------------------------------------------------------------------------------- #
# tennis fixture: trimmed from a REAL ESPN tennis scoreboard fetched live 2026-07-03        #
# (site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard, Wimbledon). Confirmed live: #
#  - the `dates=` query param is IGNORED; the endpoint always returns the WHOLE tournament. #
#  - each top-level "event" is the TOURNAMENT itself (no top-level `competitions` key);     #
#    real per-match competitions nest under event["groupings"][i]["competitions"].          #
#  - competitors carry type=="athlete" + an `athlete` block (displayName/shortName), not    #
#    `team`, and carry NO `score` field at all -- only per-set `linescores` + `winner`.      #
# --------------------------------------------------------------------------------------- #
def _tennis_match(*, live: bool, match_id="179877", winner_home=True,
                  home_name="Zsombor Piros", away_name="Ivan Ivanov"):
    """One nested tennis match competition, shaped exactly like the real trimmed
    payload (see docstring above): athlete competitors, linescores, no score key."""
    if live:
        status = {"period": 1, "type": {"id": "2", "name": "STATUS_IN_PROGRESS",
                                        "state": "in", "completed": False}}
        home_ls = [{"value": 6.0, "winner": True}]
        away_ls = [{"value": 3.0, "winner": False}]
    else:
        status = {"period": 2, "type": {"id": "3", "name": "STATUS_FINAL",
                                        "state": "post", "completed": True}}
        home_ls = [{"value": 6.0, "winner": winner_home}, {"value": 6.0, "winner": winner_home}]
        away_ls = [{"value": 2.0, "winner": not winner_home}, {"value": 2.0, "winner": not winner_home}]
    return {
        "id": match_id, "date": "2026-06-22T10:05Z",
        "status": status,
        "type": {"id": "1", "text": "Men's Singles", "slug": "mens-singles"},
        "competitors": [
            {"id": "13489", "type": "athlete", "homeAway": "away", "winner": not winner_home,
             "linescores": away_ls,
             "athlete": {"displayName": away_name, "shortName": "I. Ivanov"}},
            {"id": "3110", "type": "athlete", "homeAway": "home", "winner": winner_home,
             "linescores": home_ls,
             "athlete": {"displayName": home_name, "shortName": "Z. Piros"}},
        ],
    }


def _tennis_payload(matches):
    """Real ESPN tennis scoreboard shape: one tournament event wrapping groupings."""
    return {"events": [{"id": "188-2026", "name": "Wimbledon",
                        "groupings": [{"grouping": {"slug": "mens-singles"},
                                      "competitions": matches}]}]}


def test_tennis_events_flatten_nested_groupings():
    payload = _tennis_payload([_tennis_match(live=True), _tennis_match(live=False, match_id="X")])
    events = S._events_for("tennis", payload)
    assert len(events) == 2
    assert {e["id"] for e in events} == {"179877", "X"}
    # synthetic event carries the MATCH's own status, not the tournament's (absent/None)
    assert events[0]["status"]["type"]["state"] == "in"


def test_tennis_name_and_display_use_athlete_fallback():
    m = _tennis_match(live=True)
    home, away = S._competitors({"competitions": [m]})
    assert S._name(home) == "Z. Piros" and S._name(away) == "I. Ivanov"
    assert S._display(home) == "Zsombor Piros" and S._display(away) == "Ivan Ivanov"


def test_tennis_score_derives_sets_won_from_linescores():
    m = _tennis_match(live=False, winner_home=True)
    home, away = S._competitors({"competitions": [m]})
    assert S._score(home) == 2.0 and S._score(away) == 0.0


def _atp_only(payload):
    """http_get stub: ATP board returns *payload*, WTA board is empty (no double-count) --
    live_states("tennis") with no explicit league now fetches BOTH tour boards and merges."""
    return lambda url: payload if "/atp/" in url else {}


def test_live_state_tennis_produces_named_competitors():
    # end-to-end: the real inplay_capture_loop path (live_states -> _scan_live_by_legs)
    # bridges by home_display/away_display -- this proves those are real player names,
    # not '', for a live tennis match nested under groupings.
    payload = _tennis_payload([_tennis_match(live=True)])
    states = S.live_states("tennis", http_get=_atp_only(payload))
    assert len(states) == 1
    st = states[0]
    assert st["home"] == "Z. Piros" and st["away"] == "I. Ivanov"
    assert st["home_display"] == "Zsombor Piros" and st["away_display"] == "Ivan Ivanov"
    assert st["home_goals"] == 1.0 and st["away_goals"] == 0.0  # sets won so far
    assert st["state_diff"] == 1.0
    assert st["frac_elapsed"] is None  # tennis has no clock -- honest, never fabricated
    assert st["set"] == 1  # segment field from the match's own status.period


def test_live_state_tennis_by_event_id_finds_nested_match():
    payload = _tennis_payload([_tennis_match(live=True, match_id="179877"),
                               _tennis_match(live=False, match_id="999999")])
    st = S.live_state("tennis", "179877", http_get=lambda url: payload)
    assert st is not None and st["game_id"] == "179877"
    assert st["home_display"] == "Zsombor Piros"


def test_live_state_tennis_skips_final_match():
    # only STATUS_FINAL match present -> no in-progress match -> None
    payload = _tennis_payload([_tennis_match(live=False)])
    assert S.live_state("tennis", http_get=lambda url: payload) is None


# --------------------------------------------------------------------------------------- #
# WTA coverage: inplay_capture_loop passes the bare capture sport "tennis" for BOTH tours
# (KXATPMATCH and KXWTAMATCH tickers alike) -- there is no per-tour sport id upstream, so
# live_state/live_states must scan BOTH tennis/atp and tennis/wta boards when no explicit
# league is pinned. Team sports (nba/mlb/soccer/soccer_intl) stay single-board, unchanged.
# --------------------------------------------------------------------------------------- #

def _by_league(atp_payload=None, wta_payload=None):
    """http_get stub that routes by the fetched URL's tour segment."""
    def _get(url):
        if "/atp/" in url:
            return atp_payload or {}
        if "/wta/" in url:
            return wta_payload or {}
        return {}
    return _get


def test_scoreboard_url_routes_by_league():
    assert S._scoreboard_url("tennis", "atp").endswith("tennis/atp/scoreboard")
    assert S._scoreboard_url("tennis", "wta").endswith("tennis/wta/scoreboard")
    # no explicit league -> single-board default stays atp (unchanged prior behavior for
    # any direct _scoreboard_url caller that bypasses the _fetch_events dual-board merge).
    assert S._scoreboard_url("tennis", None).endswith("tennis/atp/scoreboard")


def test_team_sport_urls_unaffected_by_tennis_routing():
    assert S._scoreboard_url("nba", None).endswith("basketball/nba/scoreboard")
    assert S._scoreboard_url("mlb", None).endswith("baseball/mlb/scoreboard")


def test_live_states_merges_atp_and_wta_boards():
    atp_match = _tennis_match(live=True, match_id="1", home_name="ATP Home", away_name="ATP Away")
    wta_match = _tennis_match(live=True, match_id="2", home_name="WTA Home", away_name="WTA Away")
    getter = _by_league(atp_payload=_tennis_payload([atp_match]),
                        wta_payload=_tennis_payload([wta_match]))
    states = S.live_states("tennis", http_get=getter)
    assert {st["game_id"] for st in states} == {"1", "2"}
    assert {st["home_display"] for st in states} == {"ATP Home", "WTA Home"}


def test_live_states_wta_only_match_is_found():
    # a match that exists ONLY on the WTA board must still surface (the gap this closes:
    # before this fix, tennis always queried tennis/atp only -- a WTA-only live match was
    # invisible to live_states/_scan_live_by_legs no matter what).
    wta_match = _tennis_match(live=True, match_id="42", home_name="Iga Swiatek",
                              away_name="Coco Gauff")
    getter = _by_league(atp_payload={}, wta_payload=_tennis_payload([wta_match]))
    states = S.live_states("tennis", http_get=getter)
    assert len(states) == 1
    assert states[0]["home_display"] == "Iga Swiatek"


def test_live_state_wta_only_match_by_event_id():
    wta_match = _tennis_match(live=True, match_id="42", home_name="Iga Swiatek",
                              away_name="Coco Gauff")
    getter = _by_league(atp_payload={}, wta_payload=_tennis_payload([wta_match]))
    st = S.live_state("tennis", "42", http_get=getter)
    assert st is not None and st["home_display"] == "Iga Swiatek"


def test_live_states_explicit_league_stays_single_board():
    # an explicit league= still fetches exactly that one board (no merge) -- unchanged
    # single-league contract for a caller that already knows the tour.
    atp_match = _tennis_match(live=True, match_id="1")
    wta_match = _tennis_match(live=True, match_id="2")
    getter = _by_league(atp_payload=_tennis_payload([atp_match]),
                        wta_payload=_tennis_payload([wta_match]))
    states = S.live_states("tennis", league="wta", http_get=getter)
    assert {st["game_id"] for st in states} == {"2"}


def test_live_states_one_tour_feed_error_does_not_lose_the_other():
    # a raising ATP fetch must not sink the WTA half of the merge.
    wta_match = _tennis_match(live=True, match_id="7")

    def _flaky(url):
        if "/atp/" in url:
            raise RuntimeError("feed down")
        return _tennis_payload([wta_match])

    states = S.live_states("tennis", http_get=_flaky)
    assert {st["game_id"] for st in states} == {"7"}


# --------------------------------------------------------------------------------------- #
# WNBA wiring (queue item 1, LANE 1): ingame_live_state._SPORTS had no "wnba" entry, so     #
# live_state("wnba")/live_states("wnba") always returned None/[] -- leaving the wave-4      #
# wnba_ingame_shadow logging None forever and m36 grading with no wnba segment fields.      #
# Same ESPN basketball scoreboard shape as nba (period + status.clock seconds-remaining),   #
# but regulation is 4x10min=2400s, not nba's 4x12min=2880s.                                 #
# --------------------------------------------------------------------------------------- #
def _wnba_event(*, live: bool, hs: str = "41", as_: str = "38", period: int = 2,
                clock: float = 320.0, event_id: str = "401700001"):
    state = "in" if live else "pre"
    name = "STATUS_IN_PROGRESS" if live else "STATUS_SCHEDULED"
    return {
        "id": event_id,
        "status": {"period": period, "clock": clock,
                   "type": {"state": state, "name": name, "shortDetail": "Q%d" % period}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": hs,
             "team": {"abbreviation": "LVA", "displayName": "Las Vegas Aces"}},
            {"homeAway": "away", "score": as_,
             "team": {"abbreviation": "CHI", "displayName": "Chicago Sky"}},
        ]}],
    }


def test_wnba_scoreboard_url_uses_basketball_wnba_path():
    assert S._scoreboard_url("wnba", None) == (
        "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard")


def test_wnba_frac_elapsed_uses_2400s_regulation():
    # period 2, 320s left in a 600s (10min) quarter -> elapsed = 600 + (600-320) = 880s / 2400s
    ev = _wnba_event(live=True, period=2, clock=320.0)
    frac = S._frac_elapsed("wnba", ev)
    assert frac is not None and abs(frac - 880.0 / 2400.0) < 1e-6


def test_live_state_wnba_extracts_real_state():
    payload = {"events": [_wnba_event(live=True)]}
    st = S.live_state("wnba", http_get=lambda url: payload, p0=0.55)
    assert st is not None
    assert st["sport"] == "wnba"
    assert st["home"] == "LVA" and st["away"] == "CHI"
    assert st["home_display"] == "Las Vegas Aces" and st["away_display"] == "Chicago Sky"
    assert st["home_score"] == 41.0 and st["away_score"] == 38.0
    assert st["state_diff"] == 3.0
    assert abs(st["frac_elapsed"] - 880.0 / 2400.0) < 1e-6
    # segment + raw clock fields: previously ONLY populated for sport=="nba" -- widened
    # so wnba_ingame_shadow.shadow_prob (which reads state["period"]/state["clock"]) has
    # real inputs instead of permanent None.
    assert st["period"] == 2
    assert st["clock"] == 320.0
    assert st["p0"] == 0.55 and st["p0_source"] == "CALLER"


def test_live_states_wnba_returns_all_in_progress():
    ev_live2 = _wnba_event(live=True, hs="10", as_="8", period=1, clock=500.0,
                           event_id="401700002")
    ev_live2["competitions"][0]["competitors"][0]["team"] = {
        "abbreviation": "NYL", "displayName": "New York Liberty"}
    ev_live2["competitions"][0]["competitors"][1]["team"] = {
        "abbreviation": "CON", "displayName": "Connecticut Sun"}
    payload = {"events": [_wnba_event(live=True), ev_live2, _wnba_event(live=False)]}
    states = S.live_states("wnba", http_get=lambda url: payload)
    assert len(states) == 2
    names = {(s["home"], s["away"]) for s in states}
    assert ("LVA", "CHI") in names and ("NYL", "CON") in names


def test_live_states_wnba_empty_when_none_live():
    payload = {"events": [_wnba_event(live=False)]}
    assert S.live_states("wnba", http_get=lambda url: payload) == []


def test_wnba_segment_bucket_resolves_via_infer_segment():
    # real downstream chain: _extract -> live_grade._state_summary -> _infer_segment,
    # same as the existing MLB roundtrip test above -- proves wnba ticks get a real Q-bucket
    # instead of falling into UNK now that _segment_fields is widened beyond sport=="nba".
    from scripts.platformkit.ingame import live_grade as lg
    from scripts.platformkit.ingame import ingame_clv_per_segment as ps
    st = S._extract("wnba", _wnba_event(live=True, period=3), None,
                    p0_provider=lambda s, g: None)
    ss = lg._state_summary(st)
    assert "period=3" in ss and "clock=" in ss
    assert ps._infer_segment("wnba", ss) == "Q3"


# --------------------------------------------------------------------------------------- #
# LANE 1 (2026-07-06): soccer tick-state instrumentation. 22/40 captured soccer_intl games   #
# had bare 'live' state (no minute/half) -- their ticks fell into the synthetic UNK segment  #
# (wave-6 finding, the only cross-corpus WORSE bucket). Root cause: _segment_fields'/         #
# _frac_elapsed's soccer branch only parsed the plain "57'" displayClock shape; stoppage-time #
# ("90'+5'") and halftime (displayClock "" / "HT", unparseable) both fell through to no       #
# minute key at all. Fixtures below are the REAL ESPN status shapes fetched live 2026-07-06   #
# from site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard (event 760501,      #
# STATUS_FIRST_HALF, displayClock "22'") plus the documented ESPN status vocabulary for the    #
# halftime/stoppage/extra-time shapes not live at probe time (no WC game was at HT/stoppage    #
# right now) -- same convention already shipped and proven in live_board._soccer_minute for    #
# the served page, so this keeps the two readers consistent.                                  #
# --------------------------------------------------------------------------------------- #
def _soccer_status(display_clock, period=1, name="STATUS_FIRST_HALF", state="in"):
    return {"displayClock": display_clock, "period": period,
            "type": {"state": state, "name": name, "shortDetail": display_clock}}


def test_soccer_minute_plain_clock_real_live_fixture():
    # real live fetch 2026-07-06: fifa.world event 760501, STATUS_FIRST_HALF, "22'"
    st = _soccer_status("22'", period=1, name="STATUS_FIRST_HALF")
    assert S._soccer_minute(st) == 22


def test_soccer_minute_stoppage_time_first_half():
    st = _soccer_status("45'+2'", period=1, name="STATUS_FIRST_HALF")
    # base minute only (45), matching live_board._soccer_minute's own '+' convention
    assert S._soccer_minute(st) == 45


def test_soccer_minute_stoppage_time_second_half():
    st = _soccer_status("90'+5'", period=2, name="STATUS_SECOND_HALF")
    assert S._soccer_minute(st) == 90


def test_soccer_minute_halftime_falls_back_to_period_boundary():
    # ESPN halftime shape: displayClock often "" or "HT" (unparseable), period still 1
    for disp in ("", "HT"):
        st = _soccer_status(disp, period=1, name="STATUS_HALFTIME")
        assert S._soccer_minute(st) == 45, "displayClock=%r" % disp


def test_soccer_minute_extra_time_second_half_boundary():
    # extra-time period (>=2) with an unreadable clock still resolves to the H2 boundary
    st = _soccer_status("", period=3, name="STATUS_END_FIRST_HALF_EXTRA")
    assert S._soccer_minute(st) == 90


def test_soccer_minute_none_when_wholly_unreadable():
    st = _soccer_status("", period=0, name="STATUS_SCHEDULED")
    assert S._soccer_minute(st) is None


def test_segment_fields_soccer_stoppage_time_populates_minute_and_half():
    ev = {"status": _soccer_status("90'+5'", period=2, name="STATUS_SECOND_HALF")}
    out = S._segment_fields("soccer_intl", ev)
    assert out["minute"] == 90 and out["half"] == "2"


def test_segment_fields_soccer_halftime_populates_minute_and_half_not_bare_live():
    # this is the exact bug: before the fix, a halftime tick had NO minute/half key at all
    # -> live_grade._state_summary returned bare "live" -> _infer_segment("live") == "UNK".
    ev = {"status": _soccer_status("", period=1, name="STATUS_HALFTIME")}
    out = S._segment_fields("soccer_intl", ev)
    assert out.get("minute") == 45 and out.get("half") == "1"


def test_frac_elapsed_soccer_stoppage_time_does_not_raise_or_return_none():
    ev = {"status": _soccer_status("90'+3'", period=2, name="STATUS_SECOND_HALF")}
    frac = S._frac_elapsed("soccer_intl", ev)
    assert frac is not None and abs(frac - 90.0 / 90.0) < 1e-6


def test_frac_elapsed_soccer_halftime_does_not_raise_or_return_none():
    ev = {"status": _soccer_status("", period=1, name="STATUS_HALFTIME")}
    frac = S._frac_elapsed("soccer_intl", ev)
    assert frac is not None and abs(frac - 45.0 / 90.0) < 1e-6


def test_stoppage_and_halftime_ticks_no_longer_land_in_unk_segment():
    # end-to-end proof of the m36 grading pickup: _extract -> live_grade._state_summary ->
    # ingame_clv_per_segment._infer_segment must flip from "UNK" to a real H1/H2 bucket.
    from scripts.platformkit.ingame import live_grade as lg
    from scripts.platformkit.ingame import ingame_clv_per_segment as ps

    stoppage_ev = {"id": "X1",
                   "status": _soccer_status("90'+4'", period=2, name="STATUS_SECOND_HALF"),
                   "competitions": [{"competitors": [
                       {"homeAway": "home", "score": "2", "team": {"abbreviation": "ARG"}},
                       {"homeAway": "away", "score": "1", "team": {"abbreviation": "AUT"}}]}]}
    st = S._extract("soccer_intl", stoppage_ev, None, p0_provider=lambda s, g: None)
    ss = lg._state_summary(st)
    assert ss != "live"
    assert ps._infer_segment("soccer_intl", ss) == "H2"

    halftime_ev = {"id": "X2",
                   "status": _soccer_status("", period=1, name="STATUS_HALFTIME"),
                   "competitions": [{"competitors": [
                       {"homeAway": "home", "score": "1", "team": {"abbreviation": "ARG"}},
                       {"homeAway": "away", "score": "0", "team": {"abbreviation": "AUT"}}]}]}
    st2 = S._extract("soccer_intl", halftime_ev, None, p0_provider=lambda s, g: None)
    ss2 = lg._state_summary(st2)
    assert ss2 != "live"
    assert ps._infer_segment("soccer_intl", ss2) == "H1"


def test_wnba_ingame_shadow_chain_produces_real_prob_from_live_state_fixture():
    # end-to-end fixture-driven proof (no live dependency): a wnba-shaped scoreboard ->
    # live_state() -> wnba_ingame_shadow.shadow_prob() via the real WNBAAdapter.predict_live
    # signature, using a fake adapter so this stays offline/deterministic.
    from scripts.platformkit.ingame import wnba_ingame_shadow as wshadow

    class _FakeAdapter:
        def predict_live(self, home, away, as_of, period, clock_s, home_score,
                         away_score, *, neutral_site: bool = False):
            return {"p_home_win": 0.71}

    payload = {"events": [_wnba_event(live=True, period=2, clock=320.0, hs="41", as_="38")]}
    st = S.live_state("wnba", http_get=lambda url: payload, p0=0.5)
    assert st is not None

    shadow = wshadow.WnbaIngameShadow(adapter=_FakeAdapter())
    prob = shadow.shadow_prob("wnba", st["home_display"], st["away_display"], st)
    assert prob == 0.71


# --------------------------------------------------------------------------------------- #
# LANE 5: espn_event_id extraction. Un-inerts the wave-11 enrichment facade's espn_wp(event_id)
# arm, which previously always got None because ingame_live_state's state dict never carried
# an ESPN event id key at all (inplay_capture_loop._enrichment_fields reads
# state.get("espn_event_id"), a key that simply did not exist before this fix). ESPN's
# scoreboard event `id` IS the numeric id the summary?event={id} endpoint (and
# espn_wp_backfill_measure.resolve_event_id) already expects -- so this is a same-value
# additive alias of game_id, not a new lookup.
# --------------------------------------------------------------------------------------- #
def test_extract_emits_espn_event_id_mlb():
    st = S._extract("mlb", _mlb_event(), None, p0_provider=lambda s, g: None)
    assert st["espn_event_id"] == "G1" == st["game_id"]


def test_extract_emits_espn_event_id_wnba():
    payload_ev = _wnba_event(live=True, event_id="401700001")
    st = S._extract("wnba", payload_ev, None, p0_provider=lambda s, g: None)
    assert st["espn_event_id"] == "401700001" == st["game_id"]


def test_live_state_carries_espn_event_id_end_to_end_mlb():
    ev = _mlb_event()
    payload = {"events": [ev]}
    st = S.live_state("mlb", http_get=lambda url: payload, p0=0.5)
    assert st is not None
    assert st["espn_event_id"] == "G1"


def test_extract_espn_event_id_none_when_id_blank():
    # honest absence: a blank/missing ESPN id must yield None, never "" or a fabricated id.
    ev = _mlb_event()
    ev["id"] = ""
    st = S._extract("mlb", ev, None, p0_provider=lambda s, g: None)
    assert st["espn_event_id"] is None


def test_enrichment_facade_espn_wp_arm_proven_live_capable_from_state(tmp_path):
    """End-to-end proof (LANE 5 DONE-WHEN): a live_state() dict carrying a real
    espn_event_id -> EnrichmentFacade.espn_wp() resolves a number from a fixture sidecar,
    exactly the inplay_capture_loop._enrichment_fields call shape
    (facade.espn_wp("mlb", state.get("espn_event_id")))."""
    import json as _json
    from scripts.platformkit.ingame import ingame_enrichment as E

    espn_dir = tmp_path / "domains"
    sidecar = espn_dir / "mlb" / "espn_wp" / "G1.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    with sidecar.open("w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"espn_wp_home": 0.42, "n_wp_points": 12}) + "\n")

    payload = {"events": [_mlb_event()]}
    st = S.live_state("mlb", http_get=lambda url: payload, p0=0.5)
    assert st is not None and st["espn_event_id"] == "G1"

    facade = E.EnrichmentFacade(espn_wp_dir=espn_dir)
    wp = facade.espn_wp("mlb", st.get("espn_event_id"))
    assert wp == {"espn_wp": 0.42}


def test_enrichment_facade_espn_wp_arm_still_none_when_event_id_absent(tmp_path):
    # honest pending case preserved: a state with no espn_event_id (e.g. tennis, or an
    # extraction that failed to find one) must still yield None, never raise.
    from scripts.platformkit.ingame import ingame_enrichment as E
    facade = E.EnrichmentFacade(espn_wp_dir=tmp_path / "domains")
    assert facade.espn_wp("mlb", None) is None


# ---- LANE 3 (wave-19): npb/kbo non-ESPN dispatch ------------------------------------
# ESPN carries neither league (verified live 400 on both site.api paths) -- npb/kbo
# route through scripts.platformkit.ingame.npb_kbo_live_state instead. These tests only
# check the DISPATCH wiring (npb_kbo_live_state itself has its own full per-file suite
# in test_npb_kbo_live_state.py); the injected http_get here is npb_kbo_live_state's own
# shape (single-arg url->body for npb, (url, body)->text for kbo), never ESPN's.

def test_npb_in_sports_and_routes_non_espn():
    assert "npb" in S._SPORTS and "kbo" in S._SPORTS
    assert "npb" in S._NON_ESPN_SPORTS and "kbo" in S._NON_ESPN_SPORTS
    assert "mlb" not in S._NON_ESPN_SPORTS


def test_live_states_npb_returns_real_games_from_fixture():
    row = ('<tr id="date0703"><th rowspan="1">7/3</th>'
           '<td><div class="team1">DeNA</div><div class="score1">5</div>'
           '<div class="state">-</div><div class="score2">3</div>'
           '<div class="team2">阪神</div></td></tr>')
    states = S.live_states("npb", http_get=lambda url: row)
    # a completed ("final") game is excluded from the LIVE scan (mirrors the ESPN
    # branch's _is_live filter) -- so this fixture (a final score) yields [].
    assert states == []


def test_live_states_npb_keeps_ambiguous_scheduled_state():
    import datetime as _dt
    today = _dt.date.today()
    row = (f'<tr id="date{today.month:02d}{today.day:02d}">'
           '<th rowspan="1">x</th>'
           '<td><div class="team1">ヤクルト</div><div class="score1">&nbsp;</div>'
           '<div class="state">-</div><div class="score2">&nbsp;</div>'
           '<div class="team2">DeNA</div></td></tr>')
    states = S.live_states("npb", http_get=lambda url: row)
    assert len(states) == 1
    st = states[0]
    assert st["home"] == "ヤクルト" and st["status"] == "scheduled"
    # p0/p0_source carried the same way every ESPN sport's live_states does
    assert "p0_source" in st and st["p0"] is None  # no pregame snapshot injected -> BASE_FALLBACK


def test_live_states_kbo_dispatches_and_carries_p0_fields():
    import datetime as _dt
    import json
    today = _dt.date.today()
    body = json.dumps({"rows": [
        {"row": [{"Class": "day", "Text": f"{today.month:02d}.{today.day:02d}(x)"},
                 {"Class": "play", "Text": '<span>NC</span><em><span class="same">0</span>'
                                            '<span>vs</span><span class="same">0</span></em>'
                                            '<span>KIA</span>'}]},
    ]})
    states = S.live_states("kbo", http_get=lambda url, b: body)
    assert len(states) == 1
    st = states[0]
    assert st["sport"] == "kbo" and st["status"] == "in_progress_or_scheduled"
    assert "p0_source" in st


def test_live_state_single_game_npb_by_synthetic_game_id():
    import datetime as _dt
    today = _dt.date.today()
    row = (f'<tr id="date{today.month:02d}{today.day:02d}">'
           '<th rowspan="1">x</th>'
           '<td><div class="team1">ヤクルト</div><div class="score1">&nbsp;</div>'
           '<div class="state">-</div><div class="score2">&nbsp;</div>'
           '<div class="team2">DeNA</div></td></tr>')
    gid = f"npb-{today.isoformat()}-DeNA-ヤクルト"
    st = S.live_state("npb", gid, http_get=lambda url: row)
    assert st is not None and st["game_id"] == gid


def test_live_state_npb_unknown_game_id_returns_none():
    row = ('<tr id="date0704"><th rowspan="1">x</th>'
           '<td><div class="team1">ヤクルト</div><div class="score1">&nbsp;</div>'
           '<div class="state">-</div><div class="score2">&nbsp;</div>'
           '<div class="team2">DeNA</div></td></tr>')
    st = S.live_state("npb", "does-not-exist", http_get=lambda url: row)
    assert st is None


def test_live_states_npb_never_raises_on_source_error():
    def _boom(url):
        raise RuntimeError("boom")
    assert S.live_states("npb", http_get=_boom) == []


def test_start_time_copied_from_event_date():
    """S107: the Kalshi-ticker bridge tells two nights of a series apart by comparing
    the ticker's encoded first pitch to THIS field, so it must carry the ESPN event's
    own scheduled start verbatim -- and be None (no info) when the feed omits it."""
    ev = _wc_event(live=True)
    ev["date"] = "2026-06-22T20:00Z"
    payload = {"events": [ev]}
    st = S.live_state("soccer_intl", http_get=lambda url: payload)
    assert st is not None and st["start_time"] == "2026-06-22T20:00Z"
    # feed omits it -> None, never fabricated
    st2 = S.live_state("soccer_intl", http_get=lambda url: {"events": [_wc_event(live=True)]})
    assert st2 is not None and st2["start_time"] is None
