"""
build_prop_correlation_matrix.py
---------------------------------
Compute a 7x7 Pearson correlation matrix from walk-forward holdout residuals
(predicted - actual) stored in data/models/prop_residuals.json.

No retraining.  Uses existing cached residuals only.

Output schema (data/models/prop_corr_matrix.json):
{
    "stats":       ["pts","reb","ast","fg3m","stl","blk","tov"],
    "corr":        [[... 7x7 floats ...]],
    "std":         [... 7 floats ...],
    "n":           int,          # number of (player, game_date) combos used
    "computed_at": "YYYY-MM-DD HH:MM:SS"
}
Also writes the legacy dict-of-dicts format alongside for back-compat consumers.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESIDUALS_PATH  = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
_CORR_OUT        = os.path.join(PROJECT_DIR, "data", "models", "prop_corr_matrix.json")

_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _load_residuals(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _pivot_residuals(records: list) -> Dict[tuple, Dict[str, float]]:
    """
    Pivot flat residual records into {(player_id, game_date): {stat: residual}}.
    Residual = predicted - actual (signed error, captures direction of correlation).
    """
    rows: Dict[tuple, Dict[str, float]] = defaultdict(dict)
    for r in records:
        stat = r.get("stat")
        pred = r.get("predicted")
        act  = r.get("actual")
        pid  = str(r.get("player_id", r.get("player_name", "")))
        gdate = str(r.get("game_date", ""))
        if stat not in _STATS or pred is None or act is None or not pid:
            continue
        rows[(pid, gdate)][stat] = float(pred) - float(act)
    return rows


def _filter_complete(rows: Dict[tuple, Dict[str, float]]) -> List[Dict[str, float]]:
    """Keep only player-game combos that have all 7 stats present."""
    return [v for v in rows.values() if all(s in v for s in _STATS)]


def compute_and_save(residuals_path: str = _RESIDUALS_PATH,
                     output_path: str = _CORR_OUT) -> dict:
    """
    Load residuals, compute correlation matrix, save, and return result dict.
    """
    print(f"[build_corr] Loading residuals from {residuals_path} ...")
    records = _load_residuals(residuals_path)
    print(f"[build_corr] {len(records)} residual records loaded")

    pivoted = _pivot_residuals(records)
    complete = _filter_complete(pivoted)
    n = len(complete)
    print(f"[build_corr] {n} complete (player, game_date) pairs with all 7 stats")

    if n < 10:
        print("[build_corr] ERROR: fewer than 10 complete rows — aborting")
        sys.exit(1)

    # Build (n, 7) matrix of residuals
    mat = np.array([[row[s] for s in _STATS] for row in complete], dtype=float)

    # 7x7 Pearson correlation matrix
    corr_mat = np.corrcoef(mat, rowvar=False)  # shape (7, 7)

    # Per-stat std dev of residuals (useful for covariance scaling)
    std_vec = np.std(mat, axis=0, ddof=1).tolist()

    # Round for readability
    corr_list = [[round(float(corr_mat[i, j]), 4) for j in range(7)] for i in range(7)]

    result = {
        "stats":        _STATS,
        "corr":         corr_list,
        "std":          [round(float(x), 4) for x in std_vec],
        "n":            n,
        "computed_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"[build_corr] Saved -> {output_path}")

    # Pretty-print the matrix
    _print_matrix(corr_list, std_vec)
    return result


def _print_matrix(corr: list, std: list) -> None:
    hdr = "       " + "  ".join(f"{s:>6s}" for s in _STATS)
    print("\n  Prop Correlation Matrix (residuals-based Pearson r)")
    print("  " + "-" * (len(hdr) - 2))
    print(hdr)
    for i, s in enumerate(_STATS):
        row = "  ".join(f"{corr[i][j]:6.3f}" for j in range(7))
        print(f"  {s:4s}  {row}")
    print()
    print("  Per-stat residual std dev:")
    for s, v in zip(_STATS, std):
        print(f"    {s:4s}: {v:.4f}")


if __name__ == "__main__":
    compute_and_save()
