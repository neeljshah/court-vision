"""S177 reproduction from the archived S88 calibration probabilities.

Run: python -m pytest tests/platformkit/eval_gate/test_s88_requote.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s88_requote as R
from scripts.platformkit.foundry import ingame_screen as S


def _by_key(artifact):
    return {(row["basis"], row["bucket"]): row for row in artifact["readout"]}


def test_archived_requote_publishes_both_cluster_bases(tmp_path):
    """n = 11,087 informative archived ticks; all values are re-computed, not fixtures."""
    artifact = R.write_artifact(tmp_path / "s88_requote.json")
    rows = _by_key(artifact)
    assert len(rows) == 6 and artifact["n_eval_ticks"] == 33920
    assert artifact["n_informative_ticks"] == 11087
    assert rows[("ticker", "pooled")]["n_clusters"] == 127
    assert rows[("ticker", "pooled")]["delta_vs_incumbent_mean"] == pytest.approx(-0.002889992, abs=1e-9)
    assert rows[("ticker", "mid|trailing")]["verdict_vs_incumbent"] == "WORSE"
    assert rows[("real_game", "pooled")]["n_clusters"] == 234
    assert rows[("real_game", "late|leading_big")]["n_clusters"] == 52
    assert rows[("real_game", "mid|trailing")]["n_clusters"] == 76
    assert rows[("real_game", "mid|trailing")]["verdict_vs_incumbent"] == "NO_CHANGE"
    assert rows[("real_game", "mid|trailing")]["delta_vs_incumbent_ci95"] == pytest.approx([
        -0.017149273, 0.004151254], abs=1e-9)
    assert len(artifact["real_game_cluster_series"]) == 234
    assert len(artifact["paired_loss_series"]) == 11087


def test_score_feature_default_cluster_and_opt_in_cluster_are_distinct(monkeypatch):
    """n = 4 (CONSTRUCT): the default ticker field and opt-in real-game field differ."""
    rows = pd.DataFrame({"game": ["A", "A", "B", "B"],
                         "real_game_cluster": ["A#1", "A#2", "B#1", "B#2"],
                         "y": [1.0, 1.0, 0.0, 0.0], "p_e4": [0.5] * 4,
                         "market": [0.5] * 4, "x": [0.0] * 4})
    candidate = pd.Series([0.6] * 4)
    null = pd.Series([0.5] * 4)
    monkeypatch.setattr(S, "_dm", lambda delta, clusters: (0.0, 1.0, [0.0, 0.0]))
    default = S.score_feature(rows, candidate, null, "x")
    corrected = S.score_feature(rows, candidate, null, "x", cluster_column="real_game_cluster")
    assert default["n_games"] == 2 and corrected["n_games"] == 4
    assert default["brier_candidate"] == corrected["brier_candidate"]
