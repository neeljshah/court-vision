"""Per-file tests for the read-only gate-manifest MCP loader.

Run: python -m pytest scripts/platformkit/mcp/test_gate_manifest_tool.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.mcp.gate_manifest_tool import _MANIFEST, _ROOT, gate_manifest, tool_specs

_FIXTURE = {
    "as_of": "2026-09-01T21:45:46.417216+00:00",
    "rows": [
        {"name": "backtest_fwer.jsonl", "source_path": "data/cache/eval_gate/backtest_fwer.jsonl",
         "mtime": "2026-09-01T21:42:42.101244+00:00", "staleness_days": 0.0,
         "status": "OK", "verdict": None, "category": "ledger", "error": None},
        {"name": "venue_table.json", "source_path": "docs/evidence/x/venue_table.json",
         "mtime": "2026-09-01T21:42:44.788207+00:00", "staleness_days": 0.0,
         "status": "EMPTY", "verdict": "BEHIND", "category": "evidence", "error": None},
    ],
    "summary": {"ok": 1, "empty": 1, "total": 2, "unreadable": 0},
}


def _write(root: Path, payload) -> Path:
    path = root / _MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_absent_manifest_is_no_data(tmp_path):
    out = gate_manifest({}, root=tmp_path)
    assert out["status"] == "no_data"
    assert out["source_artifact"] == _MANIFEST
    assert out["as_of"] is None


def test_unparseable_manifest_is_no_data(tmp_path):
    path = tmp_path / _MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert gate_manifest({}, root=tmp_path)["status"] == "no_data"


def test_rows_and_summary_are_verbatim(tmp_path):
    _write(tmp_path, _FIXTURE)
    out = gate_manifest({}, root=tmp_path)
    assert out["status"] == "ok"
    assert out["category"] == "gate_manifest"
    assert out["source_artifact"] == _MANIFEST
    assert out["as_of"] == _FIXTURE["as_of"]  # manifest's own as_of, not file mtime
    assert out["summary"] == _FIXTURE["summary"]
    assert out["rows"] == _FIXTURE["rows"]  # nothing derived, reshaped, or rounded
    assert out["n_rows"] == 2
    assert out["manifest_staleness_days"] is not None


def test_status_filter_is_case_insensitive_and_keeps_ok_when_empty(tmp_path):
    _write(tmp_path, _FIXTURE)
    only_ok = gate_manifest({"status": "ok"}, root=tmp_path)
    assert [r["name"] for r in only_ok["rows"]] == ["backtest_fwer.jsonl"]
    # a filter matching nothing is still "ok" with 0 rows -- distinct from no_data
    none_match = gate_manifest({"status": "UNREADABLE"}, root=tmp_path)
    assert none_match["status"] == "ok" and none_match["n_rows"] == 0


def test_non_object_manifest_is_no_data(tmp_path):
    _write(tmp_path, [1, 2, 3])
    assert gate_manifest({}, root=tmp_path)["status"] == "no_data"


def test_tool_spec_names_its_truth_source_and_has_a_handler():
    (spec,) = tool_specs()
    assert spec["name"] == "gate_manifest"
    assert _MANIFEST in spec["description"]
    assert spec["handler"] is gate_manifest
    assert spec["inputSchema"]["type"] == "object"


def test_live_repo_artifact_reads_or_fails_closed():
    """Against the real repo root: either a well-formed ok envelope or no_data."""
    out = gate_manifest({})
    assert out["status"] in ("ok", "no_data")
    assert out["source_artifact"] == _MANIFEST
    if out["status"] == "ok":
        assert (_ROOT / _MANIFEST).is_file()
        assert isinstance(out["rows"], list)
        assert out["as_of"]
