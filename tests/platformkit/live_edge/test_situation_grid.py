"""Per-file test: situation_grid tagging + one grid_sweep mined cell, on a
small synthetic slice (no real data touched). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_situation_grid.py -q
"""
import pathlib
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.live_edge import situation_grid as sg
from scripts.platformkit.live_edge import grid_sweep as gs


def _synthetic_possessions(n_games: int = 4, rows_per_game: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for gi in range(n_games):
        game_id = f"002230000{gi}"
        margin = 0.0
        for _ in range(rows_per_game):
            period = int(rng.integers(1, 5))
            clock = float(rng.integers(0, 720))
            pts = int(rng.choice([0, 1, 2, 3], p=[0.45, 0.05, 0.35, 0.15]))
            off_home = bool(rng.integers(0, 2))
            margin += pts if off_home else -pts
            rows.append({
                "period": period, "clock_start": clock, "off_is_home": off_home,
                "points": pts, "duration": float(rng.integers(5, 20)),
                "off_margin": margin if off_home else -margin,
                "home_margin": margin, "home_score_start": 0, "away_score_start": 0,
                "game_id": game_id, "season": "2024-25",
            })
    return pd.DataFrame(rows)


def _synthetic_box(possessions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for i, game_id in enumerate(possessions["game_id"].unique()):
        rows.append({"game_id": game_id, "date": pd.Timestamp("2024-11-01") + pd.Timedelta(days=i),
                      "team": f"HOME{i}", "is_home": 1.0})
        rows.append({"game_id": game_id, "date": pd.Timestamp("2024-11-01") + pd.Timedelta(days=i),
                      "team": f"AWAY{i}", "is_home": 0.0})
    return pd.DataFrame(rows)


def test_bucket_margin_covers_all_bands():
    margins = pd.Series([-30, -15, -3, 0, 3, 15, 30])
    out = sg.bucket_margin(margins)
    assert list(out) == ["down20plus", "down10to19", "down1to9", "tied", "up1to9", "up10to19", "up20plus"]


def test_period_clock_band_labels():
    period = pd.Series([1, 4, 5])
    clock = pd.Series([600.0, 100.0, 50.0])
    out = sg.bucket_period_clock(period, clock)
    assert list(out) == ["Q1_early", "Q4_late", "OT"]


def test_close_late_and_blowout_flags():
    margin = pd.Series([3.0, 30.0])
    period = pd.Series([4, 4])
    clock = pd.Series([200.0, 200.0])
    assert list(sg.close_late_flag(margin, period, clock)) == [True, False]
    assert list(sg.blowout_flag(margin, period)) == [False, True]


def test_tag_situations_and_enumerate_cells():
    poss = _synthetic_possessions()
    box = _synthetic_box(poss)
    tagged = sg.tag_situations(poss, box, with_lineups=False)
    for col in sg.GROUP_COLS + ["off_team", "def_team", "foul_state"]:
        assert col in tagged.columns
    assert (tagged["foul_state"] == "DATA_ABSENT").all()
    cells = sg.enumerate_cells(tagged)
    assert len(cells) > 0
    assert cells["n"].sum() == len(tagged)


def test_grid_sweep_mines_at_least_one_cell_end_to_end():
    poss = _synthetic_possessions(n_games=8, rows_per_game=150)
    box = _synthetic_box(poss)
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        base_dir = tmp / "claims"
        result = gs.run_sweep(
            base_dir=base_dir,
            possessions_source=poss, box_source=box, discovery_only=False,
        )
        assert result["cells_screened"] > 0
        assert result["cells_mined"] + result["insufficient_data"] == result["cells_screened"]
        assert result["claims_added"] >= result["cells_screened"]  # + 2 structural claims
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
