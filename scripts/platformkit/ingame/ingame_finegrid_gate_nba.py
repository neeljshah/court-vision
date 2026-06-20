"""scripts.platformkit.ingame.ingame_finegrid_gate_nba -- 6x6 fine blend-weight
grid (6 time x 6 margin) vs proven coarse 4x5 grid, gated cross-corpus OOS.

Fine margin edges: (-10,-3,0,3,10) -> 6 buckets. Min-cell=30 (sparse cells
fall back to default=0.0). SHIP only if fine Brier < coarse Brier in BOTH
cross-corpus directions AND monotone holds AND planted-null rejects.
No $ field. Verdict is CALIBRATION (Brier), not a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import (
    WeightSurface,
    blend,
    blended_predictions,
    fit_weight_surface,
    margin_bucket,
    time_bucket,
)
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_crossval_nba import (
    cross_direction,
    states_from_path,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_REPO, "data", "domains", "basketball_nba")
CORPUS_A = os.path.join(_DATA, "linescores_2024_25.parquet")
CORPUS_B = os.path.join(_DATA, "linescores.parquet")
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "finegrid_gate_nba.json")

# --- grid parameters ---
_N_TIME_COARSE = 4
_N_TIME_FINE = 6
# 5 edges -> 6 margin buckets (finer than coarse 4-edge / 5-bucket)
_MARGIN_EDGES_FINE = (-10.0, -3.0, 0.0, 3.0, 10.0)
_N_MARGIN_FINE = 6  # len(edges) + 1
MIN_CELL = 30       # raised vs coarse (20) because fine cells are smaller


# --------------------------------------------------------------------------- fine grid
def _fine_margin_bucket(score_diff: float) -> int:
    """6-bucket margin (5 edges: -10,-3,0,3,10)."""
    b = 0
    for e in _MARGIN_EDGES_FINE:
        if score_diff >= e:
            b += 1
    return b  # 0..5


def fit_fine_surface(states: List[dict], min_cell: int = MIN_CELL) -> WeightSurface:
    """Fit a 6x6 weight surface (6 time x 6 margin) with min-cell floor.

    Cells with < min_cell samples fall back to default=0.0 (trust pregame).
    The fine grid uses the same Brier-minimizing w search as the coarse grid,
    but with denser time and margin bucketing.
    """
    w_grid = np.linspace(0.0, 1.0, 21)
    surf = WeightSurface(n_time=_N_TIME_FINE, n_margin=_N_MARGIN_FINE)
    cells: Dict[Tuple[int, int], List[dict]] = {}
    for s in states:
        tb = time_bucket(s["seconds_remaining"], n=_N_TIME_FINE)
        mb = _fine_margin_bucket(s["score_diff"])
        cells.setdefault((tb, mb), []).append(s)
    for key, rows in cells.items():
        if len(rows) < min_cell:
            continue  # sparse -> default (never overfit thin cells)
        p0 = np.array([r["p0"] for r in rows])
        pl = np.array([r["p_live"] for r in rows])
        y = np.array([r["outcome"] for r in rows], dtype=float)
        best_w, best_b = 0.0, float(np.mean((p0 - y) ** 2))
        for w in w_grid:
            b = float(np.mean((w * pl + (1.0 - w) * p0 - y) ** 2))
            if b < best_b:
                best_b, best_w = b, float(w)
        surf.grid[key] = best_w
    return surf


def fine_blended(states: List[dict], surf: WeightSurface) -> np.ndarray:
    """Apply the fine surface to states -> blended probs."""
    out = []
    for s in states:
        tb = time_bucket(s["seconds_remaining"], n=_N_TIME_FINE)
        mb = _fine_margin_bucket(s["score_diff"])
        w = surf.grid.get((tb, mb), surf.default)
        out.append(blend(s["p0"], s["p_live"], w))
    return np.asarray(out)


# --------------------------------------------------------------------------- monotone check
def monotone_holds(surf: WeightSurface) -> bool:
    """Later time buckets should carry >= weight than earlier ones (on average).

    Computes the mean weight per time bucket (over all filled margin buckets) and
    checks that the sequence is non-decreasing. A single pair of violations -> False.
    """
    means: Dict[int, List[float]] = {}
    for (tb, _mb), w in surf.grid.items():
        means.setdefault(tb, []).append(w)
    if not means:
        return False
    sorted_tb = sorted(means.keys())
    avgs = [float(np.mean(means[tb])) for tb in sorted_tb]
    # allow at most 0 violations (strictly non-decreasing across populated buckets)
    return all(avgs[i] <= avgs[i + 1] + 1e-9 for i in range(len(avgs) - 1))


# --------------------------------------------------------------------------- min-cell guard
def assert_no_thin_cells(
    surf: WeightSurface,
    min_cell: int,
    states: List[dict],
) -> None:
    """Verify every fitted cell in surf had >= min_cell training rows.

    Recomputes per-cell counts from states using the same bucketing as
    fit_fine_surface.  Each key in surf.grid must have count >= min_cell;
    cells below the floor must NOT appear in surf.grid (surface default).
    Pass the same states list that was passed to fit_fine_surface.
    """
    counts: Dict[Tuple[int, int], int] = {}
    for s in states:
        tb = time_bucket(s["seconds_remaining"], n=_N_TIME_FINE)
        mb = _fine_margin_bucket(s["score_diff"])
        counts[(tb, mb)] = counts.get((tb, mb), 0) + 1
    for key in surf.grid:
        n = counts.get(key, 0)
        if n < min_cell:
            raise AssertionError(
                f"Fitted cell {key} has only {n} rows (min_cell={min_cell}). "
                "fit_fine_surface must have skipped the min-cell floor check."
            )


# --------------------------------------------------------------------------- one direction
def _fine_vs_coarse_direction(train: List[dict], test: List[dict]) -> Dict:
    """Fit fine + coarse surfaces on train; score Brier on test.

    Returns per-direction metrics: fine_brier, coarse_brier, delta, monotone.
    Fine wins if fine_brier < coarse_brier.
    """
    fine_surf = fit_fine_surface(train, min_cell=MIN_CELL)
    coarse_surf = fit_weight_surface(train, min_cell=20)

    y = np.array([s["outcome"] for s in test], float)
    fine_pred = fine_blended(test, fine_surf)
    coarse_pred = blended_predictions(test, coarse_surf)

    fb = float(brier(fine_pred, y))
    cb = float(brier(coarse_pred, y))
    mono = monotone_holds(fine_surf)
    n_fitted = len(fine_surf.grid)
    return {
        "n_train": len(train),
        "n_test": len(test),
        "fine_brier": round(fb, 6),
        "coarse_brier": round(cb, 6),
        "delta": round(cb - fb, 6),   # >0 -> fine wins
        "fine_beats_coarse": bool(fb < cb),
        "monotone_holds": mono,
        "n_fine_cells_fitted": n_fitted,
    }


# --------------------------------------------------------------------------- planted-null test
def planted_null_rejects(states: List[dict], rng_seed: int = 42) -> bool:
    """Shuffle outcomes and verify fine surface does NOT beat coarse on shuffled data.

    A surface that beats noise is fitting noise (thin-cell overfit). If fine_brier
    < coarse_brier on shuffled outcomes, the gate should REJECT.
    Returns True when the null is correctly rejected (fine does NOT win on noise).
    """
    rng = np.random.default_rng(rng_seed)
    n = len(states)
    shuffled_y = rng.permutation([s["outcome"] for s in states]).tolist()
    null_states = [dict(s, outcome=int(shuffled_y[i])) for i, s in enumerate(states)]

    # split 50/50 train/test for the null
    half = n // 2
    train_null = null_states[:half]
    test_null = null_states[half:]
    if not train_null or not test_null:
        return True  # insufficient data; treat as no signal -> null "rejected"
    res = _fine_vs_coarse_direction(train_null, test_null)
    # planted null should NOT show fine beating coarse
    return not res["fine_beats_coarse"]


# --------------------------------------------------------------------------- verdict
@dataclass
class FineGridVerdict:
    verdict: str          # SHIP | REJECT
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    null_rejected: bool = False
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "design": "6x6 fine grid (6 time x 6 margin, min_cell=30) vs 4x5 coarse "
                      "grid -- OOS Brier both cross-corpus directions; monotone sanity; "
                      "planted-null rejects. SHIP only if fine beats coarse both dirs "
                      "AND monotone AND null rejected.",
            "min_cell_floor": MIN_CELL,
            "vs_close": "UNPROVEN -- calibration vs coarse grid, not a market edge",
            "a_to_b": self.a_to_b,
            "b_to_a": self.b_to_a,
            "null_rejected": self.null_rejected,
            "caveats": list(self.caveats),
        }


def run_gate(states_a: List[dict], states_b: List[dict],
             caveats: Optional[List[str]] = None) -> FineGridVerdict:
    """Run the fine-grid gate: both cross-corpus directions + null test + monotone."""
    a_to_b = _fine_vs_coarse_direction(states_a, states_b)
    b_to_a = _fine_vs_coarse_direction(states_b, states_a)
    null_ok = planted_null_rejects(states_a + states_b)

    both_dirs_fine_win = a_to_b["fine_beats_coarse"] and b_to_a["fine_beats_coarse"]
    both_mono = a_to_b["monotone_holds"] and b_to_a["monotone_holds"]

    if both_dirs_fine_win and both_mono and null_ok:
        verdict = "SHIP"
    else:
        verdict = "REJECT"

    return FineGridVerdict(verdict, a_to_b, b_to_a, null_ok, list(caveats or []))


def run(path_a: str = CORPUS_A, path_b: str = CORPUS_B) -> FineGridVerdict:
    """Load both real corpora, build leak-free states, run the fine-grid gate."""
    states_a = states_from_path(path_a)
    states_b = states_from_path(path_b)
    caveats = [
        "6x6 fine grid (6 time x 6 margin, 5 edges: -10,-3,0,3,10). min_cell=30 "
        "prevents thin-cell overfit; sparse cells fall back to default weight=0.0.",
        "Cross-corpus gate: fit fine+coarse on corpus A, score OOS Brier on B, then "
        "reverse. SHIP requires fine_brier < coarse_brier in BOTH directions.",
        "Monotone check: average blend weight must be non-decreasing across time "
        "buckets -- a violated monotone means the surface is fitting noise, not "
        "the freshness lever.",
        "Planted-null: shuffle outcomes -> fine surface must NOT beat coarse on noise.",
        "No $ field. Verdict is CALIBRATION vs coarse grid, not a market edge.",
    ]
    return run_gate(states_a, states_b, caveats)


def write(verdict: FineGridVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _report(v: FineGridVerdict) -> str:
    def _dir(name: str, d: Dict) -> str:
        return (
            f"  {name}:\n"
            f"    fine brier={d['fine_brier']:.6f}  coarse brier={d['coarse_brier']:.6f}"
            f"  delta={d['delta']:+.6f}  fine_wins={d['fine_beats_coarse']}\n"
            f"    monotone={d['monotone_holds']}  cells_fitted={d['n_fine_cells_fitted']}"
        )
    lines = [
        "=" * 70,
        "IN-GAME FINE GRID GATE (NBA): 6x6 fine vs 4x5 coarse",
        "=" * 70,
        f"VERDICT       : {v.verdict}",
        f"null_rejected : {v.null_rejected}",
        "-" * 70,
        _dir("A->B (train 2024-25, test 2025-26)", v.a_to_b),
        "-" * 70,
        _dir("B->A (train 2025-26, test 2024-25)", v.b_to_a),
        "=" * 70,
    ]
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
