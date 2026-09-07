"""Focused checks for the sealed S283 empirical NBA time-score blend."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.ingame import s283_bayes_timescore_blend as S


def _state(game: str, y: int, margin: str = "close_le5", rem: float = 0.5, market: float = 0.8) -> dict:
    feature = {"period_bucket": "P1", "margin_bucket": margin, "rem_bucket": "rem_gt12",
               "rem_fraction": rem, "market_prob": market, "cluster_id": game}
    return {"game_id": game, "outcome": y, "features": feature}


def test_sparse_cell_uses_named_parent_and_blend_formula():
    train = [_state("dense-%03d" % i, i % 2) for i in range(200)] + [_state("sparse", 1, "mid_06_12")]
    full, parent = S._fit_table(train)
    dense_probability, dense_source = S.table_probability(train[0]["features"], full, parent)
    sparse_probability, sparse_source = S.table_probability(train[-1]["features"], full, parent)
    assert dense_source == "full_cell" and dense_probability == pytest.approx(0.5)
    assert sparse_source == "period_bucket_parent" and sparse_probability == pytest.approx(101.0 / 201.0)
    blended, source = S.blend_probability(train[-1]["features"], full, parent, 1.0)
    assert source == "period_bucket_parent"
    assert blended == pytest.approx(0.5 * (101.0 / 201.0) + 0.5 * 0.8)


def test_seal_and_one_archived_game_brier_reproduce_from_paired_csv():
    S.verify_preregistration()
    paired = pd.read_csv(S.EVIDENCE / (S.STEM + "_paired_loss.csv.gz"))
    summary = json.loads((S.EVIDENCE / (S.STEM + "_summary.json")).read_text(encoding="ascii"))
    game = sorted(paired["cluster_id"].astype(str).unique())[0]
    rows = paired[paired["cluster_id"].astype(str) == game]
    y = rows["y"].to_numpy(float)
    assert rows["loss_recal_null"].mean() == pytest.approx(((rows["recal_null"] - y) ** 2).mean(), abs=1e-12)
    assert rows["loss_blended"].mean() == pytest.approx(((rows["blended"] - y) ** 2).mean(), abs=1e-12)
    assert len(paired) == summary["n_ticks"] and paired["game_id"].is_unique
