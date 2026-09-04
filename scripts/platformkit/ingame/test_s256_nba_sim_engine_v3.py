"""Archived-output verification for the sealed S266 construct measurement."""
import json
from pathlib import Path

import pandas as pd
import psutil

from scripts.platformkit.ingame import s256_nba_sim_engine_v3 as s266

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/harness/S266_nba_sim_third_arm_construct_2026-09-04"


def test_one_game_paired_loss_denominator_and_legacy_aliases() -> None:
    assert s266.select_sample is s266.select_games
    assert s266.price_snapshot_only is s266.price
    assert s266.evaluate is s266.score
    ticks = pd.read_csv(OUT / "S266_selected_tick_series.csv", dtype={"game": str})
    games = pd.read_csv(OUT / "S266_per_game_paired_loss_series.csv", dtype={"game": str})
    summary = json.loads((OUT / "S266_summary.json").read_text(encoding="ascii"))
    game = sorted(games["game"])[0]
    expected = ticks.loc[ticks["game"] == game, "paired_loss_recal_null_minus_simulator"].mean()
    actual = games.loc[games["game"] == game, "paired_loss_recal_null_minus_simulator"].iloc[0]
    assert ticks["game"].nunique() == games["game"].nunique() == 30
    assert len(ticks) == 180
    assert abs(expected - actual) < 1e-12
    assert summary["status"] == summary["verdict"] in ("SCREEN_NULL", "BEHIND")
    assert (OUT / "S256_summary_construct.json").read_bytes() == (OUT / "S266_summary.json").read_bytes()
    assert (OUT / "S256_selected_tick_series_construct.csv").read_bytes() == (OUT / "S266_selected_tick_series.csv").read_bytes()
    assert (OUT / "S256_per_game_paired_loss_series_construct.csv").read_bytes() == (OUT / "S266_per_game_paired_loss_series.csv").read_bytes()
    assert psutil.Process().memory_info().rss < 200 * 1048576
