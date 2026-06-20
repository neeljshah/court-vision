"""scripts.platformkit.ingame.ingame_foul_gate_nba_signals -- alternative leak-free
FOUL signals for the NBA foul-trouble gate (companion to ingame_foul_gate_nba.py).

The base gate tested the raw signed foul_diff (away_fouls - home_fouls) and REJECTED it.
This module tests two more THEORY-GROUNDED, narrower foul signals, each still leak-free
(strictly the as-of past) and each gated with the SAME cross-corpus, DM-clustered,
grid-includes-0 (no-op on null) machinery -- so each is an independent honest test:

  bonus_late : foul_diff but ONLY in close & late states (|margin|<=8 AND frac>=0.75),
               zeroed elsewhere -- where free throws from the bonus actually swing a
               game. (Foul state in a blowout or early is noise.)
  foul_x_lead: foul_diff * sign(margin) -- compounding (dis)advantage: a side that is
               BOTH trailing AND in foul trouble is doubly hurt; tests an interaction
               the additive foul_diff cannot capture.

Each signal feeds the existing per-time-bucket Brier-grid corrector (with 0 in the grid)
so a useless signal collapses to a no-op -> REJECT. NO $; CALIBRATION only.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_foul_gate_nba_signals
"""
from __future__ import annotations

import json
import os
from typing import Callable, Dict, List

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.ingame.ingame_foul_gate_nba import (
    FOUL_A,
    FOUL_B,
    LINES_A,
    LINES_B,
    _C_GRID,
    _N_TBUCKET,
    _logit,
    _sigmoid,
    _tbucket,
    decide,
    states_from_foul_pbp,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "foul_gate_nba_signals.json")
_EPS_C = 1e-6

SignalFn = Callable[[List[dict]], np.ndarray]


def sig_bonus_late(states: List[dict]) -> np.ndarray:
    """foul_diff in close (|margin|<=8) & late (frac>=0.75) states; 0 elsewhere."""
    fd = np.array([s["foul_diff"] for s in states], float)
    margin = np.array([s["score_diff"] for s in states], float)
    frac = np.array([s["frac_elapsed"] for s in states], float)
    mask = (np.abs(margin) <= 8.0) & (frac >= 0.75)
    return np.where(mask, fd, 0.0)


def sig_foul_x_lead(states: List[dict]) -> np.ndarray:
    """foul_diff * sign(margin): compounding (dis)advantage interaction."""
    fd = np.array([s["foul_diff"] for s in states], float)
    margin = np.array([s["score_diff"] for s in states], float)
    return fd * np.sign(margin)


SIGNALS: Dict[str, SignalFn] = {
    "bonus_late": sig_bonus_late,
    "foul_x_lead": sig_foul_x_lead,
}


def _fit_c(sig_tr: np.ndarray, m0_tr: np.ndarray, frac_tr: np.ndarray,
           y_tr: np.ndarray) -> Dict[int, float]:
    """Per-time-bucket logit slope on a standardized signal; grid includes 0 (no-op)."""
    spread = float(np.std(sig_tr)) or 1.0
    z = sig_tr / spread
    lg = _logit(m0_tr)
    tb = _tbucket(frac_tr)
    c_by: Dict[int, float] = {}
    for t in range(_N_TBUCKET):
        m = tb == t
        if m.sum() < 50:
            c_by[t] = 0.0
            continue
        best_c, best_b = 0.0, float(np.mean((m0_tr[m] - y_tr[m]) ** 2))
        for c in _C_GRID:
            p = _sigmoid(lg[m] + c * z[m])
            b = float(np.mean((p - y_tr[m]) ** 2))
            if b < best_b:
                best_b, best_c = b, float(c)
        c_by[t] = best_c
    c_by["__spread__"] = spread  # type: ignore[index]
    return c_by


def _apply(sig: np.ndarray, m0: np.ndarray, frac: np.ndarray,
           c_by: Dict[int, float]) -> np.ndarray:
    spread = float(c_by.get("__spread__", 1.0)) or 1.0  # type: ignore[arg-type]
    z = sig / spread
    tb = _tbucket(frac)
    c = np.array([float(c_by.get(int(t), 0.0)) for t in tb], float)
    return _sigmoid(_logit(m0) + c * z)


def cross_direction(train: List[dict], test: List[dict], sig_fn: SignalFn,
                    eps: float = 0.05) -> Dict:
    """Fit M0 + signal corrector on TRAIN; score M0 vs M1 on held-out TEST."""
    surf = fit_weight_surface(train, min_cell=20)
    m0_tr = blended_predictions(train, surf)
    frac_tr = np.array([s["frac_elapsed"] for s in train], float)
    y_tr = np.array([s["outcome"] for s in train], float)
    c_by = _fit_c(sig_fn(train), m0_tr, frac_tr, y_tr)
    m0 = blended_predictions(test, surf)
    frac = np.array([s["frac_elapsed"] for s in test], float)
    m1 = _apply(sig_fn(test), m0, frac, c_by)
    y = np.array([s["outcome"] for s in test], float)
    gids = [s["game_id"] for s in test]
    b0, b1 = float(brier(m0, y)), float(brier(m1, y))
    d = (m0 - y) ** 2 - (m1 - y) ** 2
    dm = diebold_mariano(d, gids)
    nontrivial = any(abs(float(v)) > _EPS_C
                     for k, v in c_by.items() if k != "__spread__")
    beats = bool((b1 < b0) and (dm.p_value < eps) and nontrivial)
    return {
        "n_test_states": len(test), "n_test_games": dm.n_clusters,
        "c_by_bucket": {str(k): round(float(v), 4)
                        for k, v in c_by.items() if k != "__spread__"},
        "brier_m0": round(b0, 4), "brier_m1": round(b1, 4),
        "brier_delta": round(b0 - b1, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "foul_beats_m0": beats, "nontrivial_correction": bool(nontrivial),
    }


def gate_signal(states_a: List[dict], states_b: List[dict],
                sig_fn: SignalFn) -> Dict:
    a_to_b = cross_direction(states_a, states_b, sig_fn)
    b_to_a = cross_direction(states_b, states_a, sig_fn)
    return {"verdict": decide(a_to_b, b_to_a),
            "a_to_b": a_to_b, "b_to_a": b_to_a}


def run() -> Dict:
    a = states_from_foul_pbp(FOUL_A, LINES_A)
    b = states_from_foul_pbp(FOUL_B, LINES_B)
    results = {name: gate_signal(a, b, fn) for name, fn in SIGNALS.items()}
    out = {
        "reference_model": "M0 = PROVEN blend(p0, p_live, w) -- not refit",
        "design": "per-signal cross-corpus A<->B; DM clustered by game_id; c-grid incl 0",
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
        "coverage": {"a_games": len({s['game_id'] for s in a}),
                     "b_games": len({s['game_id'] for s in b})},
        "signals": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="ascii") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    return out


def _report(out: Dict) -> str:
    lines = ["=" * 72,
             "NBA FOUL-SIGNAL VARIANTS vs PROVEN base+prior (cross-corpus, DM-clustered)",
             "=" * 72]
    for name, r in out["signals"].items():
        lines.append(f"SIGNAL {name:12s} VERDICT {r['verdict']}")
        for d, lab in ((r["a_to_b"], "A->B"), (r["b_to_a"], "B->A")):
            lines.append(f"  {lab}: M0 {d['brier_m0']} -> M1 {d['brier_m1']} "
                         f"(delta {d['brier_delta']:+.5f})  DM p {d['dm_p']}  "
                         f"beats={d['foul_beats_m0']}  c={d['c_by_bucket']}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    out = run()
    print(_report(out))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
