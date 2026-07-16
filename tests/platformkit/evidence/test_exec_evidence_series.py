"""Per-file tests for exec_evidence_series (synthetic ledger rows + tmp paths,
no network, no real ledger writes).

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/evidence/test_exec_evidence_series.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.evidence import exec_evidence_series as S

NOW = "2026-07-15T12:00:00Z"

LEDGER_ROWS = [
    {"market_type": "moneyline", "ts": "2026-07-01T00:00:00Z", "clv_pct": -5.0},
    {"market_type": "moneyline", "ts": "2026-07-10T00:00:00Z", "clv_pct": -3.0,
     "clv_is_proxy": True},
    {"market_type": "prop", "ts": "2026-07-10T00:00:00Z", "clv_pct": 2.0,
     "exec_gate": {"expected_clv_pct": 1.5}, "placement_latency_ms": 200},
    {"market_type": "prop", "ts": "2026-07-11T00:00:00Z", "clv_pct": -1.0},
    # settled props for calibration -- one recent win, one recent loss, one stale (>30d)
    {"market_type": "prop", "sport": "mlb", "prop_stat": "hits", "status": "settled",
     "settled_at": "2026-07-14T00:00:00Z", "outcome": "win", "model_prob": 0.6},
    {"market_type": "prop", "sport": "mlb", "prop_stat": "hits", "status": "settled",
     "settled_at": "2026-07-13T00:00:00Z", "outcome": "loss", "model_prob": 0.55},
    {"market_type": "prop", "sport": "mlb", "prop_stat": "hits", "status": "settled",
     "settled_at": "2026-05-01T00:00:00Z", "outcome": "win", "model_prob": 0.9},
    {"market_type": "prop", "sport": "mlb", "prop_stat": "hits", "status": "open",
     "outcome": None, "model_prob": 0.5},
]


def test_snapshot_shape_honest_null_when_ledger_unavailable(monkeypatch):
    monkeypatch.setattr(S, "cached_load_ledger", None)
    doc = S.snapshot(NOW)
    assert doc["ts"] == NOW
    assert doc["snapshot_hour"] == "2026-07-15T12"
    assert doc["clv_by_market"] == {}
    assert doc["exec_quality"] == {"n_gated": 0, "n_ungated": 0,
                                    "avg_expected_clv_pct": None, "median_latency_ms": None}
    assert doc["prop_calibration"] == {}
    assert doc["edge_claimed"] is False


def test_snapshot_composes_real_rows(monkeypatch):
    monkeypatch.setattr(S, "cached_load_ledger", lambda: LEDGER_ROWS)
    doc = S.snapshot(NOW)

    q = doc["exec_quality"]
    assert q["n_gated"] == 1 and q["n_ungated"] == 7
    assert q["avg_expected_clv_pct"] == 1.5
    assert q["median_latency_ms"] == 200

    assert "moneyline" in doc["clv_by_market"] and "prop" in doc["clv_by_market"]
    ml = doc["clv_by_market"]["moneyline"]
    assert ml["breaker_state"] in ("LIVE", "CAPPED", "UNKNOWN")

    calib = doc["prop_calibration"]["mlb|hits"]
    assert calib["n"] == 2  # only the two within 30d of NOW (the May row is stale)
    assert calib["hit_rate"] == 0.5  # 1 win / (1 win + 1 loss)
    assert calib["median_model_prob"] == 0.575  # median(0.6, 0.55)


def test_append_snapshot_hourly_idempotent_and_append_only(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "cached_load_ledger", lambda: [])
    path = tmp_path / "series.jsonl"

    doc1 = S.append_snapshot(path=path, now_iso=NOW)
    assert doc1 is not None
    text_after_first = path.read_text(encoding="ascii")
    assert text_after_first.count("\n") == 1

    doc2 = S.append_snapshot(path=path, now_iso="2026-07-15T12:45:00Z")
    assert doc2 is None  # same UTC hour -- no-op
    assert path.read_text(encoding="ascii") == text_after_first  # byte-identical

    doc3 = S.append_snapshot(path=path, now_iso="2026-07-15T13:05:00Z")
    assert doc3 is not None
    text_after_third = path.read_text(encoding="ascii")
    assert text_after_third.startswith(text_after_first)  # existing lines untouched
    assert text_after_third.count("\n") == 2


def test_summarize_series_math(tmp_path):
    path = tmp_path / "series.jsonl"
    rows = [
        {"ts": "2026-07-14T10:00:00Z",
         "clv_by_market": {"moneyline": {"median_clv_pct": 1.0}}},
        {"ts": "2026-07-14T18:00:00Z",  # later vintage same day -- should win
         "clv_by_market": {"moneyline": {"median_clv_pct": 2.0}}},
        {"ts": "2026-07-15T09:00:00Z",
         "clv_by_market": {"moneyline": {"median_clv_pct": 3.0}}},
    ]
    with path.open("w", encoding="ascii") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    out = S.summarize_series(path=path, days=30)
    assert out["moneyline"]["2026-07-14"]["median_clv_pct"] == 2.0
    assert out["moneyline"]["2026-07-15"]["median_clv_pct"] == 3.0


def test_registry_entry_importable_and_wired():
    import importlib
    from supervisor.stack_specs import base_specs

    specs = {s.name: s for s in base_specs()}
    assert "m44_exec_evidence" in specs
    spec = specs["m44_exec_evidence"]
    assert spec.module == "scripts.platformkit.evidence.exec_evidence_daemon"
    mod = importlib.import_module(spec.module)
    assert mod.HEARTBEAT_COMPONENT == "m44_exec_evidence"
