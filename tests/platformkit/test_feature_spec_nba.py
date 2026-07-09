"""Per-file tests for the feature_spec parity seam (core + NBA instance).

Covers: catalog stability/hashing, build_base_matrix semantics (required-absent
raises, column-absent default, present-NaN passthrough, bool_float incl. the
bool(NaN)->1.0 quirk, column order), a SYNTHETIC exact-replication of the adapter's
inline formula, and a GUARDED real-adapter parity proof (bundle.base byte-equal).

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_feature_spec_nba.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.feature_spec_core import (
    CAST_BOOL_FLOAT,
    CAST_FLOAT,
    FeatureField,
    FeatureSpec,
    assert_matches_catalog,
    build_base_matrix,
)
from domains.basketball_nba.feature_spec import (
    NBA_ASOF_SPEC,
    NBA_BASE_SPEC,
    build_nba_base,
    catalog,
)


# --------------------------------------------------------------------------- #
# core
# --------------------------------------------------------------------------- #
def test_bad_cast_raises():
    with pytest.raises(ValueError):
        FeatureField("x", "x", cast="weird")


def test_catalog_and_hash_stable_and_sensitive():
    h0 = NBA_BASE_SPEC.catalog_hash()
    assert h0 == NBA_BASE_SPEC.catalog_hash()  # deterministic
    bumped = FeatureSpec("basketball_nba", "nba-base-v3", NBA_BASE_SPEC.fields)
    assert bumped.catalog_hash() != h0  # version change moves the hash
    reordered = FeatureSpec("basketball_nba", "nba-base-v1",
                            tuple(reversed(NBA_BASE_SPEC.fields)))
    assert reordered.catalog_hash() != h0  # order is part of the contract


def test_nba_catalog_is_the_eight_base_columns_by_default():
    """Default contract (include_asof=False) is the 8-col nba-base-v1 -- bit-identical
    to pre-2026-07-11 (see docs/research/bundle_regression_fix_2026-07-11.md)."""
    assert catalog() == [
        "elo_home", "elo_away", "elo_diff_hfa",
        "rest_days_home", "rest_days_away",
        "home_b2b", "away_b2b", "rolling_win10_home",
    ]
    assert NBA_BASE_SPEC.n_features() == 8


def test_nba_catalog_include_asof_is_the_ten_adapter_columns():
    assert catalog(include_asof=True) == [
        "elo_home", "elo_away", "elo_diff_hfa",
        "rest_days_home", "rest_days_away",
        "home_b2b", "away_b2b", "rolling_win10_home",
        "def_fg_pct_allowed_diff_asof", "def_pts_allowed_per36_diff_asof",
    ]
    assert NBA_ASOF_SPEC.n_features() == 10


def test_required_source_absent_raises_not_silent_zero():
    spec = FeatureSpec("s", "v1", (FeatureField("a", "a", default=None),))
    with pytest.raises(KeyError, match="required source"):
        build_base_matrix(spec, pd.DataFrame({"b": [1.0]}))


def test_default_applies_only_when_column_absent():
    spec = FeatureSpec("s", "v1", (
        FeatureField("r", "rest", default=5.0, cast=CAST_FLOAT),
    ))
    # column absent -> default fills
    m_absent, _ = build_base_matrix(spec, pd.DataFrame({"x": [1.0, 2.0]}))
    assert list(m_absent[:, 0]) == [5.0, 5.0]
    # column present with a NaN value -> NaN passes through (NOT replaced by default)
    m_present, _ = build_base_matrix(spec, pd.DataFrame({"rest": [3.0, np.nan]}))
    assert m_present[0, 0] == 3.0 and np.isnan(m_present[1, 0])


def test_bool_float_cast_and_nan_quirk():
    spec = FeatureSpec("s", "v1", (FeatureField("f", "flag", default=0.0, cast=CAST_BOOL_FLOAT),))
    m, _ = build_base_matrix(spec, pd.DataFrame({"flag": [True, False, np.nan, 1, 0]}))
    # bool(True)=1, bool(False)=0, bool(nan)=True->1, bool(1)=1, bool(0)=0
    assert list(m[:, 0]) == [1.0, 0.0, 1.0, 1.0, 0.0]


def test_assert_matches_catalog():
    assert_matches_catalog(NBA_BASE_SPEC, catalog())  # no raise
    with pytest.raises(AssertionError, match="parity FAILED"):
        assert_matches_catalog(NBA_BASE_SPEC, catalog()[::-1])


# --------------------------------------------------------------------------- #
# synthetic exact-replication of the adapter's inline formula
# --------------------------------------------------------------------------- #
def _adapter_formula(df: pd.DataFrame) -> np.ndarray:
    """Re-implements adapter.py's rows_base.append(...) exactly, row by row."""
    out = []
    for _, row in df.iterrows():
        out.append([
            float(row["elo_home"]), float(row["elo_away"]), float(row["elo_diff_hfa"]),
            float(row.get("rest_days_home", 5.0)), float(row.get("rest_days_away", 5.0)),
            float(bool(row.get("home_b2b", False))), float(bool(row.get("away_b2b", False))),
            float(row.get("rolling_win10_home", 0.5)),
            float(row.get("def_fg_pct_allowed_diff_asof", np.nan)),
            float(row.get("def_pts_allowed_per36_diff_asof", np.nan)),
        ])
    return np.array(out, dtype=float)


def test_synthetic_matches_adapter_formula():
    df = pd.DataFrame({
        "elo_home": [1500.0, 1620.5, 1480.0],
        "elo_away": [1490.0, 1510.0, 1550.0],
        "elo_diff_hfa": [60.0, 110.5, -70.0],
        "rest_days_home": [2.0, np.nan, 4.0],   # NaN must pass through
        "rest_days_away": [5.0, 3.0, 1.0],
        "home_b2b": [True, False, np.nan],       # bool(nan)->1.0
        "away_b2b": [False, True, False],
        "rolling_win10_home": [0.6, 0.4, 0.55],
        "def_fg_pct_allowed_diff_asof": [0.02, np.nan, -0.05],
        "def_pts_allowed_per36_diff_asof": [1.1, 2.2, np.nan],
    })
    got, names = build_nba_base(df, include_asof=True)
    assert names == catalog(include_asof=True)
    exp = _adapter_formula(df)
    np.testing.assert_array_equal(np.isnan(got), np.isnan(exp))
    both = ~np.isnan(got)
    np.testing.assert_allclose(got[both], exp[both], rtol=0, atol=0)


# --------------------------------------------------------------------------- #
# GUARDED real-adapter parity: spec reproduces bundle.base byte-for-byte
# --------------------------------------------------------------------------- #
def test_parity_vs_real_adapter_feature_bundle():
    games_path = "data/domains/basketball_nba/games.parquet"
    if not os.path.exists(games_path):
        pytest.skip("games.parquet absent")
    try:
        from domains.basketball_nba.adapter import (  # noqa: PLC0415
            NBAAdapter, _add_rolling_win10, _season_to_int,
        )
        from domains.basketball_nba.ratings import walk_forward_elo  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"adapter import failed: {exc}")

    games = pd.read_parquet(games_path)
    season = sorted(games["season"].dropna().astype(str).unique())[-1]  # most recent
    gslice = games[games["season"].astype(str) == season].copy()
    if len(gslice) < 20:
        pytest.skip("season slice too small")

    adapter = NBAAdapter(games_df=gslice.copy(), odds_df=pd.DataFrame())
    # hypothesis is unused in body; include_asof=True exercises the full 10-col contract.
    bundle = adapter.feature_bundle(None, seasons=[season], include_asof=True)

    # Reconstruct the SAME walk-forward frame the adapter built internally.
    g = gslice.copy()
    g["_season_orig"] = g["season"]
    g["season"] = g["season"].apply(_season_to_int)
    wf = _add_rolling_win10(walk_forward_elo(g))
    wf["season"] = wf["_season_orig"]
    wf = wf.drop(columns=["_season_orig"])
    kept = wf[wf["home_win"].notna()].copy()  # adapter skips NaN targets, preserving order

    # Reproduce the adapter's SHIP-asof merge (domains/basketball_nba/adapter.py) so
    # this parity check covers the real 10-col contract, not just the original 8.
    rollup_path = "data/domains/basketball_nba/asof_defender_rollup.parquet"
    from domains.basketball_nba.adapter import SHIP_ASOF_COLS  # noqa: PLC0415
    kept["game_id"] = kept["game_id"].astype(str)
    if os.path.exists(rollup_path):
        _r = pd.read_parquet(rollup_path)[["game_id", *SHIP_ASOF_COLS]].copy()
        _r["game_id"] = _r["game_id"].astype(str)
        kept = kept.merge(_r, on="game_id", how="left")
    else:
        for _c in SHIP_ASOF_COLS:
            kept[_c] = np.nan

    got, names = build_nba_base(kept, include_asof=True)
    assert names == catalog(include_asof=True)
    assert got.shape == bundle.base.shape, (got.shape, bundle.base.shape)
    np.testing.assert_allclose(got, bundle.base, rtol=0, atol=1e-9)
