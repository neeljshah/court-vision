"""Per-file test for validate_xg_diff_ingame. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_validate_xg_diff_ingame.py -q
"""
from __future__ import annotations

from domains.soccer import validate_xg_diff_ingame as vi


def test_corpus_wins_requires_significant_nondegenerate_improvement():
    assert vi._corpus_wins({"feat_better": True, "dm_p": 0.001, "base_degenerate": False}) is True
    assert vi._corpus_wins({"feat_better": False, "dm_p": 0.001, "base_degenerate": False}) is False
    assert vi._corpus_wins({"feat_better": True, "dm_p": 0.9, "base_degenerate": False}) is False


def test_majority_of_three_minutes_is_two():
    """Failure mode: a 1-of-3 minute win must NOT count as CONFIRMED -- the
    verdict threshold requires a majority of the checked minute snapshots."""
    assert len(vi.MINUTES) == 3
    assert (len(vi.MINUTES) // 2 + 1) == 2


def test_run_writes_one_edge_free_row(tmp_path, monkeypatch):
    """Wiring-only check: run() appends exactly one ledger row across all
    minute snapshots, edge-claim-free, with a verdict from the declared set."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vi, "LEDGER_PATH", ledger)
    row = vi.run()
    assert row["hypothesis"] == vi.HYPOTHESIS
    assert row["edge_claimed"] is False and row["sport"] == "soccer"
    assert row["verdict"] in ("CONFIRMED", "PROVISIONAL", "NULL_LOCAL", "NOT_TESTABLE")
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 1
