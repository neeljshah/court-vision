"""
test_prop_retrain.py — Wave 0 stubs for end-to-end retrain smoke test.

All tests are xfail(strict=False) — scripts/retrain_props_temporal.py
is created in Plan 04/05 and does not exist yet.
"""
import importlib
import sys
from pathlib import Path

import pytest


@pytest.mark.xfail(strict=False, reason="impl pending Plan 04/05")
def test_retrain_produces_model_files() -> None:
    """retrain_props_temporal_cv(stats=['pts'], dry_run=True) returns a dict
    with key 'pts' and raises no exception."""
    try:
        # scripts/ is not a package — add project root to path if needed
        scripts_path = Path(__file__).parent.parent / "scripts"
        if str(scripts_path.parent) not in sys.path:
            sys.path.insert(0, str(scripts_path.parent))

        retrain_mod = importlib.import_module("scripts.retrain_props_temporal")
        retrain_fn = retrain_mod.retrain_props_temporal_cv
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
        pytest.xfail(f"Module not yet created: {exc}")

    result = retrain_fn(stats=["pts"], dry_run=True)
    assert isinstance(result, dict), f"Expected dict result, got {type(result)}"
    assert "pts" in result, f"Expected 'pts' key in result, got {list(result.keys())}"


@pytest.mark.xfail(strict=False, reason="impl pending Plan 04/05")
def test_retrain_updates_registry() -> None:
    """After dry-run, result['pts'] must contain 'holdout_r2' key."""
    try:
        scripts_path = Path(__file__).parent.parent / "scripts"
        if str(scripts_path.parent) not in sys.path:
            sys.path.insert(0, str(scripts_path.parent))

        retrain_mod = importlib.import_module("scripts.retrain_props_temporal")
        retrain_fn = retrain_mod.retrain_props_temporal_cv
    except (ImportError, ModuleNotFoundError, AttributeError) as exc:
        pytest.xfail(f"Module not yet created: {exc}")

    result = retrain_fn(stats=["pts"], dry_run=True)
    pts_result = result.get("pts", {})
    assert "holdout_r2" in pts_result, (
        f"Expected 'holdout_r2' in result['pts'], got keys: {list(pts_result.keys())}"
    )
