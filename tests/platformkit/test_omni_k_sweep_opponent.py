"""Tests for scripts.platformkit.omni.k_sweep_opponent (K opponent-dimension sweep).

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_k_sweep_opponent.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.omni import claims_ledger as cl
from scripts.platformkit.omni import k_coverage as kc
from scripts.platformkit.omni import k_sweep_opponent as kso


def _synthetic_tier_source() -> pd.DataFrame:
    """3 teams x 2 seasons; ELI is always the elite (lowest) def_rtg, WEK the
    weakest -- asof__def_rtg values are already shifted (as team_offdef_asof
    guarantees), so season S here is "valid for S", summarizing S-1."""
    rows = []
    for season in ("2023-24", "2024-25"):
        rows.append({"team_tricode": "ELI", "season": season, "asof__def_rtg": 100.0})
        rows.append({"team_tricode": "MID", "season": season, "asof__def_rtg": 110.0})
        rows.append({"team_tricode": "WEK", "season": season, "asof__def_rtg": 120.0})
    return pd.DataFrame(rows)


def _synthetic_frame() -> pd.DataFrame:
    """20 games per player, opponent rotating ELI/MID/WEK; Alpha scores less
    facing ELI (elite_def) than WEK (weak_def) -- clean effect to detect."""
    rows = []
    dates = pd.date_range("2023-11-01", periods=20, freq="3D")
    opponents = ["ELI", "MID", "WEK"]
    for pid, name, effect in ((1, "Alpha", -8.0), (2, "Bravo", 0.0), (3, "Charlie", -8.0)):
        for i, d in enumerate(dates):
            opp = opponents[i % 3]
            pts = 20.0 + (effect if opp == "ELI" else (0.0 if opp == "MID" else -effect))
            rows.append({
                "player_id": pid, "player_name": name, "game_id": f"g{pid}_{i}",
                "date": d, "season": "2023-24", "team": "HOM", "opp": opp,
                "is_home": float(i % 2), "pts": pts, "min": 30.0,
            })
    return pd.DataFrame(rows)


def _active_players_stub(tmp_path):
    return pd.DataFrame({"player_id": [1, 2, 3], "player_name": ["Alpha", "Bravo", "Charlie"]})


@pytest.fixture(autouse=True)
def _stub_deps(monkeypatch, tmp_path):
    monkeypatch.setattr(kc, "load_active_players", lambda *a, **k: _active_players_stub(tmp_path))
    monkeypatch.setattr(kso, "_archetype_map", lambda: {1: "Scoring Guard", 2: "Scoring Guard", 3: "Stretch Big"})
    kc.init_matrix(base_dir=tmp_path, players=_active_players_stub(tmp_path))
    return tmp_path


def test_join_rate_full_on_clean_synthetic_slice(_stub_deps):
    df = kso._load_sweep_frame(_synthetic_frame(), _synthetic_tier_source())
    assert df["opp_tier"].notna().mean() == pytest.approx(1.0)
    assert set(df["opp_tier"].unique()) == {"elite_def", "mid_def", "weak_def"}


def test_join_uses_prior_season_asof_value_not_current(_stub_deps):
    """The merged opp_tier/def_rtg for a (opp, season) row must come from the
    team_offdef_asof frame's own row for that exact (team, season) -- no
    additional shift or leak introduced by this module's join."""
    tier_source = _synthetic_tier_source()
    df = kso._load_sweep_frame(_synthetic_frame(), tier_source)
    row = df[(df["opp"] == "ELI") & (df["season"] == "2023-24")].iloc[0]
    expected = tier_source[(tier_source["team_tricode"] == "ELI") & (tier_source["season"] == "2023-24")]
    assert row["asof__def_rtg"] == pytest.approx(expected["asof__def_rtg"].iloc[0])
    assert row["opp_tier"] == "elite_def"


def test_insufficient_data_path_when_below_floor(_stub_deps):
    tmp_path = _stub_deps
    result = kso.run_sweep(
        base_dir=tmp_path, source=_synthetic_frame(), tier_source=_synthetic_tier_source(),
        top_n=200, discovery_only=False,
    )
    assert result["cells_mined"] > 0
    claims = cl.query(sport="nba", base_dir=tmp_path)
    insufficient = claims[claims["effect_json"].str.contains("INSUFFICIENT_DATA")]
    assert len(insufficient) > 0
    assert result["insufficient_data_share"] > 0


def test_idempotent_rerun_adds_near_zero_claims(_stub_deps):
    tmp_path = _stub_deps
    kwargs = dict(base_dir=tmp_path, source=_synthetic_frame(), tier_source=_synthetic_tier_source(),
                  top_n=200, discovery_only=False)
    first = kso.run_sweep(**kwargs)
    assert first["claims_added"] > 0
    journal_path = tmp_path / "journal.jsonl"
    lines_after_first = journal_path.read_text(encoding="ascii").count("\n")

    second = kso.run_sweep(**kwargs)
    assert second["claims_added"] == 0
    lines_after_second = journal_path.read_text(encoding="ascii").count("\n")
    assert lines_after_second == lines_after_first


def test_coverage_matrix_updated_for_opponent_dimension(_stub_deps):
    tmp_path = _stub_deps
    kso.run_sweep(base_dir=tmp_path, source=_synthetic_frame(), tier_source=_synthetic_tier_source(),
                  top_n=200, discovery_only=False)
    matrix = kc.load_matrix(base_dir=tmp_path)
    opponent = matrix[matrix["dimension"] == "opponent"]
    assert (opponent["status"] != "UNMINED").any()


def test_discovery_only_excludes_2025_26_reserve_rows(_stub_deps):
    tmp_path = _stub_deps
    df = kso._load_sweep_frame(_synthetic_frame(), _synthetic_tier_source())
    discovery, reserve = kso.split_discovery_reserve(df)
    assert len(reserve) == 0  # frame is entirely 2023-24 (discovery) by construction
    assert len(discovery) == len(df)
