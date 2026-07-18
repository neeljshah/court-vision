"""scripts.platformkit.pod_sprint.extreme_state_sweep -- dense synthetic
extreme-state grid over winprob_dispatch.dispatch, never a $/ROI/edge claim.

Sweeps a per-sport grid of game states (NBA elapsed x lead, MLB inning/half x
run_diff, tennis set/game states, soccer minute x lead), calls the SANCTIONED
resolver (scripts.platformkit.answers.winprob_dispatch.dispatch, one subprocess
per state -- never predict_matchup imported directly) for each, and records:
  - status counts (ok / no_data / nan_or_out_of_range -- this one MUST be 0)
  - monotonicity violations: within a fixed (sport, time-axis) slice, p must be
    non-decreasing in home advantage within MONO_TOL
  - boundary violations: terminal-time states with a decisive lead must land
    within BOUNDARY_TOL of 0/1

Writes data/cache/calibration_grid/extreme_state_report.json.

CLI: python -m scripts.platformkit.pod_sprint.extreme_state_sweep --max-calls 400
Tests: covered indirectly by test_winprob_extreme_states.py's check_envelope/
check_monotone helpers; this module's own --max-calls 3 dry run is the
self-check (see __main__ block).
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.answers.winprob_dispatch import dispatch

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "cache" / "calibration_grid" / "extreme_state_report.json"

MONO_TOL = 0.02
BOUNDARY_TOL = 0.05

# (elapsed_minutes, lead) x sport=nba
_NBA_ELAPSED = [0, 6, 12, 18, 24, 30, 36, 42, 48, 50, 53, 58]
_NBA_LEADS = list(range(-30, 31, 5))
# (inning, half, run_diff) x sport=mlb
_MLB_INNINGS = list(range(1, 13))
_MLB_HALVES = ["top", "bottom"]
_MLB_DIFFS = list(range(-9, 10, 3))
# soccer: minute x lead
_SOCCER_MINUTES = list(range(0, 96, 10))
_SOCCER_LEADS = list(range(-3, 4))
# tennis: best-of-3 set/game states (sets_home, sets_away)
_TENNIS_STATES = [(0, 0), (1, 0), (0, 1), (1, 1)]


def _nba_states() -> List[Dict[str, Any]]:
    return [{"elapsed": float(e), "home_score": 60 + max(l, 0), "away_score": 60 + max(-l, 0),
             "_axis": e, "_lead": l}
            for e in _NBA_ELAPSED for l in _NBA_LEADS]


def _mlb_states() -> List[Dict[str, Any]]:
    return [{"inning": i, "half": h, "home_score": 3 + max(d, 0), "away_score": 3 + max(-d, 0),
             "_axis": (i, h), "_lead": d}
            for i in _MLB_INNINGS for h in _MLB_HALVES for d in _MLB_DIFFS]


def _soccer_states() -> List[Dict[str, Any]]:
    return [{"elapsed": float(m), "home_score": 1 + max(l, 0), "away_score": 1 + max(-l, 0),
             "_axis": m, "_lead": l}
            for m in _SOCCER_MINUTES for l in _SOCCER_LEADS]


def _tennis_states() -> List[Dict[str, Any]]:
    return [{"sets_home": sh, "sets_away": sa, "_axis": "sets", "_lead": sh - sa}
            for sh, sa in _TENNIS_STATES]


_SPORT_STATES = {"nba": _nba_states, "mlb": _mlb_states,
                 "soccer": _soccer_states, "tennis": _tennis_states}
_SPORT_TEAMS = {"nba": ("BOS", "LAL"), "mlb": ("NYY", "BOS"),
                "soccer": ("Arsenal", "Chelsea"), "tennis": ("Player A", "Player B")}


def _is_terminal(sport: str, state: Dict[str, Any]) -> bool:
    if sport == "nba":
        return state["elapsed"] >= 47.5
    if sport == "mlb":
        return state["inning"] >= 9 and state["half"] == "bottom"
    if sport == "soccer":
        return state["elapsed"] >= 90
    return False


def run_sweep(sport_filter: Optional[str], max_calls: int) -> Dict[str, Any]:
    sports = [sport_filter] if sport_filter else list(_SPORT_STATES)
    n_ok = n_no_data = n_bad = 0
    n_states = 0
    mono_violations: List[Dict[str, Any]] = []
    boundary_violations: List[Dict[str, Any]] = []
    slices: Dict[Tuple[str, Any], List[Tuple[int, float]]] = {}

    for sport in sports:
        home, away = _SPORT_TEAMS[sport]
        for state in _SPORT_STATES[sport]():
            if n_states >= max_calls:
                break
            n_states += 1
            axis, lead = state.pop("_axis"), state.pop("_lead")
            t0 = time.monotonic()
            env = dispatch(sport, home, away, state)
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            status = env.get("status")
            p = env.get("p_home_win")
            if status == "ok":
                if p is None or (isinstance(p, float) and math.isnan(p)) or not (0.0 <= float(p) <= 1.0):
                    n_bad += 1
                    boundary_violations.append({"sport": sport, "state": state,
                                                "envelope": env, "reason": "nan_or_out_of_range"})
                else:
                    n_ok += 1
                    slices.setdefault((sport, axis), []).append((lead, float(p)))
                    if _is_terminal(sport, state):
                        want_high = lead > 0
                        want_low = lead < 0
                        near_one = float(p) >= 1.0 - BOUNDARY_TOL
                        near_zero = float(p) <= BOUNDARY_TOL
                        if (want_high and not near_one) or (want_low and not near_zero):
                            boundary_violations.append({"sport": sport, "state": state,
                                                        "p_home_win": p, "reason": "terminal state not near 0/1"})
            elif status == "no_data":
                n_no_data += 1
            else:
                n_bad += 1
        if n_states >= max_calls:
            break

    for (sport, axis), rows in slices.items():
        rows.sort(key=lambda r: r[0])
        for (lead_prev, p_prev), (lead_next, p_next) in zip(rows, rows[1:]):
            if p_next < p_prev - MONO_TOL:
                mono_violations.append({"sport": sport, "fixed_axis": str(axis),
                                        "states": [lead_prev, lead_next], "ps": [p_prev, p_next]})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "edge_claimed": False,
        "honest_note": (
            "Crash-safety + calibration-shape sweep only, never a $/ROI/edge claim. "
            "Each state is one winprob_dispatch.dispatch(...) subprocess call over "
            "predict_matchup.py. n_nan_or_out_of_range MUST be 0 -- any nonzero value "
            "is a real fail-closed violation, not a threshold to relax. Monotonicity "
            "checked within a fixed (sport, time-axis) slice, non-decreasing in home "
            "lead within tolerance %.2f; boundary checked only at terminal-time states "
            "with a decisive lead, within tolerance %.2f of 0/1." % (MONO_TOL, BOUNDARY_TOL)),
        "n_states": n_states, "n_ok": n_ok, "n_no_data": n_no_data,
        "n_nan_or_out_of_range": n_bad,
        "monotonicity_violations": mono_violations,
        "boundary_violations": boundary_violations,
    }


def write_report(sport_filter: Optional[str], max_calls: int,
                 out_path: Optional[Path] = None) -> Dict[str, Any]:
    doc = run_sweep(sport_filter, max_calls)
    out = out_path or DEFAULT_OUT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    return doc


def _print_summary(doc: Dict[str, Any]) -> None:
    print("EXTREME-STATE SWEEP SUMMARY")
    print("-" * 60)
    print("%-24s %10s" % ("n_states", doc["n_states"]))
    print("%-24s %10s" % ("n_ok", doc["n_ok"]))
    print("%-24s %10s" % ("n_no_data", doc["n_no_data"]))
    print("%-24s %10s" % ("n_nan_or_out_of_range", doc["n_nan_or_out_of_range"]))
    print("%-24s %10s" % ("monotonicity_violations", len(doc["monotonicity_violations"])))
    print("%-24s %10s" % ("boundary_violations", len(doc["boundary_violations"])))
    print("-" * 60)
    print(doc["honest_note"])


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extreme-state synthetic sweep over winprob_dispatch")
    ap.add_argument("--max-calls", type=int, default=400, dest="max_calls")
    ap.add_argument("--sport", choices=list(_SPORT_STATES), default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    doc = write_report(a.sport, a.max_calls, a.out)
    _print_summary(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
