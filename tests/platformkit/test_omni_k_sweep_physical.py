"""Tests for scripts.platformkit.omni.k_sweep_physical (K physical sweep).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_physical.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba import memory_atlas_archetypes as archetypes
from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_physical as ksph


def _active_players_stub():
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})


def _synthetic_positions() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": [1, 2, 3],
        "position": ["Guard", "Center", "Forward"],
        "height_inches": [74.0, 84.0, None],   # player 3: missing height -> INSUFFICIENT_DATA
        "weight_lbs": [190.0, 250.0, 220.0],
        "birth_date": pd.to_datetime(["1995-01-01", "1990-06-15", "1998-03-01"]),
        "draft_year": [2017, 2012, 2020],
    })


def _synthetic_adv_stats() -> pd.DataFrame:
    rows = []
    months = ["2024-10-15", "2024-11-15", "2024-12-15", "2025-01-15", "2025-02-15"]
    # Player 1: clear declining minutes trend, >=30 games, 5 months -> TESTED, escalates.
    mins = [36.0, 33.0, 30.0, 27.0, 24.0]
    for month, m in zip(months, mins):
        for _ in range(8):
            rows.append({"player_id": 1, "game_date": month, "minutes": m})
    # Player 2: noisy, near-zero slope -> TESTED, not escalated.
    for month, m in zip(months, [30.0, 29.5, 30.5, 30.0, 29.5]):
        for _ in range(8):
            rows.append({"player_id": 2, "game_date": month, "minutes": m})
    # Player 3: >=30 season games but only 2 months -> below MIN_MONTHS -> INSUFFICIENT_DATA.
    for month in months[:2]:
        for _ in range(16):
            rows.append({"player_id": 3, "game_date": month, "minutes": 20.0})
    return pd.DataFrame(rows)


def _stub_archetypes(monkeypatch):
    stats = pd.DataFrame({
        "player_id": [1, 2, 3],
        "usage": [0.10, 0.10, 0.10], "ts": [0.50, 0.50, 0.50], "efg": [0.50, 0.50, 0.50],
        "ast_pct": [0.05, 0.05, 0.05], "def_rtg": [115.0, 115.0, 115.0], "reb_pct": [0.05, 0.05, 0.05],
        "minutes_avg": [30.0, 30.0, 30.0], "position": ["Guard", "Center", "Forward"],
    })
    monkeypatch.setattr(archetypes, "_build_stats", lambda *a, **k: stats)
    monkeypatch.setattr(archetypes, "_classify", lambda row: "Bench Contributor")


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "load_active_players", lambda *a, **k: _active_players_stub())
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub())
    _stub_archetypes(monkeypatch)
    return tmp_path


def test_snapshot_claims_use_descriptive_verdict_and_deviation(_stub_deps):
    tmp_path = _stub_deps
    result = ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    assert result["cells_mined"] > 0
    claims = cl.query(sport="nba", base_dir=tmp_path, type="structural")
    age_row = claims[claims["topic"] == "physical.age_curve_position"]
    assert len(age_row) == 3
    p1 = age_row[age_row["entity_ids_flat"] == "1"].iloc[0]
    assert "DESCRIPTIVE" in p1["effect_json"]
    assert "archetype_median" in p1["evidence_json"]


def test_size_missing_height_is_insufficient_data(_stub_deps):
    tmp_path = _stub_deps
    ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    claims = cl.query(sport="nba", base_dir=tmp_path, type="structural")
    height_row = claims[(claims["topic"] == "physical.size_vs_role_height_inches") & (claims["entity_ids_flat"] == "3")]
    assert len(height_row) == 1
    assert "INSUFFICIENT_DATA" in height_row.iloc[0]["effect_json"]


def test_conditioning_trend_slope_math_and_escalation(_stub_deps):
    tmp_path = _stub_deps
    ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    claims = cl.query(sport="nba", base_dir=tmp_path, type="conditional")
    p1 = claims[claims["entity_ids_flat"] == "1"].iloc[0]
    assert "TESTED" in p1["effect_json"]
    assert "-3.0" in p1["effect_json"]  # exact declining slope: -3.0 min/month
    p1_links = p1["links_json"]
    assert '"escalate_to_funnel": true' in p1_links
    p2 = claims[claims["entity_ids_flat"] == "2"].iloc[0]
    assert '"escalate_to_funnel": false' in p2["links_json"]


def test_conditioning_insufficient_months_path(_stub_deps):
    tmp_path = _stub_deps
    ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    claims = cl.query(sport="nba", base_dir=tmp_path, type="conditional")
    p3 = claims[claims["entity_ids_flat"] == "3"].iloc[0]
    assert "INSUFFICIENT_DATA" in p3["effect_json"]


def test_idempotent_rerun_adds_zero_claims(_stub_deps):
    tmp_path = _stub_deps
    first = ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    assert first["claims_added"] > 0
    journal_path = tmp_path / "journal.jsonl"
    lines_after_first = journal_path.read_text(encoding="ascii").count("\n")

    second = ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    assert second["claims_added"] == 0
    lines_after_second = journal_path.read_text(encoding="ascii").count("\n")
    assert lines_after_second == lines_after_first


def test_coverage_matrix_writeback_for_physical_dimension(_stub_deps):
    tmp_path = _stub_deps
    ksph.run_sweep(base_dir=tmp_path, positions_source=_synthetic_positions(), adv_source=_synthetic_adv_stats())
    matrix = kc.load_matrix(base_dir=tmp_path)
    phys = matrix[matrix["dimension"] == "physical"]
    assert (phys["status"] != "UNMINED").all()
    p1_status = phys[phys["player_id"] == 1].iloc[0]["status"]
    assert p1_status == "ESCALATED"
