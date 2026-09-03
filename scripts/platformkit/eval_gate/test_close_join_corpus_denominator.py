"""S181 corpus-spine coverage tests."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate.close_join import coverage_report


_SOCCER_UNITS = {
    "D1": (3366, 2142, 0.6363636364), "E0": (4180, 2660, 0.6363636364),
    "E1": (6072, 3864, 0.6363636364), "F1": (3856, 2336, 0.6058091286),
    "I1": (4180, 2660, 0.6363636364), "SP1": (4180, 2660, 0.6363636364),
}


def test_soccer_corpus_spine_includes_every_cached_corpus_row():
    report = coverage_report("soccer")
    corpus = pd.read_parquet("data/cache/combo/gate_corpus_soccer.parquet")
    corpus_rows = len(corpus)
    corpus_ids = set(corpus["event_id"].astype(str))
    del corpus
    odds = pd.read_parquet("data/domains/soccer/odds.parquet")
    odds_ids = set(odds["event_id"].astype(str))
    del odds

    assert corpus_rows == len(corpus_ids) == 25834
    assert len(corpus_ids - odds_ids) == 9512 and not odds_ids - corpus_ids
    assert report["corpus_denominator"] == 25834
    assert report["corpus_joined"] == 16322
    assert report["corpus_unjoined"] == 9512
    assert report["corpus_join_rate"] == pytest.approx(0.6318030502, abs=1e-9)
    for unit, (denominator, joined, rate) in _SOCCER_UNITS.items():
        block = report["by_corpus_unit_spine"][unit]
        assert block["corpus_denominator"] == denominator
        assert block["corpus_joined"] == joined
        assert block["corpus_join_rate"] == pytest.approx(rate, abs=1e-9)


def test_corpus_spine_guard_rejects_a_perfect_unit_with_unjoined_rows(monkeypatch):
    from scripts.platformkit.eval_gate import close_join as cj

    joined = pd.DataFrame({
        "event_id": ["e1", "e2"], "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "_spine_join": ["both", "both"], "devig_close_prob": [0.5, 0.5],
        "corpus_unit": ["A", "B"], "y": [1.0, 0.0], "p_base": [0.5, 0.5],
    })
    corpus = pd.DataFrame({"event_id": ["e1", "e2", "e3"], "corpus_unit": ["A", "B", "B"]})
    monkeypatch.setattr(cj, "_joined", lambda *args, **kwargs: (joined, {}))
    monkeypatch.setattr(cj, "load_gate_corpus", lambda *args, **kwargs: corpus)

    with pytest.raises(ValueError, match="by_corpus_unit_spine"):
        coverage_report("soccer")
