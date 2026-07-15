"""tests for card_grade_job -- watermark gating + degrade-not-raise."""
from __future__ import annotations

from scripts.platformkit.autoloop import card_grade_job as job


def test_skips_grade_when_corpus_unchanged(monkeypatch):
    monkeypatch.setattr(job, "_corpus_bytes", lambda pattern=None: 1000)
    called = []
    monkeypatch.setattr("scripts.platformkit.claims.card_miner_bulk.mine",
                        lambda **kw: {"n_open": 0, "n_queued": 0, "n_rejected": 0})
    wm = {"card_grade_corpus_bytes": 1000}
    out = job.run_card_grade(wm)
    assert out["grade"]["status"] == "skipped"
    assert not called
    assert out["edge_claimed"] is False


def test_grades_and_advances_watermark_on_growth(monkeypatch):
    monkeypatch.setattr(job, "_corpus_bytes", lambda pattern=None: 2000)
    monkeypatch.setattr("scripts.platformkit.claims.card_miner_bulk.mine",
                        lambda **kw: {"n_open": 5, "n_queued": 0, "n_rejected": 0})
    monkeypatch.setattr("scripts.platformkit.claims.card_grade_bulk.grade_bulk",
                        lambda **kw: {"counts": {"VALIDATED": 1, "REJECTED": 2, "OPEN": 3},
                                      "n_cards": 6, "n_rows": 100,
                                      "validated_card_ids": ["card_x"]})
    wm = {"card_grade_corpus_bytes": 1000}
    out = job.run_card_grade(wm)
    assert out["grade"]["n_validated"] == 1
    assert wm["card_grade_corpus_bytes"] == 2000


def test_degrades_never_raises(monkeypatch):
    monkeypatch.setattr(job, "_corpus_bytes", lambda pattern=None: 2000)
    def boom(**kw):
        raise RuntimeError("nope")
    monkeypatch.setattr("scripts.platformkit.claims.card_miner_bulk.mine", boom)
    monkeypatch.setattr("scripts.platformkit.claims.card_grade_bulk.grade_bulk", boom)
    wm = {}
    out = job.run_card_grade(wm)
    assert out["mine"]["status"] == "error"
    assert out["grade"]["status"] == "error"
    assert "card_grade_corpus_bytes" not in wm  # watermark NOT advanced on failure


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
