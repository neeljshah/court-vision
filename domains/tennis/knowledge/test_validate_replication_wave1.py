"""Per-file test for knowledge.validate_replication_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_replication_wave1.py -q
"""
from __future__ import annotations

from domains.tennis.knowledge import validate_replication_wave1 as vrep


def test_not_replicable_when_group_empty():
    r = vrep._not_replicable("altitude_effect_on_serve_ace_rate", "years_1900_1905", "no rows")
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r["hypothesis"] == "altitude_effect_on_serve_ace_rate__replication_years_1900_1905"


def test_travel_scouting_is_atp_only_confirming_tour_split_not_viable():
    travel = vrep.load_travel_scouting()
    assert travel["event_id"].str.contains("-wta-").sum() == 0


def test_replicate_altitude_effect_replicates_on_both_disjoint_year_slices():
    for group, years in vrep.YEAR_SLICE_GROUPS.items():
        r = vrep.replicate_altitude_effect(group, years)
        assert r["verdict"] == "REPLICATED", r
        assert r["n"] > 1000


def test_run_writes_ledger_rows(monkeypatch, tmp_path):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrep, "LEDGER_PATH", ledger)
    rows = vrep.run()
    assert len(rows) == 2
    assert all(r["edge_claimed"] is False for r in rows)
    assert ledger.exists()
