"""Per-file tests for output_freshness (offline; tmp_path artifacts)."""
from __future__ import annotations

import json
import os
import time

from scripts.platformkit.ops_sentinel import output_freshness as of


def _touch(p, mtime):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="ascii")
    os.utime(p, (mtime, mtime))


def test_fresh_file_is_green(tmp_path):
    p = tmp_path / "a.json"
    now = 1_000_000.0
    _touch(p, now - 10.0)
    row = of.check_one("m_x", of._Entry(p, 300.0), now=now)
    assert row["status"] == of.GREEN and row["age_sec"] == 10.0


def test_stale_file_is_red(tmp_path):
    p = tmp_path / "a.json"
    now = 1_000_000.0
    _touch(p, now - 500.0)
    row = of.check_one("m_x", of._Entry(p, 300.0), now=now)
    assert row["status"] == of.RED and row["reason"] == "stale"


def test_missing_file_is_red(tmp_path):
    row = of.check_one("m_x", of._Entry(tmp_path / "nope.json", 300.0), now=1_000_000.0)
    assert row["status"] == of.RED and row["reason"] == "missing" and row["age_sec"] is None


def test_check_all_covers_custom_table(tmp_path):
    fresh = tmp_path / "fresh.json"
    stale = tmp_path / "stale.json"
    now = 1_000_000.0
    _touch(fresh, now - 1.0)
    _touch(stale, now - 999.0)
    table = {"a": of._Entry(fresh, 300.0), "b": of._Entry(stale, 300.0)}
    rows = of.check_all(table, now=now)
    by_name = {r["name"]: r["status"] for r in rows}
    assert by_name == {"a": of.GREEN, "b": of.RED}


def test_write_and_load_status_roundtrip(tmp_path):
    out = tmp_path / "output_freshness.json"
    rows = [{"name": "a", "status": of.GREEN}, {"name": "b", "status": of.RED}]
    assert of.write_status(rows, out_path=out, now=123.0) is True
    doc = json.loads(out.read_text())
    assert doc["overall"] == of.RED and doc["n_red"] == 1 and doc["n_daemons"] == 2
    loaded = of.load_status(path=out)
    assert loaded == rows


def test_load_status_missing_file_is_empty(tmp_path):
    assert of.load_status(path=tmp_path / "nope.json") == []


# --------------------------------------------------------------------------- #
# stale_inputs (go-live hardening finding #4, 2026-07-17): the artifact stamps
# newest_input_mtime and flags stale_inputs when nothing checked this cycle has
# advanced since the artifact's OWN previous write.
# --------------------------------------------------------------------------- #

def test_first_write_never_flags_stale_inputs(tmp_path):
    out = tmp_path / "output_freshness.json"
    rows = [{"name": "a", "status": of.GREEN, "age_sec": 10.0}]
    of.write_status(rows, out_path=out, now=1000.0)
    doc = json.loads(out.read_text())
    assert doc["newest_input_mtime"] == 990.0
    assert doc["stale_inputs"] is False


def test_unchanged_input_between_writes_flags_stale_inputs(tmp_path):
    out = tmp_path / "output_freshness.json"
    # Cycle 1 @ t=1000: source file last touched at t=990 (age_sec=10).
    of.write_status([{"name": "a", "status": of.GREEN, "age_sec": 10.0}],
                    out_path=out, now=1000.0)
    # Cycle 2 @ t=1300: the SAME source file, still last touched at t=990
    # (age_sec grew to 310) -- nothing advanced between the two sentinel ticks.
    of.write_status([{"name": "a", "status": of.GREEN, "age_sec": 310.0}],
                    out_path=out, now=1300.0)
    doc = json.loads(out.read_text())
    assert doc["newest_input_mtime"] == 990.0
    assert doc["stale_inputs"] is True


def test_advancing_input_between_writes_clears_stale_inputs(tmp_path):
    out = tmp_path / "output_freshness.json"
    of.write_status([{"name": "a", "status": of.GREEN, "age_sec": 10.0}],
                    out_path=out, now=1000.0)
    # Cycle 2: the source file WAS touched again (age_sec=10 relative to the
    # new now) -- a fresh input since the last write.
    of.write_status([{"name": "a", "status": of.GREEN, "age_sec": 10.0}],
                    out_path=out, now=1300.0)
    doc = json.loads(out.read_text())
    assert doc["newest_input_mtime"] == 1290.0
    assert doc["stale_inputs"] is False


def test_rows_missing_age_sec_never_crash_stale_inputs_check(tmp_path):
    out = tmp_path / "output_freshness.json"
    rows = [{"name": "a", "status": of.RED, "age_sec": None, "reason": "missing"}]
    ok = of.write_status(rows, out_path=out, now=1000.0)
    assert ok is True
    doc = json.loads(out.read_text())
    assert doc["newest_input_mtime"] is None
    assert doc["stale_inputs"] is False


def test_merge_freshness_into_services_degrades_only():
    services = [{"name": "m25_ingame_outcome_verdict", "severity": "ok"},
                {"name": "m1_paper", "severity": "ok"},
                {"name": "m20_ingame_clv_verdict", "severity": "down"}]
    rows = [{"name": "m25_ingame_outcome_verdict", "status": of.RED},
            {"name": "m20_ingame_clv_verdict", "status": of.RED}]
    merged_by_name = {s["name"]: s for s in of.merge_freshness_into_services(services, rows)}
    assert merged_by_name["m25_ingame_outcome_verdict"]["severity"] == "degraded"
    assert merged_by_name["m1_paper"]["severity"] == "ok"          # untouched
    assert merged_by_name["m20_ingame_clv_verdict"]["severity"] == "down"  # never upgraded


def test_table_matches_readiness_none_procspecs_exactly():
    """Drift guard: a readiness=NONE daemon added to the real stack WITHOUT a
    sentinel row must fail this test, not silently go unmonitored."""
    from supervisor.manifest import NONE as READINESS_NONE
    from supervisor.stack_specs import base_specs
    real_names = {s.name for s in base_specs() if s.readiness.kind == READINESS_NONE}
    assert set(of.TABLE.keys()) == real_names


def test_real_table_paths_point_under_data_frontend():
    for entry in of.TABLE.values():
        assert "data" in entry.path.parts and "frontend" in entry.path.parts
        assert entry.max_age_sec > 0
