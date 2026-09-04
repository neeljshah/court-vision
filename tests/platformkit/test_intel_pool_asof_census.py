"""Focused S223 tests for the read-only intelligence AS-OF census."""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.intel_pool_asof_census import collect_census, inspect_store


def _write(path, frame):
    frame.to_parquet(path, index=False)
    return path


def test_labels_safe_snapshot_and_undated(tmp_path):
    safe = _write(tmp_path / "safe.parquet", pd.DataFrame({
        "player_id": [1, 1], "asof_date": ["2026-01-01", "2026-01-02"],
    }))
    snapshot = _write(tmp_path / "snapshot.parquet", pd.DataFrame({
        "team_tricode": ["AAA", "BBB"], "as_of": ["2026-05-31", "2026-05-31"],
    }))
    undated = _write(tmp_path / "undated.parquet", pd.DataFrame({
        "team_id": [1, 2], "rating": [0.2, 0.3],
    }))

    rows = collect_census(tmp_path, [
        ("intelligence", safe), ("atlas", snapshot), ("intelligence", undated),
    ])
    by_path = {row["path"]: row for row in rows}
    assert by_path["safe.parquet"]["label"] == "AS-OF SAFE"
    assert by_path["safe.parquet"]["n_distinct_as_of"] == 2
    assert by_path["safe.parquet"]["classification_field"] == "asof_date"
    assert by_path["safe.parquet"]["temporal_fields"] == ["asof_date"]
    assert by_path["snapshot.parquet"]["label"] == "SNAPSHOT-ONLY"
    assert by_path["snapshot.parquet"]["n_distinct_as_of"] == 1
    assert by_path["snapshot.parquet"]["producer_module"] == "NONE"
    assert by_path["undated.parquet"]["label"] == "UNDATED"
    assert by_path["undated.parquet"]["n_distinct_as_of"] is None


def test_single_game_date_is_not_an_as_of_snapshot(tmp_path):
    path = _write(tmp_path / "one_game_day.parquet", pd.DataFrame({
        "game_id": [1, 2], "game_date": ["2026-05-31", "2026-05-31"],
    }))

    row = inspect_store(tmp_path, "intelligence", path)

    assert row["label"] == "UNDATED"
    assert row["classification_field"] == "game_date"
    assert row["as_of_column"] == "game_date"


def test_as_of_scan_reads_every_row_group(tmp_path):
    path = tmp_path / "two_row_groups.parquet"
    table = pa.Table.from_pandas(pd.DataFrame({
        "as_of": ["2026-01-01", "2026-01-02"],
    }), preserve_index=False)
    pq.write_table(table, path, row_group_size=1)

    row = inspect_store(tmp_path, "atlas", path)

    assert row["n_distinct_as_of"] == 2
    assert row["label"] == "AS-OF SAFE"


def test_missing_declared_path_is_not_silently_dropped(tmp_path):
    row = inspect_store(tmp_path, "atlas", tmp_path / "atlas_missing.parquet")
    assert row["label"] == "UNDATED"
    assert row["error"] == "NO_MATCHING_FILES: declared path is absent"
