"""Per-file tests for domains.mlb.weather_totals_gate.

Offline only: pure synthetic pandas DataFrames, no parquet reads, no network.

Run ONLY this file:
  python -m pytest domains/mlb/test_weather_totals_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.weather_totals_gate import BURN_IN, parse_wind, run_gate


# --------------------------------------------------------------------------- #
# parse_wind vocabulary
# --------------------------------------------------------------------------- #
def test_parse_wind_out_directions():
    for suffix in ("CF", "LF", "RF"):
        speed, cls = parse_wind("8 mph, Out To %s" % suffix)
        assert speed == 8.0 and cls == "out"


def test_parse_wind_in_directions():
    for suffix in ("CF", "LF", "RF"):
        speed, cls = parse_wind("4 mph, In From %s" % suffix)
        assert speed == 4.0 and cls == "in"


def test_parse_wind_cross():
    assert parse_wind("7 mph, L To R") == (7.0, "cross")
    assert parse_wind("7 mph, R To L") == (7.0, "cross")


def test_parse_wind_calm_variants():
    assert parse_wind("0 mph, None") == (0.0, "calm")
    assert parse_wind("0 mph, Calm") == (0.0, "calm")


def test_parse_wind_varies_is_unknown():
    speed, cls = parse_wind("12 mph, Varies")
    assert speed == 12.0 and cls == "unknown"


def test_parse_wind_missing_is_unknown_none():
    assert parse_wind(None) == (None, "unknown")
    assert parse_wind(float("nan")) == (None, "unknown")
    assert parse_wind("") == (None, "unknown")


def test_parse_wind_unparseable_speed_still_classifies_direction():
    speed, cls = parse_wind("gust, Out To CF")
    assert speed is None and cls == "out"


# --------------------------------------------------------------------------- #
# synthetic corpus builders
# --------------------------------------------------------------------------- #
def _planted_effect_corpus(n: int = 500, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    temp_f = rng.uniform(40, 95, n)
    wind_out = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_in = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_out = np.where(wind_in > 0, 0.0, wind_out)
    noise = rng.normal(0, 1.5, n)
    total_runs = 8.0 + 0.03 * (temp_f - 70) + 0.05 * wind_out - 0.05 * wind_in + noise
    total_runs = np.round(np.clip(total_runs, 0, None))
    return pd.DataFrame({
        "date": dates, "game_pk": np.arange(n), "temp_f": temp_f,
        "wind_speed": np.maximum(wind_out, wind_in), "wind_out": wind_out,
        "wind_in": wind_in, "total_runs": total_runs,
    })


def _pure_noise_corpus(n: int = 500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    temp_f = rng.uniform(40, 95, n)
    wind_out = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    wind_in = np.where(rng.rand(n) < 0.3, rng.uniform(0, 15, n), 0.0)
    total_runs = np.round(np.clip(rng.normal(8.5, 2.0, n), 0, None))
    return pd.DataFrame({
        "date": dates, "game_pk": np.arange(n), "temp_f": temp_f,
        "wind_speed": np.maximum(wind_out, wind_in), "wind_out": wind_out,
        "wind_in": wind_in, "total_runs": total_runs,
    })


# --------------------------------------------------------------------------- #
# run_gate verdicts
# --------------------------------------------------------------------------- #
def test_planted_temp_wind_effect_ships_review():
    res = run_gate(_planted_effect_corpus())
    assert res["verdict"] == "SHIP_REVIEW"
    assert res["overall"]["rmse_delta"] < 0
    assert res["half1"]["rmse_delta"] < 0
    assert res["half2"]["rmse_delta"] < 0


def test_pure_noise_does_not_ship():
    res = run_gate(_pure_noise_corpus())
    assert res["verdict"] in ("REJECT", "INCONCLUSIVE")
    assert res["verdict"] != "SHIP_REVIEW"


def test_too_few_rows_is_inconclusive():
    small = _planted_effect_corpus(n=BURN_IN + 50)
    res = run_gate(small)
    assert res["verdict"] == "INCONCLUSIVE"
    assert res["n_scorable"] < 200


def test_missing_weather_falls_back_to_baseline_no_crash():
    df = _planted_effect_corpus(n=400)
    df = df.copy()
    df.loc[df.index[BURN_IN + 5:BURN_IN + 25], "temp_f"] = np.nan
    res = run_gate(df)
    assert res["verdict"] in ("SHIP_REVIEW", "REJECT", "INCONCLUSIVE")
    assert res["n"] == 400


# --------------------------------------------------------------------------- #
# leak check: game i's prediction must not depend on game i's own outcome,
# nor on any game AFTER i.
# --------------------------------------------------------------------------- #
def test_no_leak_perturbing_future_outcome_does_not_change_earlier_half():
    df = _planted_effect_corpus(n=300, seed=1)
    df_perturbed = df.copy()
    last_idx = df_perturbed.index[-1]
    df_perturbed.loc[last_idx, "total_runs"] = df_perturbed.loc[last_idx, "total_runs"] + 1000.0

    res_a = run_gate(df)
    res_b = run_gate(df_perturbed)

    # half1 is entirely determined by games strictly before it; perturbing the
    # LAST game's own outcome must not change half1's baseline or candidate
    # RMSE at all (byte-identical walk-forward predictions).
    assert res_a["half1"] == res_b["half1"]
