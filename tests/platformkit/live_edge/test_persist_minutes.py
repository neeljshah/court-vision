"""Per-file test for scripts.platformkit.live_edge.combine.persist_minutes.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_persist_minutes.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.live_edge.combine import minutes_combiner as mc
from scripts.platformkit.live_edge.combine import persist_minutes as pm


def _synthetic_frame(n_players: int = 30, n_games: int = 260, seed: int = 0) -> pd.DataFrame:
    """Same generator as test_minutes_combiner.py (deliberately duplicated,
    not imported -- a tiny fixture, and importing test modules across files
    is more coupling than it's worth)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n_games, freq="3D")
    rows = []
    for pid in range(n_players):
        base_min = 15 + (pid % 20)
        for i, d in enumerate(dates):
            pf = rng.integers(0, 6)
            m = max(0.0, base_min + rng.normal(0, 3) - (2.0 if pf >= 4 else 0.0))
            rows.append({"player_id": pid, "player_name": f"P{pid}", "game_id": f"{pid}_{i}",
                         "date": d, "is_home": int(i % 2 == 0), "pf": float(pf), "min": m,
                         "pts": m * 0.5})
    return pd.DataFrame(rows)


def test_blocked_on_empty_frame(tmp_path):
    out = pm.fit_and_persist(source=pd.DataFrame(), out_dir=tmp_path)
    assert out["blocked"] is True
    assert not (tmp_path / pm._PKL_NAME).exists()


def test_fit_and_persist_writes_pkl_and_meta(tmp_path):
    df = _synthetic_frame()
    meta = pm.fit_and_persist(source=df, out_dir=tmp_path)
    pkl_path = tmp_path / pm._PKL_NAME
    meta_path = tmp_path / pm._META_NAME
    assert pkl_path.is_file() and pkl_path.stat().st_size > 0
    assert meta_path.is_file()
    assert meta["model_name"] == "hist_gb"
    assert meta["feature_cols"] == ["baseline_min", "foul_rate_prior"]
    assert meta["reserve_pinball_at_fit"] > 0


def test_load_estimator_roundtrip_and_predicts(tmp_path):
    df = _synthetic_frame()
    pm.fit_and_persist(source=df, out_dir=tmp_path)
    model, meta = pm.load_estimator(out_dir=tmp_path)
    assert model is not None and meta is not None
    pred = model.predict([[20.0, 0.1]])
    assert len(pred) == 1 and np.isfinite(pred[0])


def test_load_estimator_missing_returns_none(tmp_path):
    model, meta = pm.load_estimator(out_dir=tmp_path)
    assert model is None and meta is None


def test_persisted_estimator_reproduces_c1_reported_oos_pinball():
    """FIDELITY CHECK (real disk data): refit via persist_minutes, then
    reload the persisted model and recompute its OOS pinball on the SAME
    reserve split minutes_combiner.py uses -- must land at the report's
    best_combiner_pinball_median (~3.06), not a re-derived number. Skips if
    the real box snapshot isn't available in this environment (mirrors
    test_minutes_combiner.test_real_slice_smoke's skip discipline)."""
    try:
        meta = pm.fit_and_persist()
    except FileNotFoundError:
        pytest.skip("real box snapshot not available in this environment")
    if meta.get("blocked"):
        pytest.skip(f"real run blocked: {meta.get('reason')}")

    model, loaded_meta = pm.load_estimator()
    assert model is not None

    from scripts.platformkit.omni import k_sweep_nba as ksn
    df = mc._add_features(ksn._load_sweep_frame(None))  # noqa: SLF001
    _, reserve = ksn.split_discovery_reserve(df)
    reserve = reserve.dropna(subset=loaded_meta["feature_cols"])
    X_test = reserve[loaded_meta["feature_cols"]].to_numpy()
    y_test = reserve["min"].to_numpy()
    pinball = mc._pinball_median(y_test, model.predict(X_test))  # noqa: SLF001

    assert pinball == pytest.approx(meta["reserve_pinball_at_fit"], abs=1e-6)
    assert pinball == pytest.approx(3.06, abs=0.05)
