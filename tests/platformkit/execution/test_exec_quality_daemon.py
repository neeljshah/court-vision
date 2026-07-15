"""Per-file tests for exec_quality_daemon (injected fns / monkeypatched module
attrs, no network, no real ledger writes -- everything under tmp_path).

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/execution/test_exec_quality_daemon.py -q
"""
from __future__ import annotations

import importlib
import json

import pytest

from scripts.platformkit.clv_grading import ingame_realized_clv as CLV
from scripts.platformkit.execution import exec_quality_daemon as D
from scripts.platformkit.paper import paper_today as PT


def test_tick_composes_breaker_states_and_calls_both_steps():
    calls = {"grade": 0, "digest": 0}

    def grade_fn(now):
        calls["grade"] += 1
        assert now == 555.0
        return {"n_bets": 3, "n_newly_graded": 2}

    def digest_fn():
        calls["digest"] += 1
        return {"execution": {"by_market_type": {
            "moneyline": {"state": "LIVE"}, "prop": {"state": "CAPPED"}}}}

    doc = D.tick(now=555.0, grade_fn=grade_fn, digest_fn=digest_fn)

    assert calls == {"grade": 1, "digest": 1}
    assert doc["component"] == "exec_quality"
    assert doc["edge_claimed"] is False
    assert doc["grading"]["n_newly_graded"] == 2
    assert doc["breaker_states"] == {"moneyline": "LIVE", "prop": "CAPPED"}


def test_tick_isolates_grading_failure_from_digest():
    def _boom(now):
        raise RuntimeError("grading exploded")

    digest_called = []

    def digest_fn():
        digest_called.append(1)
        return {"execution": {"by_market_type": {"moneyline": {"state": "LIVE"}}}}

    doc = D.tick(now=1.0, grade_fn=_boom, digest_fn=digest_fn)

    assert digest_called == [1]  # digest still ran despite grading raising
    assert "error" in doc["grading"]
    assert doc["breaker_states"] == {"moneyline": "LIVE"}


def test_tick_isolates_digest_failure_from_grading():
    grade_called = []

    def grade_fn(now):
        grade_called.append(1)
        return {"n_bets": 0, "n_newly_graded": 0}

    def _boom():
        raise RuntimeError("digest exploded")

    doc = D.tick(now=1.0, grade_fn=grade_fn, digest_fn=_boom)

    assert grade_called == [1]  # grading still ran despite digest raising
    assert "error" in doc["breaker_states"] or doc["breaker_states"] == {}
    assert doc["grading"]["n_newly_graded"] == 0


def test_min_age_s_is_longest_horizon_plus_slack():
    assert D._min_age_s() == pytest.approx(max(CLV.HORIZONS_S) + CLV.SLACK_S)


def test_default_grade_passes_min_age_and_now_epoch_through(tmp_path, monkeypatch):
    sidecar = tmp_path / "ingame_realized_clv.jsonl"
    monkeypatch.setattr(CLV, "SIDECAR", sidecar)
    captured = {}

    def fake_backfill(write=False, min_age_s=0.0, now_epoch=None, **_kw):
        captured["write"] = write
        captured["min_age_s"] = min_age_s
        captured["now_epoch"] = now_epoch
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_text('{"bet_id": "b1"}\n', encoding="utf-8")
        return {"n_bets": 1, "n_gradeable": 1}

    monkeypatch.setattr(CLV, "backfill", fake_backfill)

    out = D._default_grade(12345.0)

    assert captured["write"] is True
    assert captured["now_epoch"] == 12345.0
    # min-age filtering proven: the daemon never calls backfill unfiltered.
    assert captured["min_age_s"] == pytest.approx(max(CLV.HORIZONS_S) + CLV.SLACK_S)
    assert out["n_newly_graded"] == 1  # sidecar went 0 -> 1 lines this call


def test_default_digest_writes_atomic_json_and_returns_doc(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "TODAY_PATH", tmp_path / "paper_today.json")

    fake_doc = {"execution": {"by_market_type": {"moneyline": {"state": "LIVE"}}},
                "edge_claimed": False}
    monkeypatch.setattr(PT, "build_today", lambda **_kw: fake_doc)

    doc = D._default_digest()

    assert doc == fake_doc
    written = json.loads(D.TODAY_PATH.read_text(encoding="ascii"))
    assert written["execution"]["by_market_type"]["moneyline"]["state"] == "LIVE"


def test_registry_entry_importable_and_wired():
    from supervisor.stack_specs import base_specs

    specs = {s.name: s for s in base_specs()}
    assert "m42_exec_quality" in specs
    spec = specs["m42_exec_quality"]
    assert spec.module == "scripts.platformkit.execution.exec_quality_daemon"
    mod = importlib.import_module(spec.module)
    assert mod.HEARTBEAT_COMPONENT == "m42_exec_quality"
