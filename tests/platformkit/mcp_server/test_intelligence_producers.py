"""S57: the intelligence layer inside freshness governance.

Two things must hold and neither did before this row:
  1. every file under data/intelligence is DISCOVERED by gate_manifest with
     category "intelligence" and a labelled measurement time (its own
     generated_at where present, else mtime) -- parquet included;
  2. a producer in a human-gated tree is reported NO_RUN BY NAME, never
     silently skipped and never confused with "nothing writes this".

Everything runs against a fake repo under tmp_path. No real producer runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.eval_gate import gate_manifest as gm
from scripts.platformkit.mcp_server import artifact_refresh as ar
from scripts.platformkit.mcp_server import intelligence_producers as ip


def _fake_repo(tmp_path: Path) -> Path:
    intel = tmp_path / "data" / "intelligence"
    intel.mkdir(parents=True)
    (intel / "stamped.json").write_text(
        json.dumps({"generated_at": "2026-06-02T12:00:00+00:00"}), encoding="ascii")
    (intel / "unstamped.json").write_text(json.dumps({"rows": 3}), encoding="ascii")
    # a parquet: unparseable as text, and 99 of the real 151 look like this
    (intel / "table.parquet").write_bytes(b"PAR1\x00\x01binary\xff")
    return tmp_path


def _intel_rows(tmp_path: Path):
    manifest = gm.build_manifest(_fake_repo(tmp_path))
    return {r["name"]: r for r in manifest["rows"] if r["category"] == "intelligence"}


def test_every_intelligence_file_is_registered(tmp_path):
    rows = _intel_rows(tmp_path)
    assert set(rows) == {"stamped.json", "unstamped.json", "table.parquet"}


def test_measured_at_is_labelled_field_or_mtime(tmp_path):
    rows = _intel_rows(tmp_path)
    assert rows["stamped.json"]["measured_at_source"] == "field:generated_at"
    assert rows["stamped.json"]["measured_at"].startswith("2026-06-02T12:00:00")
    for name in ("unstamped.json", "table.parquet"):
        assert rows[name]["measured_at_source"] == "mtime"
        assert rows[name]["measured_at"] is not None


def test_binary_artifact_is_registered_not_unreadable(tmp_path):
    # reading a parquet as text would make 99 real artifacts UNREADABLE and
    # exit(1) the whole audit -- a broken reader, not broken evidence.
    rows = _intel_rows(tmp_path)
    assert rows["table.parquet"]["status"] == "OK"
    assert rows["table.parquet"]["error"] is None


def test_gated_producer_is_no_run_by_name(tmp_path):
    reason = ip.classify("intel/team_paint_defense.py", tmp_path, scope="all")
    assert reason is not None and "gated" in reason
    assert "intel/team_paint_defense.py" in reason


def test_no_run_row_names_its_reason_and_is_not_a_skip(tmp_path):
    target = ar.Target("intel:gated", ("data/intelligence/x.parquet",), None,
                       "gated tree (human-gated, read-only): intel/foo.py")
    record = ar.refresh_once(tmp_path, tmp_path / "out", (target,))
    row = record["targets"][0]
    assert row["status"] == "NO_RUN"          # not NO_PRODUCER, not absent
    assert "intel/foo.py" in row["error"]
    assert record["n_no_run"] == 1 and record["n_advanced"] == 0
    assert len(record["targets"]) == 1        # nothing dropped from the pass


def test_absent_and_out_of_scope_producers_are_named(tmp_path):
    assert "absent" in ip.classify("scripts/build_gone.py", tmp_path, scope="all")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "build_gone.py").write_text("", encoding="ascii")
    assert ip.classify("scripts/build_gone.py", tmp_path, scope="all") is None
    # not in INPUT_REBUILT -> out of the default run scope, with a reason
    assert "reproduces" in ip.classify("scripts/build_gone.py", tmp_path)


def test_map_covers_every_artifact_exactly_once():
    mapped = [n for names in ip.PRODUCERS.values() for n in names]
    assert len(mapped) == len(set(mapped)), "an artifact has two producers"
    assert not set(mapped) & set(ip.NO_PRODUCER)
    assert len(mapped) + len(ip.NO_PRODUCER) == 151
