"""Tests for model_progress -- the two-axis 'getting better?' readout.

Per-file: python -m pytest scripts/platformkit/clv/test_model_progress.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import model_progress as M


def _entry(sport, ts, brier=None, ece=None, n=0, verdict="INSUFFICIENT_DATA",
           bss=None, n_close=0):
    rd = {"n": n, "raw_brier": brier, "raw_ece": ece, "bss_vs_close": bss,
          "n_with_close": n_close, "pct_beat_close": None}
    return {"sport": sport, "ts": ts, "verdict": verdict, "readout": rd}


_EMPTY_CLV = {"coverage_pct": 0.0, "total_settled": 0, "total_measurable": 0,
              "verdict": "none"}


def test_data_gated_when_few_settled():
    rows = [_entry("mlb", "2026-06-25T01:00:00Z", brier=0.22, ece=0.31, n=30)]
    p = M.progress(rows, clv=_EMPTY_CLV)
    s = p["sports"][0]
    assert s["n_settled"] == 30
    assert "DATA-GATED" in s["verdict"]


def test_calibration_improving_trend():
    rows = [
        _entry("mlb", "2026-06-20T01:00:00Z", brier=0.30, ece=0.40, n=80),
        _entry("mlb", "2026-06-25T01:00:00Z", brier=0.22, ece=0.28, n=80),
    ]
    p = M.progress(rows, clv=_EMPTY_CLV)
    s = p["sports"][0]
    assert s["brier_trend"] == "improving"
    assert "IMPROVING" in s["verdict"]


def test_regressing_flagged():
    rows = [
        _entry("mlb", "2026-06-20T01:00:00Z", brier=0.20, ece=0.25, n=80),
        _entry("mlb", "2026-06-25T01:00:00Z", brier=0.28, ece=0.33, n=80),
    ]
    p = M.progress(rows, clv=_EMPTY_CLV)
    assert p["sports"][0]["brier_trend"] == "worse"
    assert "REGRESSING" in p["sports"][0]["verdict"]


def test_no_data_sport():
    rows = [_entry("tennis", "2026-06-25T01:00:00Z", brier=None, n=0)]
    p = M.progress(rows, clv=_EMPTY_CLV)
    assert p["sports"][0]["verdict"].startswith("NO DATA")


def test_ship_and_insufficient_counts_and_render():
    rows = [
        _entry("mlb", "2026-06-20T01:00:00Z", brier=0.30, ece=0.40, n=80,
               verdict="SHIP"),
        _entry("mlb", "2026-06-25T01:00:00Z", brier=0.22, ece=0.28, n=80,
               verdict="INSUFFICIENT_DATA", bss=0.05),
    ]
    p = M.progress(rows, clv=_EMPTY_CLV)
    assert p["ship_count"] == 1
    assert p["insufficient_count"] == 1
    txt = M.render(p)
    assert "GETTING BETTER" in txt and "AXIS 1" in txt and "AXIS 2" in txt
