"""calibrator_sweep.py — robustness check for the per-sport calibrator choice.

W73 surfaced a surprising finding: ISOTONIC (the codebase's default walk-forward
recalibrator) had the WORST OOS log-loss on all 4 real sports at refit_every=25.
Before recommending any (human-gated) change to the default, VERIFY the finding is
robust across reasonable (min_history, refit_every) settings — not an artifact of
one cadence.  This sweeps the grid, loading each sport's (probs, outcomes) ONCE.

CALIBRATION != EDGE.  This measures calibration robustness, never a market edge.

CLI: ``python -m scripts.platformkit.calibrator_sweep [--sport nba] [--json]``
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.calibrator_select import Loader, load_sport_probs, _SPORTS
from scripts.platformkit.calibrator_zoo import select_calibrator
from scripts.platformkit.recalibration import CALIBRATION_NOTE

# (min_history, refit_every) cells — brackets fine vs coarse refit cadence.
_DEFAULT_GRID: List[Tuple[int, int]] = [(100, 10), (100, 50), (200, 25)]


def _rank_of(table: List[Dict], method: str) -> Optional[int]:
    """1-based rank of *method* by OOS log-loss (table is sorted ascending)."""
    for i, row in enumerate(table, 1):
        if row["method"] == method:
            return i
    return None


def sweep_sport(
    sport: str,
    grid: Optional[List[Tuple[int, int]]] = None,
    *,
    loader: Optional[Loader] = None,
) -> Dict:
    """Run select_calibrator across the grid for one sport (load probs ONCE).

    Returns sport, n, cells (one per grid setting with chosen + per-method ranks),
    and a robustness summary: isotonic_always_worst, chosen_methods set.
    """
    load = loader or load_sport_probs
    cells_grid = grid or _DEFAULT_GRID
    try:
        p, y = load(sport)
    except Exception as exc:  # noqa: BLE001
        return {"sport": sport, "error": str(exc), "note": CALIBRATION_NOTE}

    cells: List[Dict] = []
    iso_ranks: List[int] = []
    chosen_methods: List[str] = []
    n_methods = 5
    for min_h, refit in cells_grid:
        if len(p) <= min_h:
            cells.append({"min_history": min_h, "refit_every": refit,
                          "error": f"n={len(p)} <= min_history"})
            continue
        res = select_calibrator(p, y, min_history=min_h, refit_every=refit)
        iso_rank = _rank_of(res["table"], "isotonic")
        cells.append({
            "min_history": min_h, "refit_every": refit,
            "chosen": res["chosen_method"], "n_eval": res["n_eval"],
            "isotonic_rank": iso_rank,
            "identity_rank": _rank_of(res["table"], "identity"),
            "logloss": {r["method"]: round(r["logloss"], 6) for r in res["table"]},
        })
        if iso_rank is not None:
            iso_ranks.append(iso_rank)
        chosen_methods.append(res["chosen_method"])

    return {
        "sport": sport,
        "n": int(len(p)),
        "cells": cells,
        "isotonic_always_worst": bool(iso_ranks) and all(r == n_methods for r in iso_ranks),
        "isotonic_never_chosen": "isotonic" not in chosen_methods,
        "chosen_methods": sorted(set(chosen_methods)),
        "note": CALIBRATION_NOTE,
    }


def sweep_all(
    sports: Optional[List[str]] = None,
    grid: Optional[List[Tuple[int, int]]] = None,
    *,
    loader: Optional[Loader] = None,
) -> Dict[str, Dict]:
    """Sweep every sport; return {sport: sweep_sport(...)}."""
    return {s: sweep_sport(s, grid, loader=loader) for s in (sports or _SPORTS)}


def _print_sport(res: Dict) -> None:
    sport = res.get("sport", "?")
    if "error" in res:
        print(f"\n[{sport}] ERROR: {res['error']}")
        return
    print(f"\n[{sport}] n={res['n']}  isotonic_always_worst={res['isotonic_always_worst']}"
          f"  isotonic_never_chosen={res['isotonic_never_chosen']}"
          f"  chosen={res['chosen_methods']}")
    for c in res["cells"]:
        if "error" in c:
            print(f"  (mh={c['min_history']}, K={c['refit_every']}): {c['error']}")
            continue
        print(f"  (mh={c['min_history']:>3}, K={c['refit_every']:>2}): chosen={c['chosen']:<12}"
              f" isotonic_rank={c['isotonic_rank']}/5  identity_rank={c['identity_rank']}/5")


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    results = sweep_all([sport] if sport else None)
    if "--json" in argv:
        print(json.dumps(results, indent=2, default=str))
        return 0
    print("calibrator_sweep — robustness of the per-sport calibrator choice")
    print(f"NOTE: {CALIBRATION_NOTE}")
    for res in results.values():
        _print_sport(res)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
