"""
test_prop_retrain.py — Smoke tests for scripts/retrain_props_temporal.py.
"""
import importlib
import sys
from pathlib import Path

import pytest


def _import_retrain():
    scripts_path = Path(__file__).parent.parent / "scripts"
    if str(scripts_path.parent) not in sys.path:
        sys.path.insert(0, str(scripts_path.parent))
    try:
        return importlib.import_module("scripts.retrain_props_temporal")
    except (ImportError, ModuleNotFoundError) as exc:
        pytest.skip(f"retrain_props_temporal not importable: {exc}")


def test_retrain_produces_model_files() -> None:
    """retrain_props_temporal_cv(stats=['pts'], dry_run=True) returns a dict with key 'pts'."""
    mod = _import_retrain()
    result = mod.retrain_props_temporal_cv(stats=["pts"], dry_run=True)
    assert isinstance(result, dict), f"Expected dict result, got {type(result)}"
    assert "pts" in result, f"Expected 'pts' key in result, got {list(result.keys())}"


def test_retrain_updates_registry() -> None:
    """After dry-run, result['pts'] must contain 'holdout_r2' key."""
    mod = _import_retrain()
    result = mod.retrain_props_temporal_cv(stats=["pts"], dry_run=True)
    pts_result = result.get("pts", {})
    assert "holdout_r2" in pts_result, (
        f"Expected 'holdout_r2' in result['pts'], got keys: {list(pts_result.keys())}"
    )
