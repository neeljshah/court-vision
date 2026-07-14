"""Tests for scripts.platformkit.live_edge.combine.foul_minutes +
run_foul_minutes (LIVE-EDGE CYCLE 5 FOUL-MINUTES).

Per-file run only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_foul_minutes.py -q
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.combine import foul_minutes as fm
from scripts.platformkit.live_edge.combine import run_foul_minutes as rfm


def _synthetic_foul_state(n_games: int = 40) -> pd.DataFrame:
    """Tiny possession-grain synthetic mimicking foul_state_<season>.parquet:
    2 players, one who chronically fouls early (pf>=2 in period 1) and one
    who never does -- and a lineup-available half so the exposure feature
    has signal too."""
    rows = []
    for gi in range(n_games):
        game_id = f"G{gi:03d}"
        lineup_available = gi >= n_games // 2  # first half = pre-lineup era (2023-24-like)
        # possession where player 1 (chronic fouler) hits pf=2 in period 1
        rows.append({
            "game_id": game_id, "poss_idx": 0, "period": 1,
            "pf_map": json.dumps({"1": 2}) if gi % 2 == 0 else "{}",
            "off_lineup_ids": "1,2,3,4,5" if lineup_available else None,
            "def_lineup_ids": "6,7,8,9,10" if lineup_available else None,
            "off_lineup_foultrouble_ct": 1.0 if (lineup_available and gi % 3 == 0) else 0.0,
            "def_lineup_foultrouble_ct": 0.0,
            "lineup_available": lineup_available,
        })
        # a later possession, player 2 never in foul trouble
        rows.append({
            "game_id": game_id, "poss_idx": 1, "period": 2,
            "pf_map": json.dumps({"2": 1}),
            "off_lineup_ids": "1,2,3,4,5" if lineup_available else None,
            "def_lineup_ids": "6,7,8,9,10" if lineup_available else None,
            "off_lineup_foultrouble_ct": 0.0,
            "def_lineup_foultrouble_ct": 0.0,
            "lineup_available": lineup_available,
        })
    return pd.DataFrame(rows)


def _synthetic_sweep(n_games: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n_games, freq="3D")
    rows = []
    for gi, d in enumerate(dates):
        game_id = f"G{gi:03d}"
        for pid in (1, 2):
            pf = 4.0 if (pid == 1 and gi % 2 == 0) else 1.0
            rows.append({"player_id": pid, "player_name": f"P{pid}", "game_id": game_id,
                         "date": d, "is_home": int(gi % 2 == 0), "pf": pf,
                         "min": 20.0 + (0 if pid == 1 else 5), "pts": 10.0})
    return pd.DataFrame(rows)


def test_build_per_game_foul_features_flags_early_foul(tmp_path):
    fs = _synthetic_foul_state()
    fs_path = tmp_path
    (fs_path / "foul_state_2023_24.parquet")  # not written -- pass df directly via monkeypatch pattern instead
    # build_per_game_foul_features reads from disk; test the private helpers directly instead.
    long_pf = fm._explode_pf_map(fs)
    pairs = fm._early_foul_q1_pairs(long_pf)
    assert ("G000", 1) in pairs  # player 1 hit pf=2 in period 1 on even games
    assert ("G001", 1) not in pairs  # odd game: pf_map empty for that possession


def test_team_foultrouble_exposure_only_where_lineup_available():
    fs = _synthetic_foul_state()
    exp = fm._team_foultrouble_exposure(fs)
    assert not exp.empty
    # only lineup-available games (second half) produce rows
    assert set(exp["game_id"]).issubset({f"G{gi:03d}" for gi in range(20, 40)})


def test_add_foul_state_features_shifted_leak_free():
    fs = _synthetic_foul_state()
    long_pf = fm._explode_pf_map(fs)
    pairs = fm._early_foul_q1_pairs(long_pf)
    all_players = long_pf[["game_id", "player_id"]].drop_duplicates().reset_index(drop=True)
    all_players["early_foul_q1_flag"] = [(g, p) in pairs for g, p in
                                          zip(all_players["game_id"], all_players["player_id"])]
    exposure = fm._team_foultrouble_exposure(fs)
    per_game = all_players.merge(exposure, on=["game_id", "player_id"], how="outer")
    per_game["early_foul_q1_flag"] = per_game["early_foul_q1_flag"].fillna(False)

    sweep = _synthetic_sweep()
    from scripts.platformkit.live_edge.combine import minutes_combiner as mc
    sweep = mc._add_features(sweep)
    out = fm.add_foul_state_features(sweep, per_game)
    g = out[out["player_id"] == 1].sort_values("date").reset_index(drop=True)
    # row i's trailing rate must never depend on row i's own flag
    flags = g["early_foul_q1_flag"].fillna(False).astype(float)
    for i in range(3, len(g)):
        prior = flags.iloc[:i]
        expected = prior.tail(10).mean()
        got = g.loc[i, "early_foul_q1_rate_prior"]
        if not pd.isna(got):
            assert abs(got - expected) < 1e-9


def test_run_foul_minutes_blocked_on_empty_frame(tmp_path):
    out = rfm.run_foul_minutes(source=pd.DataFrame(), out_dir=tmp_path)
    assert out["blocked"] is True


def test_run_foul_minutes_blocked_when_foul_state_absent(tmp_path):
    sweep = _synthetic_sweep()
    out = rfm.run_foul_minutes(source=sweep, foul_seasons_dir=tmp_path, out_dir=tmp_path)
    assert out["blocked"] is True
    assert "foul_state" in out["reason"]


def test_run_foul_minutes_end_to_end_writes_report_and_verdict(tmp_path):
    # n_games=250 @ freq=3D crosses ksn's 2025-10-01 reserve cutover with
    # enough rows on both sides of the walk-forward split.
    n_games = 250
    fs = _synthetic_foul_state(n_games=n_games)
    (tmp_path / "foul_state_2023_24.parquet").parent.mkdir(parents=True, exist_ok=True)
    fs.to_parquet(tmp_path / "foul_state_2023_24.parquet")

    sweep = _synthetic_sweep(n_games=n_games)
    out_dir = tmp_path / "out"
    out = rfm.run_foul_minutes(source=sweep, foul_seasons_dir=tmp_path, out_dir=out_dir)
    assert out["verdict"] in ("FOUL_STATE_IMPROVES_C1_COMBINER", "HONEST_NULL")
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.md").exists()
    report = json.loads((out_dir / "report.json").read_text())
    assert report["seeds"] == [0, 42]
    assert set(report["candidates_tested"]) == {"early_foul_q1_rate_prior", "team_foultrouble_exposure_prior"}
