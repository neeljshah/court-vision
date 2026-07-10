"""Per-file test for knowledge.validate_replication_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_replication_wave1.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_replication_wave1 as vrep


def test_corpus_exists_for_the_declared_replication_season():
    assert vrep._corpus_exists(vrep.REPLICATION_SEASON)


def test_corpus_missing_season_is_not_replicable():
    assert not vrep._corpus_exists(1901)
    r = vrep._not_replicable("compassionate_umpire_count_zone", 1901)
    assert r["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r["hypothesis"] == "compassionate_umpire_count_zone__replication_1901"


def test_run_reports_not_replicable_when_corpus_missing(monkeypatch, tmp_path):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrep, "LEDGER_PATH", ledger)
    rows = vrep.run(season=1901)
    assert len(rows) == 2
    assert all(r["verdict"] == "NOT_REPLICABLE_NO_CORPUS" for r in rows)
    assert all(r["edge_claimed"] is False for r in rows)


def test_dispersion_replication_maps_confirmed_local_to_replicated(monkeypatch):
    # reuse the original module's own CONFIRMED_LOCAL synthetic fixture shape
    fake = pd.DataFrame({"n": [50, 50, 50, 50, 50], "calls": [2, 3, 2, 20, 3]})
    monkeypatch.setattr(vrep, "per_game_frame", lambda df: fake)
    monkeypatch.setattr(vrep, "load_season", lambda season=2024: pd.DataFrame({"a": [1]}))
    r = vrep.replicate_called_strike_dispersion(season=2024)
    assert r["verdict"] == "REPLICATED"
    assert r["hypothesis"].endswith("__replication_2024")


def test_dispersion_replication_maps_null_local_to_failed_replication(monkeypatch):
    fake = pd.DataFrame({"n": [50] * 20, "calls": [3] * 20})
    monkeypatch.setattr(vrep, "per_game_frame", lambda df: fake)
    monkeypatch.setattr(vrep, "load_season", lambda season=2024: pd.DataFrame({"a": [1]}))
    r = vrep.replicate_called_strike_dispersion(season=2024)
    assert r["verdict"] == "FAILED_REPLICATION"
