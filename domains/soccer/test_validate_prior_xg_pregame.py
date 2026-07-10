"""Per-file test for validate_prior_xg_pregame. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_validate_prior_xg_pregame.py -q
"""
from __future__ import annotations

from domains.soccer import validate_prior_xg_pregame as vp


def test_corpus_wins_requires_significant_nondegenerate_improvement():
    """Failure mode: a corpus must not count as a 'win' unless the feature
    actually improved Brier AND cleared DM significance AND the base itself
    is skillful -- any one of those failing must return False."""
    assert vp._corpus_wins({"feat_better": True, "dm_p": 0.001, "base_degenerate": False}) is True
    assert vp._corpus_wins({"feat_better": False, "dm_p": 0.001, "base_degenerate": False}) is False
    assert vp._corpus_wins({"feat_better": True, "dm_p": 0.9, "base_degenerate": False}) is False
    assert vp._corpus_wins({"feat_better": True, "dm_p": 0.001, "base_degenerate": True}) is False


def test_run_writes_one_edge_free_row(tmp_path, monkeypatch):
    """Wiring-only check: run() appends exactly one ledger row, edge-claim-free,
    with a verdict from the declared set -- a bad-corpus swap must not sink it."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vp, "LEDGER_PATH", ledger)
    row = vp.run()
    assert row["hypothesis"] == vp.HYPOTHESIS
    assert row["edge_claimed"] is False and row["sport"] == "soccer"
    assert row["verdict"] in ("CONFIRMED", "PROVISIONAL", "NULL_LOCAL", "NOT_TESTABLE")
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 1
