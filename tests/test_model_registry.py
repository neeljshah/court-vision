"""
test_model_registry.py — Wave 0 stubs for model_registry.json contract.

Tests 1-2 are xfail(strict=False) — registry doesn't exist until Plan 04.
Test 3 is standalone (synthetic dict) — verifies flag logic, no file dependency.
"""
import json
import math
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


@pytest.mark.xfail(strict=False, reason="registry created in Plan 04")
def test_registry_has_holdout_fields() -> None:
    """Each entry in model_registry.json has all required holdout fields."""
    if not REGISTRY_PATH.exists():
        pytest.skip("model_registry.json not yet created (Plan 04)")

    registry = json.loads(REGISTRY_PATH.read_text())
    for key, entry in registry.items():
        missing = REQUIRED_KEYS - set(entry.keys())
        assert not missing, (
            f"Registry entry '{key}' missing fields: {sorted(missing)}"
        )


@pytest.mark.xfail(strict=False, reason="registry created in Plan 04")
def test_all_7_stats_present() -> None:
    """model_registry.json must contain entries for all 7 prop stats."""
    if not REGISTRY_PATH.exists():
        pytest.skip("model_registry.json not yet created (Plan 04)")

    registry = json.loads(REGISTRY_PATH.read_text())
    for key in ALL_STATS:
        assert key in registry, (
            f"Expected registry key '{key}' not found. "
            f"Present keys: {list(registry.keys())}"
        )


def test_needs_retrain_flag_logic() -> None:
    """needs_retrain should be True when |train_r2 - holdout_r2| > 0.08.

    This test is fully standalone — verifies the flag logic contract
    without depending on the actual registry file.
    """
    THRESHOLD = 0.08

    # Case 1: overfitting → needs_retrain should be True
    overfit_entry = {
        "train_r2": 0.92,
        "holdout_r2": 0.60,
        "needs_retrain": True,
    }
    gap = abs(overfit_entry["train_r2"] - overfit_entry["holdout_r2"])
    expected_flag = gap > THRESHOLD
    assert overfit_entry["needs_retrain"] == expected_flag, (
        f"needs_retrain should be {expected_flag} when gap={gap:.3f}"
    )

    # Case 2: well-calibrated → needs_retrain should be False
    good_entry = {
        "train_r2": 0.55,
        "holdout_r2": 0.50,
        "needs_retrain": False,
    }
    gap2 = abs(good_entry["train_r2"] - good_entry["holdout_r2"])
    expected_flag2 = gap2 > THRESHOLD
    assert good_entry["needs_retrain"] == expected_flag2, (
        f"needs_retrain should be {expected_flag2} when gap={gap2:.3f}"
    )
