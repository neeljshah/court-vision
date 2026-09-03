"""Gap S183 -- corpus cache feature coverage census.

Per-file test only: `python -m pytest scripts/platformkit/combo/test_corpus_cache_coverage.py -q`
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.combo import corpus_cache as cc
from scripts.platformkit.combo import corpus_cache_sources as sources


def test_column_coverage_excludes_spine_and_names_zero_unit_cells():
    df = pd.DataFrame({
        "event_id": ["a", "b", "c"], "corpus_unit": ["alpha", "alpha", "beta"],
        "event_date": ["2026-01-01", "2026-01-02", "2026-01-03"], "y": [1.0, 0.0, 1.0],
        "partial": [1.0, None, 3.0], "empty_beta": [1.0, 2.0, None],
    })
    census = sources.column_coverage(df)
    assert set(census["coverage"]) == {"partial", "empty_beta"}
    assert census["coverage"]["partial"]["n_non_null"] == 2
    assert census["coverage"]["partial"]["rate"] == 2 / 3
    assert census["coverage"]["empty_beta"]["corpus_unit"]["beta"] == {
        "n_rows": 1, "n_non_null": 0, "rate": 0.0}
    assert census["zero_coverage"] == [{"column": "empty_beta", "corpus_unit": "beta"}]


def test_build_and_freshness_report_include_the_same_census(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    source = tmp_path / "source.parquet"
    source.write_bytes(b"source")
    df = pd.DataFrame({
        "event_id": ["a", "b"], "corpus_unit": ["u", "v"],
        "event_date": ["2026-01-01", "2026-01-02"], "y": [1.0, 0.0],
        "present": [1.0, 2.0], "missing_v": [1.0, None],
    })
    monkeypatch.setitem(cc._BUILDERS, "mlb", lambda: (df, [source]))
    cc.build_gate_corpus("mlb")
    manifest = json.loads((tmp_path / "gate_corpus_mlb.sources.json").read_text(encoding="utf-8"))
    report = cc.freshness_report("mlb")
    assert report["coverage"] == manifest["coverage"]
    assert report["zero_coverage"] == manifest["zero_coverage"] == [
        {"column": "missing_v", "corpus_unit": "v"}]
