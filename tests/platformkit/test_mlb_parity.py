"""Per-file tests for domains.mlb.feature_spec + domains.mlb.ingest_manifest.

Covers: catalog column order, synthetic exact-replication of the adapter formula,
a GUARDED real-adapter byte-equality proof (atol 1e-9), and manifest structural
validation + live census check.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_mlb_parity.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.feature_spec_core import (
    FeatureSpec,
    assert_matches_catalog,
    build_base_matrix,
)
from domains.mlb.feature_spec import MLB_BASE_SPEC, build_mlb_base, catalog
from domains.mlb.ingest_manifest import MLB_MANIFEST


# ---------------------------------------------------------------------------
# feature_spec: catalog
# ---------------------------------------------------------------------------

def test_mlb_catalog_is_six_adapter_columns():
    assert catalog() == [
        "elo_home", "elo_away", "elo_diff_hfa",
        "rest_days_home", "rest_days_away", "h2h_rate",
    ]
    assert MLB_BASE_SPEC.n_features() == 6


def test_mlb_catalog_hash_deterministic_and_sensitive():
    h0 = MLB_BASE_SPEC.catalog_hash()
    assert h0 == MLB_BASE_SPEC.catalog_hash()
    bumped = FeatureSpec("mlb", "mlb-base-v2", MLB_BASE_SPEC.fields)
    assert bumped.catalog_hash() != h0
    reordered = FeatureSpec("mlb", "mlb-base-v1", tuple(reversed(MLB_BASE_SPEC.fields)))
    assert reordered.catalog_hash() != h0


def test_assert_matches_catalog_passes_and_fails():
    assert_matches_catalog(MLB_BASE_SPEC, catalog())
    with pytest.raises(AssertionError, match="parity FAILED"):
        assert_matches_catalog(MLB_BASE_SPEC, catalog()[::-1])


# ---------------------------------------------------------------------------
# feature_spec: synthetic exact-replication of the adapter inline formula
# ---------------------------------------------------------------------------

def _adapter_formula(df: pd.DataFrame) -> np.ndarray:
    """Re-implements adapter.py:219-223 exactly, row by row."""
    out = []
    for _, row in df.iterrows():
        out.append([
            float(row["elo_home"]),
            float(row["elo_away"]),
            float(row["elo_diff_hfa"]),
            float(row.get("rest_days_home", 5.0)),
            float(row.get("rest_days_away", 5.0)),
            float(row.get("h2h_rate", 0.5)),
        ])
    return np.array(out, dtype=float)


def test_synthetic_matches_adapter_formula():
    df = pd.DataFrame({
        "elo_home": [1520.0, 1480.0, 1600.0],
        "elo_away": [1490.0, 1530.0, 1450.0],
        "elo_diff_hfa": [70.0, -10.0, 200.0],
        "rest_days_home": [2.0, np.nan, 5.0],
        "rest_days_away": [4.0, 3.0, 1.0],
        "h2h_rate": [0.6, 0.5, np.nan],
    })
    got, names = build_mlb_base(df)
    assert names == catalog()
    exp = _adapter_formula(df)
    # NaN positions must match; non-NaN must be bit-exact
    np.testing.assert_array_equal(np.isnan(got), np.isnan(exp))
    both = ~np.isnan(got)
    np.testing.assert_allclose(got[both], exp[both], rtol=0, atol=0)


def test_default_fills_when_column_absent():
    # rest_days and h2h_rate absent -> defaults apply
    df = pd.DataFrame({
        "elo_home": [1500.0],
        "elo_away": [1490.0],
        "elo_diff_hfa": [60.0],
    })
    got, _ = build_mlb_base(df)
    assert got[0, 3] == pytest.approx(5.0)   # rest_days_home default
    assert got[0, 4] == pytest.approx(5.0)   # rest_days_away default
    assert got[0, 5] == pytest.approx(0.5)   # h2h_rate default


def test_required_absent_raises_not_silent_zero():
    df = pd.DataFrame({"elo_away": [1500.0], "elo_diff_hfa": [0.0]})
    with pytest.raises(KeyError, match="required source"):
        build_mlb_base(df)


# ---------------------------------------------------------------------------
# GUARDED real-adapter parity: spec reproduces bundle.base byte-for-byte
# ---------------------------------------------------------------------------

def test_parity_vs_real_mlb_adapter():
    games_path = "data/domains/mlb/games.parquet"
    if not os.path.exists(games_path):
        pytest.skip("mlb games.parquet absent")
    try:
        from domains.mlb.adapter import MLBAdapter, _add_context  # noqa: PLC0415
        from domains.mlb.ratings import walk_forward_elo  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"mlb adapter import failed: {exc}")

    games = pd.read_parquet(games_path)
    seasons = sorted(games["season"].dropna().unique())
    season = seasons[-1]
    gslice = games[games["season"] == season].copy()
    if len(gslice) < 20:
        pytest.skip("season slice too small")

    adapter = MLBAdapter(games_df=gslice.copy(), odds_df=pd.DataFrame())
    bundle = adapter.feature_bundle(None, seasons=[season])

    # Reconstruct the SAME walk-forward frame the adapter built internally.
    # _add_context calls walk_forward_elo and appends rest_days/h2h/recent_win10.
    wf = _add_context(walk_forward_elo(gslice.copy()))
    kept = wf[wf["target_home_win"].notna()]  # adapter skips NaN targets

    got, names = build_mlb_base(kept)
    assert names == catalog()
    assert got.shape == bundle.base.shape, (got.shape, bundle.base.shape)
    # atol=1e-9 (floating-point tolerance from identical arithmetic paths)
    np.testing.assert_allclose(got, bundle.base, rtol=0, atol=1e-9)


# ---------------------------------------------------------------------------
# manifest: structural validation + live census
# ---------------------------------------------------------------------------

def test_mlb_manifest_is_structurally_valid():
    assert MLB_MANIFEST.validate() == []


def test_mlb_manifest_has_required_corpora():
    corpora = {s.corpus for s in MLB_MANIFEST.sources}
    # spine + odds must always be declared
    assert "games" in corpora
    assert "odds" in corpora


def test_mlb_manifest_leak_classes_sane():
    classes = {s.corpus: s.leak_class for s in MLB_MANIFEST.sources}
    # training label spine must be pre_game (schedule is known before first pitch)
    assert classes["games"] == "pre_game"
    # post-game settlement artifacts must never be pre_game
    assert classes["postmortem"] == "post_game"
    assert classes["player_gamelogs"] == "post_game"
    # odds are available pre-game
    assert classes["odds"] == "pre_game"
    # derived as-of features are pre_game by construction
    assert classes["asof_features"] == "pre_game"


def test_mlb_pregame_corpora_excludes_post_game():
    pregame = set(MLB_MANIFEST.pregame_corpora())
    assert "postmortem" not in pregame
    assert "player_gamelogs" not in pregame
    assert "games" in pregame
    assert "odds" in pregame


def test_mlb_manifest_against_real_census():
    try:
        from data_registry.inventory import build_inventory  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"data_registry unavailable: {exc}")
    inv = build_inventory(sports=["mlb"])
    if inv["n_corpora"] == 0:
        pytest.skip("no mlb corpora on disk")
    errs = MLB_MANIFEST.validate_against_inventory(inv)
    assert errs == [], f"manifest/census mismatch: {errs}"
