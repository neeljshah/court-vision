"""Per-file tests for domains.mlb.weather_vs_close_gate.

Offline only: pure synthetic pandas DataFrames shaped like
build_close_weather_corpus() output (date, game_pk, event_id, close_total,
temp_f, wind_out, wind_in, total_runs). No parquet reads, no network, no
odds-jsonl parsing.

Run ONLY this file:
  python -m pytest domains/mlb/test_weather_vs_close_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.weather_vs_close_gate import BURN_IN, run_gate


# --------------------------------------------------------------------------- #
# synthetic close+weather corpus builders
# --------------------------------------------------------------------------- #
def _close_already_prices_weather_corpus(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """The close ALREADY embeds the weather effect: realized total = close +
    pure noise (weather has zero residual predictive power once the close is
    known). Expected verdict: REJECT (no residual gain -- the market priced it)."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    temp_f = rng.uniform(40, 95, n)
    wind_out = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_in = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_out = np.where(wind_in > 0, 0.0, wind_out)
    # close itself already tracks temp/wind (as if books priced it in)
    close_total = 8.0 + 0.03 * (temp_f - 70) + 0.05 * wind_out - 0.05 * wind_in
    noise = rng.normal(0, 1.5, n)
    total_runs = np.round(np.clip(close_total + noise, 0, None))
    return pd.DataFrame({
        "date": dates, "game_pk": np.arange(n),
        "event_id": [f"e{i}" for i in range(n)],
        "close_total": close_total,
        "temp_f": temp_f, "wind_speed": np.maximum(wind_out, wind_in),
        "wind_out": wind_out, "wind_in": wind_in, "total_runs": total_runs,
    })


def _close_ignores_weather_corpus(n: int = 500, seed: int = 11) -> pd.DataFrame:
    """The close is a FLAT market consensus that ignores a real planted weather
    effect -- realized total = flat_close + weather_effect + small noise.
    Expected verdict: SHIP_REVIEW (residual correction should recover the
    planted effect and beat the close in both halves)."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2025-01-01", periods=n, freq="D")
    temp_f = rng.uniform(40, 95, n)
    wind_out = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_in = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_out = np.where(wind_in > 0, 0.0, wind_out)
    close_total = np.full(n, 8.5)  # market ignores weather entirely
    weather_effect = 0.08 * (temp_f - 70) + 0.15 * wind_out - 0.15 * wind_in
    noise = rng.normal(0, 0.5, n)
    total_runs = np.round(np.clip(close_total + weather_effect + noise, 0, None))
    return pd.DataFrame({
        "date": dates, "game_pk": np.arange(n),
        "event_id": [f"e{i}" for i in range(n)],
        "close_total": close_total,
        "temp_f": temp_f, "wind_speed": np.maximum(wind_out, wind_in),
        "wind_out": wind_out, "wind_in": wind_in, "total_runs": total_runs,
    })


# --------------------------------------------------------------------------- #
# run_gate verdicts
# --------------------------------------------------------------------------- #
def test_close_already_prices_weather_rejects():
    res = run_gate(_close_already_prices_weather_corpus())
    assert res["verdict"] == "REJECT"


def test_close_ignoring_planted_weather_ships_review():
    res = run_gate(_close_ignores_weather_corpus())
    assert res["verdict"] == "SHIP_REVIEW"
    assert res["overall"]["rmse_delta"] < 0
    assert res["half1"]["rmse_delta"] < 0
    assert res["half2"]["rmse_delta"] < 0


def test_too_few_rows_is_inconclusive():
    small = _close_ignores_weather_corpus(n=BURN_IN + 50)
    res = run_gate(small)
    assert res["verdict"] == "INCONCLUSIVE"
    assert res["n_scorable"] < 200


def test_honest_note_present_and_framed_correctly():
    res = run_gate(_close_already_prices_weather_corpus())
    note = res["honest_note"].lower()
    assert "close is the benchmark" in note
    assert "extraordinary" in note
    assert "no $ edge" in note


def test_residual_coefs_reported():
    res = run_gate(_close_ignores_weather_corpus())
    coefs = res["residual_coefs"]
    assert coefs is not None
    for k in ("intercept", "temp_f_centered", "wind_out", "wind_in"):
        assert k in coefs


# --------------------------------------------------------------------------- #
# leak check: game i's prediction must not depend on game i's own outcome,
# nor on any game AFTER i.
# --------------------------------------------------------------------------- #
def test_no_leak_perturbing_own_outcome_does_not_change_earlier_half():
    df = _close_ignores_weather_corpus(n=300, seed=1)
    df_perturbed = df.copy()
    last_idx = df_perturbed.index[-1]
    df_perturbed.loc[last_idx, "total_runs"] = df_perturbed.loc[last_idx, "total_runs"] + 1000.0

    res_a = run_gate(df)
    res_b = run_gate(df_perturbed)

    # half1 is entirely determined by games strictly before it; perturbing the
    # LAST game's own outcome must not change half1's close/candidate RMSE at
    # all (byte-identical walk-forward predictions).
    assert res_a["half1"] == res_b["half1"]


def test_missing_weather_falls_back_to_close_no_crash():
    df = _close_ignores_weather_corpus(n=400)
    df = df.copy()
    df.loc[df.index[BURN_IN + 5:BURN_IN + 25], "temp_f"] = np.nan
    res = run_gate(df)
    assert res["verdict"] in ("SHIP_REVIEW", "REJECT", "INCONCLUSIVE")
    assert res["n"] == 400
