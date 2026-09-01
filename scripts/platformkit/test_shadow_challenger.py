"""Focused progressive-validation tests for shadow_challenger."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.platformkit import shadow_challenger as sc


def _setup(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(sc, "DATA_ROOT", tmp_path / "data")
    sc.register_challenger("better", "pkg.predict:better", {"version": 2})
    sc.register_challenger("equal", "pkg.predict:equal", {})


def _write_rows(rows):
    for row in rows:
        sc.log_shadow(row["ts"], row["key"], row["champion"], row["challengers"], 0.5)
        sc.settle_shadow(row["key"], row["outcome"])


def test_genuinely_better_challenger_promotes_with_live_shadow_ci(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"ts": now, "key": "better-{0}".format(i), "outcome": i % 2,
             "champion": 0.7, "challengers": {"better": 0.99 if i % 2 else 0.01, "equal": 0.5}}
            for i in range(240)]
    _write_rows(rows)

    result = sc.compare()
    better = result["challengers"]["better"]
    assert better["verdict"] == "PROMOTE"
    assert better["n_settled"] == 240
    assert better["bootstrap_ci"]["high"] < 0
    assert result["human_gate_required"] is True
    assert "human/orchestrator" in result["promotion_note"]


def test_noisy_equal_challenger_holds_when_ci_includes_zero(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"ts": now, "key": "equal-{0}".format(i), "outcome": i % 2,
             "champion": 0.5, "challengers": {"better": 0.5, "equal": 0.5}}
            for i in range(240)]
    _write_rows(rows)

    equal = sc.compare()["challengers"]["equal"]
    assert equal["verdict"] == "HOLD"
    assert equal["reason"] == "CI_INCLUDES_ZERO"
    assert equal["bootstrap_ci"]["low"] <= 0 <= equal["bootstrap_ci"]["high"]


def test_too_few_rows_holds_insufficient(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    _write_rows([{"ts": now, "key": "few-{0}".format(i), "outcome": i % 2,
                  "champion": 0.5, "challengers": {"better": 0.1, "equal": 0.5}}
                 for i in range(12)])

    result = sc.compare()["challengers"]["better"]
    assert result["verdict"] == "HOLD"
    assert result["reason"] == "INSUFFICIENT_SETTLED_ROWS"
    assert result["n_settled"] == 12


def test_settle_matches_only_the_requested_unsettled_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "DATA_ROOT", tmp_path / "data")
    sc.log_shadow("2026-08-31T12:00:00+00:00", "right", 0.5, {"c": 0.5}, 0.5)
    sc.log_shadow("2026-08-31T12:01:00+00:00", "wrong", 0.5, {"c": 0.5}, 0.5)

    assert sc.settle_shadow("right", 1) == 1
    records = [json.loads(line) for line in sc._ledger_path().read_text(encoding="utf-8").splitlines()]
    assert records[0]["outcome"] == 1
    assert records[1]["outcome"] is None
    assert sc.settle_shadow("right", 0) == 0


def test_predictions_are_logged_before_outcomes(monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "DATA_ROOT", tmp_path / "data")
    sc.log_shadow("2026-08-31T12:00:00+00:00", "open", 0.4, {"c": 0.3}, 0.5)
    record = json.loads(sc._ledger_path().read_text(encoding="utf-8"))
    assert record["outcome"] is None
