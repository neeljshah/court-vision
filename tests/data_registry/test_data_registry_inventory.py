"""Per-file tests for the data_registry census + fail-closed drift gate.

Builds tiny real parquet files in a tmp data/domains tree (absolute root path), then
exercises scan, fingerprint stability, drift detection, the fail-closed gate, and the
atomic write/load roundtrip. No real corpora touched.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/data_registry/test_data_registry_inventory.py -q
"""
from __future__ import annotations

import pandas as pd

from data_registry.inventory import (
    build_inventory,
    check_drift,
    fail_closed,
    load_inventory,
    scan_corpora,
    write_inventory,
)
from data_registry.schema import CensusRow, make_census_row, schema_hash


def _mk(root, sport, name, df):
    d = root / "data" / "domains" / sport
    d.mkdir(parents=True, exist_ok=True)
    df.to_parquet(d / f"{name}.parquet", index=False)


def _domains_root(tmp_path):
    return str(tmp_path / "data" / "domains")


# --------------------------------------------------------------------------- #
# schema helpers
# --------------------------------------------------------------------------- #
def test_schema_hash_stable_and_order_independent():
    a = {"x": "int64", "y": "string"}
    b = {"y": "string", "x": "int64"}  # same set, different order
    assert schema_hash(a) == schema_hash(b)
    assert schema_hash(a) != schema_hash({"x": "double", "y": "string"})


def test_make_census_row_consistency():
    r = make_census_row("tennis", "games", "p/games.parquet", 0, {"a": "int64"})
    assert r.is_empty is True and r.n_cols == 1
    r2 = make_census_row("tennis", "games", "p/games.parquet", 5, {"a": "int64", "b": "string"})
    assert r2.is_empty is False and r2.n_cols == 2


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #
def test_scan_reports_rows_and_empty_flag(tmp_path):
    _mk(tmp_path, "tennis", "matches", pd.DataFrame({"event_id": [1, 2, 3], "p1": ["a", "b", "c"]}))
    _mk(tmp_path, "tennis", "odds", pd.DataFrame({"event_id": []}))  # empty corpus
    _mk(tmp_path, "mlb", "games", pd.DataFrame({"event_id": [1]}))

    rows = scan_corpora(root=_domains_root(tmp_path))
    by = {(r.sport, r.name): r for r in rows}
    assert by[("tennis", "matches")].n_rows == 3
    assert by[("tennis", "matches")].n_cols == 2
    assert by[("tennis", "odds")].is_empty is True
    assert by[("mlb", "games")].n_rows == 1
    assert {r.sport for r in rows} == {"tennis", "mlb"}


def test_scan_sport_filter(tmp_path):
    _mk(tmp_path, "tennis", "matches", pd.DataFrame({"x": [1]}))
    _mk(tmp_path, "mlb", "games", pd.DataFrame({"x": [1]}))
    rows = scan_corpora(root=_domains_root(tmp_path), sports=["tennis"])
    assert {r.sport for r in rows} == {"tennis"}


# --------------------------------------------------------------------------- #
# drift + fail-closed
# --------------------------------------------------------------------------- #
def test_zero_rows_blocks(tmp_path):
    _mk(tmp_path, "tennis", "matches", pd.DataFrame({"event_id": [1]}))
    _mk(tmp_path, "tennis", "odds", pd.DataFrame({"event_id": []}))
    ok, findings = fail_closed(root=_domains_root(tmp_path), baseline_path="nonexistent.json")
    assert ok is False
    kinds = {(f.name, f.kind) for f in findings}
    assert ("odds", "zero_rows") in kinds


def test_clean_no_baseline_passes(tmp_path):
    _mk(tmp_path, "tennis", "matches", pd.DataFrame({"event_id": [1, 2]}))
    ok, findings = fail_closed(root=_domains_root(tmp_path), baseline_path="nonexistent.json")
    assert ok is True and findings == []


def test_drift_vs_baseline_detects_removed_cols_missing_and_regression(tmp_path):
    # baseline: matches has 100 rows + cols {event_id, surface}; odds present
    base_rows = [
        make_census_row("tennis", "matches", "p", 100, {"event_id": "int64", "surface": "string"}),
        make_census_row("tennis", "odds", "p", 50, {"event_id": "int64"}),
    ]
    baseline = {"rows": [r.to_dict() for r in base_rows]}

    # current: matches lost the surface column AND dropped to 50 rows; odds vanished
    current = [
        make_census_row("tennis", "matches", "p", 50, {"event_id": "int64"}),
    ]
    findings = check_drift(current, baseline)
    kinds = {(f.name, f.kind) for f in findings}
    assert ("matches", "removed_columns") in kinds
    assert ("matches", "row_regression") in kinds
    assert ("odds", "missing_corpus") in kinds
    assert any(f.severity == "block" for f in findings)


def test_drift_schema_change_is_warn_not_block(tmp_path):
    base_rows = [make_census_row("mlb", "games", "p", 10, {"event_id": "int64"})]
    baseline = {"rows": [r.to_dict() for r in base_rows]}
    # added a column (superset) + same rows -> schema_change WARN, no block
    current = [make_census_row("mlb", "games", "p", 12, {"event_id": "int64", "new": "double"})]
    findings = check_drift(current, baseline)
    assert len(findings) == 1
    assert findings[0].kind == "schema_change" and findings[0].severity == "warn"


# --------------------------------------------------------------------------- #
# persistence roundtrip
# --------------------------------------------------------------------------- #
def test_write_load_roundtrip_and_dataclass_roundtrip(tmp_path):
    _mk(tmp_path, "tennis", "matches", pd.DataFrame({"event_id": [1, 2], "p1": ["a", "b"]}))
    inv = build_inventory(root=_domains_root(tmp_path))
    out = tmp_path / "_INVENTORY.json"
    write_inventory(inv, path=str(out))
    loaded = load_inventory(path=str(out))
    assert loaded is not None
    assert loaded["n_corpora"] == inv["n_corpora"] == 1
    assert loaded["sports"] == ["tennis"]
    # CensusRow survives a dict roundtrip
    r0 = CensusRow.from_dict(loaded["rows"][0])
    assert r0.sport == "tennis" and r0.name == "matches" and r0.n_rows == 2
