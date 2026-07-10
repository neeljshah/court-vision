"""Per-file test: scripts/platformkit/ingame/test_inplay_capture_bridge.py
Run: python -m pytest scripts/platformkit/ingame/test_inplay_capture_bridge.py -q

Covers the Kalshi-ticker -> ESPN-live-state BRIDGE that makes in-play (in-game) game-market
trading actually fire: the capture loop keys games by their Kalshi ticker, which never equals
the ESPN numeric event id, so live_state(sport, ticker) misses. _scan_live_by_legs bridges by
matching the legs' team-name labels to an in-progress ESPN game. NO network: all callbacks
injected; _ls.live_states monkeypatched. Failure mode is "no bet", never a misaligned bet.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

from scripts.platformkit.ingame import inplay_capture_loop as L


_LIVE_USA_MEX = {
    "sport": "soccer_intl", "home": "USA", "away": "MEX",
    "home_display": "United States", "away_display": "Mexico",
    "home_goals": 1.0, "away_goals": 0.0, "state_diff": 1.0,
    "frac_elapsed": 0.6, "p0": 0.55, "p0_source": "PRIOR",
}


def _kalshi_legs():
    # a realistic two-way market (overround sum > 1) keyed by a Kalshi ticker, full-name legs
    return [{"game_id": "KXWCGAME-26JUN22USAMEX", "side": "United States", "prob": 0.58},
            {"game_id": "KXWCGAME-26JUN22USAMEX", "side": "Mexico", "prob": 0.47}]


def test_scan_live_by_legs_matches_by_team(monkeypatch):
    monkeypatch.setattr(L._ls, "live_states",
                        lambda sport, **kw: [_LIVE_USA_MEX] if sport == "soccer_intl" else [])
    legs = {"United States": 0.58, "Mexico": 0.47}
    st = L._scan_live_by_legs("soccer_intl", legs)
    assert st is not None and st["home"] == "USA" and st["away"] == "MEX"


def test_scan_returns_none_when_no_team_match(monkeypatch):
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_USA_MEX])
    # legs for a different game -> no alignment -> None (never a misaligned pair)
    assert L._scan_live_by_legs("soccer_intl", {"Brazil": 0.6, "Spain": 0.5}) is None


def test_scan_requires_both_teams_not_one(monkeypatch):
    """A market sharing ONE team with the live game (e.g. live ARG-AUT vs a future JOR-ARG
    market, both containing Argentina) must NOT bind -- both teams are required."""
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_USA_MEX])
    # United States is live (USA-MEX) but this market is USA-Canada -> only one team shared
    assert L._scan_live_by_legs("soccer_intl",
                                {"United States": 0.6, "Canada": 0.5}) is None
    # both teams present (order-independent) -> binds
    assert L._scan_live_by_legs("soccer_intl",
                                {"Mexico": 0.47, "United States": 0.58}) is not None


def test_draw_leg_folds_into_field():
    # 3-way soccer market: the draw leg is detected and folded into the not-home complement
    legs = {"Argentina": 0.84, "Tie": 0.12, "Austria": 0.05}
    assert L._draw_leg(legs) == 0.12
    folded = L._fold_draw_into_field({"yes_home": 0.84, "yes_away": 0.05}, legs)
    assert folded["yes_home"] == 0.84
    assert abs(folded["yes_away"] - 0.17) < 1e-9   # 0.05 away + 0.12 draw = field
    # a 2-way market (no draw leg) is unchanged
    legs2 = {"NYY": 0.55, "BOS": 0.50}
    assert L._draw_leg(legs2) is None
    assert L._fold_draw_into_field({"yes_home": 0.55, "yes_away": 0.50}, legs2) == \
        {"yes_home": 0.55, "yes_away": 0.50}


def test_threeway_market_pairs_not_bad_price(monkeypatch, tmp_path):
    """A live soccer game on a 3-way Kalshi market (home/draw/away) must PAIR (devig folds
    the draw into the field), not throw bad_price as a naive 2-way devig would."""
    monkeypatch.setattr(L._ls, "live_states",
                        lambda sport, **kw: [_LIVE_USA_MEX])
    ticks = [{"game_id": "KXWCGAME-26JUN22USAMEX", "side": "United States", "prob": 0.60},
             {"game_id": "KXWCGAME-26JUN22USAMEX", "side": "Tie", "prob": 0.25},
             {"game_id": "KXWCGAME-26JUN22USAMEX", "side": "Mexico", "prob": 0.20}]
    hb = L.poll_once(sports=["soccer_intl"], inplay_fetch_fn=lambda s: ticks,
                     live_state_fn=lambda s, g: None, model_fn=lambda s, st: 0.55,
                     finals_fn=lambda s: [], grade_dir=tmp_path / "g",
                     ledger_path=tmp_path / "l.jsonl",
                     now=datetime(2026, 6, 22, 20, 0, 0, tzinfo=timezone.utc))  # ticket's own ET date
    g = hb["games"][0]
    assert g["paired"] is True and g["reason"] != "bad_price"
    assert g["devigged_price"] is not None  # 0.60/(0.60+0.25+0.20) ~ 0.571


def test_bridge_enables_ingame_bet(monkeypatch, tmp_path):
    """Full chain: Kalshi-id miss -> bridge by team -> calibrated model -> gates -> tier bet."""
    monkeypatch.setattr(L._ls, "live_states",
                        lambda sport, **kw: [_LIVE_USA_MEX] if sport == "soccer_intl" else [])
    hb = L.poll_once(
        sports=["soccer_intl"],
        inplay_fetch_fn=lambda s: _kalshi_legs(),
        live_state_fn=lambda s, g: None,        # simulate the Kalshi-ticker miss
        model_fn=lambda s, st: 0.82,            # stub calibrated P(home win) as-of tick
        finals_fn=lambda s: [],
        grade_dir=tmp_path / "grade",
        ledger_path=tmp_path / "ingame_ledger.jsonl",
        now=datetime(2026, 6, 22, 20, 0, 0, tzinfo=timezone.utc),  # ticket's own ET date
    )
    assert hb["n_pairs"] == 1 and hb["n_bets"] == 1
    g = hb["games"][0]
    assert g["paired"] is True and g["bet"] is True
    assert g["action"] == "bet" and g["tier"] in ("A", "B", "C") and g["reason"] == "ok"


_LIVE_MIL_PIT = {
    "sport": "mlb", "home": "PIT", "away": "MIL",
    "home_display": "Pittsburgh Pirates", "away_display": "Milwaukee Brewers",
    "home_runs": 3.0, "away_runs": 2.0, "state_diff": 1.0,
    "frac_elapsed": 0.7, "p0": 0.5, "p0_source": "PRIOR",
}
_MIL_PIT_LEGS = {"Pittsburgh Pirates": 0.465, "Milwaukee Brewers": 0.535}
_NOW_JUL10_EVENING = datetime(2026, 7, 10, 22, 0, 0, tzinfo=timezone.utc)  # ~18:00 ET Jul 10


def test_date_guard_rejects_tomorrow_dated_ticker(monkeypatch):
    """Series wrong-date class: tonight's live MIL@PIT must NOT bind to tomorrow's market
    ticket even though the team names are identical (mental-revert of the guard -> binds)."""
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_MIL_PIT])
    st = L._scan_live_by_legs("mlb", _MIL_PIT_LEGS,
                              gid="KXMLBGAME-26JUL111605MILPIT", nowdt=_NOW_JUL10_EVENING)
    assert st is None


def test_date_guard_allows_today_dated_ticker(monkeypatch):
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_MIL_PIT])
    st = L._scan_live_by_legs("mlb", _MIL_PIT_LEGS,
                              gid="KXMLBGAME-26JUL101840MILPIT", nowdt=_NOW_JUL10_EVENING)
    assert st is not None


def test_date_guard_allows_yesterday_dated_ticker(monkeypatch):
    """Past-midnight-ET finish: a game ticketed for ET-yesterday can still be live now."""
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_MIL_PIT])
    st = L._scan_live_by_legs("mlb", _MIL_PIT_LEGS,
                              gid="KXMLBGAME-26JUL091840MILPIT", nowdt=_NOW_JUL10_EVENING)
    assert st is not None


def test_date_guard_noop_on_unparseable_ticker(monkeypatch):
    """No parseable ticker date -> honest no-info -> old team-only behavior unchanged."""
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [_LIVE_MIL_PIT])
    st = L._scan_live_by_legs("mlb", _MIL_PIT_LEGS,
                              gid="MALFORMED-NO-DATE-MILPIT", nowdt=_NOW_JUL10_EVENING)
    assert st is not None


def test_no_live_game_no_bet(monkeypatch, tmp_path):
    monkeypatch.setattr(L._ls, "live_states", lambda sport, **kw: [])  # nothing in progress
    hb = L.poll_once(
        sports=["soccer_intl"],
        inplay_fetch_fn=lambda s: _kalshi_legs(),
        live_state_fn=lambda s, g: None,
        model_fn=lambda s, st: 0.82,
        finals_fn=lambda s: [],
        grade_dir=tmp_path / "grade",
        ledger_path=tmp_path / "ingame_ledger.jsonl",
    )
    assert hb["n_bets"] == 0
    assert hb["games"][0]["reason"] == "no_live_state"  # honest: no fabricated game
