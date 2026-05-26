"""
test_feature_engineering_spacing.py

Tests for the two team_spacing sentinel bug fixes:
  BUG 1 — shot_quality_proxy must not treat team_spacing==0 as real tight spacing.
  BUG 2 — impute_team_spacing forward-fills sentinel/NaN rows per (game_id, team)
           with a 90-frame cap.

Skip cleanly when the module cannot import (e.g. partial environment).
"""

import numpy as np
import pandas as pd
import pytest

fe = pytest.importorskip(
    "src.features.feature_engineering",
    reason="src.features.feature_engineering not importable in this environment",
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_shot_df(team_spacing_vals, court_zone="paint", nearest_opp=5.0):
    """Minimal DataFrame suitable for add_game_flow_features shot quality branch."""
    n = len(team_spacing_vals)
    return pd.DataFrame(
        {
            "frame": range(n),
            "player_id": [1] * n,
            "team": ["teamA"] * n,
            "ball_possession": [1] * n,
            "event": ["shot"] * n,
            "court_zone": [court_zone] * n,
            "nearest_opponent": [nearest_opp] * n,
            "team_spacing": team_spacing_vals,
            "x_position": [0.0] * n,
            "y_position": [0.0] * n,
        }
    )


def _make_tracking_df(spacing_vals, game_ids=None, teams=None):
    """Minimal DataFrame suitable for impute_team_spacing."""
    n = len(spacing_vals)
    df = pd.DataFrame(
        {
            "frame": range(n),
            "player_id": [1] * n,
            "team_spacing": spacing_vals,
        }
    )
    if game_ids is not None:
        df["game_id"] = game_ids
    if teams is not None:
        df["team"] = teams
    return df


# ─── BUG 1: shot_quality_proxy ignores zero sentinel ─────────────────────────

def test_shot_quality_proxy_ignores_zero_spacing_sentinel():
    """
    When team_spacing==0 (sentinel), shot_quality_proxy must be computed with
    the median real spacing — not 0.  Proxy should be at least as high as when
    spacing is explicitly set to the median value.
    """
    real_spacing = [200.0, 300.0, 250.0, 0.0, 0.0, 0.0, 280.0]
    df = _make_shot_df(real_spacing)
    out = fe.add_game_flow_features(df)

    assert "shot_quality_proxy" in out.columns, "shot_quality_proxy column missing"

    # All rows are shot events, so shot_quality_proxy should be non-zero for ALL.
    # The critical assertion: values on sentinel rows (index 3,4,5) must NOT be
    # lower than the value on a real-value row when sentinel means "unknown", not
    # "zero spacing".  Because we impute with median, sentinel rows should yield
    # the same proxy as a row with median spacing.
    proxy_real   = out.loc[out["team_spacing"].isin([200.0, 300.0, 250.0, 280.0]), "shot_quality_proxy"]
    proxy_sentl  = out.loc[out["team_spacing"] == 0.0, "shot_quality_proxy"]

    # Sentinel rows must not all be lower than the minimum of non-sentinel rows.
    # (If 0 were used, spacing_n=0 and the 0.5+0.5*0 factor = 0.5; with median
    # spacing, factor is 1.0 — so sentinel proxy would be 2× lower incorrectly.)
    assert proxy_sentl.mean() > 0.0, "sentinel shot_quality_proxy should be non-zero"
    assert proxy_sentl.mean() >= proxy_real.min() * 0.9, (
        f"Sentinel rows have suspiciously low shot_quality_proxy "
        f"({proxy_sentl.mean():.4f}) vs non-sentinel min ({proxy_real.min():.4f}) — "
        f"sentinel may still be treated as zero spacing"
    )


# ─── BUG 2: impute_team_spacing ──────────────────────────────────────────────

def test_impute_team_spacing_forward_fills_gap():
    """[10, 0, 0, 0, 12] → imputed=[10,10,10,10,12], is_imputed=[F,T,T,T,F]."""
    df = _make_tracking_df([10.0, 0.0, 0.0, 0.0, 12.0])
    out = fe.impute_team_spacing(df)

    assert "team_spacing_imputed" in out.columns
    assert "is_spacing_imputed"   in out.columns

    expected_imputed = [10.0, 10.0, 10.0, 10.0, 12.0]
    expected_flag    = [False, True, True, True, False]

    np.testing.assert_array_almost_equal(
        out["team_spacing_imputed"].values, expected_imputed,
        err_msg="team_spacing_imputed values incorrect",
    )
    assert list(out["is_spacing_imputed"].values) == expected_flag, (
        f"is_spacing_imputed flags incorrect: {list(out['is_spacing_imputed'].values)}"
    )


def test_impute_team_spacing_respects_90_frame_cap():
    """A gap longer than 90 frames must leave trailing rows as NaN."""
    # Build: 1 real value, then 100 sentinel zeros
    spacing = [150.0] + [0.0] * 100
    df = _make_tracking_df(spacing)
    out = fe.impute_team_spacing(df)

    imputed = out["team_spacing_imputed"].values

    # Frames 1-90 (within cap) must be filled
    assert all(~np.isnan(imputed[1:91])), (
        "Frames within 90-frame cap should be forward-filled"
    )
    # Frame 91-100 (beyond cap) must be NaN
    assert all(np.isnan(imputed[91:])), (
        "Frames beyond 90-frame cap must remain NaN"
    )


def test_impute_per_game_team():
    """Imputation must not cross game boundaries or team boundaries."""
    # Game A / teamX: real value then zeros
    # Game B / teamY: leading zeros (no prior value — should stay NaN)
    spacing  = [100.0, 0.0, 0.0,   0.0,  0.0]
    game_ids = ["gA",  "gA", "gA", "gB", "gB"]
    teams    = ["tX",  "tX", "tX", "tY", "tY"]

    df = _make_tracking_df(spacing, game_ids=game_ids, teams=teams)
    out = fe.impute_team_spacing(df)

    imputed = out["team_spacing_imputed"].values

    # gA/tX: rows 1 and 2 should get 100.0 via ffill
    assert imputed[1] == pytest.approx(100.0), "row 1 in gA/tX should be filled with 100.0"
    assert imputed[2] == pytest.approx(100.0), "row 2 in gA/tX should be filled with 100.0"

    # gB/tY: no prior value — rows 3 and 4 must remain NaN (different game)
    assert np.isnan(imputed[3]), "row 3 in gB/tY has no prior — must be NaN"
    assert np.isnan(imputed[4]), "row 4 in gB/tY has no prior — must be NaN"


def test_impute_team_spacing_no_prior_value_stays_nan():
    """Leading sentinel zeros with no prior real value must remain NaN after impute."""
    df = _make_tracking_df([0.0, 0.0, 0.0, 0.0])
    out = fe.impute_team_spacing(df)

    assert out["team_spacing_imputed"].isna().all(), (
        "All rows were sentinel; no prior real value to ffill — all must stay NaN"
    )
    assert out["is_spacing_imputed"].all(), (
        "All sentinel rows should be flagged is_spacing_imputed=True"
    )


# ─── Regression: original sentinel filter (lines 142-144) still works ────────

def test_existing_sentinel_filter_still_works():
    """
    compute_spatial_features must still convert team_spacing==0 to NaN
    (lines 142-144 untouched).  The NEW impute_team_spacing columns are additive.
    """
    df = _make_tracking_df([150.0, 0.0, 250.0])
    # Add 'team' column so compute_spatial_features doesn't early-return
    df["team"] = "teamA"
    df["x_position"] = 0.0
    df["y_position"] = 0.0

    out = fe.compute_spatial_features(df)

    # Original sentinel-to-NaN conversion must be intact
    assert np.isnan(out["team_spacing"].iloc[1]), (
        "team_spacing==0 must be converted to NaN by existing sentinel filter (lines 142-144)"
    )
    # Real values must be unchanged
    assert out["team_spacing"].iloc[0] == pytest.approx(150.0)
    assert out["team_spacing"].iloc[2] == pytest.approx(250.0)

    # New columns must now exist (wired via impute_team_spacing call inside compute_spatial_features)
    assert "team_spacing_imputed" in out.columns, (
        "team_spacing_imputed column missing — impute_team_spacing not wired into compute_spatial_features"
    )
    assert "is_spacing_imputed" in out.columns, (
        "is_spacing_imputed column missing"
    )
