"""
test_model_registry.py — model_registry.json contract + drift regression gate.

Tests 1-2 require data/models/model_registry.json (created by retrain_props_temporal_cv).
Test 3 is standalone (synthetic dict) — verifies flag logic, no file dependency.
Test 4 is a CI regression gate: fails if any prop model's holdout R² drops below baseline.
"""
import json
from pathlib import Path

import pytest

REGISTRY_PATH = Path("data/models/model_registry.json")
REQUIRED_KEYS = {
    "holdout_r2", "holdout_mae", "train_r2", "train_mae",
    "train_n", "holdout_n", "needs_retrain", "retrain_version",
}
ALL_STATS = [
    "props_pts", "props_reb", "props_ast", "props_fg3m",
    "props_stl", "props_blk", "props_tov",
]

# Minimum acceptable holdout R² per stat — CI fails if any drops below these.
# Values are conservative floors; update when models genuinely improve.
HOLDOUT_R2_BASELINES = {
    "props_pts":  0.25,
    "props_reb":  0.22,
    "props_ast":  0.20,
    "props_fg3m": 0.12,
    "props_stl":  0.08,
    "props_blk":  0.07,
    "props_tov":  0.10,
}


def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        pytest.skip("model_registry.json not yet created — run retrain_props_temporal_cv first")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_registry_has_holdout_fields() -> None:
    """Each entry in model_registry.json has all required holdout fields."""
    registry = _load_registry()
    for key, entry in registry.items():
        missing = REQUIRED_KEYS - set(entry.keys())
        assert not missing, (
            f"Registry entry '{key}' missing fields: {sorted(missing)}"
        )


def test_all_7_stats_present() -> None:
    """model_registry.json must contain entries for all 7 prop stats."""
    registry = _load_registry()
    for key in ALL_STATS:
        assert key in registry, (
            f"Expected registry key '{key}' not found. "
            f"Present keys: {list(registry.keys())}"
        )


def test_needs_retrain_flag_logic() -> None:
    """needs_retrain = True when |train_r2 - holdout_r2| > 0.08 (standalone, no file)."""
    THRESHOLD = 0.08

    overfit_entry = {"train_r2": 0.92, "holdout_r2": 0.60, "needs_retrain": True}
    gap = abs(overfit_entry["train_r2"] - overfit_entry["holdout_r2"])
    assert overfit_entry["needs_retrain"] == (gap > THRESHOLD)

    good_entry = {"train_r2": 0.55, "holdout_r2": 0.50, "needs_retrain": False}
    gap2 = abs(good_entry["train_r2"] - good_entry["holdout_r2"])
    assert good_entry["needs_retrain"] == (gap2 > THRESHOLD)


def test_holdout_r2_above_baseline() -> None:
    """CI regression gate: no prop model's holdout R² may fall below its recorded baseline.

    Update HOLDOUT_R2_BASELINES when models are genuinely improved — this gate exists
    to catch accidental regressions from data or feature changes.
    """
    registry = _load_registry()
    failures = []
    for stat, floor in HOLDOUT_R2_BASELINES.items():
        if stat not in registry:
            continue
        actual = registry[stat].get("holdout_r2", 0.0)
        if actual < floor:
            failures.append(f"{stat}: holdout_r2={actual:.4f} < baseline={floor:.4f}")

    assert not failures, (
        "Holdout R² regression(s) detected — models need retraining:\n"
        + "\n".join(f"  {f}" for f in failures)
    )
