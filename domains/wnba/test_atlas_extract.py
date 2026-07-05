"""Per-file tests for domains.wnba.atlas_extract (lane wnba-atlas).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/wnba/test_atlas_extract.py -q

Acceptance criteria:
  1. Each builder derives the correct headline 'value' from its source
     columns (playmaking=assists, defense_activity=steals+blocks,
     usage_volume=fga, ft_profile=ft_pct, team_defense_allowed=paint pts).
  2. Missing source columns / empty source frame -> empty output (never a
     fabricated row), matching the "never raises" invariant.
  3. run_extract_atlas() writes real parquet files with the expected row
     counts and skips writing for any all-empty dimension.
  4. The REAL on-disk atlas_wnba_player_box_profile / _shooting_profile /
     _team_pace_shooting parquets (already materialized by
     domains/basketball_wnba) actually parse and produce non-empty output
     -- proves this module reads the true corpus shape, not just a fixture.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import domains.wnba.atlas_extract as ae


def _fixture_box() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["1", "2"],
        "player_name": ["A", "B"],
        "n_games_played": [22, 11],
        "assists_per_game": [6.5, 2.0],
        "steals_per_game": [1.2, 0.5],
        "blocks_per_game": [0.3, 0.1],
        "confidence": ["high", "medium"],
    })


def _fixture_shooting() -> pd.DataFrame:
    return pd.DataFrame({
        "player_id": ["1", "2"],
        "player_name": ["A", "B"],
        "n_games_played": [22, 11],
        "fga_per_game": [12.0, 6.5],
        "fta_per_game": [4.0, 1.5],
        "ft_pct_season": [0.85, 0.70],
        "confidence": ["high", "medium"],
    })


def _fixture_team_pace() -> pd.DataFrame:
    return pd.DataFrame({
        "team_id": ["100", "101"],
        "team_tricode": ["NYL", "IND"],
        "n_games": [24, 22],
        "opp_fg3_pct_allowed": [0.32, 0.35],
        "opp_paint_pts_allowed_per_game": [39.5, 43.8],
        "confidence": ["high", "high"],
    })


# ---------------------------------------------------------------------------
# build_player_playmaking
# ---------------------------------------------------------------------------

def test_playmaking_value_is_assists_per_game():
    out = ae.build_player_playmaking(_fixture_box())
    row = out[out["player_id"] == "1"].iloc[0]
    assert row["value"] == 6.5
    assert row["n"] == 22


def test_playmaking_missing_column_returns_empty():
    box = _fixture_box().drop(columns=["assists_per_game"])
    assert ae.build_player_playmaking(box).empty


def test_playmaking_empty_input_returns_empty():
    assert ae.build_player_playmaking(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_player_defense_activity
# ---------------------------------------------------------------------------

def test_defense_activity_stocks_is_steals_plus_blocks():
    out = ae.build_player_defense_activity(_fixture_box())
    row = out[out["player_id"] == "1"].iloc[0]
    assert row["stocks_per_game"] == 1.5  # 1.2 + 0.3
    assert row["value"] == 1.5


def test_defense_activity_missing_column_returns_empty():
    box = _fixture_box().drop(columns=["blocks_per_game"])
    assert ae.build_player_defense_activity(box).empty


# ---------------------------------------------------------------------------
# build_player_usage_volume
# ---------------------------------------------------------------------------

def test_usage_volume_value_is_fga_per_game():
    out = ae.build_player_usage_volume(_fixture_shooting())
    row = out[out["player_id"] == "1"].iloc[0]
    assert row["value"] == 12.0


def test_usage_volume_empty_input_returns_empty():
    assert ae.build_player_usage_volume(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# build_player_ft_profile
# ---------------------------------------------------------------------------

def test_ft_profile_value_is_ft_pct_season():
    out = ae.build_player_ft_profile(_fixture_shooting())
    row = out[out["player_id"] == "1"].iloc[0]
    assert row["value"] == 0.85
    assert row["fta_per_game"] == 4.0


def test_ft_profile_missing_column_returns_empty():
    shooting = _fixture_shooting().drop(columns=["ft_pct_season"])
    assert ae.build_player_ft_profile(shooting).empty


# ---------------------------------------------------------------------------
# build_team_defense_allowed
# ---------------------------------------------------------------------------

def test_team_defense_allowed_value_is_paint_pts_allowed():
    out = ae.build_team_defense_allowed(_fixture_team_pace())
    row = out[out["team_id"] == "100"].iloc[0]
    assert row["value"] == 39.5
    assert row["opp_fg3_pct_allowed"] == 0.32


def test_team_defense_allowed_missing_column_returns_empty():
    tp = _fixture_team_pace().drop(columns=["n_games"])
    assert ae.build_team_defense_allowed(tp).empty


# ---------------------------------------------------------------------------
# run_extract_atlas -- disk round-trip
# ---------------------------------------------------------------------------

def test_run_extract_atlas_writes_parquets(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "_BOX_PROFILE_SRC", tmp_path / "box.parquet")
    monkeypatch.setattr(ae, "_SHOOTING_PROFILE_SRC", tmp_path / "shooting.parquet")
    monkeypatch.setattr(ae, "_TEAM_PACE_SRC", tmp_path / "team_pace.parquet")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(ae, "_CACHE_DIR", out_dir)
    monkeypatch.setattr(ae, "_out_path", lambda name: out_dir / f"atlas_wnba_{name}.parquet")

    _fixture_box().to_parquet(tmp_path / "box.parquet", index=False)
    _fixture_shooting().to_parquet(tmp_path / "shooting.parquet", index=False)
    _fixture_team_pace().to_parquet(tmp_path / "team_pace.parquet", index=False)

    summary = ae.run_extract_atlas()
    assert summary["player_playmaking"] == 2
    assert summary["team_defense_allowed"] == 2
    assert (out_dir / "atlas_wnba_player_playmaking.parquet").exists()
    assert (out_dir / "atlas_wnba_team_defense_allowed.parquet").exists()


def test_run_extract_atlas_missing_sources_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "_BOX_PROFILE_SRC", tmp_path / "absent_box.parquet")
    monkeypatch.setattr(ae, "_SHOOTING_PROFILE_SRC", tmp_path / "absent_shooting.parquet")
    monkeypatch.setattr(ae, "_TEAM_PACE_SRC", tmp_path / "absent_team_pace.parquet")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(ae, "_out_path", lambda name: out_dir / f"atlas_wnba_{name}.parquet")

    summary = ae.run_extract_atlas()
    assert all(v == 0 for v in summary.values())
    assert not out_dir.exists()


# ---------------------------------------------------------------------------
# Real on-disk corpus -- proves this reads the TRUE materialized shape
# ---------------------------------------------------------------------------

def test_real_box_profile_produces_nonempty_playmaking_and_defense():
    box = ae._read_source(ae._BOX_PROFILE_SRC)
    assert not box.empty, "atlas_wnba_player_box_profile.parquet must exist on disk for this lane"
    playmaking = ae.build_player_playmaking(box)
    defense = ae.build_player_defense_activity(box)
    assert len(playmaking) == len(box)
    assert len(defense) == len(box)
    assert (defense["stocks_per_game"] >= 0).all()


def test_real_shooting_profile_produces_nonempty_usage_and_ft():
    shooting = ae._read_source(ae._SHOOTING_PROFILE_SRC)
    assert not shooting.empty
    usage = ae.build_player_usage_volume(shooting)
    ft = ae.build_player_ft_profile(shooting)
    assert len(usage) == len(shooting)
    assert len(ft) == len(shooting)


def test_real_team_pace_produces_nonempty_defense_allowed():
    team_pace = ae._read_source(ae._TEAM_PACE_SRC)
    assert not team_pace.empty
    defense_allowed = ae.build_team_defense_allowed(team_pace)
    assert len(defense_allowed) == len(team_pace)
