"""tests.soccer.test_sot_blend — OFFLINE unit tests for domains.soccer.sot_blend.

All tests use SYNTHETIC data only — no parquet reads, no network, no heavy corpus.
Fast and deterministic.

Coverage:
  1. NaN sot rows pass through baseline unchanged (leak-free fallback).
  2. Flip-future-no-change: changing a future row does NOT alter earlier predictions.
  3. Dict shape: build_blended_forecast returns required keys including dBrier/improves.
  4. Constructed case where SoT truly predicts residual -> blend Brier < baseline Brier.
  5. No banned edge words in the honest note.
"""
from __future__ import annotations

import math
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from domains.soccer.sot_blend import (
    _BANNED,
    _HONEST_NOTE,
    _walk_forward_logistic_stack,
    build_blended_forecast,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_bundle(p_base: np.ndarray, target: np.ndarray, n: int):
    """Build a minimal mock FeatureBundle."""
    mock = MagicMock()
    mock.signal_col = p_base
    mock.target = target
    mock.dates = [f"2022-01-{i+1:02d}" for i in range(n)]
    return mock


def _make_matches(n: int, season: int = 2021) -> pd.DataFrame:
    """Synthetic matches DataFrame with event_id + walk-forward-compatible columns."""
    rows = []
    for i in range(n):
        home = f"Home{i % 5}"
        away = f"Away{i % 5}"
        date = pd.Timestamp(f"2022-01-{(i % 28) + 1:02d}")
        rows.append({
            "event_id": f"ev{i:04d}",
            "date": date,
            "div": "E0",
            "home_team": home,
            "away_team": away,
            "fthg": int(i % 4),
            "ftag": int(i % 3),
            "total_goals": int(i % 4) + int(i % 3),
            "target_over25": float((int(i % 4) + int(i % 3)) >= 3),
            "season": season,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: NaN sot rows fall back to baseline
# ---------------------------------------------------------------------------


def test_nan_sot_falls_back_to_baseline() -> None:
    """Rows with NaN sot_feat must return exactly p_base (no model applied)."""
    rng = np.random.default_rng(42)
    n = 200
    p_base = rng.uniform(0.3, 0.7, n)
    target = rng.binomial(1, p_base).astype(float)

    # sot_feat: NaN everywhere -> all rows should pass through
    sot_nan = np.full(n, np.nan)
    result = _walk_forward_logistic_stack(p_base, sot_nan, target)

    np.testing.assert_allclose(result, p_base, rtol=1e-9,
                               err_msg="NaN sot should leave predictions == p_base")


# ---------------------------------------------------------------------------
# Test 2: Flip-future-no-change
# ---------------------------------------------------------------------------


def test_flip_future_no_change() -> None:
    """Changing a future row's sot_feat must NOT alter earlier predictions."""
    rng = np.random.default_rng(7)
    n = 250
    p_base = rng.uniform(0.3, 0.7, n)
    target = rng.binomial(1, 0.5, n).astype(float)
    sot_base = rng.normal(0.0, 1.0, n)

    result_orig = _walk_forward_logistic_stack(p_base.copy(), sot_base.copy(), target.copy())

    # Mutate the LAST quarter of sot_feat wildly.
    sot_mutated = sot_base.copy()
    sot_mutated[n // 2:] = 9999.0
    result_mutated = _walk_forward_logistic_stack(p_base.copy(), sot_mutated, target.copy())

    # First half (rows before mutation start) must be identical.
    half = n // 2
    np.testing.assert_allclose(
        result_orig[:half], result_mutated[:half], rtol=1e-9,
        err_msg="Earlier predictions changed when future sot_feat was mutated"
    )


# ---------------------------------------------------------------------------
# Test 3: Dict shape check
# ---------------------------------------------------------------------------


def _mock_build(p_base, target, sot_for_vals, event_ids) -> Dict[str, Any]:
    """Drive build_blended_forecast with synthetic data via mocking.

    Patches the lazy-imported SoccerAdapter and walk_forward_goals inside
    build_blended_forecast; passes asof_df directly to skip parquet I/O.
    """
    n = len(p_base)
    matches_df = _make_matches(n)
    matches_df["event_id"] = event_ids
    matches_df["target_over25"] = target
    matches_df["p_over25"] = p_base

    asof_df = pd.DataFrame({
        "event_id": event_ids,
        "diff_sot_for_asof": sot_for_vals,
    })

    # walk_forward_goals output must mirror matches_df with p_over25 + valid target.
    wf_out = matches_df.copy()
    wf_out["lam_home"] = 1.2
    wf_out["lam_away"] = 1.1
    wf_out["lam_total"] = 2.3
    wf_out["p_over25"] = p_base

    bundle_mock = _make_bundle(p_base, target, n)

    # Patch at the modules where the lazy imports resolve.
    with (
        patch("domains.soccer.adapter.SoccerAdapter") as MockAdapter,
        patch("domains.soccer.ratings.walk_forward_goals", return_value=wf_out),
    ):
        inst = MockAdapter.return_value
        inst.feature_bundle.return_value = bundle_mock
        inst._get_matches.return_value = matches_df

        result = build_blended_forecast(seasons=None, asof_df=asof_df)
    return result


def test_dict_shape() -> None:
    """build_blended_forecast returns all required keys."""
    rng = np.random.default_rng(99)
    n = 200
    p_base = rng.uniform(0.35, 0.65, n)
    target = rng.binomial(1, 0.5, n).astype(float)
    sot = rng.normal(0.0, 1.0, n)
    eids = [f"ev{i:04d}" for i in range(n)]

    result = _mock_build(p_base, target, sot, eids)

    required_keys = {"n", "baseline", "blend", "dBrier", "dECE", "improves", "note"}
    assert required_keys.issubset(result.keys()), f"Missing keys: {required_keys - result.keys()}"
    assert isinstance(result["dBrier"], float)
    assert isinstance(result["improves"], bool)
    assert isinstance(result["note"], str)
    for sub in ("baseline", "blend"):
        assert "brier" in result[sub], f"'{sub}' missing brier"
        assert "ece" in result[sub], f"'{sub}' missing ece"
        assert "log_loss" in result[sub], f"'{sub}' missing log_loss"
    assert result["n"] > 0


# ---------------------------------------------------------------------------
# Test 4: Constructed case — SoT predicts residual -> blend Brier < baseline Brier
# ---------------------------------------------------------------------------


def test_blend_beats_baseline_when_sot_predicts_residual() -> None:
    """On a constructed corpus where SoT form drives outcomes, blend < baseline Brier."""
    rng = np.random.default_rng(2024)
    n = 500

    # SoT differential: strongly signals over/under beyond Poisson.
    sot = rng.normal(0.0, 1.5, n)
    # True probability depends on both a flat baseline AND sot.
    true_p = 1.0 / (1.0 + np.exp(-(0.0 + 0.6 * sot)))
    target = rng.binomial(1, true_p).astype(float)

    # Baseline is flat (ignores sot) — deliberately miscalibrated.
    p_base = np.full(n, 0.45)

    blend = _walk_forward_logistic_stack(p_base, sot, target, min_history=80)

    # Only score on the post-warmup portion where blend has a fitted model.
    post = 80
    base_brier = float(np.mean((p_base[post:] - target[post:]) ** 2))
    blend_brier = float(np.mean((blend[post:] - target[post:]) ** 2))

    assert blend_brier < base_brier, (
        f"Expected blend Brier ({blend_brier:.5f}) < baseline ({base_brier:.5f}) "
        "on a corpus where SoT genuinely drives outcomes"
    )


# ---------------------------------------------------------------------------
# Test 5: No banned edge words in the honest note
# ---------------------------------------------------------------------------


def test_no_banned_words_in_note() -> None:
    """The honest note must NOT contain any banned edge-claim words."""
    note_lower = _HONEST_NOTE.lower()
    for word in _BANNED:
        assert word.lower() not in note_lower, (
            f"Banned word '{word}' found in honest note: {_HONEST_NOTE!r}"
        )
