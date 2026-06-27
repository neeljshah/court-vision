"""Per-file tests for the Tennis feature_spec (diff op) + ingest_manifest.

Covers the OP_DIFF extraction, a SYNTHETIC exact-replication of the tennis base
formula, a GUARDED real-adapter parity proof (bundle.base byte-equal), and the
tennis manifest validated against the live census.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_feature_spec_tennis.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.feature_spec_core import (
    OP_DIFF,
    FeatureField,
    FeatureSpec,
    build_base_matrix,
)
from domains.tennis.feature_spec import TENNIS_BASE_SPEC, build_tennis_base, catalog
from domains.tennis.ingest_manifest import TENNIS_MANIFEST


# --------------------------------------------------------------------------- #
# diff op
# --------------------------------------------------------------------------- #
def test_diff_op_requires_source2():
    with pytest.raises(ValueError, match="op=diff requires source2"):
        FeatureField("d", "a", op=OP_DIFF)


def test_diff_op_computes_difference_with_defaults():
    spec = FeatureSpec("s", "v1", (
        FeatureField("d", "a", default=1500.0, source2="b", op=OP_DIFF),
    ))
    # both present
    m, _ = build_base_matrix(spec, pd.DataFrame({"a": [1600.0, 1400.0], "b": [1500.0, 1500.0]}))
    assert list(m[:, 0]) == [100.0, -100.0]
    # operand column absent -> default fills that operand (1500 - 1500 = 0)
    m2, _ = build_base_matrix(spec, pd.DataFrame({"a": [1600.0]}))
    assert m2[0, 0] == pytest.approx(100.0)  # 1600 - 1500(default)


def test_tennis_catalog_is_the_five_base_columns():
    assert catalog() == ["elo_diff", "surface_elo_diff", "best_of",
                         "rest_days_a", "rest_days_b"]
    assert TENNIS_BASE_SPEC.n_features() == 5


# --------------------------------------------------------------------------- #
# synthetic exact-replication of the harness base formula
# --------------------------------------------------------------------------- #
def _harness_formula(df: pd.DataFrame) -> np.ndarray:
    out = []
    for _, row in df.iterrows():
        out.append([
            float(row.get("p1_elo", 1500.0)) - float(row.get("p2_elo", 1500.0)),
            float(row.get("p1_surface_elo", 1500.0)) - float(row.get("p2_surface_elo", 1500.0)),
            float(row.get("best_of", 3.0)),
            float(row.get("rest_days_a", 15.0)),
            float(row.get("rest_days_b", 15.0)),
        ])
    return np.array(out, dtype=float)


def test_synthetic_matches_harness_formula():
    df = pd.DataFrame({
        "p1_elo": [1550.0, 1480.0], "p2_elo": [1490.0, 1520.0],
        "p1_surface_elo": [1540.0, 1470.0], "p2_surface_elo": [1485.0, 1515.0],
        "best_of": [3.0, 5.0], "rest_days_a": [2.0, 7.0], "rest_days_b": [5.0, 1.0],
    })
    got, names = build_tennis_base(df)
    assert names == catalog()
    np.testing.assert_allclose(got, _harness_formula(df), rtol=0, atol=0)


# --------------------------------------------------------------------------- #
# GUARDED real-adapter parity: spec reproduces bundle.base byte-for-byte
# --------------------------------------------------------------------------- #
def test_parity_vs_real_tennis_adapter():
    if not os.path.exists("data/domains/tennis/matches.parquet"):
        pytest.skip("tennis matches.parquet absent")
    try:
        from domains.tennis.adapter import TennisAdapter  # noqa: PLC0415
        from domains.tennis.adapter_helpers import _add_rest_days  # noqa: PLC0415
        from domains.tennis.elo import walk_forward_elo  # noqa: PLC0415
        from scripts.platformkit.proof_tennis.gate_test_asof import (  # noqa: PLC0415
            _build_base_bundle_with_ids,
        )
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"tennis adapter import failed: {exc}")

    season = 2024
    bundle, _ids = _build_base_bundle_with_ids(seasons=[season])

    adapter = TennisAdapter()
    matches = adapter._get_matches()
    if "season" in matches.columns:
        matches = matches[matches["season"].isin([season])]
    else:
        matches = matches[pd.to_datetime(matches["date"]).dt.year.isin([season])]
    if len(matches) < 20:
        pytest.skip("season slice too small")
    wf = _add_rest_days(walk_forward_elo(matches))
    kept = wf[wf["winner"].notna()]  # harness skips winner-NaN, preserving order

    got, names = build_tennis_base(kept)
    assert names == catalog()
    assert got.shape == bundle.base.shape, (got.shape, bundle.base.shape)
    np.testing.assert_allclose(got, bundle.base, rtol=0, atol=1e-9)


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
def test_tennis_manifest_valid_and_leak_classes():
    assert TENNIS_MANIFEST.validate() == []
    # match_stats must be post_game (the as-of features derive from it but are pre_game)
    classes = {s.corpus: s.leak_class for s in TENNIS_MANIFEST.sources}
    assert classes["match_stats"] == "post_game"
    assert classes["asof_return"] == "pre_game"
    assert "match_stats" not in TENNIS_MANIFEST.pregame_corpora()
    assert "asof_return" in TENNIS_MANIFEST.pregame_corpora()


def test_tennis_manifest_against_real_census():
    try:
        from data_registry.inventory import build_inventory  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"data_registry unavailable: {exc}")
    inv = build_inventory(sports=["tennis"])
    if inv["n_corpora"] == 0:
        pytest.skip("no tennis corpora on disk")
    errs = TENNIS_MANIFEST.validate_against_inventory(inv)
    assert errs == [], f"manifest/census mismatch: {errs}"
