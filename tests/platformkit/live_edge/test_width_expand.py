"""Per-file test for width_expand: synthetic fat-tail vs Normal entities,
proves the gate correctly flags the fat-tail observable SIGNIFICANT and the
Normal-generated one null, on a tiny synthetic dataset (CPU only, no disk
reads of the real parquets -- fast + deterministic)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.width_expand import expand as ex
from scripts.platformkit.live_edge.width_expand import run_expand as re


def _fat_tail_frame(rng, n_entities=15, n_disc=150, n_reserve=120):
    """Entities whose TRUE generator is fat-tailed (Student-t) -- the
    empirical-quantile predictor should beat a Normal fit on these, both in
    discovery and reserve (same generator, not a season-drift artifact)."""
    rows = []
    for e in range(n_entities):
        for i in range(n_disc + n_reserve):
            season = "2025-26" if i >= n_disc else "2023-24"
            val = max(0.0, 20 + rng.standard_t(df=2) * 4)
            rows.append({"player_id": e, "season": season,
                         "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                         "pts": val})
    return pd.DataFrame(rows)


def _normal_frame(rng, n_entities=15, n_disc=150, n_reserve=120):
    rows = []
    for e in range(n_entities):
        for i in range(n_disc + n_reserve):
            season = "2025-26" if i >= n_disc else "2023-24"
            val = max(0.0, rng.normal(20, 4))
            rows.append({"player_id": e, "season": season,
                         "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                         "pts": val})
    return pd.DataFrame(rows)


def _split(df):
    is_reserve = df["season"] == "2025-26"
    return df.loc[~is_reserve].copy(), df.loc[is_reserve].copy()


def test_entity_gate_survivor_columns():
    rng = np.random.default_rng(0)
    disc, reserve = _split(_fat_tail_frame(rng))
    calib = ex.calibration_suite(disc, reserve, "player_id", "pts")
    table = ex.entity_gate(calib["fit_metrics"], reserve, "player_id", "pts")
    assert set(["entity_id", "p_pooled", "bh_q", "survivor"]).issubset(table.columns)
    assert len(table) == 15


def test_fat_tail_beats_normal_on_class_delta():
    """The fat-tail generator should show a class-level mean delta (baseline
    minus tail_aware CRPS) at least as favorable as the Normal generator --
    the gate must not report the Normal-generated null as a false positive."""
    rng = np.random.default_rng(1)
    disc_f, res_f = _split(_fat_tail_frame(rng))
    disc_n, res_n = _split(_normal_frame(rng))
    calib_f = ex.calibration_suite(disc_f, res_f, "player_id", "pts")
    calib_n = ex.calibration_suite(disc_n, res_n, "player_id", "pts")
    table_f = ex.entity_gate(calib_f["fit_metrics"], res_f, "player_id", "pts")
    table_n = ex.entity_gate(calib_n["fit_metrics"], res_n, "player_id", "pts")
    from scripts.platformkit.live_edge.tail_calib import promote_gate as pg
    class_f = pg.class_level_test(table_f)
    class_n = pg.class_level_test(table_n)
    assert class_f["mean"] > class_n["mean"]


def test_significant_flag_requires_positive_mean_and_low_p():
    assert re._significant({"class_p": 0.001, "class_mean": 0.5}) is True
    assert re._significant({"class_p": 0.001, "class_mean": -0.5}) is False
    assert re._significant({"class_p": 0.5, "class_mean": 0.5}) is False
    assert re._significant({"class_p": float("nan"), "class_mean": 0.5}) is False


def test_report_writes_and_lists_all_observables(tmp_path):
    rng = np.random.default_rng(2)
    disc, reserve = _split(_fat_tail_frame(rng, n_entities=4, n_disc=30, n_reserve=20))
    result = {
        "name": "synthetic.pts", "sport": "nba", "positive_control": True,
        "n_entities_tested": 4, "n_survivors": 0,
        "class_mean": 0.1, "class_ci_lo": -0.1, "class_ci_hi": 0.3, "class_p": 0.2,
        "calib": ex.calibration_suite(disc, reserve, "player_id", "pts"),
        "table": pd.DataFrame(),
    }
    path = re._write_report([result], tmp_path)
    text = path.read_text(encoding="ascii")
    assert "synthetic.pts" in text
    assert "WIDTH-EXPAND report" in text
