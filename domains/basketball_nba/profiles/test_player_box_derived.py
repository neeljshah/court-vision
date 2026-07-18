"""Per-file test: box-derived rate attributes (oreb/dreb rate+share,
stocks_per36, ast_to_tov) -- synthetic boxscore parquet, no data/ dependency.

Run: python -m pytest domains/basketball_nba/profiles/test_player_box_derived.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

import domains.basketball_nba.profiles.player_box_derived as bd
import domains.basketball_nba.profiles.profile_compute as profile_compute


def _setup_box(tmp_path, monkeypatch, rows):
    box = pd.DataFrame(rows)
    box_path = tmp_path / "player_boxscores.parquet"
    box.to_parquet(box_path, index=False)
    monkeypatch.setattr(bd, "_BOX", box_path)
    monkeypatch.setattr(profile_compute, "REPO_ROOT", tmp_path)


def test_oreb_rate_and_share(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, [
        {"player_id": 1, "player_name": "Boards A Lot", "season": "2024-25",
         "oreb": 108.0, "dreb": 252.0, "reb": 360.0, "min": 720.0},
        {"player_id": 2, "player_name": "Bench Guy", "season": "2024-25",
         "oreb": 5.0, "dreb": 5.0, "reb": 10.0, "min": 50.0},  # below 200min floor
    ])
    rows = bd.build_oreb_rate("2024_25")
    by_attr = {(r["attribute"], r["entity_id"]): r for r in rows}
    assert len(rows) == 2  # only player 1 clears the floor, 2 attrs (per36 + share)
    assert by_attr[("oreb_per36", 1)]["raw_value"] == pytest.approx(108.0 / 720.0 * 36.0)
    assert by_attr[("oreb_share", 1)]["raw_value"] == pytest.approx(108.0 / 360.0)


def test_dreb_rate_and_share(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, [
        {"player_id": 1, "player_name": "Boards A Lot", "season": "2024-25",
         "oreb": 108.0, "dreb": 252.0, "reb": 360.0, "min": 720.0},
    ])
    rows = bd.build_dreb_rate("2024_25")
    by_attr = {r["attribute"]: r for r in rows}
    assert by_attr["dreb_per36"]["raw_value"] == pytest.approx(252.0 / 720.0 * 36.0)
    assert by_attr["dreb_share"]["raw_value"] == pytest.approx(252.0 / 360.0)


def test_stocks_per36(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, [
        {"player_id": 1, "player_name": "Steal Man", "season": "2024-25",
         "stl": 72.0, "blk": 36.0, "min": 720.0},
    ])
    rows = bd.build_stocks_per36("2024_25")
    assert rows[0]["raw_value"] == pytest.approx((72.0 + 36.0) / 720.0 * 36.0)


def test_ast_to_tov(tmp_path, monkeypatch):
    _setup_box(tmp_path, monkeypatch, [
        {"player_id": 1, "player_name": "Point God", "season": "2024-25",
         "ast": 400.0, "tov": 100.0, "min": 720.0},
        {"player_id": 2, "player_name": "Zero TOV Edge Case", "season": "2024-25",
         "ast": 10.0, "tov": 0.0, "min": 720.0},  # tov==0 excluded (div-by-zero guard)
    ])
    rows = bd.build_ast_to_tov("2024_25")
    assert len(rows) == 1
    assert rows[0]["entity_id"] == 1
    assert rows[0]["raw_value"] == pytest.approx(4.0)


def test_skips_non_box_season():
    assert bd.build_oreb_rate("2023_24") == []
    assert bd.build_all_player_box_derived_rows(["2023_24"]) == []
