"""Per-file test for domains.mlb.prereg.mlb_savant_2024. Run ONLY this file:

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/prereg/test_mlb_savant_2024.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.mlb.prereg import mlb_savant_2024 as m2024


def test_build_baseout_contacttype_filters_and_labels():
    df = pd.DataFrame({
        "type": ["X", "X", "B", "X"],  # 3rd row (not in-play) must be dropped
        "bb_type": ["ground_ball", "fly_ball", None, "ground_ball"],
        "on_2b": [123, None, None, None],
        "on_3b": [None, None, None, 456],
        "outs_when_up": [2, 1, 0, 2],
    })
    out = m2024.build_baseout_contacttype(df)
    assert len(out) == 3  # the type=='B' row dropped
    assert out["is_groundball"].tolist() == [1, 0, 1]
    assert out["is_risp"].tolist() == [1, 0, 1]
    assert out["two_outs"].tolist() == [1, 0, 1]


def test_build_launchangle_park_merges_park_factor(monkeypatch):
    df = pd.DataFrame({
        "game_pk": [1, 1, 2],
        "launch_angle": [15.0, 40.0, 20.0],
        "events": ["double", "field_out", "home_run"],
    })

    def _fake_local_park_factor(_df):
        return pd.DataFrame({"game_pk": [1, 2], "park_factor": [1.2, 0.8]})

    monkeypatch.setattr(m2024, "_local_park_factor", _fake_local_park_factor)
    out = m2024.build_launchangle_park(df)
    assert len(out) == 3
    assert out["is_xbh"].tolist() == [1, 0, 1]
    assert out["is_sweet_spot"].tolist() == [1, 0, 1]  # 40deg is outside 8-32
    assert out["is_hitter_park"].tolist() == [1, 1, 0]  # game 1 -> 1.2>1.0, game 2 -> 0.8


def _synthetic_2024_corpus(seed=7) -> pd.DataFrame:
    """Enough rows/columns to exercise run_replication + run_newly_unblocked end to
    end without hitting the real network corpus. PA rows are built game-by-game so
    each (game_pk, pitcher, batter) tuple repeats 4x -- add_tto's cumcount needs real
    repeats or tto3 is constant and the interaction fit is singular. Count-level (h5)
    rows are appended separately (no TTO structure needed there)."""
    rng = np.random.default_rng(seed)
    # 150 games / 5 home teams = 30 home appearances/team -> clears asof_park's
    # 10-prior-game warmup with room to spare (needed for a non-degenerate
    # is_hitter_park split in build_launchangle_park's test).
    n_games = 150
    pa_rows = []
    for g in range(1, n_games + 1):
        pitcher = (g % 8) + 1
        batter = (g % 15) + 1
        pitcher_base_velo = 90 + pitcher  # gives real per-pitcher avg_velo variation
        home_team, away_team = f"T{g % 5}", f"T{(g + 1) % 5}"
        game_date = pd.Timestamp("2024-04-01") + pd.Timedelta(days=g)
        for k in range(4):  # 4 PAs -> tto 1..4 for this (game,pitcher,batter) tuple
            stand = rng.choice(["L", "R"])
            p_throws = rng.choice(["L", "R"])
            pitch_type = rng.choice(["FF", "SL", "CU", "SI"])
            velo = pitcher_base_velo + rng.normal(0, 1.5)
            events = rng.choice(["single", "double", "field_out", "strikeout"])
            pa_rows.append({
                "game_pk": g, "game_date": str(game_date.date()),
                "pitcher": pitcher, "batter": batter, "at_bat_number": k + 1,
                "stand": stand, "p_throws": p_throws, "pitch_type": pitch_type,
                "events": events, "type": "X", "strikes": rng.integers(0, 3),
                "balls": rng.integers(0, 4), "release_speed": velo,
                "outs_when_up": rng.integers(0, 3),
                "on_1b": rng.choice([None, 1]), "on_2b": rng.choice([None, 1]),
                "on_3b": rng.choice([None, 1]),
                "bb_type": rng.choice(["ground_ball", "fly_ball", "line_drive"]),
                "launch_angle": rng.normal(15, 20),
                "home_team": home_team, "away_team": away_team,
                "post_home_score": rng.integers(0, 8), "post_away_score": rng.integers(0, 8),
            })
    pa = pd.DataFrame(pa_rows)

    n_pitch = 3000
    pitch = pd.DataFrame({
        "game_pk": rng.integers(1, n_games + 1, n_pitch),
        "game_date": "2024-05-01",
        "pitcher": rng.integers(1, 9, n_pitch), "batter": rng.integers(1, 16, n_pitch),
        "at_bat_number": rng.integers(1, 40, n_pitch),
        "stand": rng.choice(["L", "R"], n_pitch), "p_throws": rng.choice(["L", "R"], n_pitch),
        "pitch_type": rng.choice(["FF", "SL", "CU", "SI"], n_pitch),
        "events": None, "type": rng.choice(["S", "B"], n_pitch),
        "strikes": rng.integers(0, 3, n_pitch), "balls": rng.integers(0, 4, n_pitch),
        "release_speed": rng.normal(92, 3, n_pitch),
        "outs_when_up": rng.integers(0, 3, n_pitch),
        "on_1b": None, "on_2b": None, "on_3b": None, "bb_type": None,
        "launch_angle": None,
        "home_team": "T0", "away_team": "T1",
        "post_home_score": 0, "post_away_score": 0,
    })
    return pd.concat([pa, pitch], ignore_index=True)


def test_run_replication_end_to_end_shapes():
    df = _synthetic_2024_corpus()
    rows = m2024.run_replication(df)
    assert len(rows) == 3
    for r in rows:
        assert r["method"] == "replication_savant_2024"
        assert r["verdict"] in ("REPLICATED", "FAILED_REPLICATION")


def test_run_newly_unblocked_end_to_end_shapes():
    df = _synthetic_2024_corpus()
    rows = m2024.run_newly_unblocked(df)
    assert len(rows) == 5  # 2 tested + 3 still-blocked recheck rows
    tested = [r for r in rows if r["verdict"] != "BLOCKED"]
    blocked = [r for r in rows if r["verdict"] == "BLOCKED"]
    assert len(tested) == 2
    assert len(blocked) == 3
    for r in tested:
        assert r["method"] == "unblocked_savant_2024"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
