"""scripts.platformkit.ingame.sp_fatigue_gate_mlb -- GATE the MLB starting-pitcher
WITHIN-START fatigue signal (H1_sp_fatigue_ingame, docs/research/intel-layer/
mlb_truth_spec.json) as an in-game win-prob CONDITIONING layer, leak-free +
walk-forward, on held-out Brier. Clone of the PROVEN NBA pattern
scripts/platformkit/ingame/ingame_layer_gate_nba.py (expanding-window walk-forward,
>=3 folds, clustered DM, planted-null control) -- structure only, never edited.

THE QUESTION (H1): does starting-pitcher within-start fatigue (velo_decline_vs_early,
banded into {fresh,declining,fatigued} terciles fit on TRAIN only) condition in-game
win-prob Brier BEYOND a pure (score_diff, frac_elapsed) BASE?

TWO MODELS over the reconstructed half-inning as-of states:
  BASE     = sigmoid((a + b*frac_elapsed) * state_diff)      # (margin,time) only
  +FATIGUE = sigmoid(logit(BASE) + beta[tercile])             # BASE + a per-tercile
             logit shift, beta fit on the TRAIN fold ONLY (never the test fold);
             tercile edges (quantile cut points of velo_decline_vs_early) are ALSO
             fit on TRAIN only and applied unchanged to TEST (no leak either way).

DISCIPLINE (per spec floors): >=3 expanding-window walk-forward folds; min_cell=20
states per (tercile) group before a beta is fit for it (else beta->0, trust BASE);
>=100 states per tercile pooled OOS; DM clustered by proxy_pitcher (game_id,pitch_side
-- no individual pitcher id in this corpus, documented substitute); PLANTED NULL =
shuffle the tercile assignment across proxy pitchers within the same game-state cell
(sp_fatigue_gate_mlb_io.shuffle_tercile_planted_null) -- it MUST NOT beat BASE.

VERDICT (honest, gated): SHIP_FATIGUE_LAYER iff Brier(+FATIGUE) < Brier(BASE) AND DM
p<0.05 AND the fatigue-beats-base sign holds on >=2/3 folds AND the planted-null run
(identical pipeline, shuffled tercile) does NOT also pass this bar. Else REJECT --
a valid, honest, loggable result (mirrors the existing sp_adjust_verdict.json REJECT
on a related SP lever). INSUFFICIENT_DATA if no season corpus is on disk.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge. No pregame claim:
in-game conditioning ONLY, per H1_sp_fatigue_ingame's pregame_expectation="not
applicable". PROPOSAL-ONLY: writes only data/domains/mlb/sp_fatigue_gate_verdict.json,
never data/registry/, flips no flag.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.sp_fatigue_gate_mlb
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate, base_predict, fit_base)
from scripts.platformkit.ingame.ingame_ladder_mlb_layers import logit, sigmoid
from scripts.platformkit.ingame.sp_fatigue_gate_mlb_io import (
    TERCILES, shuffle_tercile_planted_null)

_MIN_CELL = 20
_MIN_PER_TERCILE = 100
_MIN_FOLDS = 3


# --------------------------------------------------------------------- fatigue layer
def fit_fatigue_layer(train: List[dict], base_tr: np.ndarray,
                      min_cell: int = _MIN_CELL) -> Dict[str, float]:
    """Fit a per-tercile logit shift beta[tercile] on TRAIN by Brier of
    sigmoid(logit(BASE)+beta[tercile]). Terciles with <min_cell TRAIN rows fall back
    to beta=0.0 (trust BASE) -- a sparse or noise tercile cannot overfit."""
    y = np.array([s["outcome"] for s in train], float)
    lo = logit(base_tr)
    tercile = np.array([s["tercile"] for s in train])
    beta: Dict[str, float] = {t: 0.0 for t in TERCILES}
    for t in TERCILES:
        m = tercile == t
        if int(m.sum()) < min_cell:
            continue
        best_b = float(np.mean((base_tr[m] - y[m]) ** 2))
        best_beta = 0.0
        for b in np.linspace(-0.75, 0.75, 31):
            p = sigmoid(lo[m] + b)
            sc = float(np.mean((p - y[m]) ** 2))
            if sc < best_b:
                best_b, best_beta = sc, float(b)
        beta[t] = best_beta
    return beta


def apply_fatigue_layer(test: List[dict], base_te: np.ndarray,
                        beta: Dict[str, float]) -> np.ndarray:
    lo = logit(base_te)
    shift = np.array([beta.get(s["tercile"], 0.0) for s in test], float)
    return sigmoid(lo + shift)


# --------------------------------------------------------------------------- folds
def _fold_predictions(train: List[dict], test: List[dict]):
    ab = fit_base(train)
    base_tr, base_te = base_predict(train, ab), base_predict(test, ab)
    y = np.array([s["outcome"] for s in test], float)
    degen = base_is_degenerate(ab, train, base_te, y)
    beta = fit_fatigue_layer(train, base_tr)
    fatigue = apply_fatigue_layer(test, base_te, beta)
    gids = [s["proxy_pitcher"] for s in test]
    tercile = [s["tercile"] for s in test]
    return y, base_te, fatigue, gids, tercile, degen


def walk_forward(states_by_game: Dict[str, List[dict]], order: List[str],
                 n_folds: int = _MIN_FOLDS):
    """Expanding-window walk-forward over games in chronological `order` (mirrors
    ingame_layer_gate_nba.walk_forward -- same fold-boundary logic)."""
    n = len(order)
    if n < (n_folds + 1) * 2:
        n_folds = max(1, n // 2 - 1)
    bounds = [int(round(i * n / (n_folds + 1))) for i in range(n_folds + 2)]
    folds = []
    for k in range(1, n_folds + 1):
        train_games = order[:bounds[k]]
        test_games = order[bounds[k]:bounds[k + 1]]
        if not train_games or not test_games:
            continue
        train = [s for g in train_games for s in states_by_game[g]]
        test = [s for g in test_games for s in states_by_game[g]]
        if not train or not test:
            continue
        folds.append(_fold_predictions(train, test))
    return folds


# --------------------------------------------------------------------------- verdict
@dataclass
class FatigueVerdict:
    verdict: str
    metrics: Dict[str, object] = field(default_factory=dict)
    per_fold: List[Dict[str, object]] = field(default_factory=list)
    per_tercile: Dict[str, Dict[str, float]] = field(default_factory=dict)
    planted_null: Dict[str, object] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "hypothesis_id": "H1_sp_fatigue_ingame",
            "layer": "sp_within_start_fatigue_tercile (velo_decline_vs_early)",
            "base_model": "sigmoid((a+b*frac_elapsed)*state_diff) -- (margin,time) only",
            "fatigue_model": "sigmoid(logit(BASE)+beta[tercile]); beta+edges fit TRAIN-only",
            "vs_close": "NOT APPLICABLE -- CALIBRATION only (held-out Brier), no market edge",
            "no_dollar_field": True, "proposal_only": True, "pregame_claim": False,
            "metrics": self.metrics,
            "per_fold": self.per_fold,
            "per_tercile": self.per_tercile,
            "planted_null": self.planted_null,
            "caveats": list(self.caveats),
        }


def _per_tercile(y, base, fatigue, tercile) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    tercile = np.asarray(tercile)
    for t in TERCILES:
        m = tercile == t
        if not m.any():
            continue
        bb, bf = brier(base[m], y[m]), brier(fatigue[m], y[m])
        out[t] = {"brier_base": round(float(bb), 4), "brier_fatigue": round(float(bf), 4),
                  "delta": round(float(bb - bf), 5), "n": int(m.sum())}
    return out


def _pool_and_score(folds) -> Optional[Dict]:
    """Pool folds -> (y,base,fatigue,gids,tercile) + pooled/DM/consistency metrics.
    Returns None if no folds (caller reports INSUFFICIENT_DATA)."""
    if not folds:
        return None
    ys, bases, fats, gids, tercile = [], [], [], [], []
    per_fold: List[Dict[str, object]] = []
    n_fatigue_better = 0
    any_degenerate = False
    for i, (y, base, fat, g, t, degen) in enumerate(folds):
        any_degenerate = any_degenerate or bool(degen["degenerate"])
        bb, bf = brier(base, y), brier(fat, y)
        better = bf < bb
        n_fatigue_better += int(better)
        per_fold.append({
            "fold": i, "n": int(len(y)),
            "brier_base": round(float(bb), 4), "brier_fatigue": round(float(bf), 4),
            "delta": round(float(bb - bf), 5), "fatigue_beats_base": bool(better),
            "base_degenerate": bool(degen["degenerate"]),
        })
        ys.append(y); bases.append(base); fats.append(fat)
        gids += list(g); tercile += list(t)
    y = np.concatenate(ys); base = np.concatenate(bases); fat = np.concatenate(fats)
    brier_base, brier_fat = float(brier(base, y)), float(brier(fat, y))
    d = (base - y) ** 2 - (fat - y) ** 2
    dm = diebold_mariano(d, gids)
    consistent = n_fatigue_better >= int(np.ceil(2 * len(folds) / 3.0))
    return {
        "y": y, "base": base, "fatigue": fat, "tercile": tercile,
        "per_fold": per_fold, "any_degenerate": any_degenerate,
        "metrics": {
            "n_states": int(len(y)), "n_folds": len(folds),
            "brier_base": round(brier_base, 4), "brier_fatigue": round(brier_fat, 4),
            "brier_delta": round(brier_base - brier_fat, 5),
            "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
            "n_clusters": dm.n_clusters,
            "folds_fatigue_better": int(n_fatigue_better),
            "fold_sign_consistent": bool(consistent),
        },
        "ship_bar": (brier_fat < brier_base) and (dm.p_value < 0.05) and consistent,
    }


def gate(states_by_game: Dict[str, List[dict]], order: List[str],
         n_folds: int = _MIN_FOLDS, caveats: Optional[List[str]] = None,
         seed: int = 0) -> FatigueVerdict:
    """Run the real walk-forward gate + the planted-null control; return an honest
    SHIP/REJECT/NOT_TESTABLE FatigueVerdict."""
    caveats = list(caveats or [])
    folds = walk_forward(states_by_game, order, n_folds=n_folds)
    scored = _pool_and_score(folds)
    if scored is None:
        return FatigueVerdict("INSUFFICIENT_DATA", {}, [], {}, {},
                              caveats + ["no usable walk-forward folds"])
    n_per_tercile = {t: int(np.sum(np.asarray(scored["tercile"]) == t)) for t in TERCILES}
    floor_ok = (scored["metrics"]["n_folds"] >= _MIN_FOLDS - 0 and
                all(n_per_tercile[t] >= _MIN_PER_TERCILE for t in TERCILES))
    per_t = _per_tercile(scored["y"], scored["base"], scored["fatigue"], scored["tercile"])

    # Planted-null control: IDENTICAL pipeline, tercile shuffled across proxy pitchers.
    null_by_game: Dict[str, List[dict]] = {}
    for gid, rows in states_by_game.items():
        null_by_game[gid] = shuffle_tercile_planted_null(rows, seed=seed)
    null_folds = walk_forward(null_by_game, order, n_folds=n_folds)
    null_scored = _pool_and_score(null_folds)
    null_ships = bool(null_scored and null_scored["ship_bar"])
    planted_null = {
        "method": "shuffle fatigue-tercile across proxy_pitcher within game-state cell",
        "null_metrics": null_scored["metrics"] if null_scored else {},
        "null_would_ship": null_ships,
        "null_rejected": not null_ships,
    }

    if not floor_ok:
        return FatigueVerdict(
            "INSUFFICIENT_DATA", scored["metrics"], scored["per_fold"], per_t,
            planted_null,
            caveats + [f"floors not met: need >={_MIN_FOLDS} folds and "
                       f">={_MIN_PER_TERCILE} states/tercile; got "
                       f"n_folds={scored['metrics']['n_folds']} per_tercile={n_per_tercile}"])
    if scored["any_degenerate"]:
        return FatigueVerdict("INVALID_BASE", scored["metrics"], scored["per_fold"],
                              per_t, planted_null,
                              caveats + ["BASE (margin,time) is degenerate in >=1 fold "
                                         "-- no real in-game signal for fatigue to add to"])
    if null_ships:
        return FatigueVerdict("NOT_TESTABLE", scored["metrics"], scored["per_fold"],
                              per_t, planted_null,
                              caveats + ["UNTRUSTWORTHY: planted-null (shuffled tercile) "
                                         "ALSO passed the ship bar -- the gate failed to "
                                         "fail a noise control; verdict withheld"])
    verdict = "SHIP_FATIGUE_LAYER" if scored["ship_bar"] else "REJECT"
    return FatigueVerdict(verdict, scored["metrics"], scored["per_fold"], per_t,
                          planted_null, caveats)


# Driver (corpus loading, CLI report, write) lives in sp_fatigue_gate_mlb_driver.py
# to keep this module <=300 LOC -- see run()/write()/main() there.
