"""Per-file test: frontend.report.build_report -- full per-game report shape.

Stubs a canonical store envelope on disk (via store_out_dir), then asserts:
  * a known game returns status='ok' with pregame/markets/edges populated;
  * live + intel degrade gracefully (never crash) when their sources are absent;
  * an unknown game / unavailable snapshot -> a clean status='unavailable';
  * NO dollar / $edge / roi / pnl key appears ANYWHERE in the report.

Run: python -m pytest tests/frontend/test_report.py -q
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from predict_service.contracts import (EdgeRow, MarketRow, PredictionRecord,
                                       SnapshotEnvelope)
from predict_service import store
import frontend.report as report_mod
from frontend.report import build_report

_SPORT = "nba"
_GID = "0042500401"
_FORBIDDEN = ("$", "dollar", "roi", "pnl", "profit", "stake", "bankroll")


def _envelope() -> SnapshotEnvelope:
    market = MarketRow(sport=_SPORT, game_id=_GID, market_type="moneyline",
                       side="home", line=None, odds=1.71, book="espn:DK",
                       devigged_prob=0.57, captured_at="2026-06-18T22:00:00+00:00",
                       is_close=False, clv_is_proxy=True)
    record = PredictionRecord(
        sport=_SPORT, game_id=_GID, home="Boston Celtics", away="New York Knicks",
        tipoff="2026-06-18T23:30:00+00:00",
        pregame_probs={"home_ml": 0.58, "away_ml": 0.42},
        markets=[market], leak_guard={"in_sample": False},
        produced_at="2026-06-18T21:00:00+00:00")
    edge = EdgeRow(game_id=_GID, market_type="moneyline", side="home",
                   model_prob=0.58, market_prob=0.555, ev=0.045, tier="B",
                   book="espn:DK", line=None, clv_is_proxy=True)
    return SnapshotEnvelope(sport=_SPORT, generated_at="2026-06-18T22:01:00+00:00",
                            status="ok", predictions=[record], markets=[market],
                            edges=[edge])


@pytest.fixture()
def store_dir(tmp_path, monkeypatch):
    """Write the stub envelope to a temp store and force live -> unavailable."""
    store.save(_envelope(), out_dir=tmp_path, append=False)
    # Keep the test hermetic: no network from the best-effort live board.
    monkeypatch.setattr(report_mod, "_live", lambda *a, **k: {
        "status": "unavailable", "reason": "stubbed in test"})
    return tmp_path


def _assert_no_money(obj: Any) -> None:
    """Recursively assert no forbidden $/roi/pnl key appears anywhere."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            for bad in _FORBIDDEN:
                assert bad not in kl, "forbidden key %r in report" % k
            _assert_no_money(v)
    elif isinstance(obj, list):
        for it in obj:
            _assert_no_money(it)


def test_full_shape_ok(store_dir):
    rep = build_report(_SPORT, _GID, store_out_dir=store_dir)
    assert rep["status"] == "ok"
    assert rep["sport"] == _SPORT and rep["game_id"] == _GID

    pre = rep["pregame"]
    assert pre["home"] == "Boston Celtics" and pre["away"] == "New York Knicks"
    assert pre["tipoff"] == "2026-06-18T23:30:00+00:00"
    assert pre["model_probs"] == {"home_ml": 0.58, "away_ml": 0.42}
    assert pre["leak_guard"] == {"in_sample": False}

    assert len(rep["markets"]) == 1
    assert rep["markets"][0]["market_type"] == "moneyline"

    assert len(rep["edges"]) == 1
    e = rep["edges"][0]
    assert e["tier"] == "B" and e["model_prob"] == 0.58
    assert "ev" in e and e["clv_is_proxy"] is True

    # live + intel are present and never crash the report.
    assert rep["live"]["status"] == "unavailable"
    assert isinstance(rep["intel"], dict)

    meta = rep["meta"]
    assert meta["clv_is_proxy"] is True
    assert meta["freshness"]["status"] in ("fresh", "stale", "unknown")
    assert meta["snapshot_generated_at"] == "2026-06-18T22:01:00+00:00"
    assert "honest_note" in meta

    _assert_no_money(rep)


def test_intel_graceful_null_when_sources_absent(monkeypatch, store_dir):
    """If intel raises, the section nulls -- the report still builds."""
    def _boom(*a, **k):
        raise RuntimeError("no profiles")
    monkeypatch.setattr("frontend.report_intel.intel_blurbs", _boom)
    rep = build_report(_SPORT, _GID, store_out_dir=store_dir)
    assert rep["status"] == "ok"
    assert rep["intel"]["status"] == "unavailable"
    assert rep["intel"]["home"] is None
    _assert_no_money(rep)


def test_unknown_game_is_unavailable(store_dir):
    rep = build_report(_SPORT, "DOES_NOT_EXIST", store_out_dir=store_dir)
    assert rep["status"] == "unavailable"
    assert rep["pregame"] is None
    assert rep["markets"] == [] and rep["edges"] == []
    assert rep["reason"]
    _assert_no_money(rep)


def test_missing_snapshot_is_unavailable(tmp_path):
    rep = build_report(_SPORT, _GID, store_out_dir=tmp_path)  # empty store
    assert rep["status"] == "unavailable"
    assert "snapshot" in rep["reason"].lower()
    _assert_no_money(rep)
