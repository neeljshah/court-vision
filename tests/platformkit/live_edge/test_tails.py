"""Per-file test: tails.py metrics + tail_sweep.py end-to-end on synthetic
data (no real data touched). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_tails.py -q
"""
import pathlib
import shutil
import tempfile

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge import tail_sweep as ts


def _synthetic_nba_box(n_players: int = 6, n_games: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for pid in range(n_players):
        base = 8 + pid * 4
        for gi in range(n_games):
            pts = max(0, rng.normal(base, base * 0.4))
            rows.append({
                "game_id": f"G{gi}", "date": pd.Timestamp("2024-11-01") + pd.Timedelta(days=gi),
                "season": "2024-25", "team": f"T{pid % 3}", "opp": f"T{(pid + 1) % 3}",
                "player_id": f"P{pid}", "player_name": f"Player{pid}",
                "pts": float(pts), "min": float(rng.normal(28, 6)),
            })
    return pd.DataFrame(rows)


def _synthetic_mlb_box(n_teams: int = 6, n_games: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for gi in range(n_games):
        h, a = gi % n_teams, (gi + 1) % n_teams
        rows.append({
            "event_id": gi, "date": pd.Timestamp("2025-04-01") + pd.Timedelta(days=gi),
            "home_abbr": f"M{h}", "away_abbr": f"M{a}",
            "home_bat_runs": float(max(0, rng.normal(4.5, 2.5))),
            "away_bat_runs": float(max(0, rng.normal(4.5, 2.5))),
        })
    return pd.DataFrame(rows)


def test_compute_tail_metrics_flags_insufficient_and_computes_quantiles():
    df = pd.DataFrame({"player_id": ["A"] * 3 + ["B"] * 20,
                         "pts": [10, 12, 8] + list(np.random.default_rng(0).normal(20, 5, 20))})
    out = tl.compute_tail_metrics(df, "player_id", "pts")
    assert out["A"]["insufficient"] is True
    assert out["B"]["insufficient"] is False
    assert 0.0 <= out["B"]["breakout_prob"] <= 1.0
    assert set(out["B"]["quantiles"].keys()) == {str(q) for q in tl.QUANTILES}


def test_split_nba_discovery_reserve():
    df = pd.DataFrame({"season": ["2023-24", "2024-25", "2025-26"]})
    disc, res = tl.split_nba_discovery_reserve(df)
    assert list(disc["season"]) == ["2023-24", "2024-25"]
    assert list(res["season"]) == ["2025-26"]


def test_load_mlb_team_runs_reshapes_to_one_row_per_team_game():
    box = _synthetic_mlb_box(n_teams=4, n_games=10)
    reshaped = tl.load_mlb_team_runs(box)
    assert len(reshaped) == 2 * len(box)
    assert set(reshaped.columns) >= {"team", "opp", "runs", "date"}


def test_tail_sweep_end_to_end():
    nba_box = _synthetic_nba_box(n_players=6, n_games=40)
    mlb_box = _synthetic_mlb_box(n_teams=6, n_games=40)
    tmp = pathlib.Path(tempfile.mkdtemp())
    try:
        base_dir = tmp / "claims"
        result = ts.run_sweep(base_dir=base_dir, nba_box_source=nba_box, mlb_source=mlb_box)
        assert result["nba_players_screened"] == 6
        assert result["mlb_teams_screened"] == 6
        assert result["claims_added"] >= result["nba_players_screened"] + result["mlb_teams_screened"]
        report = base_dir / "data" / "omni" / "live_edge" / "tails" / "TAIL_REPORT.md"
        assert report.is_file()
        text = report.read_text(encoding="ascii")
        assert "Tail-bin calibration" in text
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
