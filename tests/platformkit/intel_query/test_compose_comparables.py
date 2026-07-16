"""Per-file test: python -m pytest tests/platformkit/intel_query/test_compose_comparables.py -q

Tiny fixture parquet -> deterministic nearest neighbor; missing entity ->
no_data; thin shared-attribute intersection -> refused.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_query.compose_comparables import compose_comparables

ATTRS = ["a1", "a2", "a3", "a4", "a5", "a6"]


def _row(eid, name, attr, pct):
    return {"entity_id": eid, "entity_name": name, "window": "season_2025_26",
            "attribute": attr, "percentile": pct}


def _make_profiles(tmp_path) -> str:
    rows = []
    # A (target): [10,20,30,40,50,60] across a1..a6
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row(1, "Player A", attr, pct))
    # B: close to A (delta=2 on every shared attr) -- the expected nearest neighbor
    for attr, pct in zip(ATTRS, [12, 22, 32, 42, 52, 62]):
        rows.append(_row(2, "Player B", attr, pct))
    # C: far from A (mirrored values)
    for attr, pct in zip(ATTRS, [90, 80, 70, 60, 50, 40]):
        rows.append(_row(3, "Player C", attr, pct))
    # D: only 3 attrs shared with A -- below the default floor of 5, must be excluded
    for attr, pct in zip(ATTRS[:3], [10, 20, 30]):
        rows.append(_row(4, "Player D", attr, pct))
    df = pd.DataFrame(rows)
    path = tmp_path / "profiles"
    path.mkdir()
    df.to_parquet(path / "fake_player_profiles.parquet")
    return str(path)


def test_deterministic_nearest_neighbor(tmp_path):
    profiles_dir = _make_profiles(tmp_path)
    result = compose_comparables("fake", "Player A", k=2, profiles_dir=profiles_dir)
    assert result["status"] == "ok"
    assert result["entity_id"] == 1
    neighbors = result["neighbors"]
    # B (dist RMS=2) must rank ahead of C (far); D never appears (below floor)
    assert [n["entity_id"] for n in neighbors] == [2, 3]
    assert neighbors[0]["distance"] == 2.0
    assert neighbors[0]["n_attrs"] == 6
    assert all(n["entity_id"] != 4 for n in neighbors)


def test_missing_entity_is_no_data(tmp_path):
    profiles_dir = _make_profiles(tmp_path)
    result = compose_comparables("fake", "Nobody Here", profiles_dir=profiles_dir)
    assert result["status"] == "no_data"
    assert result["category"] == "player_comparables"


def test_thin_intersection_is_refused(tmp_path):
    # Only A and D exist -- D shares just 3 attrs with A, below the floor of 5.
    rows = []
    for attr, pct in zip(ATTRS, [10, 20, 30, 40, 50, 60]):
        rows.append(_row(1, "Player A", attr, pct))
    for attr, pct in zip(ATTRS[:3], [10, 20, 30]):
        rows.append(_row(4, "Player D", attr, pct))
    df = pd.DataFrame(rows)
    path = tmp_path / "profiles"
    path.mkdir()
    df.to_parquet(path / "fake_player_profiles.parquet")

    result = compose_comparables("fake", "Player A", profiles_dir=str(path))
    assert result["status"] == "refused"
    assert "floor" in result["note"] or "intersection" in result["note"]


def test_no_data_when_parquet_absent(tmp_path):
    result = compose_comparables("fake", "Player A", profiles_dir=str(tmp_path))
    assert result["status"] == "no_data"
