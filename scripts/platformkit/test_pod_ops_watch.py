"""Tests for the cron-safe pod health record."""

import json

from scripts.platformkit import pod_ops_watch as watch


def test_build_record_warn_shape(monkeypatch):
    monkeypatch.setattr(watch, "collect_ram", lambda: 91.0)
    monkeypatch.setattr(watch, "disk_free_gb", lambda path: 20.0)
    monkeypatch.setattr(watch, "collect_gpu", lambda: None)
    monkeypatch.setattr(watch, "collect_heartbeats", lambda now: (10.0, ["old.txt"]))
    monkeypatch.setattr(watch, "ledger_last_ts", lambda: "2026-08-31T00:00:00Z")

    record = watch.build_record(now=1000.0)

    assert record["verdict"] == "WARN"
    assert set(record) == {"ts", "ram_gb", "disk_ws_gb", "disk_root_gb", "gpu", "newest_beat_age_s", "stale", "ledger_last_ts", "verdict"}
    assert json.loads(json.dumps(record))["ts"] == 1000


def test_verdict_failures_and_ok():
    assert watch.verdict_for(105.1, 20.0, 1.0, []) == "FAIL"
    assert watch.verdict_for(10.0, 4.9, 1.0, []) == "FAIL"
    assert watch.verdict_for(10.0, 20.0, 301.0, []) == "FAIL"
    assert watch.verdict_for(10.0, 20.0, 1.0, []) == "OK"
