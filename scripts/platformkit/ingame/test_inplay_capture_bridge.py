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
    )
    assert hb["n_pairs"] == 1 and hb["n_bets"] == 1
    g = hb["games"][0]
    assert g["paired"] is True and g["bet"] is True
    assert g["action"] == "bet" and g["tier"] in ("A", "B", "C") and g["reason"] == "ok"


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
