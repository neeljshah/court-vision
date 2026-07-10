"""Per-file test for system_proof. Mocks every section (no subprocess/network/data/
dependency) -- exercises the composition/isolation/precedence logic only. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/proof_harness/test_system_proof.py -q
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from scripts.platformkit.proof_harness import system_proof as sp


def _sec(overall: str, summary: str = "ok") -> dict:
    return {"overall": overall, "summary": summary}


def test_run_all_green_when_every_section_green():
    fns = {"a": lambda: _sec(sp.GREEN), "b": lambda: _sec(sp.GREEN)}
    doc = sp.run_all(fns, now=0.0)
    assert doc["overall"] == sp.GREEN
    assert doc["n_red_sections"] == 0 and doc["n_pending_sections"] == 0


def test_run_all_red_wins_over_pending():
    fns = {"fleet": lambda: _sec(sp.RED), "autonomy": lambda: _sec(sp.PENDING),
           "gates": lambda: _sec(sp.GREEN)}
    doc = sp.run_all(fns, now=0.0)
    assert doc["overall"] == sp.RED
    assert doc["n_red_sections"] == 1 and doc["n_pending_sections"] == 1


def test_run_all_pending_when_no_red():
    fns = {"autonomy": lambda: _sec(sp.PENDING), "gates": lambda: _sec(sp.GREEN)}
    doc = sp.run_all(fns, now=0.0)
    assert doc["overall"] == sp.PENDING


def test_run_all_isolates_a_crashing_section():
    def _boom():
        raise RuntimeError("kaboom")
    fns = {"broken": _boom, "fine": lambda: _sec(sp.GREEN)}
    doc = sp.run_all(fns, now=0.0)
    assert doc["sections"]["broken"]["overall"] == sp.RED
    assert "kaboom" in doc["sections"]["broken"]["error"]
    assert doc["sections"]["fine"]["overall"] == sp.GREEN
    assert doc["overall"] == sp.RED


def test_render_table_lists_every_section_and_overall_verdict():
    doc = sp.run_all({"fleet": lambda: _sec(sp.GREEN, "45 ProcSpecs")}, now=0.0)
    table = sp.render_table(doc)
    assert "fleet" in table and "45 ProcSpecs" in table
    assert "OVERALL: GREEN" in table


def test_canonical_job_names_scanned_from_source(tmp_path):
    src = tmp_path / "fake_maintenance.py"
    src.write_text(
        'out["census_drift"] = run_check()\n'
        'out["mechanism_reval"] = run_mechanism_reval(watermarks)\n'
        'out["mechanism_reval"] = again()\n',  # duplicate must dedupe
        encoding="utf-8")
    names = sp._canonical_job_names(src=src)
    assert names == ["census_drift", "mechanism_reval"]


def test_canonical_job_names_missing_source_is_empty_not_crash(tmp_path):
    assert sp._canonical_job_names(src=tmp_path / "absent.py") == []


def test_section_ledgers_missing_file_is_na_not_red(tmp_path):
    out = sp.section_ledgers({"ghost": tmp_path / "nope.jsonl"})
    assert out["rows"][0]["status"] == sp.NA
    assert out["overall"] == sp.GREEN  # NA never fails the section


def test_section_ledgers_counts_nonblank_rows(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text('{"a":1}\n\n{"a":2}\n', encoding="utf-8")
    out = sp.section_ledgers({"l": p})
    row = out["rows"][0]
    assert row["status"] == sp.GREEN
    assert row["n_rows"] == 2  # blank line not counted


def test_section_ledgers_stale_last_append_is_red(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text('{"a":1}\n', encoding="utf-8")
    old = time.time() - (sp._STALE_LEDGER_HOURS + 1) * 3600
    os.utime(p, (old, old))
    out = sp.section_ledgers({"l": p})
    assert out["rows"][0]["status"] == sp.RED
    assert out["overall"] == sp.RED


def test_section_ledgers_empty_present_file_is_red_not_green(tmp_path):
    p = tmp_path / "l.jsonl"
    p.write_text("", encoding="utf-8")
    out = sp.section_ledgers({"l": p})
    assert out["rows"][0]["status"] == sp.RED
    assert out["rows"][0]["n_rows"] == 0


def test_section_autonomy_red_when_job_registry_unreadable(monkeypatch):
    monkeypatch.setattr(sp, "_canonical_job_names", lambda: [])
    out = sp.section_autonomy()
    assert out["overall"] == sp.RED
    assert out["rows"] == []


def test_section_data_folds_census_drift_into_red(monkeypatch):
    def _fake_run_check():
        return {"n_ok": 1, "n_drift": 1, "n_missing": 0, "n_unverifiable": 0, "drift_entries": []}
    monkeypatch.setattr("scripts.platformkit.census_drift.run_check", _fake_run_check)
    out = sp.section_data()
    assert out["overall"] == sp.RED


def test_section_data_flags_stale_key_store_as_red(monkeypatch):
    ancient = time.time() - (sp._STALE_DATA_HOURS + 24) * 3600
    monkeypatch.setattr(sp.os.path, "getmtime", lambda p: ancient)
    out = sp.section_data()
    assert out["overall"] == sp.RED
    assert any(s.get("status") == sp.RED and "stale" in (s.get("reason") or "")
               for s in out["key_stores"])
