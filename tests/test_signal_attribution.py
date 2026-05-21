"""tests/test_signal_attribution.py — Unit tests for SignalAttributionModel.

Builds synthetic data with 4 known feature-group contributions and verifies
that:
  1. The fitted coefficients sum to ~1 (within tolerance).
  2. The module handles a missing CSV path gracefully (no crash, empty dict).
  3. The JSON output file is written when data is present.
  4. Each individual coefficient is non-negative for a positive-weight setup.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.prediction.signal_attribution import SignalAttributionModel, _FEATURE_GROUPS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_df(
    n: int = 500,
    weights: tuple = (0.30, 0.25, 0.25, 0.20),
    noise_std: float = 0.01,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic DataFrame where CLV is a known linear combination.

    CLV = w1*cv + w2*api + w3*timing + w4*pinnacle + small_noise
    with binary (Bernoulli 0.5) feature flags.
    """
    rng = np.random.default_rng(seed)
    data = {g: rng.integers(0, 2, size=n).astype(float) for g in _FEATURE_GROUPS}
    df = pd.DataFrame(data)
    df["clv"] = sum(w * df[g] for w, g in zip(weights, _FEATURE_GROUPS))
    df["clv"] += rng.normal(0, noise_std, size=n)
    return df


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSignalAttributionCoefficients:
    """Core behaviour: coefficients match synthetic ground truth."""

    def test_coefficients_sum_to_approx_one(self, tmp_path: Path) -> None:
        """Sum of feature-group coefficients should be within 0.15 of 1.0.

        The tolerance is generous because linear regression spreads weight
        across correlated features; what matters is that all signal is
        accounted for across the four groups.
        """
        df = _make_synthetic_df(weights=(0.30, 0.25, 0.25, 0.20))
        out_file = tmp_path / "signal_attribution.json"

        model = SignalAttributionModel()
        result = model.fit(df, output_path=out_file)

        assert result, "fit() should return a non-empty dict"
        coef_sum = sum(result[g] for g in _FEATURE_GROUPS)
        assert abs(coef_sum - 1.0) < 0.15, (
            f"Coefficient sum {coef_sum:.4f} not within 0.15 of 1.0"
        )

    def test_coefficients_are_positive(self, tmp_path: Path) -> None:
        """All four group coefficients should be positive for positive-only weights."""
        df = _make_synthetic_df(weights=(0.30, 0.25, 0.25, 0.20))
        out_file = tmp_path / "signal_attribution.json"

        model = SignalAttributionModel()
        result = model.fit(df, output_path=out_file)

        for group in _FEATURE_GROUPS:
            assert result[group] > 0, f"Coefficient for {group} should be positive"

    def test_coefficient_ordering(self, tmp_path: Path) -> None:
        """cv_features (largest weight 0.40) should have the highest coefficient."""
        df = _make_synthetic_df(
            weights=(0.40, 0.25, 0.20, 0.15), n=1000, noise_std=0.001
        )
        out_file = tmp_path / "signal_attribution.json"

        model = SignalAttributionModel()
        result = model.fit(df, output_path=out_file)

        assert result["cv_features"] == max(result[g] for g in _FEATURE_GROUPS), (
            "cv_features should have the largest coefficient when its weight is highest"
        )


class TestSignalAttributionOutputFile:
    """JSON output is written correctly."""

    def test_json_output_created(self, tmp_path: Path) -> None:
        df = _make_synthetic_df()
        out_file = tmp_path / "signal_attribution.json"

        model = SignalAttributionModel()
        model.fit(df, output_path=out_file)

        assert out_file.exists(), "JSON output file should be created"
        with out_file.open() as fh:
            data = json.load(fh)
        for group in _FEATURE_GROUPS:
            assert group in data, f"Output JSON missing key: {group}"
        assert "intercept" in data

    def test_json_values_are_floats(self, tmp_path: Path) -> None:
        df = _make_synthetic_df()
        out_file = tmp_path / "signal_attribution.json"

        model = SignalAttributionModel()
        model.fit(df, output_path=out_file)

        with out_file.open() as fh:
            data = json.load(fh)
        for k, v in data.items():
            assert isinstance(v, float), f"JSON value for {k} should be float"


class TestSignalAttributionGracefulDegradation:
    """Module must not crash when input is absent or malformed."""

    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        model = SignalAttributionModel()
        result = model.fit(
            tmp_path / "does_not_exist.csv",
            output_path=tmp_path / "out.json",
        )
        assert result == {}, "Missing file should yield empty dict, not an exception"

    def test_missing_file_does_not_write_output(self, tmp_path: Path) -> None:
        out_file = tmp_path / "out.json"
        model = SignalAttributionModel()
        model.fit(tmp_path / "does_not_exist.csv", output_path=out_file)
        assert not out_file.exists(), "No output file should be written for missing input"

    def test_missing_columns_returns_empty_dict(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"cv_features": [1, 0], "clv": [0.3, 0.1]})
        model = SignalAttributionModel()
        result = model.fit(df, output_path=tmp_path / "out.json")
        assert result == {}, "Missing feature columns should yield empty dict"

    def test_too_few_rows_returns_empty_dict(self, tmp_path: Path) -> None:
        df = pd.DataFrame(
            {g: [1] for g in _FEATURE_GROUPS} | {"clv": [0.5]}
        )
        model = SignalAttributionModel()
        result = model.fit(df, output_path=tmp_path / "out.json")
        assert result == {}, "Single-row DataFrame should yield empty dict"

    def test_empty_dataframe_returns_empty_dict(self, tmp_path: Path) -> None:
        df = pd.DataFrame(columns=_FEATURE_GROUPS + ["clv"])
        model = SignalAttributionModel()
        result = model.fit(df, output_path=tmp_path / "out.json")
        assert result == {}, "Empty DataFrame should yield empty dict"

    def test_csv_path_string_accepted(self, tmp_path: Path) -> None:
        """Accept a plain string path, not just Path objects."""
        csv_path = tmp_path / "clv_training_data.csv"
        df = _make_synthetic_df(n=100)
        df.to_csv(csv_path, index=False)

        model = SignalAttributionModel()
        result = model.fit(str(csv_path), output_path=tmp_path / "out.json")
        assert result, "Should succeed with string path to existing CSV"
