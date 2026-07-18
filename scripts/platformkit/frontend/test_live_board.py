"""Per-file tests for scripts.platformkit.frontend.live_board on CANNED ESPN payloads.

NO network and NO live corpus: the ESPN http getter and the predictor factory are both
injected. Verifies:
  * parse  -> normalized rows (home/away/state/score/clock/period, as_of stamp);
  * in-progress game -> an in-game prediction is attached (pregame + ingame block);
  * feed down (empty payload) -> status='unavailable' (no fabricated games);
  * a team that cannot be resolved to a predictor id -> SKIPPED with a note, not faked;
  * ESPN abbreviation/name remapping (SA->SAS, SF->SFG, Congo DR->DR Congo).

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/frontend/test_live_board.py -q
"""
from __future__ import annotations

import argparse

from scripts.platformkit.frontend import live_board as lb


# --------------------------------------------------------------------------- stubs
class _StubMLBPredictor:
    """Minimal MLB-shaped predictor: pregame .predict + live .predict_live."""

    def predict(self, home, away, **kw):  # noqa: ANN001
        return {"p_home_win": 0.54, "expected_total": 8.5,
                "expected_runs_home": 4.4, "expected_runs_away": 4.1,
                "markets": {}, "honest_note": "Moneyline matches the devigged close."}

    def predict_live(self, home, away, inning, half, home_runs, away_runs, **kw):  # noqa: ANN001
        # leading by 2 in the 9th -> a high home win prob (sensible move vs pregame 0.54)
        p = 0.96 if (home_runs > away_runs and inning >= 8) else 0.54
        return {"p_home_win": p, "pregame_p_home": 0.54, "innings_remaining": 0.5,
                "honest_note": "in-game calibrated (W156 identity)."}


class _StubIntlPredictor:
    """World-Cup-shaped predictor: pregame only, NO predict_live (honest pregame-only)."""

    def predict(self, home, away, **kw):  # noqa: ANN001
        return {"p_home_win": 0.58, "p_draw": 0.25, "p_away_win": 0.17,
                "over_2.5": 0.5, "lam_home": 1.4, "lam_away": 0.9, "btts_yes": 0.45,
                "top_correct_scores": [], "markets": {},
                "honest_note": "1X2 matches the devigged close."}


def _mlb_factory(sport):  # noqa: ANN001
    return _StubMLBPredictor()


def _intl_factory(sport):  # noqa: ANN001
    return _StubIntlPredictor()


def _none_factory(sport):  # noqa: ANN001
    return None


# --------------------------------------------------------------------------- payloads
def _event(home_abbr, home_name, home_score, away_abbr, away_name, away_score,
           state, detail, clock, period):
    return {"competitions": [{"competitors": [
        {"homeAway": "home", "score": home_score,
         "team": {"abbreviation": home_abbr, "displayName": home_name}},
        {"homeAway": "away", "score": away_score,
         "team": {"abbreviation": away_abbr, "displayName": away_name}}]}],
        "status": {"displayClock": clock, "period": period,
                   "type": {"state": state, "shortDetail": detail}}}


_MLB_PAYLOAD = {"events": [
    # LIVE: HOU leading DET 4-2 in the top of the 9th
    _event("HOU", "Houston Astros", "4", "DET", "Detroit Tigers", "2",
           "in", "Top 9th", "0:00", 9),
    # FINAL (post): not live
    _event("CIN", "Cincinnati Reds", "1", "NYM", "New York Mets", "9",
           "post", "Final", "0:00", 9),
    # LIVE with ESPN non-standard abbr SF -> must remap to SFG
    _event("ATL", "Atlanta Braves", "3", "SF", "San Francisco Giants", "5",
           "in", "Bot 6th", "0:00", 6),
]}

_INTL_PAYLOAD = {"events": [
    # LIVE World Cup: England 1-0 Croatia at 31'
    _event("ENG", "England", "1", "CRO", "Croatia", "0", "in", "31'", "31'", 1),
    # LIVE with ESPN "Congo DR" -> must remap to corpus "DR Congo"
    _event("POR", "Portugal", "1", "COD", "Congo DR", "1", "in", "70'", "70'", 2),
]}


# --------------------------------------------------------------------------- tests
def test_feed_down_is_unavailable():
    out = lb.todays_live_games("mlb", http_get=lambda url: {},
                               predictor_factory=_mlb_factory)
    assert out["status"] == "unavailable"
    assert out["games"] == []           # never fabricates a game
    assert "fabricate" in out["note"].lower() or "no scores" in out["note"].lower()


def test_unknown_sport():
    out = lb.todays_live_games("cricket", http_get=lambda url: {"events": []},
                               predictor_factory=_mlb_factory)
    assert out["status"] == "unknown_sport"
    assert out["games"] == []


def test_parse_normalized_rows():
    out = lb.todays_live_games("mlb", http_get=lambda url: _MLB_PAYLOAD,
                               predictor_factory=_mlb_factory)
    assert out["status"] == "ok"
    assert out["n_games"] == 3
    assert out["n_live"] == 2
    g = out["games"][0]
    assert g["home"] == "Houston Astros" and g["away"] == "Detroit Tigers"
    assert g["state"] == "in" and g["home_score"] == 4 and g["away_score"] == 2
    assert g["period"] == 9 and g["detail"] == "Top 9th"
    assert g["as_of"]                 # stamped
    # the FINAL game is present, marked post, and carries NO prediction
    post = out["games"][1]
    assert post["state"] == "post"
    assert "prediction" not in post


def test_inprogress_game_gets_ingame_prediction():
    out = lb.todays_live_games("mlb", http_get=lambda url: _MLB_PAYLOAD,
                               predictor_factory=_mlb_factory)
    g = out["games"][0]               # HOU 4-2 top 9th
    pred = g["prediction"]
    assert pred is not None
    assert "pregame" in pred and "ingame" in pred
    # in-game number moved sensibly above pregame for a late lead
    assert pred["pregame"]["p_home_win"] == 0.54
    assert pred["ingame"]["p_home_win"] == 0.96
    assert g["predictor_ids"] == {"home": "HOU", "away": "DET"}


def test_espn_abbr_remap_mlb():
    out = lb.todays_live_games("mlb", http_get=lambda url: _MLB_PAYLOAD,
                               predictor_factory=_mlb_factory)
    # the ATL vs SF game: ESPN 'SF' must resolve to corpus 'SFG'
    g = out["games"][2]
    assert g["predictor_ids"] == {"home": "ATL", "away": "SFG"}


def test_unresolvable_team_is_skipped_not_faked():
    # An event whose home team has NO abbreviation -> NBA resolver returns None -> skip.
    payload = {"events": [_event(None, "Mystery Team", "10", "LAL", "Los Angeles Lakers",
                                 "8", "in", "Q3 5:00", "5:00", 3)]}

    out = lb.todays_live_games("nba", http_get=lambda url: payload,
                               predictor_factory=_mlb_factory)  # any non-None predictor
    g = out["games"][0]
    assert g["prediction"] is None                  # never fabricated
    assert "resolve" in g["predict_note"].lower()


def test_predictor_unavailable_no_fabrication():
    out = lb.todays_live_games("mlb", http_get=lambda url: _MLB_PAYLOAD,
                               predictor_factory=_none_factory)
    assert out["predictor_available"] is False
    g = out["games"][0]               # live game, but no predictor
    assert g["prediction"] is None    # no fabricated number
    assert "predict_note" in g


def test_worldcup_pregame_only_when_no_predict_live():
    out = lb.todays_live_games("soccer_intl", http_get=lambda url: _INTL_PAYLOAD,
                               predictor_factory=_intl_factory)
    assert out["n_live"] == 2
    g = out["games"][0]               # England 1-0 Croatia
    pred = g["prediction"]
    assert pred is not None
    assert pred["pregame"]["p_home_win"] == 0.58
    assert "ingame" not in pred       # predictor has no predict_live
    assert "no in-game" in pred["ingame_note"].lower()
    # the Congo DR remap resolved to the corpus name
    assert out["games"][1]["predictor_ids"]["away"] == "DR Congo"


def test_nba_elapsed_minutes_from_period_and_clock():
    # Q3 with 5:00 remaining -> elapsed = 2*12 + (12-5) = 31.0 minutes
    assert lb._nba_elapsed(3, "5:00") == 31.0
    assert lb._nba_elapsed(1, "12:00") == 0.0
    assert lb._nba_elapsed(None, None) is None


def test_soccer_minute_parse():
    assert lb._soccer_minute("31'") == 31.0
    assert lb._soccer_minute("90'+5'") == 95.0
    assert lb._soccer_minute(None) is None


def test_resolve_team_paths():
    assert lb.resolve_team("nba", "SA", "San Antonio Spurs") == "SAS"
    assert lb.resolve_team("mlb", "TB", "Tampa Bay Rays") == "TAM"
    assert lb.resolve_team("soccer_intl", None, "England") == "England"
    assert lb.resolve_team("soccer_intl", None, "Congo DR") == "DR Congo"
    assert lb.resolve_team("nba", None, "Some Team") is None   # no abbr -> unresolved


# --------------------------------------------------------------------------- WNBA (LANE 2)
_WNBA_PAYLOAD = {"events": [
    # LIVE: Las Vegas Aces leading Indiana Fever 55-50, Q3 5:00 remaining
    _event(None, "Las Vegas Aces", "55", None, "Indiana Fever", "50",
           "in", "Q3 5:00", "5:00", 3),
]}


class _StubWNBAPredictor:
    """WNBA-shaped predictor: predict(home,away) + predict_live_state(...)."""

    def predict(self, home, away, **kw):  # noqa: ANN001
        return {"p_home_win": 0.62, "markets": {"moneyline": {"p_home_win": 0.62,
                                                              "p_away_win": 0.38}},
                "honest_note": "WNBA pregame Elo, moneyline only."}

    def predict_live_state(self, home, away, *, elapsed_minutes, home_score,
                           away_score, **kw):  # noqa: ANN001
        p = 0.85 if home_score > away_score else 0.5
        return {"p_home_win": p, "pregame_p_home": 0.62,
                "honest_note": "WNBA in-game blend."}


def _wnba_factory(sport):  # noqa: ANN001
    return _StubWNBAPredictor()


def test_wnba_espn_route_registered():
    assert lb._ESPN_ROUTES.get("wnba") == ("basketball/wnba", "wnba")


def test_wnba_resolve_team_passthrough_full_display_name():
    # WNBA corpus keys on the ESPN displayName directly (no short-code map).
    assert lb.resolve_team("wnba", None, "Las Vegas Aces") == "Las Vegas Aces"
    assert lb.resolve_team("wnba", None, None) is None


def test_wnba_elapsed_minutes_from_period_and_clock():
    # Q3 (period 3) with 5:00 remaining -> elapsed = 2*10 + (10-5) = 25.0 minutes
    assert lb._wnba_elapsed(3, "5:00") == 25.0
    assert lb._wnba_elapsed(1, "10:00") == 0.0
    assert lb._wnba_elapsed(None, None) is None


def test_wnba_inprogress_game_gets_pregame_and_ingame_prediction():
    out = lb.todays_live_games("wnba", http_get=lambda url: _WNBA_PAYLOAD,
                               predictor_factory=_wnba_factory)
    assert out["status"] == "ok"
    assert out["n_live"] == 1
    g = out["games"][0]
    assert g["home"] == "Las Vegas Aces" and g["away"] == "Indiana Fever"
    pred = g["prediction"]
    assert pred is not None
    assert pred["pregame"]["p_home_win"] == 0.62
    assert pred["ingame"]["p_home_win"] == 0.85  # home leading -> moved up
    assert g["predictor_ids"] == {"home": "Las Vegas Aces", "away": "Indiana Fever"}


def test_wnba_feed_down_is_unavailable():
    out = lb.todays_live_games("wnba", http_get=lambda url: {},
                               predictor_factory=_wnba_factory)
    assert out["status"] == "unavailable"
    assert out["games"] == []


# --------------------------------------------------- live_model_home_prob (in-game seam)
class _StubLiveIntlPredictor:
    """Soccer-shaped predictor: predict_live(home,away,minute,hg,ag) -> p_home_win."""
    def predict_live(self, home, away, minute, hg, ag, **kw):  # noqa: ANN001
        # monotone in score diff so the test can assert the sign is carried through
        base = 0.5 + 0.1 * (hg - ag) + 0.001 * minute
        return {"p_home_win": max(0.0, min(1.0, base)), "home": home, "away": away}


def test_live_model_home_prob_soccer(monkeypatch):
    monkeypatch.setitem(lb._PREDICTOR_CACHE, "soccer_intl", _StubLiveIntlPredictor())
    st = {"home": "ARG", "away": "AUT", "home_display": "Argentina",
          "away_display": "Austria", "home_goals": 1.0, "away_goals": 0.0,
          "frac_elapsed": 0.5}
    p = lb.live_model_home_prob("soccer_intl", st)
    assert p is not None and 0.5 < p < 1.0  # home leading -> > coin flip
    st_down = dict(st, home_goals=0.0, away_goals=1.0)
    assert lb.live_model_home_prob("soccer_intl", st_down) < 0.5  # trailing -> < coin flip


def test_live_model_home_prob_skips_unsupported_and_unresolved(monkeypatch):
    monkeypatch.setitem(lb._PREDICTOR_CACHE, "soccer_intl", _StubLiveIntlPredictor())
    # nba IS wired, but this state has no period/clock/scores -> honest None, not a
    # fabricated number (see test_live_model_home_prob_nba_* below for the wired path).
    assert lb.live_model_home_prob("nba", {"home": "BOS", "frac_elapsed": 0.5}) is None
    # a genuinely unsupported sport -> None (never fabricates a number)
    assert lb.live_model_home_prob("cricket", {"home": "IND", "frac_elapsed": 0.5}) is None
    # missing frac_elapsed -> None
    assert lb.live_model_home_prob("soccer_intl",
                                   {"home": "ARG", "home_display": "Argentina",
                                    "away": "AUT", "away_display": "Austria"}) is None
    # unresolved team (no display for a national team) -> None
    assert lb.live_model_home_prob("soccer_intl",
                                   {"home": "ARG", "away": "AUT",
                                    "frac_elapsed": 0.5}) is None


class _StubNbaShadow:
    """Deterministic stand-in for domains.basketball_nba.ingame_shadow's singleton --
    same contract as the real NbaIngameShadow.shadow_prob: None on incomplete state."""
    def shadow_prob(self, sport, home, away, state):
        if state.get("period") is None or state.get("clock") is None:
            return None
        if state.get("home_score") is None or state.get("away_score") is None:
            return None
        return 0.62


def test_live_model_home_prob_nba_complete_state(monkeypatch):
    import domains.basketball_nba.ingame_shadow as nba_shadow
    monkeypatch.setattr(nba_shadow, "get_shadow", lambda: _StubNbaShadow())
    st = {"home": "BOS", "away": "LAL", "period": 3, "clock": 200.0,
          "home_score": 62.0, "away_score": 58.0}
    assert lb.live_model_home_prob("nba", st) == 0.62


def test_live_model_home_prob_nba_incomplete_state_is_none(monkeypatch):
    import domains.basketball_nba.ingame_shadow as nba_shadow
    monkeypatch.setattr(nba_shadow, "get_shadow", lambda: _StubNbaShadow())
    # no period/clock/scores at all -> honest None, never a guessed number
    assert lb.live_model_home_prob("nba", {"home": "BOS", "away": "LAL"}) is None


def test_live_model_home_prob_wnba_complete_state(monkeypatch):
    import scripts.platformkit.ingame.wnba_ingame_shadow as wshadow
    monkeypatch.setattr(wshadow, "get_shadow", lambda: _StubNbaShadow())  # same contract
    st = {"home": "LVA", "away": "NYL", "period": 2, "clock": 320.0,
          "home_score": 41.0, "away_score": 38.0}
    assert lb.live_model_home_prob("wnba", st) == 0.62


def test_live_model_home_prob_wnba_incomplete_state_is_none(monkeypatch):
    import scripts.platformkit.ingame.wnba_ingame_shadow as wshadow
    monkeypatch.setattr(wshadow, "get_shadow", lambda: _StubNbaShadow())
    assert lb.live_model_home_prob("wnba", {"home": "LVA", "away": "NYL"}) is None
