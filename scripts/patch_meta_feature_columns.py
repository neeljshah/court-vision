"""patch_meta_feature_columns.py — one-shot patch for both _meta.json files.

Writes feature_columns + n_features under each stat in:
  1. data/models/oos_pre_playoffs/_meta.json  (109-col current schema)
  2. data/models/_backup_wave2b_20260527T120342Z/_meta.json  (85-col pre-Wave-2b schema)

Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (
    feature_columns,
    _BBREF_EXTRA_KEYS,
    _DMATCH_KEYS,
    _PROF_KEYS,
    STATS,
)


def _current_cols(stat: str) -> list:
    """109-col list for the given stat (current Wave-2b schema)."""
    return feature_columns(stat)


def _pre_wave2b_cols(stat: str) -> list:
    """85-col list — current minus the 24 Wave-2b additions."""
    full = feature_columns(stat)
    extra = set(f"bbref_{k}" for k in _BBREF_EXTRA_KEYS) | set(_DMATCH_KEYS) | set(_PROF_KEYS)
    return [c for c in full if c not in extra]


def patch_meta(meta_path: str, col_fn,
               n_features_override: dict | None = None) -> None:
    """Patch feature_columns into each stat entry of a _meta.json file.

    n_features_override: {stat: n} — when the actual artifact n_features_in_
    differs from col_fn(stat) (e.g. reb was trained on 109 global cols despite
    feature_columns('reb') returning 112 with reb-context), pass the override
    so the frozen list is truncated to match the real artifact shape.
    """
    if not os.path.exists(meta_path):
        print(f"  SKIP (not found): {meta_path}")
        return
    with open(meta_path, encoding="utf-8") as fh:
        all_meta: dict = json.load(fh)
    all_meta.setdefault("stats", {})
    n_overrides = n_features_override or {}
    for stat in all_meta["stats"]:
        cols = col_fn(stat)
        target_n = n_overrides.get(stat, len(cols))
        if len(cols) != target_n:
            # Truncate to the global (non-stat-specific) list by stripping
            # any per-stat extras that pushed cols beyond target_n.
            cols = cols[:target_n]
        all_meta["stats"][stat]["feature_columns"] = cols
        all_meta["stats"][stat]["n_features"] = len(cols)
        print(f"  {os.path.basename(meta_path)} [{stat}] n_features={len(cols)}")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"  written: {meta_path}")


if __name__ == "__main__":
    oos_dir = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
    backup_dir = os.path.join(PROJECT_DIR, "data", "models",
                              "_backup_wave2b_20260527T120342Z")

    print("Patching oos_pre_playoffs/_meta.json (109-col schema):")
    # reb LGB-q50 artifact was trained on 109 global cols (not 112 with reb-context).
    patch_meta(os.path.join(oos_dir, "_meta.json"), _current_cols,
               n_features_override={"reb": 109})

    print("\nPatching _backup_wave2b/_meta.json (85-col pre-Wave-2b schema):")
    patch_meta(os.path.join(backup_dir, "_meta.json"), _pre_wave2b_cols)

    print("\nDone.")
