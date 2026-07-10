"""Per-file test for knowledge.validate_replication_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_replication_wave1.py -q
"""
from __future__ import annotations

from domains.basketball_nba.knowledge import validate_replication_wave1 as vrw


def test_self_check():
    vrw._self_check()


def test_boxdetail_replication_is_honest_not_replicable(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(vrw, "LEDGER_PATH", ledger)
    r_fb = vrw.fast_break_pts_persistence_replication()
    r_pt = vrw.paint_pts_persistence_replication()
    assert r_fb["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r_pt["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert r_fb["n"] == 0 and r_pt["n"] == 0


def test_run_against_real_corpus_matches_expected_verdicts(tmp_path, monkeypatch):
    """Integration check against the real on-disk corpora (no mocking of the
    data files themselves -- only the ledger write target, so this test
    never mutates the real validation_ledger.jsonl)."""
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(vrw, "LEDGER_PATH", ledger)
    rows = vrw.run()
    by_hyp = {r["hypothesis"]: r for r in rows}
    assert by_hyp["timeout_interrupts_opponent_run_replication_2022_23"]["verdict"] == "REPLICATED"
    assert by_hyp["q1_slow_start_persists_replication_2024_25"]["verdict"] == "REPLICATED"
    assert by_hyp["fast_break_pts_persistence_replication"]["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert by_hyp["paint_pts_persistence_replication"]["verdict"] == "NOT_REPLICABLE_NO_CORPUS"
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == len(rows)
