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


def test_remaining_frac_nba_and_mlb():
    assert ol.remaining_frac("nba", None) is None
    assert ol.remaining_frac("nba", {"elapsed": 0.0}) == 1.0
    assert ol.remaining_frac("nba", {"elapsed": 48.0}) == 0.0
    assert ol.remaining_frac("nba", {"elapsed": 24.0}) == 0.5
    assert ol.remaining_frac("wnba", {"elapsed": 20.0}) == 0.5
    # mlb: bottom of the 8th of 9 -> progress 7.5/9 elapsed, 1.5/9 remaining
    frac = ol.remaining_frac("mlb", {"inning": 8, "half": "bottom"})
    assert abs(frac - (1.5 / 9.0)) < 1e-9
    assert ol.remaining_frac("mlb", {"inning": 1}) is None  # missing half


def test_n_eff_for_state_tightens_late_never_widens():
    # pregame / no state -> unchanged baseline
    assert ol.n_eff_for_state("nba", None) == ol.DEFAULT_N_EFF
    # tip-off (remaining_frac=1) -> baseline
    assert ol.n_eff_for_state("nba", {"elapsed": 0.0}) == ol.DEFAULT_N_EFF
    # late game -> n_eff must RISE (tighter band), never fall below baseline
    late = ol.n_eff_for_state("nba", {"elapsed": 46.0})
    assert late > ol.DEFAULT_N_EFF
    # floor at 0.1 remaining_frac caps the tightening at 10x
    final_seconds = ol.n_eff_for_state("nba", {"elapsed": 47.99})
    assert final_seconds <= ol.DEFAULT_N_EFF / 0.1 + 1e-6
    # monotone: half_width using the late n_eff must be <= half_width at baseline
    hw_base = ol.band_half_width(0.5, n_eff=ol.DEFAULT_N_EFF)
    hw_late = ol.band_half_width(0.5, n_eff=late)
    assert hw_late <= hw_base


def test_own_quote_ingame_forwards_state_and_tightens_band(monkeypatch):
    captured = {}

    def _fake_dispatch(sport, home, away, ingame_state=None):
        captured["ingame_state"] = ingame_state
        return {"status": "ok", "as_of": "2026-07-18T00:00:00+00:00", "p_home_win": 0.7,
                "pregame": {"p_home_win": 0.55, "honest_note": "calibration only"},
                "ingame": {"p_home_win": 0.7}}
    monkeypatch.setattr(ol, "dispatch", _fake_dispatch)

    state = {"elapsed": 46.0, "home_score": 100, "away_score": 90}
    row = ol.own_quote("nba", "BOS", "MIA", ingame_state=state)
    assert captured["ingame_state"] == state  # CLI-built dict reaches dispatch() verbatim
    assert row["status"] == "ok" and row["p_fair"] == 0.7
    assert "heuristic" in row["band_basis"]

    pregame_row = ol.own_quote("nba", "BOS", "MIA", ingame_state=None)
    # same p not guaranteed equal (fake ignores state for p), but the late-game
    # band must be no wider than a pregame band at the same n_eff-derived p.
    hw_ingame = row["ask"] - row["bid"]
    hw_pregame_equiv = ol.quote_from_p(0.7, ol.DEFAULT_N_EFF)
    assert hw_ingame <= (hw_pregame_equiv["ask"] - hw_pregame_equiv["bid"])


if __name__ == "__main__":
    test_half_width_floor()
    test_half_width_monotone_decreasing_in_n_eff()
    test_quote_contains_p_fair()
    test_remaining_frac_nba_and_mlb()
    test_n_eff_for_state_tightens_late_never_widens()
    test_own_quote_ingame_forwards_state_and_tightens_band()
    print("own_lines synthetic checks OK")
