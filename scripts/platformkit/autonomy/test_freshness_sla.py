"""Per-file tests for freshness_sla / freshness_sla_runner.

Covers: NA for a name with no table entry (never GREEN), GREEN for a fresh
artifact, RED for a stale/missing artifact, write_status/load_status round
trip, and the runner tick with fake check/write callables (no real daemon
names or filesystem probing beyond tmp_path).

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autonomy/test_freshness_sla.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.autonomy.freshness_sla import (
    GREEN,
    NA,
    RED,
    SlaEntry,
    check_all,
    check_one,
    load_status,
    probe,
    write_status,
)


def test_missing_table_entry_is_na_never_green():
    row = check_one("totally_unknown_daemon_xyz", now=1000.0)
    assert row["status"] == NA
    assert row["reason"] == "no_sla_entry"


def test_green_for_fresh_artifact(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["status"] == GREEN
    assert row["age_sec"] == 10.0


def test_red_for_stale_artifact(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 1000.0
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["status"] == RED
    assert row["reason"] == "stale"


def test_red_for_missing_artifact(tmp_path):
    p = tmp_path / "does_not_exist.json"
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=1000.0, table=table)
    assert row["status"] == RED
    assert row["reason"] == "missing"


def test_negative_age_clamped_to_zero(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime - 500.0  # clock skew: "now" before mtime
    table = {"svc": SlaEntry(p, 100.0)}
    row = check_one("svc", now=now, table=table)
    assert row["age_sec"] == 0.0
    assert row["status"] == GREEN


def test_check_all_preserves_order_and_mixes_statuses(tmp_path):
    p = tmp_path / "out.json"
    p.write_text("{}", encoding="utf-8")
    now = p.stat().st_mtime + 10.0
    table = {"a": SlaEntry(p, 100.0)}
    rows = check_all(["a", "b_unknown"], now=now, table=table)
    assert [r["name"] for r in rows] == ["a", "b_unknown"]
    assert rows[0]["status"] == GREEN
    assert rows[1]["status"] == NA


def test_write_status_and_load_status_round_trip(tmp_path):
    out = tmp_path / "freshness_sla.json"
    rows = [
        {"name": "a", "status": GREEN},
        {"name": "b", "status": RED},
        {"name": "c", "status": NA},
    ]
    assert write_status(rows, out_path=out, now=500.0) is True
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["n_red"] == 1
    assert doc["n_na"] == 1
    assert doc["overall"] == RED
    loaded = load_status(path=out)
    assert [r["name"] for r in loaded] == ["a", "b", "c"]


def test_write_status_overall_green_when_no_red(tmp_path):
    out = tmp_path / "freshness_sla.json"
    rows = [{"name": "a", "status": GREEN}, {"name": "b", "status": NA}]
    write_status(rows, out_path=out, now=500.0)
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["overall"] == GREEN


def test_load_status_missing_file_returns_empty(tmp_path):
    assert load_status(path=tmp_path / "nope.json") == []


def test_load_status_garbage_returns_empty(tmp_path):
    p = tmp_path / "garbage.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_status(path=p) == []


def test_probe_convenience_uses_real_table_and_returns_status_string():
    # Every real TABLE-entry daemon reads a status string; an unknown name is NA.
    assert probe("totally_unknown_daemon_xyz") == NA


def test_table_entries_have_positive_staleness():
    from scripts.platformkit.autonomy.freshness_sla import TABLE
    assert len(TABLE) > 0
    for name, entry in TABLE.items():
        assert entry.max_staleness_sec > 0, name


# --------------------------------------------------------------------------- #
# runner: fake check/write callables, no real supervisor.manifest() names touched
# --------------------------------------------------------------------------- #
def test_runner_tick_calls_check_and_write():
    from scripts.platformkit.autonomy.freshness_sla_runner import tick

    calls = {}

    def fake_check(names, now=None):
        calls["names"] = names
        calls["now"] = now
        return [{"name": n, "status": GREEN} for n in names]

    def fake_write(rows, now=None):
        calls["written"] = rows
        return True

    rows = tick(now=123.0, names=["x", "y"], check_fn=fake_check, write_fn=fake_write)
    assert calls["names"] == ["x", "y"]
    assert calls["now"] == 123.0
    assert len(rows) == 2
    assert calls["written"] == rows


def test_runner_tick_never_raises_when_check_fn_raises():
    from scripts.platformkit.autonomy.freshness_sla_runner import tick

    def boom(names, now=None):
        raise RuntimeError("boom")

    rows = tick(now=0.0, names=["x"], check_fn=boom, write_fn=lambda rows, now=None: True)
    assert rows == []


def test_daemon_names_helper_never_raises():
    from scripts.platformkit.autonomy.freshness_sla_runner import _daemon_names
    names = _daemon_names()
    assert isinstance(names, list)
