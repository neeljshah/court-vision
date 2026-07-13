"""Unit tests for build_form_trajectory_asof.py -- leak trap, first-game NaN,
rolling-window correctness, determinism, and a real-data row-count smoke test.

CLI: python -m pytest scripts/signals/test_build_form_trajectory_asof.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.signals.build_form_trajectory_asof import (  # noqa: E402
    FEATURE_COLS,
    build,
    build_player_season_asof,
    load_one,
)


def _write_gamelog(tmp_dir: Path, pid: int, season: str, games: list[dict]) -> Path:
    """games: list of dicts w/ game_id, game_date ('Mon DD, YYYY'), pts, min, fga, fta."""
    path = tmp_dir / f"gamelog_full_{pid}_{season}.json"
    path.write_text(json.dumps(games), encoding="utf-8")
    return path


def _synthetic_games(n: int, pts_seq: list[float] | None = None) -> list[dict]:
    """n games on consecutive days, deterministic game_ids, given (or ramp) pts."""
    pts_seq = pts_seq if pts_seq is not None else [10.0 + 5 * i for i in range(n)]
    out = []
    for i in range(n):
        out.append({
            "game_id": f"002200{1000 + i}", "game_date": f"Jan {i + 1:02d}, 2023",
            "pts": pts_seq[i], "min": 30.0, "fga": 10, "fta": 2,
        })
    return out


def test_first_game_nan(tmp_path: Path):
    games = _synthetic_games(6)
    _write_gamelog(tmp_path, 1, "2022-23", games)
    df = load_one(str(tmp_path / "gamelog_full_1_2022-23.json"), 1, "2022-23")
    out = build_player_season_asof(df)
    first = out.iloc[0]
    assert first["n_prior_games"] == 0
    for col in [c for c in FEATURE_COLS if c != "n_prior_games"]:
        assert pd.isna(first[col]), f"{col} should be NaN on first game, got {first[col]}"


def test_rolling_window_correctness(tmp_path: Path):
    # 6 games, pts = 10,20,30,40,50,60. At game index 5 (6th game), l5_pts uses the
    # 5 strictly-prior games (10,20,30,40,50) -> mean 30.0.
    games = _synthetic_games(6, pts_seq=[10, 20, 30, 40, 50, 60])
    _write_gamelog(tmp_path, 2, "2022-23", games)
    df = load_one(str(tmp_path / "gamelog_full_2_2022-23.json"), 2, "2022-23")
    out = build_player_season_asof(df)
    last = out.iloc[5]
    assert last["n_prior_games"] == 5
    assert abs(last["l5_pts"] - 30.0) < 1e-9
    # l10_pts window (10) has only 5 prior obs available -> same mean
    assert abs(last["l10_pts"] - 30.0) < 1e-9
    # baseline_pts = expanding mean of all 5 prior games = same as l5 here
    assert abs(last["baseline_pts"] - 30.0) < 1e-9
    # at game index 2 (3rd game), l5_pts uses 2 prior games (10,20) -> mean 15.0
    third = out.iloc[2]
    assert abs(third["l5_pts"] - 15.0) < 1e-9


def test_leak_trap(tmp_path: Path):
    games = _synthetic_games(8)
    _write_gamelog(tmp_path, 3, "2022-23", games)
    path = tmp_path / "gamelog_full_3_2022-23.json"
    df_before = load_one(str(path), 3, "2022-23")
    out_before = build_player_season_asof(df_before)

    # tamper game index 4's OWN pts line
    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered[4]["pts"] = 999.0
    path.write_text(json.dumps(tampered), encoding="utf-8")
    df_after = load_one(str(path), 3, "2022-23")
    out_after = build_player_season_asof(df_after)

    row_before = out_before.iloc[4][FEATURE_COLS]
    row_after = out_after.iloc[4][FEATURE_COLS]
    pd.testing.assert_series_equal(row_before, row_after, check_names=False)

    # but a LATER game (index 5) must now differ (it saw game 4's tampered pts)
    later_before = out_before.iloc[5]["l5_pts"]
    later_after = out_after.iloc[5]["l5_pts"]
    assert later_before != later_after


def test_deterministic_rerun(tmp_path: Path):
    games_a = _synthetic_games(5)
    games_b = _synthetic_games(4, pts_seq=[8, 16, 24, 32])
    _write_gamelog(tmp_path, 10, "2022-23", games_a)
    _write_gamelog(tmp_path, 11, "2023-24", games_b)

    out1 = build(gamelog_dir=str(tmp_path))
    out2 = build(gamelog_dir=str(tmp_path))
    pd.testing.assert_frame_equal(out1, out2)


def test_real_run_row_count():
    out = build()
    assert len(out) > 0, "real gamelog_full corpus produced zero as-of rows"
    assert out.duplicated(subset=["player_id", "season", "game_id"]).sum() == 0
    print(f"\n  real-run rows={len(out)}  seasons={sorted(out.season.unique())}")
