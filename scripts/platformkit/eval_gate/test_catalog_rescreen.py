"""Per-file test for the uncharged catalog re-screen (S64)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.eval_gate import catalog_rescreen as cr  # noqa: E402


def _frame(n: int = 900, planted: bool = True, seed: int = 7) -> pd.DataFrame:
    """One corpus_unit whose label is driven by a feature the incumbent cannot see."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)          # the incumbent's own information
    z = rng.normal(size=n)          # the planted, incumbent-invisible driver
    lin = 0.8 * x + (2.5 * z if planted else 0.0)
    y = (rng.uniform(size=n) < 1.0 / (1.0 + np.exp(-lin))).astype(float)
    return pd.DataFrame({
        "event_id": [f"e{i}" for i in range(n)],
        "corpus_unit": "unit_a",
        cr.DATE_COL: pd.date_range("2020-01-01", periods=n, freq="D"),
        "y": y,
        "p_inc": 1.0 / (1.0 + np.exp(-0.8 * x)),
        "feature": z,
    })


def test_planted_feature_screens_positive_with_an_archived_differential(tmp_path):
    summary, diff = cr.screen_feature(_frame())
    assert summary["verdict"] == "SCREEN_POSITIVE", summary
    assert summary["brier_delta"] > 0 and summary["dm_p"] < cr.ALPHA
    assert len(diff) == summary["n"] == 450          # folds cover the back half only
    assert summary["n_eff"] == diff["event_id"].nunique()
    # Q9: the archived differential is per-unit, paired, and re-scorable alone.
    cr.DIFF_DIR = tmp_path
    rel = cr._archive("nba", "planted:Signal", diff)
    stored = pd.read_parquet(tmp_path / "nba" / "planted_Signal.parquet")
    assert len(stored) == len(diff)
    assert set(stored.columns) >= {"event_id", "corpus_unit", cr.DATE_COL,
                                   "p_incumbent", "p_model", "loss_incumbent",
                                   "loss_model", "d"}
    assert np.allclose(stored["d"], stored["loss_incumbent"] - stored["loss_model"])
    assert rel.endswith("planted_Signal.parquet")


def test_no_plant_does_not_screen_positive():
    summary, _ = cr.screen_feature(_frame(planted=False))
    assert summary["verdict"] in ("SCREEN_NULL", "SCREEN_NEGATIVE"), summary


def test_missing_column_is_not_testable_and_names_the_absent_column():
    row = cr._record("nba", "player.scoring.catch_shoot_ppp", "registry", "p_base",
                     None, ["player.scoring.catch_shoot_ppp", "catch_shoot_ppp"])
    assert row["verdict"] == "NOT_TESTABLE"
    assert row["differential_path"] is None
    assert row["n"] == 0 and row["n_eff"] == 0
    assert "catch_shoot_ppp" in row["absent_columns"]


def test_too_few_rows_is_not_testable():
    summary, diff = cr.screen_feature(_frame(n=40))
    assert summary["verdict"] == "NOT_TESTABLE" and diff.empty


@pytest.mark.parametrize("delta,p,expected", [
    (0.01, 0.01, "SCREEN_POSITIVE"), (-0.01, 0.01, "SCREEN_NEGATIVE"),
    (0.01, 0.90, "SCREEN_NULL"), (float("nan"), 0.01, "SCREEN_NULL")])
def test_verdict_of(delta, p, expected):
    assert cr.verdict_of(delta, p) == expected
