"""
prop_validation.py — Registry write + holdout gap validation for prop models.

Public API
----------
    write_registry(results, version)              -> dict  (the written registry)
    validate_gap_threshold(registry, threshold)   -> dict  {stat: bool}
    generate_report(registry, threshold)          -> None  (prints to stdout)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

_MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))) / "data" / "models"

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_DEFAULT_VERSION = "v3_temporal_cv_gridtuned_2026-04"


def write_registry(
    results: Dict[str, dict],
    version: str = _DEFAULT_VERSION,
    registry_path: Path = None,
) -> dict:
    """Write model_registry.json from retrain results dict.

    Args:
        results:       Output of retrain_props_temporal_cv() — keyed by stat name.
        version:       Retrain version string embedded in each registry entry.
        registry_path: Override path (default: data/models/model_registry.json).

    Returns:
        The registry dict written to disk.
    """
    registry_path = registry_path or (_MODEL_DIR / "model_registry.json")

    # Load existing registry to preserve entries for stats not in this results batch
    existing: dict = {}
    if registry_path.exists():
        try:
            existing = json.loads(registry_path.read_text())
        except json.JSONDecodeError:
            pass

    now_iso = datetime.now(timezone.utc).isoformat()

    for stat, metrics in results.items():
        existing[f"props_{stat}"] = {
            "holdout_r2":      metrics.get("holdout_r2"),
            "holdout_mae":     metrics.get("holdout_mae"),
            "holdout_n":       metrics.get("holdout_n"),
            "train_r2":        metrics.get("train_r2"),
            "train_mae":       metrics.get("train_mae"),
            "train_n":         metrics.get("train_n"),
            "needs_retrain":   metrics.get("needs_retrain", False),
            "retrained_at":    now_iso,
            "retrain_version": version,
        }

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(existing, indent=2))
    print(f"  [registry] Written -> {registry_path} ({len(existing)} entries)")
    return existing


def validate_gap_threshold(
    registry: dict,
    threshold: float = 0.08,
) -> Dict[str, bool]:
    """Return {stat: passed} for each stat in registry.

    A stat passes if abs(train_r2 - holdout_r2) <= threshold.
    Missing entries are marked False.
    """
    result = {}
    for stat in _STATS:
        entry = registry.get(f"props_{stat}")
        if entry is None:
            result[stat] = False
            continue
        train_r2   = entry.get("train_r2",   float("nan"))
        holdout_r2 = entry.get("holdout_r2", float("nan"))
        gap = abs(train_r2 - holdout_r2)
        result[stat] = gap <= threshold
    return result


def generate_report(registry: dict, threshold: float = 0.08) -> None:
    """Print a formatted train-holdout gap report to stdout."""
    gate_results = validate_gap_threshold(registry, threshold)
    print(f"\n{'='*60}")
    print(f"  Phase 14.5a — Holdout Gap Report  (threshold={threshold})")
    print(f"{'='*60}")
    print(f"  {'Stat':<6}  {'Train R²':>8}  {'Hold R²':>8}  {'Gap':>6}  {'Status'}")
    print(f"  {'-'*50}")
    all_pass = True
    for stat in _STATS:
        entry = registry.get(f"props_{stat}", {})
        train_r2   = entry.get("train_r2",   float("nan"))
        holdout_r2 = entry.get("holdout_r2", float("nan"))
        gap  = abs(train_r2 - holdout_r2)
        ok   = gate_results.get(stat, False)
        flag = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {stat:<6}  {train_r2:>8.3f}  {holdout_r2:>8.3f}  {gap:>6.3f}  [{flag}]")
    print(f"{'='*60}")
    print(f"  Overall: {'ALL PASS' if all_pass else 'FAILURES DETECTED — retune needed'}")
    print(f"{'='*60}\n")
