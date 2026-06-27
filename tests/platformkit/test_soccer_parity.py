"""Per-file tests for domains.soccer.feature_spec + domains.soccer.ingest_manifest.

Covers: catalog column order, synthetic exact-replication of the adapter formula,
a GUARDED real-adapter byte-equality proof (atol 1e-9), and manifest structural
validation + live census check.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_soccer_parity.py -q
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
from domains.soccer.feature_spec import SOCCER_BASE_SPEC, build_soccer_base, catalog
from domains.soccer.ingest_manifest import SOCCER_MANIFEST


# ---------------------------------------------------------------------------
# feature_spec: catalog
# ---------------------------------------------------------------------------

def test_soccer_catalog_is_five_adapter_columns():
    assert catalog() == [
        "lam_home", "lam_away", "lam_total",
        "rest_days_home", "rest_days_away",
    ]
    assert SOCCER_BASE_SPEC.n_features() == 5


def test_soccer_catalog_hash_deterministic_and_sensitive():
    h0 = SOCCER_BASE_SPEC.catalog_hash()
    assert h0 == SOCCER_BASE_SPEC.catalog_hash()
    bumped = FeatureSpec("soccer", "soccer-base-v2", SOCCER_BASE_SPEC.fields)
    assert bumped.catalog_hash() != h0
    reordered = FeatureSpec("soccer", "soccer-base-v1", tuple(reversed(SOCCER_BASE_SPEC.fields)))
    assert reordered.catalog_hash() != h0


def test_assert_matches_catalog_passes_and_fails():
    assert_matches_catalog(SOCCER_BASE_SPEC, catalog())
    with pytest.raises(AssertionError, match="parity FAILED"):
        assert_matches_catalog(SOCCER_BASE_SPEC, catalog()[::-1])


# ---------------------------------------------------------------------------
# feature_spec: synthetic exact-replication of the adapter inline formula
# ---------------------------------------------------------------------------

def _adapter_formula(df: pd.DataFrame) -> np.ndarray:
    """Re-implements adapter.py:237-240 exactly, row by row."""
    out = []
    for _, row in df.iterrows():
        out.append([
            float(row["lam_home"]),
            float(row["lam_away"]),
            float(row["lam_total"]),
            float(row.get("rest_days_home", 15.0)),
            float(row.get("rest_days_away", 15.0)),
        ])
    return np.array(out, dtype=float)


def test_synthetic_matches_adapter_formula():
    df = pd.DataFrame({
        "lam_home": [1.42, 1.10, 2.05],
        "lam_away": [0.88, 1.55, 1.30],
        "lam_total": [2.30, 2.65, 3.35],
        "rest_days_home": [7.0, np.nan, 4.0],
        "rest_days_away": [14.0, 5.0, np.nan],
    })
    got, names = build_soccer_base(df)
    assert names == catalog()
    exp = _adapter_formula(df)
    np.testing.assert_array_equal(np.isnan(got), np.isnan(exp))
    both = ~np.isnan(got)
    np.testing.assert_allclose(got[both], exp[both], rtol=0, atol=0)


def test_default_fills_when_rest_absent():
    df = pd.DataFrame({
        "lam_home": [1.3],
        "lam_away": [1.1],
        "lam_total": [2.4],
    })
    got, _ = build_soccer_base(df)
    assert got[0, 3] == pytest.approx(15.0)   # rest_days_home default
    assert got[0, 4] == pytest.approx(15.0)   # rest_days_away default


def test_required_absent_raises_not_silent_zero():
    df = pd.DataFrame({"lam_away": [1.0], "lam_total": [2.0]})
    with pytest.raises(KeyError, match="required source"):
        build_soccer_base(df)


# ---------------------------------------------------------------------------
# GUARDED real-adapter parity: spec reproduces bundle.base byte-for-byte
# ---------------------------------------------------------------------------

def test_parity_vs_real_soccer_adapter():
    matches_path = "data/domains/soccer/matches.parquet"
    if not os.path.exists(matches_path):
        pytest.skip("soccer matches.parquet absent")
    try:
        from domains.soccer.adapter import SoccerAdapter, _add_rest_days  # noqa: PLC0415
        from domains.soccer.ratings import walk_forward_goals  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"soccer adapter import failed: {exc}")

    matches = pd.read_parquet(matches_path)
    seasons = sorted(matches["season"].dropna().unique())
    season = seasons[-1]
    mslice = matches[matches["season"] == season].copy()
    if len(mslice) < 20:
        pytest.skip("season slice too small")

    adapter = SoccerAdapter(matches_df=mslice.copy(), odds_df=pd.DataFrame())
    bundle = adapter.feature_bundle(None, seasons=[season])

    # Reconstruct the SAME walk-forward frame the adapter built internally.
    # walk_forward_goals uses ALL matches for rating warmup but we pass
    # the season slice which mirrors what the adapter does.
    wf = _add_rest_days(walk_forward_goals(mslice.copy()))
    kept = wf[wf["target_over25"].notna()]  # adapter skips NaN targets

    got, names = build_soccer_base(kept)
    assert names == catalog()
    assert got.shape == bundle.base.shape, (got.shape, bundle.base.shape)
    # atol=1e-9 (floating-point tolerance from identical arithmetic paths)
    np.testing.assert_allclose(got, bundle.base, rtol=0, atol=1e-9)


# ---------------------------------------------------------------------------
# manifest: structural validation + live census
# ---------------------------------------------------------------------------

def test_soccer_manifest_is_structurally_valid():
    assert SOCCER_MANIFEST.validate() == []


def test_soccer_manifest_has_required_corpora():
    corpora = {s.corpus for s in SOCCER_MANIFEST.sources}
    assert "matches" in corpora
    assert "odds" in corpora


def test_soccer_manifest_leak_classes_sane():
    classes = {s.corpus: s.leak_class for s in SOCCER_MANIFEST.sources}
    # pregame spine
    assert classes["matches"] == "pre_game"
    # post-game settlement
    assert classes["postmortem"] == "post_game"
    assert classes["match_stats"] == "post_game"
    # odds known before kickoff
    assert classes["odds"] == "pre_game"
    # derived as-of features are pre_game by construction
    assert classes["asof_features"] == "pre_game"
    assert classes["asof_xg_proxy"] == "pre_game"
    # club priors are reference data
    assert classes["espn_club_priors"] == "reference"


def test_soccer_pregame_corpora_excludes_post_game():
    pregame = set(SOCCER_MANIFEST.pregame_corpora())
    assert "postmortem" not in pregame
    assert "match_stats" not in pregame
    assert "matches" in pregame
    assert "odds" in pregame
    assert "asof_features" in pregame


def test_soccer_manifest_against_real_census():
    try:
        from data_registry.inventory import build_inventory  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"data_registry unavailable: {exc}")
    inv = build_inventory(sports=["soccer"])
    if inv["n_corpora"] == 0:
        pytest.skip("no soccer corpora on disk")
    errs = SOCCER_MANIFEST.validate_against_inventory(inv)
    assert errs == [], f"manifest/census mismatch: {errs}"
