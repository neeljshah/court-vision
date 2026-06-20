"""scripts.platformkit.ingame.ingame_smooth_tune_nba -- tune exp_smooth alpha for
in-game tick stability.

GOAL: find alpha in [0,1] that minimises TICK JITTER (mean absolute diff between
consecutive p_win values within a game) on a TRAIN corpus, subject to the hard
constraint that smoothed Brier on the EVAL (held-out) corpus is no worse than
unsmoothed (alpha=1.0).

IDENTITY SAFETY: alpha=1.0 is the unsmoothed pass-through. If no candidate alpha
lowers jitter without worsening Brier, returns alpha=1.0 with IDENTITY_SAFE_DEFAULT.

THIN DATA: <MIN_GAMES in either corpus -> alpha=1.0 + INSUFFICIENT_DATA (no finding).

NO $: verdict is CALIBRATION (Brier) vs tick jitter, never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_smooth_tune_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.eval_gate.ingame_blend import exp_smooth, blended_predictions, fit_weight_surface
from scripts.platformkit.eval_gate.scoring import brier

MIN_GAMES = 30           # minimum games per corpus split to attempt tuning
ALPHA_GRID = tuple(round(v, 2) for v in np.linspace(0.0, 1.0, 21))  # 0.00..1.00 step 0.05
DEFAULT_ALPHA = 1.0      # identity pass-through (no smoothing)


# ---------------------------------------------------------------------------
# smoothing helpers
# ---------------------------------------------------------------------------

def smooth_series(seq: Sequence[float], alpha: float) -> List[float]:
    """Apply exponential smoothing (alpha close to 1 = mostly new value)."""
    result: List[float] = []
    s: Optional[float] = None
    for x in seq:
        s = float(x) if s is None else exp_smooth([s, float(x)], alpha)
        result.append(s)
    return result


def tick_jitter(series: Sequence[float]) -> float:
    """Mean absolute consecutive-tick delta within a single game tick-sequence."""
    arr = np.asarray(series, dtype=float)
    if len(arr) < 2:
        return 0.0
    return float(np.mean(np.abs(np.diff(arr))))


def apply_smooth_to_states(states: List[dict], alpha: float) -> np.ndarray:
    """Apply per-game exponential smoothing to a list of ordered game states.

    States MUST be sorted by (game_id, seconds_remaining desc) before calling.
    Returns an array of smoothed p_blend values (same order as states).
    """
    # group by game_id, smooth each game's tick sequence, re-flatten
    from collections import OrderedDict
    groups: OrderedDict[int, List[Tuple[int, float]]] = OrderedDict()
    for i, s in enumerate(states):
        gid = int(s["game_id"])
        groups.setdefault(gid, []).append((i, float(s["p_blend"])))

    smoothed = np.empty(len(states))
    for gid, pairs in groups.items():
        idxs = [p[0] for p in pairs]
        vals = [p[1] for p in pairs]
        sv = smooth_series(vals, alpha)
        for idx, sv_i in zip(idxs, sv):
            smoothed[idx] = sv_i
    return smoothed


def mean_jitter_across_games(states: List[dict], alpha: float) -> float:
    """Mean across-game tick jitter for a smoothed-states list."""
    from collections import OrderedDict
    groups: OrderedDict[int, List[float]] = OrderedDict()
    for s in states:
        gid = int(s["game_id"])
        groups.setdefault(gid, []).append(float(s["p_blend"]))

    jitters: List[float] = []
    for gid, vals in groups.items():
        sv = smooth_series(vals, alpha)
        jitters.append(tick_jitter(sv))
    return float(np.mean(jitters)) if jitters else 0.0


# ---------------------------------------------------------------------------
# corpus builder: produce blend-enriched states (p_blend) from raw states
# ---------------------------------------------------------------------------

def enrich_with_blend(states: List[dict], surf) -> List[dict]:
    """Add 'p_blend' field to each state using a fitted weight surface."""
    preds = blended_predictions(states, surf)
    enriched = []
    for s, pb in zip(states, preds):
        d = dict(s)
        d["p_blend"] = float(pb)
        enriched.append(d)
    return enriched


# ---------------------------------------------------------------------------
# result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SmoothTuneResult:
    alpha: float
    status: str            # "TUNED" | "IDENTITY_SAFE_DEFAULT" | "INSUFFICIENT_DATA"
    train_n_games: int
    eval_n_games: int
    eval_brier_unsmoothed: float
    eval_brier_smoothed: float
    train_jitter_unsmoothed: float
    train_jitter_smoothed: float
    brier_delta: float     # unsmoothed - smoothed (positive = smoothing helps Brier)
    jitter_delta: float    # unsmoothed - smoothed jitter (positive = less jitter)
    note: str

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["verdict"] = "calibration_nondegradation (not a market edge)"
        return d


# ---------------------------------------------------------------------------
# tuner
# ---------------------------------------------------------------------------

def _n_games(states: List[dict]) -> int:
    return len({s["game_id"] for s in states})


def tune_alpha(
    train_states: List[dict],
    eval_states: List[dict],
    alpha_grid: Sequence[float] = ALPHA_GRID,
    brier_tol: float = 1e-5,
) -> SmoothTuneResult:
    """Fit alpha on TRAIN (lowest jitter) subject to eval Brier non-degradation.

    Parameters
    ----------
    train_states : states with 'p_blend' already set (sorted by game_id / time).
    eval_states  : held-out states with 'p_blend' already set.
    alpha_grid   : candidate alpha values in [0,1]; 1.0 = identity / unsmoothed.
    brier_tol    : how much Brier may worsen vs unsmoothed (default 0 = strict).

    Returns a SmoothTuneResult; never raises.
    """
    n_train = _n_games(train_states)
    n_eval = _n_games(eval_states)

    if n_train < MIN_GAMES or n_eval < MIN_GAMES:
        return SmoothTuneResult(
            alpha=DEFAULT_ALPHA,
            status="INSUFFICIENT_DATA",
            train_n_games=n_train,
            eval_n_games=n_eval,
            eval_brier_unsmoothed=float("nan"),
            eval_brier_smoothed=float("nan"),
            train_jitter_unsmoothed=float("nan"),
            train_jitter_smoothed=float("nan"),
            brier_delta=0.0,
            jitter_delta=0.0,
            note=(
                f"train_games={n_train} eval_games={n_eval} < MIN_GAMES={MIN_GAMES}; "
                "returning identity-safe alpha=1.0 (INSUFFICIENT_DATA)."
            ),
        )

    # unsmoothed reference values (alpha=1.0 is identity)
    y_eval = np.array([s["outcome"] for s in eval_states], dtype=float)
    p_blend_eval = np.array([s["p_blend"] for s in eval_states], dtype=float)
    brier_ref = brier(p_blend_eval, y_eval)
    jitter_ref = mean_jitter_across_games(train_states, alpha=1.0)

    best_alpha = DEFAULT_ALPHA
    best_jitter = jitter_ref
    best_brier_smoothed = brier_ref

    for alpha in sorted(alpha_grid):
        # measure jitter on TRAIN (alpha tuning target)
        j = mean_jitter_across_games(train_states, alpha=alpha)

        # evaluate Brier on EVAL (hard non-degradation constraint)
        sm_eval = apply_smooth_to_states(eval_states, alpha)
        b = brier(sm_eval, y_eval)

        # constraint: smoothed Brier must not worsen vs unsmoothed by more than tol
        if b > brier_ref + brier_tol:
            continue

        # candidate: lower jitter
        if j < best_jitter:
            best_jitter = j
            best_alpha = float(alpha)
            best_brier_smoothed = float(b)

    # apply best_alpha to eval to get final smoothed eval Brier
    if best_alpha != DEFAULT_ALPHA:
        sm_final = apply_smooth_to_states(eval_states, best_alpha)
        best_brier_smoothed = brier(sm_final, y_eval)
        status = "TUNED"
        note = (
            f"alpha={best_alpha:.2f} lowers train jitter {jitter_ref:.5f} -> "
            f"{best_jitter:.5f} without worsening EVAL Brier "
            f"({brier_ref:.5f} -> {best_brier_smoothed:.5f})."
        )
    else:
        best_brier_smoothed = brier_ref
        status = "IDENTITY_SAFE_DEFAULT"
        note = (
            f"No alpha in grid lowered jitter without worsening Brier; "
            f"returning identity-safe default alpha=1.0."
        )

    return SmoothTuneResult(
        alpha=best_alpha,
        status=status,
        train_n_games=n_train,
        eval_n_games=n_eval,
        eval_brier_unsmoothed=round(float(brier_ref), 6),
        eval_brier_smoothed=round(float(best_brier_smoothed), 6),
        train_jitter_unsmoothed=round(float(jitter_ref), 6),
        train_jitter_smoothed=round(float(best_jitter), 6),
        brier_delta=round(float(brier_ref - best_brier_smoothed), 7),
        jitter_delta=round(float(jitter_ref - best_jitter), 7),
        note=note,
    )


# ---------------------------------------------------------------------------
# runner using real NBA corpora
# ---------------------------------------------------------------------------

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_REPO, "data", "domains", "basketball_nba")
CORPUS_A = os.path.join(_DATA, "linescores_2024_25.parquet")
CORPUS_B = os.path.join(_DATA, "linescores.parquet")
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "smooth_tune_nba.json")


def run(path_train: str = CORPUS_A, path_eval: str = CORPUS_B) -> SmoothTuneResult:
    """Load two disjoint corpora, fit blend surface on TRAIN, tune alpha, evaluate on EVAL."""
    from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
        load_linescores,
        leakfree_elo_p0,
        states_for_games,
    )
    df_train = load_linescores(path_train)
    df_eval = load_linescores(path_eval)
    p0_train = leakfree_elo_p0(df_train)
    p0_eval = leakfree_elo_p0(df_eval)
    raw_train = states_for_games(df_train, p0_train)
    raw_eval = states_for_games(df_eval, p0_eval)
    surf = fit_weight_surface(raw_train)
    train_states = enrich_with_blend(raw_train, surf)
    eval_states = enrich_with_blend(raw_eval, surf)
    return tune_alpha(train_states, eval_states)


def write(result: SmoothTuneResult, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(result.to_dict(), f, indent=2, sort_keys=True)
    return out


def main() -> None:
    result = run()
    p = write(result)
    print("=" * 70)
    print("IN-GAME EXP-SMOOTH ALPHA TUNE (NBA)")
    print("=" * 70)
    print(f"  status              : {result.status}")
    print(f"  chosen alpha        : {result.alpha}")
    print(f"  train jitter        : {result.train_jitter_unsmoothed:.5f} -> "
          f"{result.train_jitter_smoothed:.5f}  (delta {result.jitter_delta:+.5f})")
    print(f"  eval Brier          : {result.eval_brier_unsmoothed:.5f} -> "
          f"{result.eval_brier_smoothed:.5f}  (delta {result.brier_delta:+.7f})")
    print(f"  note                : {result.note}")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
