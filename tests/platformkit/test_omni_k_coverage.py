"""Tests for scripts.platformkit.omni.k_coverage (K1 coverage matrix, S15).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_coverage.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import k_coverage as kc


def _synthetic_players() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 2, 3],
        "player_name": ["Alpha", "Bravo", "Charlie"],
    })


def test_init_matrix_covers_all_players_x_dimensions(tmp_path):
    matrix = kc.init_matrix(base_dir=tmp_path, players=_synthetic_players())
    assert len(matrix) == 3 * len(kc.DIMENSIONS)
    assert set(matrix["dimension"]) == set(kc.DIMENSIONS)
    assert (matrix["status"] == "UNMINED").all()
    assert (matrix["n_claims"] == 0).all()
    assert matrix["last_refreshed"].isna().all()


def test_update_cell_round_trip(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_synthetic_players())
    kc.update_cell(1, "reactions", "MINED", 4, base_dir=tmp_path)
    matrix = kc.load_matrix(base_dir=tmp_path)
    cell = matrix[(matrix["player_id"] == 1) & (matrix["dimension"] == "reactions")].iloc[0]
    assert cell["status"] == "MINED"
    assert cell["n_claims"] == 4
    assert cell["last_refreshed"] is not None
    # Other cells for player 1 stay untouched.
    other = matrix[(matrix["player_id"] == 1) & (matrix["dimension"] == "health")].iloc[0]
    assert other["status"] == "UNMINED"


def test_update_cell_rejects_unknown_dimension_or_status(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_synthetic_players())
    with pytest.raises(ValueError):
        kc.update_cell(1, "not_a_dim", "MINED", 1, base_dir=tmp_path)
    with pytest.raises(ValueError):
        kc.update_cell(1, "reactions", "NOT_A_STATUS", 1, base_dir=tmp_path)


def test_update_cell_missing_player_raises(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_synthetic_players())
    with pytest.raises(KeyError):
        kc.update_cell(999, "reactions", "MINED", 1, base_dir=tmp_path)


def test_k5_metrics_math_on_synthetic_matrix(tmp_path):
    kc.init_matrix(base_dir=tmp_path, players=_synthetic_players())
    # 3 players x 6 dims = 18 cells. Mine 3 cells: 1 MINED, 1 INSUFFICIENT_DATA, 1 ESCALATED.
    kc.update_cell(1, "reactions", "MINED", 2, base_dir=tmp_path)
    kc.update_cell(2, "reactions", "INSUFFICIENT_DATA", 0, base_dir=tmp_path)
    kc.update_cell(3, "reactions", "ESCALATED", 5, base_dir=tmp_path)
    metrics = kc.k5_metrics(base_dir=tmp_path)
    assert metrics["total_cells"] == 18
    assert metrics["mined_cells"] == 3
    assert metrics["coverage_pct_overall"] == pytest.approx(100.0 * 3 / 18, abs=1e-3)
    assert metrics["insufficient_data_share"] == pytest.approx(1 / 3, abs=1e-3)
    assert metrics["escalated_cells"] == 1
    assert metrics["escalation_yield_per_1k_mined"] == pytest.approx(1000.0 * 1 / 3, abs=1e-3)
    assert metrics["by_dimension"]["reactions"]["n_cells"] == 3
    assert metrics["by_dimension"]["reactions"]["coverage_pct"] == pytest.approx(100.0, abs=1e-3)
    assert metrics["by_dimension"]["health"]["coverage_pct"] == 0.0
    assert metrics["median_staleness_days"] is not None
    assert (tmp_path / "k5_metrics.json").is_file()
