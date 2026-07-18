"""Synthetic tests for own_lines.py -- band math + quote shape. No network/data/ access.
Run: python -m pytest scripts/platformkit/kalshi_complete/test_own_lines.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.kalshi_complete import own_lines as ol


def test_half_width_floor():
    # near p=0 or p=1 the sqrt term vanishes -> floor must hold
    assert ol.band_half_width(0.001, n_eff=1000.0) == ol.MIN_HALF_WIDTH
    assert ol.band_half_width(0.999, n_eff=1000.0) == ol.MIN_HALF_WIDTH


def test_half_width_monotone_decreasing_in_n_eff():
    p = 0.5
    hw_small_n = ol.band_half_width(p, n_eff=20.0)
    hw_big_n = ol.band_half_width(p, n_eff=2000.0)
    assert hw_small_n >= hw_big_n  # more effective sample -> tighter (or equal, if floor hit)


def test_quote_contains_p_fair():
    for p in (0.05, 0.3, 0.5, 0.72, 0.95):
        q = ol.quote_from_p(p, n_eff=50.0)
        assert q["bid"] <= p <= q["ask"]
        assert 0.0 <= q["bid"] <= q["ask"] <= 1.0


def test_own_quote_passes_through_no_data(monkeypatch):
    def _fake_dispatch(sport, home, away, ingame_state=None):
        return {"status": "no_data", "as_of": "2026-07-18T00:00:00+00:00",
                "note": "predict_matchup produced no JSON"}
    monkeypatch.setattr(ol, "dispatch", _fake_dispatch)
    row = ol.own_quote("mlb", "NYY", "BOS")
    assert row["status"] == "no_data"
    assert row["p_fair"] is None and row["bid"] is None and row["ask"] is None
    assert row["edge_claimed"] is False


def test_own_quote_ok_shape(monkeypatch):
    def _fake_dispatch(sport, home, away, ingame_state=None):
        return {"status": "ok", "as_of": "2026-07-18T00:00:00+00:00", "p_home_win": 0.62,
                "pregame": {"p_home_win": 0.62, "honest_note": "calibration only"}}
    monkeypatch.setattr(ol, "dispatch", _fake_dispatch)
    row = ol.own_quote("nba", "BOS", "MIA")
    assert row["status"] == "ok"
    assert row["p_fair"] == 0.62
    assert row["bid"] <= row["p_fair"] <= row["ask"]
    assert row["edge_claimed"] is False
    dumped = json.dumps(row)
    assert "roi" not in dumped.lower()
    assert "profit" not in dumped.lower()


if __name__ == "__main__":
    test_half_width_floor()
    test_half_width_monotone_decreasing_in_n_eff()
    test_quote_contains_p_fair()
    print("own_lines synthetic checks OK")
