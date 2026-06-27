"""Per-file tests for forward_capture.inplay_clv_replay -- offline in-play CLV replay harness.

Self-contained: builds synthetic schema-correct series inline (does NOT depend on any real
captured fixture file landing). Covers:
  1. A drift 0.50 -> 0.65 series where a LEADING model BEATs, the naive market-follow baseline
     does NOT beat (MATCH/INSUFFICIENT_DATA), and a CONTRARIAN model is BEHIND.
  2. INSUFFICIENT_DATA when fewer than MIN_TICKS ticks.
  3. load_series round-trips a tiny JSONL written in tmp_path.

Run: python -m pytest tests/platformkit/test_inplay_clv_replay.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.forward_capture import inplay_clv_replay as ic


def _tick(prob: float, ts: str, **over) -> dict:
    base = {
        "sport": "nba", "game_id": "G1", "venue": "kalshi",
        "market_type": "winner_home", "side": "YES",
        "ticker": "NBA-G1-HOME", "prob": float(prob), "ts": ts,
    }
    base.update(over)
    return base


def _drift_series(n: int = 12, start: float = 0.50, end: float = 0.65) -> list:
    """A monotone in-play drift from `start` toward `end`, evenly spaced 60s apart."""
    t0 = datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
    out = []
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        prob = start + (end - start) * frac
        ts = (t0 + timedelta(seconds=60 * i)).isoformat()
        out.append(_tick(prob, ts))
    return out


# --------------------------------------------------------------------------------------- #
# 1. Drift series: leader BEATs, market-follow does NOT, contrarian BEHIND.               #
# --------------------------------------------------------------------------------------- #
def test_leading_model_beats_the_close():
    series = _drift_series()

    # A LEADING model: it sees the up-drift and pushes ABOVE the current price (correct lean,
    # toward where the market actually closes at 0.65). Leak-free: only reads the given tick.
    def leader(tick, history):
        return min(1.0, float(tick["prob"]) + 0.05)

    res = ic.replay_series(series, leader)
    assert res.verdict == "BEAT", res.as_dict()
    assert res.mean_clv > 0
    assert res.hit_rate > 0.5
    assert res.n_ticks_scored == len(series) - 1  # final close tick excluded


def test_naive_market_follow_never_beats():
    series = _drift_series()
    res = ic.replay_series(series, ic.naive_market_follow_model)
    # A copy-the-market model has zero edge every tick -> cannot beat the close.
    assert res.verdict in ("MATCH", "INSUFFICIENT_DATA"), res.as_dict()
    assert res.verdict != "BEAT"
    assert res.mean_clv == pytest.approx(0.0, abs=1e-9)
    assert res.hit_rate == pytest.approx(0.0, abs=1e-9)


def test_contrarian_model_is_behind():
    series = _drift_series()

    # A CONTRARIAN model leans DOWN while the market drifts UP -> wrong direction -> BEHIND.
    def contrarian(tick, history):
        return max(0.0, float(tick["prob"]) - 0.05)

    res = ic.replay_series(series, contrarian)
    assert res.verdict == "BEHIND", res.as_dict()
    assert res.mean_clv < 0


def test_report_is_ascii_and_mentions_verdict():
    series = _drift_series()
    res = ic.replay_series(series, lambda t, h: min(1.0, float(t["prob"]) + 0.05))
    report = ic.format_report(res)
    report.encode("ascii")  # raises if any non-ASCII slipped in
    assert "verdict" in report
    assert res.verdict in report


# --------------------------------------------------------------------------------------- #
# 2. INSUFFICIENT_DATA below MIN_TICKS.                                                    #
# --------------------------------------------------------------------------------------- #
def test_insufficient_data_below_min_ticks():
    # 5 ticks -> 4 scored < MIN_TICKS (8) -> honest can't-tell, even though the model leads.
    series = _drift_series(n=5)

    def leader(tick, history):
        return min(1.0, float(tick["prob"]) + 0.05)

    res = ic.replay_series(series, leader)
    assert res.n_ticks_scored < ic.MIN_TICKS_DEFAULT
    assert res.verdict == "INSUFFICIENT_DATA", res.as_dict()


def test_single_tick_series_is_insufficient():
    series = _drift_series(n=1)
    res = ic.replay_series(series, ic.naive_market_follow_model)
    assert res.verdict == "INSUFFICIENT_DATA"
    assert res.n_ticks_scored == 0


# --------------------------------------------------------------------------------------- #
# 3. load_series round-trips a tiny JSONL.                                                 #
# --------------------------------------------------------------------------------------- #
def test_load_series_roundtrip(tmp_path):
    series = _drift_series(n=4)
    # Write out of order to prove load_series sorts by ts.
    path = tmp_path / "series.jsonl"
    shuffled = [series[2], series[0], series[3], series[1]]
    with open(path, "w", encoding="utf-8") as fh:
        for t in shuffled:
            fh.write(json.dumps(t) + "\n")
        fh.write("\n")  # blank line must be skipped

    loaded = ic.load_series(str(path))
    assert len(loaded) == 4
    ts_list = [t["ts"] for t in loaded]
    assert ts_list == sorted(ts_list)  # sorted by ts
    assert [t["prob"] for t in loaded] == [t["prob"] for t in series]


def test_load_series_rejects_bad_prob(tmp_path):
    path = tmp_path / "bad.jsonl"
    bad = _tick(1.5, datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc).isoformat())
    path.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ic.load_series(str(path))


def test_load_series_rejects_missing_key(tmp_path):
    path = tmp_path / "missing.jsonl"
    rec = {"sport": "nba", "prob": 0.5, "ts": "2026-06-18T01:00:00+00:00"}
    path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ic.load_series(str(path))
