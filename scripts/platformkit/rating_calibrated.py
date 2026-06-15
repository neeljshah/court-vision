"""rating_calibrated.py — the model_ops stack composed end-to-end (C14 capstone).

Chains the platformkit model + calibration prototypes on REAL per-sport data:

    GenericRatingModel (W76, logistic Elo)  ->  select_calibrator (W73, best leak-free
    walk-forward calibrator by OOS log-loss)  ->  OOS scorecard vs the adapter baseline.

This demonstrates the pieces COMPOSE: a single generic Elo, then the best calibrator,
yields a well-calibrated forecast that is competitive with each sport's hand-tuned
baseline.  Each stage's gain is measured (Brier / log-loss / ECE), all leak-free.

ACCURACY / CALIBRATION != EDGE.  Beating a baseline on calibration metrics is not a
market edge; neither beats the close.  Durable home: kernel/ (model_ops + calibration),
HUMAN-GATED.  This is the platformkit prototype.

CLI: ``python -m scripts.platformkit.rating_calibrated [--sport nba] [--json]``
"""
from __future__ import annotations

import json
import sys
from typing import Dict, List, Optional

import numpy as np

from scripts.platformkit.generic_rating import (
    _SPORT_HFA, GenericRatingModel, Loader, _brier, _default_loader, _ece, _logloss,
)
from scripts.platformkit.calibrator_zoo import select_calibrator

_NOTE = ("model -> calibrate stack on real data; ACCURACY/CALIBRATION != EDGE. "
         "A baseline match on calibration metrics is not a market edge.")


def _score(p: np.ndarray, y: np.ndarray) -> Dict[str, float]:
    return {"brier": round(_brier(p, y), 5), "logloss": round(_logloss(p, y), 5),
            "ece": round(_ece(p, y), 5)}


def run_sport(sport: str, *, min_history: int = 200, refit_every: int = 25,
              loader: Optional[Loader] = None,
              model: Optional[GenericRatingModel] = None) -> Dict:
    """Compose generic Elo -> best calibrator; OOS-score raw/calibrated/baseline."""
    load = loader or _default_loader
    mdl = model or GenericRatingModel(hfa=_SPORT_HFA.get(sport, 65.0))
    try:
        games, base_p, base_y = load(sport)
    except Exception as exc:  # noqa: BLE001
        return {"sport": sport, "error": str(exc), "note": _NOTE}
    if len(games) <= min_history:
        return {"sport": sport, "error": f"too few games ({len(games)})", "note": _NOTE}

    elo = mdl.walkforward(games)
    y = np.array([g["home_win"] for g in games], dtype=float)
    # Calibrators with a classifier path (Platt/LR) reject soft labels with
    # "Unknown label type: continuous" (soccer draws are encoded 0.5 by
    # generic_rating.py). Binarize for fitting; keep soft y for Brier/ECE below.
    y_cls = (y > 0.5).astype(float)
    sel = select_calibrator(elo, y_cls, min_history=min_history, refit_every=refit_every)
    cal = sel["chosen_probs"]
    sl = slice(min_history, None)

    raw_s = _score(elo[sl], y[sl])
    cal_s = _score(cal[sl], y[sl])
    out: Dict = {
        "sport": sport, "n_games": len(games), "n_eval": int(len(y) - min_history),
        "chosen_calibrator": sel["chosen_method"],
        "raw_elo": raw_s, "calibrated_elo": cal_s,
        "calib_improves_ece": bool(cal_s["ece"] <= raw_s["ece"]),
        "calib_improves_logloss": bool(cal_s["logloss"] <= raw_s["logloss"]),
        "note": _NOTE,
    }
    if base_p is not None and base_y is not None and len(base_p) > min_history:
        bsl = slice(min_history, None)
        bs = _score(base_p[bsl], base_y[bsl])
        out["baseline"] = bs
        out["calibrated_beats_baseline_brier"] = bool(cal_s["brier"] <= bs["brier"])
    return out


def _print(res: Dict) -> None:
    s = res.get("sport", "?")
    if "error" in res:
        print(f"\n[{s}] ERROR: {res['error']}")
        return
    print(f"\n[{s}] n={res['n_games']} n_eval={res['n_eval']} "
          f"chosen_calibrator={res['chosen_calibrator']}")
    for tag in ("raw_elo", "calibrated_elo", "baseline"):
        if tag in res:
            m = res[tag]
            print(f"  {tag:<15} brier={m['brier']} logloss={m['logloss']} ece={m['ece']}")
    print(f"  calibration improves ECE={res['calib_improves_ece']} "
          f"logloss={res['calib_improves_logloss']}"
          + (f" | calib beats baseline brier={res['calibrated_beats_baseline_brier']}"
             if "baseline" in res else ""))


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0
    sport = None
    if "--sport" in argv:
        i = argv.index("--sport")
        sport = argv[i + 1] if i + 1 < len(argv) else None
    sports = [sport] if sport else ["nba", "mlb"]
    results = {s: run_sport(s) for s in sports}
    if "--json" in argv:
        print(json.dumps(results, indent=2))
        return 0
    print(f"rating_calibrated — generic Elo -> best calibrator -> OOS scorecard\nNOTE: {_NOTE}")
    for res in results.values():
        _print(res)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
