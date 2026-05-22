"""
test_run_walk_forward.py -- Tests for the walk-forward report (PRED-02 / PRED-07).

Acceptance criterion: run_walk_forward produces a per-model train-vs-holdout
R²/MAE report with the gap, written to walk_forward_report.json; the --gate
flag fails CI when a model's overfit gap is too large.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

from run_walk_forward import (  # noqa: E402
    OVERFIT_GAP_THRESHOLD,
    PROP_STATS,
    build_model_report,
    holdout_from_residuals,
    main,
    run_walk_forward_for_model,
)


def _residuals(stat: str, n: int, bias: float = 0.0) -> list:
    """n recorded (predicted, actual) pairs for one stat, predicted = actual+bias."""
    return [{"stat": stat, "predicted": 20.0 + i * 0.1 + bias,
             "actual": 20.0 + i * 0.1, "game_date": f"2026-01-{(i % 27) + 1:02d}"}
            for i in range(n)]


def _write(tmp_path, name, data) -> str:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ── holdout_from_residuals ────────────────────────────────────────────────────

def test_holdout_from_residuals_computes_r2():
    """Holdout R²/MAE are recomputed from recorded predictions."""
    result = holdout_from_residuals(_residuals("pts", 50), "pts")
    assert result["n"] == 50
    assert result["holdout_r2"] is not None
    assert result["holdout_mae"] is not None


def test_holdout_insufficient_rows_returns_none():
    """Too few residual rows -> holdout R² is None, not a noisy estimate."""
    result = holdout_from_residuals(_residuals("reb", 5), "reb")
    assert result["holdout_r2"] is None
    assert result["n"] == 5


# ── build_model_report ────────────────────────────────────────────────────────

def test_report_covers_all_seven_props_plus_win_prob(tmp_path):
    """The report includes all 7 prop models and win probability."""
    residuals = []
    for stat in PROP_STATS:
        residuals += _residuals(stat, 40)
    registry = {f"props_{s}": {"train_r2": 0.50, "train_mae": 3.0} for s in PROP_STATS}

    report = build_model_report(
        residuals_path=_write(tmp_path, "res.json", residuals),
        registry_path=_write(tmp_path, "reg.json", registry),
        win_prob_path=_write(tmp_path, "wp.json", {"accuracy": 0.685, "brier": 0.21, "n_games": 3685}),
        output_path=str(tmp_path / "walk_forward_report.json"),
    )
    model_names = {m["model"] for m in report["models"]}
    assert {f"props_{s}" for s in PROP_STATS}.issubset(model_names)
    assert "win_probability" in model_names
    assert (tmp_path / "walk_forward_report.json").exists()


def test_report_computes_train_holdout_gap(tmp_path):
    """Each prop model carries a train−holdout R² gap."""
    registry = {"props_pts": {"train_r2": 0.80, "train_mae": 2.0}}
    report = build_model_report(
        residuals_path=_write(tmp_path, "res.json", _residuals("pts", 60)),
        registry_path=_write(tmp_path, "reg.json", registry),
        win_prob_path=_write(tmp_path, "wp.json", {}),
        output_path=str(tmp_path / "r.json"),
    )
    pts = next(m for m in report["models"] if m["model"] == "props_pts")
    assert pts["train_r2"] == 0.80
    assert pts["holdout_r2"] is not None
    assert pts["gap"] == round(0.80 - pts["holdout_r2"], 4)


def test_overfit_model_flagged(tmp_path):
    """A model with a large train−holdout gap is listed as overfit."""
    # Residuals with heavy bias -> low holdout R²; registry train_r2 high -> big gap.
    registry = {"props_pts": {"train_r2": 0.95, "train_mae": 1.0}}
    report = build_model_report(
        residuals_path=_write(tmp_path, "res.json", _residuals("pts", 60, bias=8.0)),
        registry_path=_write(tmp_path, "reg.json", registry),
        win_prob_path=_write(tmp_path, "wp.json", {}),
        output_path=str(tmp_path / "r.json"),
    )
    assert "props_pts" in report["overfit_models"]


# ── walk-forward CV path ──────────────────────────────────────────────────────

def test_run_walk_forward_for_model_reports_gap():
    """The walk-forward path returns train + holdout metrics and a gap."""
    import numpy as np
    from sklearn.linear_model import LinearRegression

    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 3))
    y = X @ np.array([1.5, -2.0, 0.7]) + rng.normal(scale=0.3, size=200)
    dates = list(range(200))

    result = run_walk_forward_for_model(LinearRegression, X, y, dates, n_folds=4)
    assert "train_r2" in result and "holdout_r2" in result
    assert result["gap"] == round(result["train_r2"] - result["holdout_r2"], 4)
    # A well-specified linear model should generalise — small gap.
    assert result["holdout_r2"] > 0.8


# ── --gate CLI (PRED-07) ──────────────────────────────────────────────────────

def test_gate_exit_code(tmp_path, monkeypatch):
    """--gate exits 1 when an overfit model is present, 0 otherwise."""
    import run_walk_forward as rwf

    # Clean report -> gate passes.
    clean = {"props_pts": {"train_r2": 0.45, "train_mae": 3.0}}
    monkeypatch.setattr(rwf, "_RESIDUALS", _write(tmp_path, "res.json", _residuals("pts", 60)))
    monkeypatch.setattr(rwf, "_REGISTRY", _write(tmp_path, "reg.json", clean))
    monkeypatch.setattr(rwf, "_WIN_PROB", _write(tmp_path, "wp.json", {}))
    monkeypatch.setattr(rwf, "_REPORT_PATH", str(tmp_path / "r.json"))
    assert main(["--gate"]) == 0

    # Overfit registry -> gate fails.
    overfit = {"props_pts": {"train_r2": 0.99, "train_mae": 0.5}}
    monkeypatch.setattr(rwf, "_REGISTRY", _write(tmp_path, "reg2.json", overfit))
    monkeypatch.setattr(rwf, "_RESIDUALS", _write(tmp_path, "res2.json", _residuals("pts", 60, bias=9.0)))
    assert main(["--gate"]) == 1


def test_overfit_threshold_is_sane():
    """The overfit threshold is a sensible fraction, not 0 or 1."""
    assert 0.0 < OVERFIT_GAP_THRESHOLD < 0.5


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
