"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_mlb_utilization_audit.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.data_frontier import mlb_utilization_audit as mua


def test_parquet_schema_reads_names_dtypes_coverage(tmp_path):
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "y", "z"]})
    fp = tmp_path / "t.parquet"
    df.to_parquet(fp, index=False)
    cols = mua._parquet_schema(fp)
    names = {c[0] for c in cols}
    assert names == {"a", "b"}
    cov = {c[0]: c[2] for c in cols}
    assert cov["b"] == 100.0
    assert cov["a"] < 100.0  # one null


def test_jsonl_fields_reads_keys(tmp_path):
    fp = tmp_path / "t.jsonl"
    fp.write_text('{"x": 1, "y": "a"}\n{"x": 2, "y": null}\n', encoding="utf-8")
    fields = {k for k, _, _ in mua._jsonl_fields(fp)}
    assert "x" in fields
    # y is null on line 2 but present (non-null) on line 1, so still counted
    assert "y" in fields


def test_consumers_for_finds_known_symbol():
    # "ATTRIBUTES" is a real top-level symbol in domains/mlb/profiles/attribute_registry.py
    hits = mua.consumers_for("ATTRIBUTES", roots=["domains/mlb"])
    assert hits, "expected git grep to find at least one hit for a known symbol"
    assert any("attribute_registry.py" in h for h in hits)


def test_consumers_for_returns_empty_for_nonsense_token():
    hits = mua.consumers_for("zzz_definitely_not_a_real_column_zzz", roots=["domains/mlb"])
    assert hits == []


def test_build_inventory_shape(monkeypatch):
    # Restrict to one tiny, always-present corpus so the test stays fast.
    monkeypatch.setattr(mua, "CORPORA", [("data/domains/mlb/platoon_split_index.parquet", "parquet")])
    rows = mua.build_inventory()
    assert rows, "expected at least one column row"
    row = rows[0]
    assert set(row) == {"column", "dtype", "corpora", "coverage_pct_sample", "used_in", "status"}
    assert row["status"] in ("USED", "UNUSED")
    json.dumps(rows)  # must be JSON-serializable
