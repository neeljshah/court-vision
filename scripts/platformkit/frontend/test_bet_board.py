"""Per-file tests for the per-game bet board (network-free, corpus-free).

A STUBBED predictor returns a known per-sport markets dict, so every assertion is
deterministic and runs with NO live data and NO network. Validates: the uniform
schema, populated groups, fair_odds == 1/model_prob, EV computed when a price is
supplied + null when not, ranked + capped best_bets, and live rows when a live
state is given.

Run ONLY this file (and frontend/test_serve.py):
    python -m pytest scripts/platformkit/frontend/test_bet_board.py -q
"""
from __future__ import annotations

import math
from typing import Any, Dict

import pytest

from scripts.platformkit.frontend import bet_board as bb

# --------------------------------------------------------------------------- #
# Known per-sport markets surfaces (shapes mirror the real domain markets).
# --------------------------------------------------------------------------- #
_NBA = {
    "moneyline": {"p_home_win": 0.60, "p_away_win": 0.40},
    "spread_main": {"line_home": 0.0, "p_home_cover": 0.60, "p_away_cover": 0.40},
    "spread_ladder": [{"line": -3.5, "over": 0.45, "under": 0.55}],
    "total_ladder": [{"line": 220.5, "over": 0.52, "under": 0.48}],
    "team_total_home": {"ladder": [{"line": 112.5, "over": 0.5, "under": 0.5}]},
    "team_total_away": {"ladder": [{"line": 108.5, "over": 0.5, "under": 0.5}]},
    "q1": {"p_home_win": 0.55, "p_away_win": 0.45, "total_line": 52.5,
           "over": 0.51, "under": 0.49},
}
_MLB = {
    "moneyline": {"home": 0.65, "away": 0.35},
    "run_line": {"standard": {"home_minus_1.5": 0.50, "away_plus_1.5": 0.50,
                              "away_minus_1.5": 0.21, "home_plus_1.5": 0.79},
                 "alternates": [{"line": 2.5, "p_home_cover_minus": 0.41,
                                 "p_away_cover_minus": 0.15}]},
    "game_total": [{"line": 8.5, "over": 0.50, "under": 0.50}],
    "team_totals": {"home": {"lines": [{"line": 4.5, "over": 0.54, "under": 0.46}]},
                    "away": {"lines": [{"line": 3.5, "over": 0.44, "under": 0.56}]}},
    "first_5_innings": {"f5_ml_home_2way": 0.63, "f5_ml_away_2way": 0.37,
                        "f5_totals": [{"line": 4.5, "over": 0.48, "under": 0.52}]},
}
_SOCCER = {
    "1X2_home": 0.58, "1X2_draw": 0.27, "1X2_away": 0.15,
    "dc_1X": 0.85, "dc_12": 0.73, "dc_X2": 0.42,
    "dnb_home": 0.79, "dnb_away": 0.21, "btts_yes": 0.37, "btts_no": 0.63,
    "over_2.5": 0.36, "under_2.5": 0.64,
    "team_home_over_1.5": 0.44, "ah_home_-0.5": 0.58,
    "cs_home_clean": 0.53, "cs_away_clean": 0.22, "wm_home_by_1": 0.27,
}
_TENNIS = {
    "match_winner": {"p1": 0.41, "p2": 0.59},
    "set_score": {"0-2": 0.32, "2-0": 0.19},
    "total_sets": {"line": 2.5, "over": 0.49, "under": 0.51},
    "set_handicap": [{"side": "p1", "line": -1.5, "cover": 0.19}],
    "total_games": {"ou": [{"line": 22.5, "over": 0.65, "under": 0.35}]},
    "game_handicap": [{"side": "p1", "line": 2.5, "cover": 0.59}],
    "per_set_winner": {"p1": 0.43, "p2": 0.57},
}
# WNBA is moneyline-only (see predict_matchup._pregame_block wnba branch --
# no spread/total model exists yet); reuses flatten_nba's guarded .get(...)
# reads, so only the moneyline rows should ever come out.
_WNBA = {"moneyline": {"p_home_win": 0.69, "p_away_win": 0.31}}
_SURFACES = {"nba": _NBA, "mlb": _MLB, "soccer": _SOCCER, "soccer_intl": _SOCCER,
             "tennis": _TENNIS, "wnba": _WNBA}


class _StubPredictor:
    """A placeholder built-predictor object (presence routes past the corpus gate).

    The bet board calls pm.build_result(sport, predictor, ns); we patch build_result
    (see autouse fixture) so this object only needs to be non-None.
    """


def _fake_build_result(sport: str, predictor: Any, ns: Any) -> Dict[str, Any]:
    """Deterministic stand-in for predict_matchup.build_result: returns a known
    pregame markets surface per sport (+ an in-game block when ns carries a live
    state), with NO corpus and NO network."""
    s = sport.lower()
    out: Dict[str, Any] = {"sport": s, "home": ns.home, "away": ns.away,
                           "pregame": {"markets": _SURFACES[s],
                                       "honest_note": "matches the close"}}
    if getattr(ns, "_live", False):
        out["ingame"] = {"p_home_win": 0.72, "pregame_p_home": 0.60,
                         "honest_note": "in-game re-priced"}
    return out


@pytest.fixture(autouse=True)
def _patch_build_result(monkeypatch):
    monkeypatch.setattr(bb.pm, "build_result", _fake_build_result)


def _board(sport: str, home="H", away="A", *, live=None, **kw):
    # mark live on the predictor stub via a closure: game_bet_board builds ns
    # internally, so we tag it through build_result by carrying live in kw.
    return bb.game_bet_board(sport, home, away, predictor=_StubPredictor(),
                             live=live, **kw)


# --------------------------------------------------------------------------- #
def test_uniform_schema_all_sports():
    for sport in ("nba", "mlb", "soccer", "soccer_intl", "tennis", "wnba"):
        b = _board(sport)
        assert set(b) >= {"sport", "home", "away", "status", "as_of", "live",
                          "best_bets", "groups", "honest_note"}
        assert b["status"] == "ok"
        assert b["groups"], f"{sport} groups empty"
        for grp in b["groups"]:
            assert grp["bets"]
            for r in grp["bets"]:
                assert set(r) >= {"group", "selection", "model_prob", "line",
                                  "fair_odds", "best_book", "best_price",
                                  "ev_pct", "verdict", "note"}


def test_fair_odds_is_reciprocal_of_prob():
    b = _board("nba")
    for grp in b["groups"]:
        for r in grp["bets"]:
            p, fo = r["model_prob"], r["fair_odds"]
            if isinstance(p, float) and 0 < p < 1:
                assert fo is not None and math.isclose(fo, 1.0 / p, rel_tol=1e-3)


def test_groups_cover_expected_markets():
    names = {g["name"] for g in _board("nba")["groups"]}
    assert {"Moneyline", "Spread", "Total"} <= names
    assert "1st quarter" in names
    snames = {g["name"] for g in _board("soccer")["groups"]}
    assert {"1X2", "Double chance", "Draw no bet", "Both teams to score"} <= snames
    mnames = {g["name"] for g in _board("mlb")["groups"]}
    assert {"Moneyline", "Run line", "Game total", "First 5 innings"} <= mnames
    tnames = {g["name"] for g in _board("tennis")["groups"]}
    assert {"Match winner", "Total sets", "Total games"} <= tnames


def test_ev_null_without_prices():
    b = _board("nba")
    for grp in b["groups"]:
        for r in grp["bets"]:
            assert r["ev_pct"] is None and r["best_price"] is None


def test_ev_computed_when_price_supplied():
    # supply a multi-book moneyline price for the home team only
    def odds_lookup(sport, home, away):
        return {"BookX": {home: 2.0}, "BookY": {home: 1.85}}
    b = _board("nba", odds_lookup=odds_lookup)
    ml = next(g for g in b["groups"] if g["name"] == "Moneyline")
    home_row = next(r for r in ml["bets"] if r["selection"] == "H")
    # best price 2.0 from BookX; ev = 0.60*2.0 - 1 = 0.20 -> 20.0%
    assert home_row["best_book"] == "BookX"
    assert home_row["best_price"] == 2.0
    assert math.isclose(home_row["ev_pct"], 20.0, rel_tol=1e-6)
    assert home_row["verdict"] == "PRICED+EV"
    # away has no price -> ev null, fair odds still present
    away_row = next(r for r in ml["bets"] if r["selection"] == "A")
    assert away_row["ev_pct"] is None and away_row["fair_odds"] is not None


def test_best_bets_ranked_and_capped():
    def odds_lookup(sport, home, away):
        return {"BookX": {home: 2.0}}
    b = _board("nba", odds_lookup=odds_lookup)
    assert len(b["best_bets"]) <= 8
    # priced row (the +EV home ML) should rank first when a price exists
    assert b["best_bets"][0]["ev_pct"] is not None
    # no-price board falls back to confidence ranking, still capped
    b2 = _board("soccer")
    assert 0 < len(b2["best_bets"]) <= 8
    confs = [abs(r["model_prob"] - 0.5) for r in b2["best_bets"]]
    assert confs == sorted(confs, reverse=True)
    assert "model VIEW" in b2["best_bets"][0]["note"]


def test_live_rows_when_live_supplied():
    live = {"state": "in_progress", "home_score": 55, "away_score": 50,
            "clock": "Q3 4:12"}
    b = _board("nba", live=live)
    assert b["live"]["home_score"] == 55 and b["live"]["clock"] == "Q3 4:12"
    live_grp = [g for g in b["groups"] if g["name"] == "LIVE Moneyline"]
    assert live_grp, "no live rows emitted"
    row = live_grp[0]["bets"][0]
    assert row["verdict"] == "LIVE" and math.isclose(row["model_prob"], 0.72)
    # no live state -> no live block, no live rows
    b2 = _board("nba")
    assert b2["live"] is None
    assert not any(g["name"] == "LIVE Moneyline" for g in b2["groups"])


def test_unknown_sport():
    b = bb.game_bet_board("cricket", "H", "A", predictor=_StubPredictor())
    assert b["status"] == "unknown_sport"
    assert b["groups"] == [] and b["best_bets"] == []


def test_wnba_in_sports_and_moneyline_only():
    assert "wnba" in bb.SPORTS
    b = _board("wnba")
    assert b["status"] == "ok"
    names = {g["name"] for g in b["groups"]}
    # moneyline-only: no spread/total groups fabricated for a sport with no
    # such model yet.
    assert names == {"Moneyline"}
    ml = next(g for g in b["groups"] if g["name"] == "Moneyline")
    assert {r["selection"] for r in ml["bets"]} == {"H", "A"}


def test_wnba_honest_no_odds_degrade_then_priced_when_matched():
    # no odds_lookup -> fair odds only, no price/EV fabricated
    b_no_odds = _board("wnba")
    ml = next(g for g in b_no_odds["groups"] if g["name"] == "Moneyline")
    home_row = next(r for r in ml["bets"] if r["selection"] == "H")
    assert home_row["best_price"] is None and home_row["ev_pct"] is None
    assert home_row["fair_odds"] is not None

    def odds_lookup(sport, home, away):
        return {"kalshi": {home: 1.45}}
    b_priced = _board("wnba", odds_lookup=odds_lookup)
    ml2 = next(g for g in b_priced["groups"] if g["name"] == "Moneyline")
    home_row2 = next(r for r in ml2["bets"] if r["selection"] == "H")
    assert home_row2["best_price"] == 1.45
    assert home_row2["best_book"] == "kalshi"
