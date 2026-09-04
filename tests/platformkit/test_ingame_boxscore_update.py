"""Focused S245 checks: closed-form CRPS, partition labels, and archive replay."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit import ingame_boxscore_update as s245


def test_closed_form_partition_and_archived_game_replay():
    value = s245.gaussian_crps(np.array([0.0]), np.array([1.0]), np.array([0.0]))[0]
    assert value == pytest.approx((np.sqrt(2.0) - 1.0) / np.sqrt(np.pi))
    summary = s245.summarize(pd.DataFrame({"checkpoint": ["end_q1", "end_q1"],
                                            "partition": ["non-garbage", "garbage-time"], "game_id": ["a", "b"],
                                            "model_crps": [1.0, 2.0], "naive_crps": [1.5, 1.5]}))
    assert {row["partition"] for row in summary} == {"non-garbage", "garbage-time"}
    archive = Path(s245.OUT) / "S245_attempt2_paired_losses_2026-09-04.csv.gz"
    series = pd.read_csv(archive, compression="gzip")
    game_id = str(series["game_id"].iloc[0])
    replay = s245.recompute_game_crps(series, game_id)
    game = series.loc[series["game_id"].astype(str) == game_id]
    assert replay["model"] == pytest.approx(game["model_crps"].mean())
    assert replay["naive"] == pytest.approx(game["naive_crps"].mean())
