"""Per-file tests for scripts.platformkit.execution.ingame_exec_gate.

Covers: expected-CLV + drift suppression (pre-existing), the placement-time
depth stamp (LEVER 1: tick-carried fields, book_depth sidecar fallback within
120s, honest null when no source), and the max-spread suppress gate (LEVER 3:
suppress over threshold, never suppress on unknown spread, env toggle off).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/execution/test_ingame_exec_gate.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.execution import ingame_exec_gate as X

_EV_OK = {"obtainable_decimal": 1.818, "bet_model_prob": 0.80}   # big model edge
_EV_LOW = {"obtainable_decimal": 1.818, "bet_model_prob": 0.55}  # tiny model edge


# --------------------------------------------------------------------------- #
# pre-existing expected-CLV + drift behavior (unchanged)                      #
# --------------------------------------------------------------------------- #
def test_big_edge_passes_no_drift():
    r = X.evaluate_placement(_EV_OK, {})
    assert r["suppress"] is False
    assert r["exec_gate"]["drift_pct"] is None


def test_tiny_edge_suppressed_below_floor():
    r = X.evaluate_placement(_EV_LOW, {})
    assert r["suppress"] is True and r["reason"] == "expected_clv_below_floor"


def test_adverse_drift_suppresses():
    r = X.evaluate_placement(_EV_OK, {"fresh_obtainable_decimal": 1.60})
    assert r["suppress"] is True and r["reason"] == "drift"


# --------------------------------------------------------------------------- #
# LEVER 1: build_exec_depth / exec_depth stamp                                #
# --------------------------------------------------------------------------- #
def test_depth_from_tick_fields_directly():
    tick = {"spread_bp": 150.0, "book_thinness": 500.0, "best_bid": 0.60, "best_ask": 0.615}
    depth = X.build_exec_depth(tick)
    assert depth["spread_bp"] == 150.0
    assert depth["book_thinness"] == 500.0
    assert depth["best_bid"] == 0.60 and depth["best_ask"] == 0.615
    assert abs(depth["mid"] - 0.6075) < 1e-9
    assert "reason" not in depth


def test_depth_honest_null_when_no_source():
    depth = X.build_exec_depth({})  # no tick fields, no ticker
    assert depth["reason"] == "no_depth_source"
    assert depth["spread_bp"] is None and depth["mid"] is None


def test_depth_from_sidecar_within_120s(tmp_path):
    now_dt = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = {"ts": "2026-07-15T11:59:30.000000Z", "venue": "kalshi", "ticker": "KXNBATEST-Y",
           "best_bid": 0.55, "best_ask": 0.57, "spread_bp": 200.0, "book_thinness": 300.0}
    sidecar = tmp_path / "kalshi" / "2026-07-15.jsonl"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(json.dumps(row) + "\n", encoding="ascii")
    depth = X.build_exec_depth({}, ticker="KXNBATEST-Y", now=now_dt, sidecar_dir=tmp_path)
    assert depth["spread_bp"] == 200.0
    assert depth["best_bid"] == 0.55 and depth["best_ask"] == 0.57
    assert abs(depth["mid"] - 0.56) < 1e-9
    assert depth["depth_ts"] == row["ts"]


def test_depth_sidecar_row_older_than_120s_is_ignored(tmp_path):
    now_dt = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    row = {"ts": "2026-07-15T11:50:00.000000Z",  # 600s stale -- outside the 120s window
           "ticker": "KXNBATEST-Y", "best_bid": 0.55, "best_ask": 0.57, "spread_bp": 200.0}
    sidecar = tmp_path / "kalshi" / "2026-07-15.jsonl"
    sidecar.parent.mkdir(parents=True)
    sidecar.write_text(json.dumps(row) + "\n", encoding="ascii")
    depth = X.build_exec_depth({}, ticker="KXNBATEST-Y", now=now_dt, sidecar_dir=tmp_path)
    assert depth["reason"] == "no_depth_source"


def test_depth_no_ticker_skips_sidecar_lookup(tmp_path):
    depth = X.build_exec_depth({}, ticker=None, sidecar_dir=tmp_path)
    assert depth["reason"] == "no_depth_source"


# --------------------------------------------------------------------------- #
# LEVER 3: max-spread suppress gate                                            #
# --------------------------------------------------------------------------- #
def test_wide_spread_suppresses():
    r = X.evaluate_placement(_EV_OK, {"spread_bp": 900.0})  # > 800bp threshold
    assert r["suppress"] is True and r["reason"] == "spread_too_wide"
    assert r["exec_gate"]["spread_flag"] is True
    assert r["exec_gate"]["spread_unknown"] is False


def test_tight_spread_does_not_suppress():
    r = X.evaluate_placement(_EV_OK, {"spread_bp": 100.0})  # well under 800bp
    assert r["suppress"] is False
    assert r["exec_gate"]["spread_flag"] is False


def test_unknown_spread_never_suppresses():
    # No spread_bp anywhere (no tick fields, no ticker) -- missing data must not
    # silently kill the channel, only be logged via spread_unknown.
    r = X.evaluate_placement(_EV_OK, {})
    assert r["suppress"] is False
    assert r["exec_gate"]["spread_unknown"] is True
    assert r["exec_gate"]["spread_flag"] is False


def test_spread_suppress_env_toggle_off(monkeypatch):
    monkeypatch.setenv("CV_INGAME_MAX_SPREAD", "0")
    r = X.evaluate_placement(_EV_OK, {"spread_bp": 900.0})
    assert r["suppress"] is False  # toggle off -> the 800bp gate never fires
    assert r["exec_gate"]["spread_flag"] is True  # still recorded, just not enforced


if __name__ == "__main__":
    test_big_edge_passes_no_drift()
    test_tiny_edge_suppressed_below_floor()
    test_adverse_drift_suppresses()
    test_depth_from_tick_fields_directly()
    test_depth_honest_null_when_no_source()
    test_wide_spread_suppresses()
    test_tight_spread_does_not_suppress()
    test_unknown_spread_never_suppresses()
    print("test_ingame_exec_gate self-checks OK")
