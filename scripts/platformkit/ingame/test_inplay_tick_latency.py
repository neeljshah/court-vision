"""Per-file tests for inplay_tick_latency (synthetic tick corpora).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_inplay_tick_latency.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.platformkit.ingame import inplay_tick_latency as tl


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_ticks(dirp: Path, stem: str, ts_list, extra=None) -> None:
    dirp.mkdir(parents=True, exist_ok=True)
    with open(dirp / ("%s.jsonl" % stem), "w", encoding="utf-8") as fh:
        for ts in ts_list:
            row = {"sport": "mlb", "game_id": stem, "ts": _iso(ts),
                  "market_prob": 0.5, "model_prob": 0.5}
            if extra:
                row.update(extra)
            fh.write(json.dumps(row) + "\n")


def test_insufficient_data_below_min_ticks(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    _write_ticks(d, "G1", [base + timedelta(seconds=30 * i) for i in range(5)])
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["n_ticks"] == 5
    assert res["verdict"] == "INSUFFICIENT_DATA"


def test_green_verdict_regular_cadence(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    # 30s cadence, well under the 120s p90 threshold
    _write_ticks(d, "G1", [base + timedelta(seconds=30 * i) for i in range(40)])
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["verdict"] == "GREEN"
    assert res["gap_p50_sec"] == 30.0
    assert res["ticks_per_live_game_hour"] is not None


def test_degraded_verdict_slow_cadence(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    # 200s cadence > 120s p90 threshold
    _write_ticks(d, "G1", [base + timedelta(seconds=200 * i) for i in range(40)])
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["verdict"] == "DEGRADED"


def test_large_gap_excluded_as_window_break(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    times = [base + timedelta(seconds=30 * i) for i in range(25)]
    # one huge gap (game paused/ended) -- must not count as a live-window gap
    times += [base + timedelta(hours=5) + timedelta(seconds=30 * i) for i in range(25)]
    _write_ticks(d, "G1", times)
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["gap_max_sec"] <= tl.LIVE_GAP_MAX_SEC
    assert res["n_ticks"] == 50


def test_no_venue_ts_field_reports_not_available(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    _write_ticks(d, "G1", [base + timedelta(seconds=30 * i) for i in range(30)])
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["schema_has_venue_ts"] is False
    assert res["capture_lag_vs_venue_sec_p50"] is None
    assert "NOT_AVAILABLE" in res["capture_lag_note"]


def test_venue_ts_field_present_computes_lag(tmp_path):
    d = tmp_path / "grade" / "mlb"
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    times = [base + timedelta(seconds=30 * i) for i in range(30)]
    venue_times = [t - timedelta(seconds=5) for t in times]
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "G1.jsonl", "w", encoding="utf-8") as fh:
        for t, vt in zip(times, venue_times):
            fh.write(json.dumps({"ts": _iso(t), "venue_ts": _iso(vt),
                                 "market_prob": 0.5, "model_prob": 0.5}) + "\n")
    res = tl.measure_sport("mlb", grade_dir=tmp_path / "grade")
    assert res["schema_has_venue_ts"] is True
    assert res["capture_lag_vs_venue_sec_p50"] == 5.0


def test_missing_dir_returns_zero_never_raises(tmp_path):
    res = tl.measure_sport("tennis", grade_dir=tmp_path / "nope")
    assert res["n_ticks"] == 0
    assert res["verdict"] == "INSUFFICIENT_DATA"


def test_build_doc_and_write_artifact(tmp_path):
    doc = tl.build_doc({"tennis": {"sport": "tennis", "verdict": "INSUFFICIENT_DATA"}})
    assert doc["overall_verdict"] == "INSUFFICIENT_DATA"
    assert doc["edge_claimed"] is False
    out = tl.write_artifact(doc, out_path=tmp_path / "art.json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["component"] == "inplay_tick_latency"


def test_measure_all_never_raises(monkeypatch):
    def _boom(sport, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(tl, "measure_sport", _boom)
    results = tl.measure_all(sports=["tennis"])
    assert results["tennis"]["verdict"] == "ERROR"
