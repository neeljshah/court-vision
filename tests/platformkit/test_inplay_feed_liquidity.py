"""Per-file test: inplay_feed.default_fetch liquidity routing (4b) + 2c freshness.

Proves the liquidity-gate bypass is CLOSED:
  * Kalshi (is_liquid-gated) is the PRIMARY source -> its ticks are tagged
    tradeable=True (and carry a status/source_ts so the daemon's native gate admits
    them);
  * ESPN and Polymarket moneylines carry NO venue depth -> tagged tradeable=False
    (DEGRADED corroborators, never a tradeable in-play price) -- an ungated/frozen
    ESPN:DraftKings line can NOT be graded as in-play;
  * per-source error isolation: a Kalshi/ESPN/PM failure never sinks the others.

Offline: every source is monkeypatched; no network.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_feed_liquidity.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import inplay_feed


def _kalshi_tick():
    # The canonical liquid Kalshi in-play tick (already is_liquid-gated upstream).
    return {"sport": "nba", "game_id": "KXNBAGAME-x", "venue": "kalshi",
            "market_type": "moneyline", "side": "CHC", "ticker": "KXNBAGAME-x-CHC",
            "prob": 0.54, "ts": "2026-06-18T23:30:00Z", "phase": "in_play"}


def _espn_tick():
    return {"sport": "nba", "game_id": "401", "venue": "espn:DraftKings",
            "market_type": "moneyline", "side": "home", "ticker": "401",
            "prob": 0.5455, "commence_time": None, "close_time": None,
            "status": "in", "source_ts": "2026-06-18T23:29:30+00:00"}


class _FakeEvent:
    event_id = "PM-1"
    commence_time = "2026-06-18T23:00:00Z"
    prices = {"polymarket": {"home": 1.8, "away": 2.2}}


class _FakePM:
    name = "polymarket"

    def fetch(self, sport):
        return [_FakeEvent()]


def _patch(monkeypatch, *, kalshi=None, espn=None, pm=True):
    monkeypatch.setattr(inplay_feed, "fetch_scoreboard", lambda s: None,
                        raising=False)
    import scripts.platformkit.odds_provider.inplay_kalshi as ik
    import scripts.platformkit.odds_provider.inplay_espn as ie
    import scripts.platformkit.odds_provider.polymarket as pmmod
    monkeypatch.setattr(ik, "fetch_inplay",
                        kalshi if kalshi is not None else (lambda s: []))
    monkeypatch.setattr(ie, "fetch_espn_inplay",
                        espn if espn is not None else (lambda s: []))
    if pm:
        monkeypatch.setattr(pmmod, "PolymarketProvider", _FakePM)
    else:
        monkeypatch.setattr(pmmod, "PolymarketProvider",
                            lambda: (_ for _ in ()).throw(RuntimeError("down")))


def test_kalshi_primary_tradeable_espn_pm_degraded(monkeypatch):
    _patch(monkeypatch, kalshi=lambda s: [_kalshi_tick()],
           espn=lambda s: [_espn_tick()], pm=True)
    out = inplay_feed.default_fetch("nba")
    by_venue = {t["venue"]: t for t in out}
    # Kalshi is the only PROVEN-tradeable in-play price.
    assert by_venue["kalshi"]["tradeable"] is True
    assert by_venue["kalshi"]["status"] == "in"
    assert by_venue["kalshi"]["source_ts"]  # carries a feed time for the 2c guard
    # ESPN + PM are DEGRADED corroborators, never tradeable in-play prices.
    assert by_venue["espn:DraftKings"]["tradeable"] is False
    assert by_venue["polymarket"]["tradeable"] is False
    # Exactly one tradeable tick -> the ungated ESPN line is NOT an in-play price.
    assert sum(1 for t in out if t["tradeable"]) == 1


def test_espn_failure_does_not_sink_kalshi(monkeypatch):
    def _boom(_s):
        raise RuntimeError("espn down")
    _patch(monkeypatch, kalshi=lambda s: [_kalshi_tick()], espn=_boom, pm=False)
    out = inplay_feed.default_fetch("nba")
    assert any(t["venue"] == "kalshi" and t["tradeable"] for t in out)


def test_kalshi_failure_does_not_sink_espn_corroborator(monkeypatch):
    def _boom(_s):
        raise RuntimeError("kalshi down")
    _patch(monkeypatch, kalshi=_boom, espn=lambda s: [_espn_tick()], pm=False)
    out = inplay_feed.default_fetch("nba")
    # ESPN still surfaces but ONLY as a degraded (non-tradeable) corroborator.
    assert out and all(t["tradeable"] is False for t in out)
