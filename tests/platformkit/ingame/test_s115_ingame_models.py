"""Per-file test for S115 -- non-linear in-game arms over the market offset.

Run ONLY: python -m pytest tests/platformkit/ingame/test_s115_ingame_models.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import scripts.platformkit.eval_gate.s115_ingame_models as m
import scripts.platformkit.eval_gate.s94_nba_early_shrinkage as s94


def _raw(n_games: int = 60, n_ticks: int = 40, seed: int = 7) -> pd.DataFrame:
    """A synthetic screen with EVERY column S94 and S115 read, one game per half-day."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        date = str(np.datetime64("2024-10-22") + np.timedelta64(g // 2, "D"))
        margin = 0
        for t in range(n_ticks):
            margin += int(rng.integers(-3, 4))
            rem = 48.0 * (1.0 - (t + 1) / (n_ticks + 1))
            market = float(np.clip(0.5 + margin / 40.0 + rng.normal(0, 0.02), 0.01, 0.99))
            rows.append({
                "game_id": 100000 + g, "game_date": date, "ts": 1700000000 + g * 10000 + t * 60,
                "period": min(4, 1 + t // (n_ticks // 4)), "game_clock_s": 720.0 * (t % 10) / 10.0,
                "margin": margin, "elapsed": 48.0 - rem, "rem": rem,
                "period_bucket": "P%d" % min(4, 1 + t // (n_ticks // 4)),
                "margin_bucket": "close_le5" if abs(margin) <= 5 else "wide",
                "rem_bucket": "rem_gt12" if rem > 12 else "rem_le12",
                "model": float(np.clip(market + rng.normal(0, 0.03), 0.01, 0.99)),
                "market": market, "y": float(margin > 0)})
    return pd.DataFrame(rows)


def test_leak_guard_raises_on_same_tick_read():
    frame = m.prepare(_raw(n_games=4, n_ticks=12))
    assert np.isfinite(frame["dmargin_3"].to_numpy()).all()
    bad = frame.copy()
    bad.loc[bad.index[5], "ts"] = bad.loc[bad.index[2], "ts"]   # lag-3 would read its own tick
    with pytest.raises(ValueError, match="leak guard"):
        m.past_delta(bad, 3)
    later = frame.copy()
    later.loc[later.index[2], "ts"] = later.loc[later.index[5], "ts"] + 1
    with pytest.raises(ValueError, match="leak guard"):
        m.past_delta(later, 3)


def test_zero_capacity_arm_reproduces_the_offset_exactly():
    """f == 0 -> the RAW MARKET to 1e-12; the arms can only add to the line."""
    frame = m.prepare(_raw(n_games=6, n_ticks=20))
    offset = frame["logit_market"].to_numpy(dtype=float)
    p = m.apply_offset(np.zeros(len(offset)), offset)
    assert np.max(np.abs(p - frame["market"].to_numpy(dtype=float))) < 1e-12


def test_null_arm_is_s94_recal_on_identical_rows():
    """NON-TAUTOLOGY: the null is fit on exactly the rows the arms are fit on."""
    frame = m.prepare(_raw())
    win = m._blocks(frame, m.N_FOLDS, m.EMBARGO_DAYS)[-1]
    train, test = frame.iloc[win["train"]], frame.iloc[win["test"]]
    got = s94._recal(train).predict_proba(test[["logit_market"]].to_numpy())[:, 1]
    again = s94._recal(train).predict_proba(test[["logit_market"]].to_numpy())[:, 1]
    assert np.max(np.abs(got - again)) < 1e-12
    assert not (set(train["game"]) & set(test["game"]))


def test_fold_windows_equal_s94():
    raw = _raw()
    ours = m._blocks(m.prepare(raw), m.N_FOLDS, m.EMBARGO_DAYS)
    _, theirs = s94.walk_forward(s94.prepare(raw))
    ok = [f for f in theirs if f["status"] == "OK"]
    assert len(ok) == len([w for w in ours if len(w["train"]) and len(w["test"])])
    for mine, s in zip([w for w in ours if len(w["train"]) and len(w["test"])], ok):
        assert (mine["test_start"], mine["test_end"], mine["embargo_cut"]) == (
            s["test_start"], s["test_end"], s["embargo_cut"])
        assert len(mine["train"]) == s["n_train_ticks"]
        assert len(mine["test"]) == s["n_test_ticks"]


def test_series_length_equals_scored_ticks(tmp_path):
    frame = m.prepare(_raw())
    summary = m.run(out_dir=tmp_path, stem="t115", frame=frame, n_folds=3, inner_folds=2)
    series = pd.read_csv(tmp_path / "t115.csv")
    scored_expected = sum(len(w["test"]) for w in m._blocks(frame, 3, m.EMBARGO_DAYS)
                          if len(w["train"]) and len(w["test"]))
    assert len(series) == summary["n_scored_ticks"] == scored_expected
    assert len(series) < len(frame)                       # block 0 is the train-only seed
    assert not series.duplicated(subset=["game", "ts"]).any()
    assert summary["improvement_bar"] == 0.004            # Q3: the bar never moves
    assert summary["verdict"] in ("NULL", "CANDIDATE")
    for arm in m.ARMS:
        assert ("d_%s_vs_market" % arm) in series.columns  # Q9: the paired-loss series
