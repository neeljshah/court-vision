"""scripts.platformkit.ingame.ingame_foul_gate_nba -- does an NBA FOUL-TROUBLE detail
layer beat the PROVEN (margin, time, p0) base+prior on held-out Brier, cross-corpus?

The proven in-game model (ingame_finegrain_nba) is M0 = blend(p0_elo, p_live(margin,
frac), w(time,margin)) -- REPLICATED cross-corpus. This gate asks the next-detail
question: given the leak-free as-of FOUL STATE (cumulative fouls per side + signed
foul_diff = away_fouls - home_fouls), does a foul correction LAYER on top of the proven
M0 add OOS calibration?

  M0 (reference) = the proven base+prior blended prediction (NEVER refit here).
  M1 (candidate) = sigmoid( logit(M0) + c(frac) * z(foul_diff) )
        c(frac) is fit per ELAPSED-time bucket on TRAIN only by Brier 1-D grid search
        (the grid includes 0, so a foul signal that carries nothing collapses to c=0 ->
        M1 == M0 -> honest REJECT). z = foul_diff standardized by TRAIN spread (scale-
        free). The sign of c is DATA-DECIDED per bucket, never hardcoded.

DISCIPLINE (mirrors the generic gate, hard-learned):
  * TRUE cross-corpus: c fit on ALL of A, tested on held-out B (and reverse) -- disjoint
    games, leak-free by construction (foul state is strictly the past of each as-of grid).
  * DM CLUSTERED BY game_id: ~23 states/game; per-state iid SE over-states significance.
  * HONESTY GUARD: M0 is the PROVEN, non-degenerate reference (not a coinflip), so a beat
    here is a genuine detail-layer win. We additionally REQUIRE the TRAIN-fit |c| to be
    non-trivial in at least one bucket (else the layer is a no-op that can't have skill).
  * SHIP iff M1<M0 Brier AND DM p<eps in BOTH directions; PARTIAL if one; REJECT else.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_foul_gate_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    leakfree_elo_p0,
    load_linescores,
    p_live_from_margin,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_REPO, "data", "domains", "basketball_nba")
_CACHE = os.path.join(_REPO, "data", "cache", "ingame")
LINES_A = os.path.join(_DATA, "linescores_2024_25.parquet")
LINES_B = os.path.join(_DATA, "linescores.parquet")
FOUL_A = os.path.join(_CACHE, "pbp_foul_states_2024_25.parquet")
FOUL_B = os.path.join(_CACHE, "pbp_foul_states_2025_26.parquet")
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "foul_gate_nba.json")

_REG_SEC = 2880.0
_N_TBUCKET = 4
_EPS_C = 1e-6
_LOGIT_CLIP = 1e-6
_C_GRID = np.linspace(-0.6, 0.6, 25)   # per-bucket logit slope on standardized foul_diff


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _LOGIT_CLIP, 1.0 - _LOGIT_CLIP)
    return np.log(p / (1.0 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _tbucket(frac: np.ndarray) -> np.ndarray:
    return np.minimum(_N_TBUCKET - 1, np.maximum(0, (frac * _N_TBUCKET).astype(int)))


def states_from_foul_pbp(foul_path: str, lines_path: str) -> List[dict]:
    """Leak-free fine-grained state dicts WITH foul state from a pbp_foul_states parquet.

    Reuses the proven p0 (strictly-pregame Elo) + p_live(margin,frac) base. Adds the
    as-of foul_diff (away_fouls - home_fouls) and cumulative side fouls -- strictly the
    past of each grid point. Games without an Elo p0 are dropped (no leak-free prior).
    """
    fp = pd.read_parquet(foul_path)
    lines = load_linescores(lines_path)
    p0_map = leakfree_elo_p0(lines)
    out: List[dict] = []
    for r in fp.itertuples(index=False):
        gid = int(r.event_id)
        if gid not in p0_map:
            continue
        sr = float(r.seconds_remaining)
        diff = float(r.home_margin)
        frac = 1.0 - sr / _REG_SEC
        out.append({
            "game_id": gid, "seconds_remaining": sr, "score_diff": diff,
            "frac_elapsed": frac, "foul_diff": float(r.foul_diff),
            "home_fouls": float(r.home_fouls), "away_fouls": float(r.away_fouls),
            "p0": float(p0_map[gid]), "p_live": p_live_from_margin(diff, frac),
            "outcome": int(r.home_win),
        })
    return out


def fit_foul_correction(train: List[dict], m0_train: np.ndarray
                        ) -> Tuple[Dict[int, float], float]:
    """Fit per-time-bucket foul logit slope c[t] on TRAIN by Brier (grid includes 0).

    Returns (c_by_bucket, foul_spread). z = foul_diff / spread (scale-free). For each
    elapsed-time bucket, the c minimizing the bucket Brier of sigmoid(logit(M0)+c*z) is
    chosen from a grid that CONTAINS 0 -- so a useless foul signal yields c=0 (no-op).
    """
    fd = np.array([s["foul_diff"] for s in train], float)
    frac = np.array([s["frac_elapsed"] for s in train], float)
    y = np.array([s["outcome"] for s in train], float)
    spread = float(np.std(fd)) or 1.0
    z = fd / spread
    lg = _logit(m0_train)
    tb = _tbucket(frac)
    c_by: Dict[int, float] = {}
    for t in range(_N_TBUCKET):
        m = tb == t
        if m.sum() < 50:
            c_by[t] = 0.0
            continue
        best_c, best_b = 0.0, float(np.mean((m0_train[m] - y[m]) ** 2))
        for c in _C_GRID:
            p = _sigmoid(lg[m] + c * z[m])
            b = float(np.mean((p - y[m]) ** 2))
            if b < best_b:
                best_b, best_c = b, float(c)
        c_by[t] = best_c
    return c_by, spread


def apply_foul_correction(states: List[dict], m0: np.ndarray,
                          c_by: Dict[int, float], spread: float) -> np.ndarray:
    """Apply the TRAIN-fit per-bucket foul correction to M0 -> M1 predictions."""
    fd = np.array([s["foul_diff"] for s in states], float)
    frac = np.array([s["frac_elapsed"] for s in states], float)
    z = fd / (spread or 1.0)
    tb = _tbucket(frac)
    c = np.array([c_by.get(int(t), 0.0) for t in tb], float)
    return _sigmoid(_logit(m0) + c * z)


def _elapsed_breakdown(frac: np.ndarray, m0: np.ndarray, m1: np.ndarray,
                       y: np.ndarray) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    tb = _tbucket(frac)
    for t in range(_N_TBUCKET):
        m = tb == t
        if not m.any():
            continue
        b0, b1 = float(brier(m0[m], y[m])), float(brier(m1[m], y[m]))
        out[f"q{t+1}"] = {"brier_m0": round(b0, 4), "brier_m1": round(b1, 4),
                          "delta": round(b0 - b1, 5), "n": int(m.sum())}
    return out


def cross_direction(train: List[dict], test: List[dict], eps: float = 0.05) -> Dict:
    """Fit M0 surface + foul correction on TRAIN; score M0 vs M1 on TEST. Leak-free."""
    surf = fit_weight_surface(train, min_cell=20)
    m0_tr = blended_predictions(train, surf)
    c_by, spread = fit_foul_correction(train, m0_tr)
    m0 = blended_predictions(test, surf)
    m1 = apply_foul_correction(test, m0, c_by, spread)
    y = np.array([s["outcome"] for s in test], float)
    frac = np.array([s["frac_elapsed"] for s in test], float)
    gids = [s["game_id"] for s in test]
    b0, b1 = float(brier(m0, y)), float(brier(m1, y))
    d = (m0 - y) ** 2 - (m1 - y) ** 2          # +ve => foul layer (M1) beats M0
    dm = diebold_mariano(d, gids)
    nontrivial = any(abs(v) > _EPS_C for v in c_by.values())
    foul_beats_m0 = bool((b1 < b0) and (dm.p_value < eps) and nontrivial)
    return {
        "n_train_states": len(train), "n_test_states": len(test),
        "n_test_games": dm.n_clusters,
        "c_by_bucket": {str(k): round(v, 4) for k, v in sorted(c_by.items())},
        "nontrivial_correction": bool(nontrivial),
        "brier_m0": round(b0, 4), "brier_m1": round(b1, 4),
        "brier_delta": round(b0 - b1, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "foul_beats_m0": foul_beats_m0,
        "elapsed_breakdown": _elapsed_breakdown(frac, m0, m1, y),
    }


def decide(a_to_b: Dict, b_to_a: Dict) -> str:
    a, b = bool(a_to_b.get("foul_beats_m0")), bool(b_to_a.get("foul_beats_m0"))
    if a and b:
        return "SHIP"
    if a or b:
        return "PARTIAL"
    return "REJECT"


@dataclass
class FoulVerdict:
    verdict: str
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layer": "foul_trouble (cumulative side fouls + signed foul_diff)",
            "reference_model": "M0 = PROVEN blend(p0_elo, p_live(margin,frac), w) -- not refit",
            "candidate_model": "M1 = sigmoid(logit(M0) + c(frac)*z(foul_diff)); c fit on TRAIN",
            "design": "true cross-corpus A<->B; DM clustered by game_id; c-grid includes 0",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def run_gate(states_a: List[dict], states_b: List[dict],
             caveats: Optional[List[str]] = None) -> FoulVerdict:
    a_to_b = cross_direction(states_a, states_b)
    b_to_a = cross_direction(states_b, states_a)
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
    }
    return FoulVerdict(decide(a_to_b, b_to_a), a_to_b, b_to_a, cov, list(caveats or []))


def run(foul_a: str = FOUL_A, foul_b: str = FOUL_B,
        lines_a: str = LINES_A, lines_b: str = LINES_B) -> FoulVerdict:
    states_a = states_from_foul_pbp(foul_a, lines_a)
    states_b = states_from_foul_pbp(foul_b, lines_b)
    caveats = [
        "Foul state is strictly the PAST of each ~2-min as-of grid point (cumulative "
        "fouls from plays at-or-before that moment) -- leak-free by construction.",
        "M0 (proven base+prior) is NEVER refit by the foul layer; the layer can only "
        "add a TRAIN-fit logit correction whose grid includes 0 (so a null signal -> no-op).",
        "True cross-corpus + DM clustered by game_id; foul correction c fit on the WHOLE "
        "train season, tested on the held-out OTHER season.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs the proven M0, "
        "never a market edge. No $ anywhere.",
    ]
    return run_gate(states_a, states_b, caveats)


def write(verdict: FoulVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _dir_report(name: str, d: Dict) -> List[str]:
    lines = [
        f"  {name}: train n={d.get('n_train_states')} -> test n={d.get('n_test_states')} "
        f"({d.get('n_test_games')} games)  c_by_bucket={d.get('c_by_bucket')}",
        f"    pooled OOS Brier : M0 {d.get('brier_m0')}  +FOUL(M1) {d.get('brier_m1')}"
        f"  (delta {d.get('brier_delta')})",
        f"    DM (clustered)   : stat {d.get('dm_stat')}  p {d.get('dm_p')}",
        f"    foul_beats_m0    : {d.get('foul_beats_m0')}  "
        f"nontrivial : {d.get('nontrivial_correction')}",
    ]
    for lab in ("q1", "q2", "q3", "q4"):
        r = (d.get("elapsed_breakdown") or {}).get(lab)
        if r:
            lines.append(f"      {lab} n={r['n']:6d}  M0 {r['brier_m0']:.4f} -> "
                         f"M1 {r['brier_m1']:.4f}  delta {r['delta']:+.5f}")
    return lines


def _report(v: FoulVerdict) -> str:
    c = v.coverage
    lines = ["=" * 72,
             "IN-GAME FOUL-TROUBLE DETAIL LAYER (NBA): foul state vs PROVEN base+prior",
             "=" * 72, f"VERDICT  : {v.verdict}",
             f"coverage : A {c.get('a_games')} games / {c.get('a_states')} states ; "
             f"B {c.get('b_games')} games / {c.get('b_states')} states", "-" * 72]
    lines += _dir_report("A->B (train 2024-25, test 2025-26)", v.a_to_b)
    lines.append("-" * 72)
    lines += _dir_report("B->A (train 2025-26, test 2024-25)", v.b_to_a)
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
