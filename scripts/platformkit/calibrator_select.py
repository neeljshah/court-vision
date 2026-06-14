"""calibrator_select.py — run the calibrator-zoo on REAL per-sport (probs, outcomes).

Wires ``calibrator_zoo.select_calibrator`` to the live adapter seam used by
``recalibration.measure_sport_recal``: load a sport's FeatureBundle, take its raw
model probability column (``signal_col``) + binary ``target``, and pick the
best leak-free walk-forward calibrator by OUT-OF-SAMPLE log-loss.

The heavy adapter/pandas import happens lazily INSIDE ``load_sport_probs`` so this
module stays import-light and pytest-clean; tests inject a synthetic ``loader``.

CALIBRATION != EDGE.  A near-calibrated model (the honest expected case) yields a
tiny OOS gain or selects identity — that is a SUCCESS, not a failure.  No market
edge is claimed.  Durable home: kernel/calibration/ (HUMAN-GATED) — this is the
platformkit prototype.

CLI: ``python -m scripts.platformkit.calibrator_select [--sport nba] [--json]``
"""
from __future__ import annotations

import json
import sys
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.calibrator_zoo import select_calibrator
from scripts.platformkit.recalibration import CALIBRATION_NOTE

_SPORTS: List[str] = ["nba", "mlb", "soccer", "tennis"]

Loader = Callable[[str], Tuple[np.ndarray, np.ndarray]]


def load_sport_probs(sport: str) -> Tuple[np.ndarray, np.ndarray]:
    """Load a sport's raw model probs + binary outcomes via the adapter seam.

    Mirrors ``recalibration.measure_sport_recal``: importlib the adapter, call
    ``feature_bundle(hypothesis=None, seasons=[])``, return finite (probs, target).
    Heavy (pandas/adapter) — imported here, never at module top.
    """
    import importlib  # noqa: PLC0415

    from scripts.platformkit.recalibration import _ADAPTER_REGISTRY  # noqa: PLC0415

    if sport not in _ADAPTER_REGISTRY:
        raise KeyError(f"Unknown sport '{sport}'. Valid: {list(_ADAPTER_REGISTRY)}")
    module_path, class_name = _ADAPTER_REGISTRY[sport]
    mod = importlib.import_module(module_path)
    adapter = getattr(mod, class_name)()
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[])
    p = np.asarray(bundle.signal_col, dtype=float)
    y = np.asarray(bundle.target, dtype=float)
    valid = np.isfinite(p) & np.isfinite(y)
    return p[valid], y[valid]


def select_for_sport(
    sport: str,
    *,
    min_history: int = 100,
    refit_every: int = 25,
    loader: Optional[Loader] = None,
) -> Dict:
    """Pick the best leak-free WF calibrator for one sport on REAL data.

    ``loader`` defaults to the live adapter loader; tests inject a synthetic one.
    Returns sport, n, chosen_method, table, n_eval, note (or error on load fail).
    """
    load = loader or load_sport_probs
    try:
        p, y = load(sport)
    except Exception as exc:  # noqa: BLE001 - report load failures honestly
        return {"sport": sport, "error": str(exc), "note": CALIBRATION_NOTE}
    if len(p) <= min_history:
        return {"sport": sport, "n": int(len(p)),
                "error": f"too few events ({len(p)} <= min_history {min_history})",
                "note": CALIBRATION_NOTE}
    res = select_calibrator(p, y, min_history=min_history, refit_every=refit_every)
    return {
        "sport": sport,
        "n": int(len(p)),
        "n_eval": res["n_eval"],
        "chosen_method": res["chosen_method"],
        "table": res["table"],
        "note": res["note"],
    }


def select_all_sports(
    sports: Optional[List[str]] = None,
    *,
    min_history: int = 100,
    refit_every: int = 25,
    loader: Optional[Loader] = None,
) -> Dict[str, Dict]:
    """Run ``select_for_sport`` over each sport; return {sport: result}."""
    return {s: select_for_sport(s, min_history=min_history,
                                refit_every=refit_every, loader=loader)
            for s in (sports or _SPORTS)}


def _print_result(res: Dict) -> None:
    sport = res.get("sport", "?")
    if "error" in res:
        print(f"\n[{sport}] ERROR: {res['error']}")
        return
    print(f"\n[{sport}] n={res['n']} n_eval={res['n_eval']} "
          f"-> CHOSEN: {res['chosen_method']}")
    print(f"  {'method':<12}{'logloss':>10}{'brier':>9}{'ece':>9}")
    for row in res["table"]:
        mark = "  <- chosen" if row["method"] == res["chosen_method"] else ""
        print(f"  {row['method']:<12}{row['logloss']:>10.5f}"
              f"{row['brier']:>9.5f}{row['ece']:>9.5f}{mark}")


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    results = select_all_sports([sport] if sport else None)
    if "--json" in argv:
        print(json.dumps(results, indent=2, default=str))
        return 0
    print("calibrator_select — real per-sport leak-free OOS calibrator choice")
    print(f"NOTE: {CALIBRATION_NOTE}")
    for res in results.values():
        _print_result(res)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
