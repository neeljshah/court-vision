"""domains.mlb.pregame_gate -- honest CROSS-CORPUS pregame win-prob gate.

Question: does a candidate pregame win-prob model beat the pitcher-blind Elo
BASE on held-out OOS Brier, REPLICATED across two independent corpora
(games.parquet 2010-2021  vs  games_current.parquet 2022-2026), in BOTH
directions (A->B and B->A)?

DISCIPLINE (binding):
  * TRUE cross-corpus: the Platt calibration (and any candidate knob) is FIT on
    the WHOLE train corpus, then scored on the held-out OTHER corpus. Disjoint
    games, leak-free by construction (every per-game feature is snapshot-before-
    update walk-forward Elo).
  * DM CLUSTERED BY event_id: one row per game here, so clustering == iid, but we
    route through the same clustered DM so the gate is identical-shaped to the
    in-game gate.
  * DEGENERATE-BASE GUARD: if the BASE model's Brier barely beats the constant
    home-win base-rate (BSS < BSS_MIN), the corpus carries almost no separable
    signal and a "candidate beats base" there is not a real win -> capped below
    REPLICATED.
  * REPLICATED iff candidate Brier < base Brier AND DM p < eps in BOTH directions
    AND neither base is degenerate. PARTIAL if one. REJECT otherwise.

NO $ / edge anywhere: verdict is CALIBRATION (held-out Brier), never a market edge.
PURE numpy/pandas + the shared clustered DM + the local Elo builders. No src.*/kernel*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano

BSS_MIN = 0.003   # min Brier-skill-vs-baserate for a corpus to be "non-degenerate"


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _logit(p: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


def _platt_fit(logit_tr: np.ndarray, y_tr: np.ndarray) -> Tuple[float, float]:
    """Fit p = sigmoid(w*logit + b) by L-BFGS-B on train log-loss."""
    from scipy.optimize import minimize

    def _nll(params: np.ndarray) -> float:
        w, b = params
        p = np.clip(_sigmoid(w * logit_tr + b), 1e-7, 1.0 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 10.0), (-3.0, 3.0)])
    w, b = res.x
    return float(w), float(b)


# --------------------------------------------------------------------------- #
# One cross direction
# --------------------------------------------------------------------------- #

@dataclass
class DirResult:
    n_train: int
    n_test: int
    brier_base: float
    brier_cand: float
    brier_delta: float          # base - cand  (positive => cand better)
    dm_stat: float
    dm_p: float
    cand_beats_base: bool
    base_degenerate: bool
    base_bss: float

    def to_dict(self) -> Dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def _one_direction(
    train: pd.DataFrame, test: pd.DataFrame,
    base_col: str, cand_col: str, eps: float,
) -> DirResult:
    """Platt-fit BASE and CAND on train, score both on test. event_id clustered DM."""
    y_tr = train["target_home_win"].values.astype(float)
    y_te = test["target_home_win"].values.astype(float)

    wb, bb_ = _platt_fit(_logit(train[base_col].values.astype(float)), y_tr)
    wc, bc_ = _platt_fit(_logit(train[cand_col].values.astype(float)), y_tr)

    p_base = _sigmoid(wb * _logit(test[base_col].values.astype(float)) + bb_)
    p_cand = _sigmoid(wc * _logit(test[cand_col].values.astype(float)) + bc_)

    br_base = _brier(y_te, p_base)
    br_cand = _brier(y_te, p_cand)

    # DM clustered by event_id: d = loss_base - loss_cand (positive => cand wins)
    d = (p_base - y_te) ** 2 - (p_cand - y_te) ** 2
    gids = test["event_id"].astype(str).values
    dm = diebold_mariano(d, gids)

    # degenerate-base guard: BSS of the calibrated BASE vs the train base-rate.
    base_rate = float(np.mean(y_tr))
    br_const = _brier(y_te, np.full_like(y_te, base_rate))
    base_bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = base_bss < BSS_MIN

    cand_beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return DirResult(
        n_train=len(train), n_test=len(test),
        brier_base=br_base, brier_cand=br_cand, brier_delta=br_base - br_cand,
        dm_stat=dm.dm_stat, dm_p=dm.p_value,
        cand_beats_base=cand_beats, base_degenerate=degen, base_bss=base_bss,
    )


# --------------------------------------------------------------------------- #
# Verdict
# --------------------------------------------------------------------------- #

@dataclass
class GateVerdict:
    verdict: str
    name: str = ""
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"verdict": self.verdict, "name": self.name,
                "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
                "caveats": list(self.caveats)}


def _decide(a: DirResult, b: DirResult) -> str:
    degen = a.base_degenerate or b.base_degenerate
    if degen:
        return "PARTIAL" if (a.cand_beats_base or b.cand_beats_base) else "INVALID_BASE"
    if a.cand_beats_base and b.cand_beats_base:
        return "REPLICATED"
    if a.cand_beats_base or b.cand_beats_base:
        return "PARTIAL"
    return "REJECT"


def gate_cross_corpus(
    df_a: pd.DataFrame, df_b: pd.DataFrame,
    base_col: str, cand_col: str,
    name: str = "", eps: float = 0.05,
) -> GateVerdict:
    """Run A->B and B->A cross-corpus; return an honest replication verdict.

    df_a/df_b must each carry: event_id, target_home_win, base_col, cand_col,
    with both prob columns in (0,1) and strictly pre-game.
    """
    a = _one_direction(df_a, df_b, base_col, cand_col, eps)   # train A, test B
    b = _one_direction(df_b, df_a, base_col, cand_col, eps)   # train B, test A
    cav = [
        "True cross-corpus: Platt calibration FIT on the whole train corpus, scored "
        "on the held-out OTHER corpus -- leak-free by construction.",
        "DM clustered by event_id. Verdict is CALIBRATION (held-out Brier), no $ edge.",
    ]
    if a.base_degenerate or b.base_degenerate:
        cav.append(
            "DEGENERATE-BASE GUARD tripped: a BASE direction barely beats the constant "
            "home-win base-rate (BSS < %.3f) -- capped below REPLICATED." % BSS_MIN)
    return GateVerdict(_decide(a, b), name, a.to_dict(), b.to_dict(), cav)


__all__ = ["gate_cross_corpus", "GateVerdict", "DirResult",
           "_one_direction", "_platt_fit", "BSS_MIN"]
