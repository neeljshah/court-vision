"""S180: current MLB as-of siblings fill only the current corpus era."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.platformkit.combo import corpus_cache_sources as sources


EXPECTED_COLUMNS = [
    "event_id", "corpus_unit", "event_date", "y", "p_base", "p_home_elo",
    "sp_first6_diff_ew", "park_factor", "sp_ra_diff_asof",
]


def _write_inputs(repo: Path) -> None:
    root = repo / "data" / "domains" / "mlb"
    root.mkdir(parents=True)
    games = {
        "games.parquet": pd.DataFrame({
            "event_id": ["l1", "l2"],
            "date": pd.to_datetime(["2021-01-01", "2021-01-02"]),
            "target_home_win": [1.0, 0.0],
        }),
        "games_current.parquet": pd.DataFrame({
            "event_id": ["c1", "c2"],
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "target_home_win": [0.0, 1.0],
        }),
        "asof_park.parquet": pd.DataFrame({
            "event_id": ["l1", "l2", "c1", "c2"],
            "park_factor": [1.01, 1.02, 1.03, float("nan")],
        }),
        "asof_features.parquet": pd.DataFrame({
            "event_id": ["l1", "l2", "c1", "c2"],
            "sp_ra_diff_asof": [0.11, 0.12, 0.13, float("nan")],
        }),
        "asof_park_current.parquet": pd.DataFrame({
            "event_id": ["l1", "c1", "c2"],
            "park_factor": [9.01, 9.03, 9.04],
        }),
        "asof_features_current.parquet": pd.DataFrame({
            "event_id": ["l1", "c1", "c2"],
            "sp_ra_diff_asof": [9.11, 9.13, 9.14],
        }),
    }
    for name, frame in games.items():
        frame.to_parquet(root / name, index=False)


def test_current_siblings_fill_current_era_without_overwriting_legacy(tmp_path, monkeypatch):
    _write_inputs(tmp_path)
    monkeypatch.setattr(sources._cache, "_REPO", tmp_path)
    monkeypatch.setattr(sources, "build_sp_form_features", lambda: pd.DataFrame({
        "event_id": ["l1", "l2", "c1", "c2"],
        "sp_first6_diff_ew": [1.1, 1.2, 1.3, 1.4],
    }))
    monkeypatch.setattr(sources, "mlb_walk_forward_elo", lambda games: pd.DataFrame({
        "event_id": games["event_id"],
        "date": games["date"],
        "p_home_elo": [0.6, 0.4],
    }))

    result, source_paths = sources._build_mlb()

    assert list(result.columns) == EXPECTED_COLUMNS
    assert len(result) == 4
    assert result["y"].notna().all() and result["p_base"].notna().all()
    by_id = result.set_index("event_id")
    assert by_id.loc["l1", "park_factor"] == 1.01
    assert by_id.loc["l1", "sp_ra_diff_asof"] == 0.11
    assert by_id.loc["c1", "park_factor"] == 1.03
    assert by_id.loc["c1", "sp_ra_diff_asof"] == 0.13
    assert by_id.loc["c2", "park_factor"] == 9.04
    assert by_id.loc["c2", "sp_ra_diff_asof"] == 9.14
    assert [path.name for path in source_paths] == [
        "games.parquet", "games_current.parquet", "asof_park.parquet",
        "asof_features.parquet", "asof_park_current.parquet",
        "asof_features_current.parquet",
    ]
