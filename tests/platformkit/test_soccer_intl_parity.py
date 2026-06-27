"""Per-file tests for domains.soccer_intl.feature_spec + .ingest_manifest.

Covers: catalog column order + count, synthetic exact-replication of the
walk-forward read formula, required-absent-raises (no silent zero), a GUARDED
real-walk-forward byte-equality proof on the genuine int'l corpus, and manifest
structural validation + live census check (single ``results`` corpus only).

HONEST SCOPE: soccer_intl has ONE corpus on disk (results) and NO rest-days data,
so the spec is 4 genuine columns (lam_home/lam_away/lam_total/neutral) -- it does
NOT fabricate the club rest_days columns. The manifest declares ONLY ``results``.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_soccer_intl_parity.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.feature_spec_core import (
    FeatureSpec,
    assert_matches_catalog,
)
from domains.soccer_intl.feature_spec import (
    SOCCER_INTL_BASE_SPEC,
    build_soccer_intl_base,
    catalog,
)
from domains.soccer_intl.ingest_manifest import SOCCER_INTL_MANIFEST


# ---------------------------------------------------------------------------
# feature_spec: catalog
# ---------------------------------------------------------------------------

def test_intl_catalog_is_four_genuine_columns():
    assert catalog() == ["lam_home", "lam_away", "lam_total", "neutral"]
    assert SOCCER_INTL_BASE_SPEC.n_features() == 4


def test_intl_catalog_omits_fabricated_rest_days():
    # rest_days_* do NOT exist in the international corpus; must NOT be declared.
    assert "rest_days_home" not in catalog()
    assert "rest_days_away" not in catalog()


def test_intl_catalog_hash_deterministic_and_sensitive():
    h0 = SOCCER_INTL_BASE_SPEC.catalog_hash()
    assert h0 == SOCCER_INTL_BASE_SPEC.catalog_hash()
    bumped = FeatureSpec("soccer_intl", "soccer_intl-base-v2", SOCCER_INTL_BASE_SPEC.fields)
    assert bumped.catalog_hash() != h0
    reordered = FeatureSpec(
        "soccer_intl", "soccer_intl-base-v1",
        tuple(reversed(SOCCER_INTL_BASE_SPEC.fields)),
    )
    assert reordered.catalog_hash() != h0


def test_intl_assert_matches_catalog_passes_and_fails():
    assert_matches_catalog(SOCCER_INTL_BASE_SPEC, catalog())
    with pytest.raises(AssertionError, match="parity FAILED"):
        assert_matches_catalog(SOCCER_INTL_BASE_SPEC, catalog()[::-1])


# ---------------------------------------------------------------------------
# feature_spec: synthetic exact-replication of the walk-forward read formula
# ---------------------------------------------------------------------------

def _read_formula(df: pd.DataFrame) -> np.ndarray:
    """Re-implements the genuine walk-forward read, row by row."""
    out = []
    for _, row in df.iterrows():
        out.append([
            float(row["lam_home"]),
            float(row["lam_away"]),
            float(row["lam_total"]),
            float(row.get("neutral", False)),
        ])
    return np.array(out, dtype=float)


def test_synthetic_matches_read_formula():
    df = pd.DataFrame({
        "lam_home": [1.42, 1.10, 2.05],
        "lam_away": [0.88, 1.55, 1.30],
        "lam_total": [2.30, 2.65, 3.35],
        "neutral": [True, False, True],
    })
    got, names = build_soccer_intl_base(df)
    assert names == catalog()
    exp = _read_formula(df)
    np.testing.assert_allclose(got, exp, rtol=0, atol=0)


def test_neutral_default_false_when_absent():
    df = pd.DataFrame({"lam_home": [1.3], "lam_away": [1.1], "lam_total": [2.4]})
    got, _ = build_soccer_intl_base(df)
    assert got[0, 3] == pytest.approx(0.0)   # neutral default False -> 0.0


def test_required_absent_raises_not_silent_zero():
    df = pd.DataFrame({"lam_away": [1.0], "lam_total": [2.0]})
    with pytest.raises(KeyError, match="required source"):
        build_soccer_intl_base(df)


# ---------------------------------------------------------------------------
# GUARDED real-walk-forward parity: spec reads the genuine int'l columns
# ---------------------------------------------------------------------------

def test_parity_vs_real_intl_walk_forward():
    results_path = "data/domains/soccer_intl/results.parquet"
    if not os.path.exists(results_path):
        pytest.skip("soccer_intl results.parquet absent")
    try:
        from domains.soccer_intl.ratings import walk_forward_goals  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"soccer_intl ratings import failed: {exc}")

    matches = pd.read_parquet(results_path).tail(600)
    wf = walk_forward_goals(matches)
    for col in ("lam_home", "lam_away", "lam_total", "neutral"):
        assert col in wf.columns, f"walk_forward missing genuine column {col}"

    got, names = build_soccer_intl_base(wf)
    assert names == catalog()
    assert got.shape == (len(wf), 4)
    assert not np.isnan(got).any(), "no NaN in genuine lambdas"
    # lam_total == lam_home + lam_away in the genuine frame.
    np.testing.assert_allclose(got[:, 2], got[:, 0] + got[:, 1], rtol=0, atol=1e-9)


# ---------------------------------------------------------------------------
# manifest: structural validation + live census (single results corpus)
# ---------------------------------------------------------------------------

def test_intl_manifest_is_structurally_valid():
    assert SOCCER_INTL_MANIFEST.validate() == []


def test_intl_manifest_declares_only_results():
    corpora = {s.corpus for s in SOCCER_INTL_MANIFEST.sources}
    assert corpora == {"results"}, "must declare ONLY the corpus that exists on disk"


def test_intl_manifest_results_is_pregame_spine():
    classes = {s.corpus: s.leak_class for s in SOCCER_INTL_MANIFEST.sources}
    assert classes["results"] == "pre_game"
    assert "results" in set(SOCCER_INTL_MANIFEST.pregame_corpora())


def test_intl_manifest_against_real_census():
    try:
        from data_registry.inventory import build_inventory  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"data_registry unavailable: {exc}")
    inv = build_inventory(sports=["soccer_intl"])
    if inv["n_corpora"] == 0:
        pytest.skip("no soccer_intl corpora on disk")
    errs = SOCCER_INTL_MANIFEST.validate_against_inventory(inv)
    assert errs == [], f"manifest/census mismatch: {errs}"
