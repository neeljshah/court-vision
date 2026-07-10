"""Per-file test for knowledge.validate_replication_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_replication_wave1.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_replication_wave1 as vrep


def test_not_replicable_when_group_empty():
    r = vrep._not_replicable("xg_supremacy_persistence", "empty_group", "no rows")
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r["hypothesis"] == "xg_supremacy_persistence__replication_empty_group"


def test_match_meta_full_exists_for_sub_timing_replication():
    assert vrep.MATCH_META_FULL_PATH.exists()


def test_replicate_xg_supremacy_persistence_replicates_on_both_disjoint_groups():
    for group, divs in vrep.XG_SUPREMACY_GROUPS.items():
        r = vrep.replicate_xg_supremacy_persistence(group, divs)
        assert r["verdict"] == "REPLICATED", r
        assert r["n"] >= 10


def test_replicate_substitution_timing_reports_honest_disjoint_group_outcomes():
    big4 = vrep.replicate_substitution_timing("big4_2015_16", vrep.BIG4_2015_16)
    assert big4["verdict"] in ("REPLICATED", "FAILED_REPLICATION")
    assert big4["hypothesis"] == "substitution_timing_moderates_shift__replication_big4_2015_16"


def test_run_writes_ledger_rows(monkeypatch, tmp_path):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrep, "LEDGER_PATH", ledger)
    rows = vrep.run()
    assert len(rows) == 4
    assert all(r["edge_claimed"] is False for r in rows)
    assert ledger.exists()
