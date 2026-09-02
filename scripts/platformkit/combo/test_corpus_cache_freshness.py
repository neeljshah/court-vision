"""Gap S41/S44 -- corpus_cache.freshness_report: stale detection + order basis.

Per-file test only: `python -m pytest scripts/platformkit/combo/test_corpus_cache_freshness.py -q`
"""
from __future__ import annotations

import json
import time

import pandas as pd
import pytest

from scripts.platformkit.combo import corpus_cache as cc


def _seed(tmp_path, monkeypatch, *, with_date: bool):
    """Write one fake cached corpus + sidecar into a tmp cache dir."""
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    src = tmp_path / "fake_source.parquet"
    rows = {"event_id": ["a", "b"], "corpus_unit": ["u", "u"],
            "y": [1.0, 0.0], "p_base": [0.6, 0.4]}
    if with_date:
        rows[cc.DATE_COL] = pd.to_datetime(["2026-01-01", "2026-01-02"])
    df = pd.DataFrame(rows)
    df.to_parquet(src, index=False)
    df.to_parquet(tmp_path / "gate_corpus_mlb.parquet", index=False)
    (tmp_path / "gate_corpus_mlb.sources.json").write_text(json.dumps({
        "sport": "mlb", "built_at": time.time(), "n_rows": len(df),
        "sources": cc._source_manifest([src]),
    }), encoding="utf-8")
    return src


def test_fresh_cache_reports_not_stale(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=False)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is False
    assert rep["stale_reason"] is None
    assert rep["n_rows_cached"] == rep["n_rows_at_build"] == 2
    assert rep["cache_exists"] and rep["sidecar_exists"]
    assert rep["sources"][0]["changed"] is False


def test_changed_source_reports_stale(tmp_path, monkeypatch):
    src = _seed(tmp_path, monkeypatch, with_date=False)
    # rewrite the source with different content -> mtime AND sha both move
    pd.DataFrame({"event_id": ["a", "b", "c"]}).to_parquet(src, index=False)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is True
    assert "fake_source.parquet" in rep["stale_reason"]
    assert rep["sources"][0]["changed"] is True


def test_missing_cache_is_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    rep = cc.freshness_report("mlb")
    assert rep["stale"] is True
    assert rep["n_rows_cached"] is None


def test_order_basis_positional_without_a_date_column(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=False)
    assert cc.freshness_report("mlb")["order_basis"] == cc.POSITIONAL_ORDER


def test_order_basis_names_the_date_column_when_present(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, with_date=True)
    assert cc.freshness_report("mlb")["order_basis"] == cc.DATE_COL


def test_unknown_sport_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "_CACHE_DIR", tmp_path)
    with pytest.raises(ValueError):
        cc.freshness_report("cricket")
