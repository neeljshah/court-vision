"""Synthetic-fixture tests for tail_calib.mlb_replicate -- no real data, no
network. Covers: MLB corpus load/split reshape, the per-team gate table
structure, and end-to-end run_replication + class_level_test on a synthetic
fat-tailed MLB-shaped corpus (mirrors test_promote_gate.py's pattern).
"""
import numpy as np
import pandas as pd

from scripts.platformkit.live_edge.tail_calib import mlb_replicate as mr


def _synthetic_espn_boxscores(n_games=400, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-04-01", periods=n_games, freq="D")
    # fat-tailed runs (occasional blowout innings) so tail-aware should beat Normal
    home_runs = rng.poisson(4.0, n_games).astype(float)
    blowout = rng.random(n_games) < 0.05
    home_runs[blowout] += rng.integers(8, 15, size=int(blowout.sum()))
    away_runs = rng.poisson(4.0, n_games).astype(float)
    return pd.DataFrame({
        "event_id": np.arange(n_games), "date": dates,
        "home_abbr": np.where(np.arange(n_games) % 2 == 0, "AAA", "BBB"),
        "away_abbr": np.where(np.arange(n_games) % 2 == 0, "BBB", "AAA"),
        "home_bat_runs": home_runs, "away_bat_runs": away_runs,
    })


def test_load_mlb_corpus_splits_by_year():
    box = _synthetic_espn_boxscores(60)
    # push half the rows into 2026 to exercise the year split
    box.loc[30:, "date"] = pd.date_range("2026-01-01", periods=30, freq="D")
    disc, reserve = mr.load_mlb_corpus(box)
    assert len(disc) + len(reserve) == 2 * len(box)  # reshaped: 2 team-rows per game
    assert pd.to_datetime(disc["date"]).dt.year.max() < 2026
    assert pd.to_datetime(reserve["date"]).dt.year.min() >= 2026


def test_run_replication_returns_expected_columns():
    box = _synthetic_espn_boxscores(500)
    box.loc[250:, "date"] = pd.date_range("2026-01-01", periods=250, freq="D")
    disc, reserve = mr.load_mlb_corpus(box)
    table = mr.run_replication(disc, reserve)
    assert len(table) > 0
    for col in ("team", "n_pooled", "mean_pooled", "p_pooled", "bh_q", "survivor"):
        assert col in table.columns
    assert set(table["team"]) <= {"AAA", "BBB"}


def test_run_replication_empty_when_no_teams_qualify():
    box = _synthetic_espn_boxscores(4)  # far below MIN_N in both disc and reserve
    disc, reserve = mr.load_mlb_corpus(box)
    table = mr.run_replication(disc, reserve)
    assert len(table) == 0


def test_class_level_test_runs_on_replication_output():
    box = _synthetic_espn_boxscores(500)
    box.loc[250:, "date"] = pd.date_range("2026-01-01", periods=250, freq="D")
    disc, reserve = mr.load_mlb_corpus(box)
    table = mr.run_replication(disc, reserve)
    from scripts.platformkit.live_edge.tail_calib import promote_gate as pg
    result = pg.class_level_test(table)
    assert result["n_entities"] == len(table)
    assert np.isfinite(result["mean"])


def test_write_report_handles_empty_table(tmp_path):
    empty = pd.DataFrame()
    class_result = {"n_entities": 0, "mean": float("nan"), "p_value": float("nan"),
                     "ci_lo": float("nan"), "ci_hi": float("nan")}
    path = mr._write_report(empty, class_result, base_dir=tmp_path)
    assert path.exists()
    text = path.read_text(encoding="ascii")
    assert "insufficient entities" in text
