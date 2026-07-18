"""Per-file tests for scripts.platformkit.predictive_validity.artifacts --
SYNTHETIC fixtures only (tmp_path).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/predictive_validity/test_artifacts.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.predictive_validity.artifacts import (
    stamp_validation,
    write_predictive_validity_artifact,
)


def _fake_result(**overrides):
    base = {
        "family": "nba_gravity_proxy", "sport": "nba", "metric_name": "gravity_score",
        "baseline_name": "trailing_ts_pct", "verdict": "DESCRIPTIVE_ONLY",
        "mean_rho_metric": 0.12, "mean_rho_baseline": 0.10,
        "rho_metric_bootstrap": {"mean": 0.12, "ci_lo": -0.01, "ci_hi": 0.25, "n_boot_effective": 500},
        "bootstrap_delta_ci": {"mean_delta": 0.02, "ci_lo": -0.03, "ci_hi": 0.07, "n_boot_effective": 500},
        "sign_holds_folds": 2, "n_folds": 3, "per_cutoff": [], "forward_games": 20, "caveat": "",
    }
    base.update(overrides)
    return base


def test_write_artifact_shape(tmp_path):
    out_dir = tmp_path / "predictive_validity"
    path = write_predictive_validity_artifact(_fake_result(), out_dir=str(out_dir))
    doc = json.loads(open(path, encoding="ascii").read())
    assert doc["edge_claimed"] is False
    assert doc["verdict"] == "DESCRIPTIVE_ONLY"
    assert doc["component"] == "predictive_validity__nba_gravity_proxy__gravity_score"
    assert "market close" in doc["honest_note"]


def test_stamp_validation_merges_without_clobbering(tmp_path):
    vdir = tmp_path / "intel_claims"
    vdir.mkdir()
    existing = vdir / "nba_gravity_proxy_validation.json"
    existing.write_text(json.dumps({"n_claims": 5, "n_verified": 5, "details": []}), encoding="ascii")

    stamp_validation("nba_gravity_proxy", "gravity_score", "DESCRIPTIVE_ONLY", 0.12,
                      {"ci_lo": -0.03, "ci_hi": 0.07}, 3, validation_dir=str(vdir))
    doc = json.loads(existing.read_text(encoding="ascii"))
    assert doc["n_claims"] == 5  # pre-existing claims-validator keys untouched
    assert doc["predictive_validity"]["gravity_score"]["verdict"] == "DESCRIPTIVE_ONLY"

    # a second metric stamped later must not clobber the first
    stamp_validation("nba_gravity_proxy", "l10_ts_pct", "UNDERPOWERED", float("nan"),
                      {}, 1, validation_dir=str(vdir))
    doc2 = json.loads(existing.read_text(encoding="ascii"))
    assert doc2["n_claims"] == 5
    assert "gravity_score" in doc2["predictive_validity"]
    assert "l10_ts_pct" in doc2["predictive_validity"]
    assert doc2["predictive_validity"]["l10_ts_pct"]["verdict"] == "UNDERPOWERED"


def test_stamp_validation_creates_file_when_absent(tmp_path):
    vdir = tmp_path / "intel_claims"
    path = stamp_validation("brand_new_family", "some_metric", "UNDERPOWERED", float("nan"),
                             {}, 0, validation_dir=str(vdir))
    doc = json.loads(open(path, encoding="ascii").read())
    assert doc["predictive_validity"]["some_metric"]["verdict"] == "UNDERPOWERED"
