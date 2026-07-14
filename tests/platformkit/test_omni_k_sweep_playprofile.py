"""Tests for scripts.platformkit.omni.k_sweep_playprofile (K play_profile sweep).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_playprofile.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_playprofile as ksp


def _active_players_stub():
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})


def _synthetic_profiles() -> pd.DataFrame:
    rows = []
    # Player 1: full basket present in season_2025_26, deliberately using a
    # raw_value != percentile so a percentile-as-value bug is detectable.
    for attr in ksp.BASKET:
        rows.append({
            "entity_id": 1, "entity_name": "Alpha", "window": "season_2025_26",
            "attribute": attr, "raw_value": 0.31, "percentile": 91.0, "n": 250.0,
        })
    # Player 2: below basket majority (only 2 of 10 attrs) -> INSUFFICIENT_DATA cell.
    for attr in ksp.BASKET[:2]:
        rows.append({
            "entity_id": 2, "entity_name": "Bravo", "window": "season_2025_26",
            "attribute": attr, "raw_value": 0.20, "percentile": 40.0, "n": 100.0,
        })
    # Player 3: no season_2025_26 rows at all -> every basket cell INSUFFICIENT_DATA.

    # Stability pair: player 1 drifts a lot (baseline 0.55 -> recent 0.75, big n),
    # player 2 stable (0.55 -> 0.56), player 3 has no recent-window row.
    rows += [
        {"entity_id": 1, "entity_name": "Alpha", "window": "season_2024_25",
         "attribute": "zone_efg_rim", "raw_value": 0.55, "percentile": 50.0, "n": 300.0},
        {"entity_id": 1, "entity_name": "Alpha", "window": "last20_2024_25",
         "attribute": "zone_efg_rim", "raw_value": 0.75, "percentile": 95.0, "n": 60.0},
        {"entity_id": 2, "entity_name": "Bravo", "window": "season_2024_25",
         "attribute": "zone_efg_rim", "raw_value": 0.55, "percentile": 50.0, "n": 300.0},
        {"entity_id": 2, "entity_name": "Bravo", "window": "last20_2024_25",
         "attribute": "zone_efg_rim", "raw_value": 0.56, "percentile": 52.0, "n": 60.0},
    ]
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "load_active_players", lambda *a, **k: _active_players_stub())
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    return tmp_path


def test_descriptive_claim_shape_uses_raw_value_not_percentile(_stub_deps):
    tmp_path = _stub_deps
    result = ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    assert result["cells_mined"] > 0
    claims = cl.query(sport="nba", base_dir=tmp_path, type="structural")
    assert len(claims) > 0
    row = claims[claims["evidence_json"].str.contains('"window": "season_2025_26"')].iloc[0]
    assert "0.31" in row["effect_json"]  # raw_value made it into the claim
    assert "91.0" not in row["effect_json"]  # percentile did NOT leak in as the value


def test_insufficient_data_path_for_missing_and_partial_players(_stub_deps):
    tmp_path = _stub_deps
    ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    matrix = kc.load_matrix(base_dir=tmp_path)
    pp = matrix[matrix["dimension"] == "play_profile"].set_index("player_id")
    assert pp.loc[1, "status"] in ("MINED", "ESCALATED")  # full basket + big stability drift
    assert pp.loc[3, "status"] == "INSUFFICIENT_DATA"     # no season_2025_26 rows at all


def test_basket_majority_floor_drives_mined_vs_insufficient(_stub_deps):
    tmp_path = _stub_deps
    ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    matrix = kc.load_matrix(base_dir=tmp_path)
    pp = matrix[matrix["dimension"] == "play_profile"].set_index("player_id")
    # Player 2 has only 2/10 basket attrs, below BASKET_MAJORITY -> descriptive
    # side is INSUFFICIENT_DATA even though stability side may be MINED/TESTED.
    assert ksp.BASKET_MAJORITY > 2


def test_stability_drift_detected_for_big_mover(_stub_deps):
    tmp_path = _stub_deps
    ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    claims = cl.query(sport="nba", base_dir=tmp_path, type="conditional")
    p1 = claims[claims["entity_ids_flat"] == "1"]
    assert len(p1) == 1
    assert "TESTED" in p1.iloc[0]["effect_json"]
    p3 = claims[claims["entity_ids_flat"] == "3"]
    assert "INSUFFICIENT_DATA" in p3.iloc[0]["effect_json"]


def test_idempotent_rerun_adds_zero_claims(_stub_deps):
    tmp_path = _stub_deps
    first = ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    assert first["claims_added"] > 0
    journal_path = tmp_path / "journal.jsonl"
    lines_after_first = journal_path.read_text(encoding="ascii").count("\n")

    second = ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    assert second["claims_added"] == 0
    lines_after_second = journal_path.read_text(encoding="ascii").count("\n")
    assert lines_after_second == lines_after_first


def test_coverage_matrix_writeback_for_play_profile_dimension(_stub_deps):
    tmp_path = _stub_deps
    ksp.run_sweep(base_dir=tmp_path, source=_synthetic_profiles())
    matrix = kc.load_matrix(base_dir=tmp_path)
    pp = matrix[matrix["dimension"] == "play_profile"]
    assert (pp["status"] != "UNMINED").all()
    assert (pp["n_claims"] == len(ksp.BASKET) + 1).all()
