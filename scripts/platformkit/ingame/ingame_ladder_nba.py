"""scripts.platformkit.ingame.ingame_ladder_nba -- EXTEND the gated in-game
detail-layer LADDER on top of the current best model (BASE+PRIOR).

CONTEXT: ingame_layer_gate_nba already proved +PRIOR (leak-free Elo pregame prior
blended via a TRAIN-fit weight surface) beats a pure (margin,time) BASE on held-out
NBA Brier. So the CURRENT BEST per-state prob = BASE+PRIOR. This module gates >=2 NEW
candidate detail layers, EACH independently vs that current best, on the SAME leak-free
expanding-window walk-forward + cluster-robust DM.

CANDIDATE LAYERS (each = a pure function best_prob -> new_prob, params fit on TRAIN only):
  1. PACE / total-scoring-variance shrink. Hypothesis: high-total (fast) games carry MORE
     remaining variance, so for a given (margin,time) the win-prob should be REGRESSED
     toward 0.5. Implemented as p' = 0.5 + (p-0.5)*shrink(total_so_far), where shrink<1
     grows tighter as total rises; the (intercept,slope) of the shrink are fit on TRAIN by
     minimizing TRAIN Brier of the shrunk best-prob. A principled calibration effect --
     the most likely true SHIP.
  2. MOMENTUM / run-direction. recent-quarter margin delta (endQ2: Q2margin-Q1margin;
     endQ3: Q3-Q2). Hypothesis (momentum_worse_than_null, INT-81): an ARTIFACT that should
     REJECT. p' = sigmoid(logit(p) + beta*delta_z), beta fit on TRAIN. A CONTROL: the ladder
     must demonstrably reject a known-bad layer.
  3. HOME-BIAS calibration. A single TRAIN-fit logit intercept c: p' = sigmoid(logit(p)+c),
     correcting any residual home/away mis-calibration the best model leaves. The leak-free
     Elo prior already prices home-court, so we EXPECT c~0 / REJECT -- a principled control.

SHIP a layer ONLY iff Brier(best+layer) < Brier(best) AND DM clustered p<0.05 AND the
layer-beats-best sign holds on >=2/3 folds. Else REJECT (the expected, honest outcome for
most layers). NOTHING is massaged to ship.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_ladder_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_ladder_nba_layers import (
    LAYERS,
    Layer,
    ladder_states_for_games,
)
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    leakfree_elo_p0,
    load_linescores,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "ladder_nba.json")


# --------------------------------------------------------------------------- folds
def _best_and_states(train: List[dict], test: List[dict]):
    """Current BEST (BASE+PRIOR) on TRAIN and TEST, leak-free (surface fit on TRAIN)."""
    surf = fit_weight_surface(train, min_cell=20)
    best_train = blended_predictions(train, surf)
    best_test = blended_predictions(test, surf)
    return best_train, best_test


def walk_forward_ladder(states_by_game: Dict[int, List[dict]], order: List[int],
                        layer: Layer, n_folds: int = 3):
    """Expanding-window WF: per fold fit BEST (surface) + layer params on TRAIN, predict
    BEST and BEST+layer on TEST. Yields (y, best, layered, gids, periods) per fold."""
    n = len(order)
    if n < (n_folds + 1) * 2:
        n_folds = max(1, n // 2 - 1)
    bounds = [int(round(i * n / (n_folds + 1))) for i in range(n_folds + 2)]
    folds = []
    for k in range(1, n_folds + 1):
        tr_g, te_g = order[:bounds[k]], order[bounds[k]:bounds[k + 1]]
        if not tr_g or not te_g:
            continue
        train = [s for g in tr_g for s in states_by_game[g]]
        test = [s for g in te_g for s in states_by_game[g]]
        best_train, best_test = _best_and_states(train, test)
        params = layer.fit(train, best_train)            # TRAIN ONLY -> leak-free
        layered = layer.apply(test, best_test, params)
        y = np.array([s["outcome"] for s in test], float)
        gids = [s["game_id"] for s in test]
        periods = [s["period"] for s in test]
        folds.append((y, best_test, layered, gids, periods))
    return folds


# --------------------------------------------------------------------------- verdict
@dataclass
class LadderVerdict:
    name: str
    verdict: str
    why: str
    metrics: Dict[str, object] = field(default_factory=dict)
    per_fold: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"layer": self.name, "verdict": self.verdict, "why": self.why,
                "vs_close": "UNPROVEN -- CALIBRATION only (Brier), not a market edge",
                "baseline": "current_best_BASE+PRIOR",
                "metrics": self.metrics, "per_fold": self.per_fold}


def gate_layer(states_by_game: Dict[int, List[dict]], order: List[int],
               layer: Layer, n_folds: int = 3) -> LadderVerdict:
    """Run the WF gate for one layer vs the current best; honest SHIP/REJECT."""
    folds = walk_forward_ladder(states_by_game, order, layer, n_folds=n_folds)
    if not folds:
        return LadderVerdict(layer.name, "REJECT", "no usable folds")
    ys, bs, ls, gids, per_fold = [], [], [], [], []
    n_better = 0
    for i, (y, best, lay, g, _per) in enumerate(folds):
        bb, bl = brier(best, y), brier(lay, y)
        better = bl < bb
        n_better += int(better)
        per_fold.append({"fold": i, "n": int(len(y)),
                         "brier_best": round(float(bb), 4),
                         "brier_layer": round(float(bl), 4),
                         "delta": round(float(bb - bl), 5),
                         "layer_beats_best": bool(better)})
        ys.append(y); bs.append(best); ls.append(lay); gids += list(g)
    y = np.concatenate(ys); best = np.concatenate(bs); lay = np.concatenate(ls)
    bb, bl = float(brier(best, y)), float(brier(lay, y))
    d = (best - y) ** 2 - (lay - y) ** 2            # +ve => layer beats best
    dm = diebold_mariano(d, gids)
    consistent = n_better >= int(np.ceil(2 * len(folds) / 3.0))
    ship = (bl < bb) and (dm.p_value < 0.05) and consistent
    verdict = "SHIP" if ship else "REJECT"
    why = layer.why_ship if ship else layer.why_reject
    metrics = {"n_states": int(len(y)), "n_folds": len(folds),
               "brier_best": round(bb, 4), "brier_layer": round(bl, 4),
               "brier_delta": round(bb - bl, 5),
               "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
               "n_clusters": dm.n_clusters, "folds_layer_better": int(n_better),
               "fold_sign_consistent": bool(consistent)}
    return LadderVerdict(layer.name, verdict, why, metrics, per_fold)


def run_ladder(states_by_game, order, n_folds: int = 3) -> List[LadderVerdict]:
    return [gate_layer(states_by_game, order, lyr, n_folds=n_folds) for lyr in LAYERS]


# --------------------------------------------------------------------------- driver
def run(path=None) -> List[LadderVerdict]:
    df = load_linescores(path) if path else load_linescores()
    p0_map = leakfree_elo_p0(df)
    states = ladder_states_for_games(df, p0_map)
    by_game: Dict[int, List[dict]] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    order = [int(r["event_id"]) for _, r in df.iterrows()
             if int(r["event_id"]) in by_game]
    return run_ladder(by_game, order, n_folds=3)


def write(verdicts: List[LadderVerdict], out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    payload = {"current_best": "BASE+PRIOR (margin,time + leak-free Elo prior blend)",
               "ladder": [v.to_dict() for v in verdicts],
               "note": "Each layer gated independently vs current best on the same "
                       "leak-free WF + clustered DM. Honest REJECT is a valid outcome."}
    with open(out, "w", encoding="ascii") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    return out


def _report(verdicts: List[LadderVerdict]) -> str:
    lines = ["=" * 70,
             "IN-GAME DETAIL-LAYER LADDER (NBA) -- candidates vs current best BASE+PRIOR",
             "=" * 70]
    for v in verdicts:
        m = v.metrics
        lines.append(f"LAYER: {v.name}")
        lines.append(f"  verdict      : {v.verdict}")
        lines.append(f"  pooled Brier : best {m.get('brier_best')} -> "
                     f"+layer {m.get('brier_layer')}  (delta {m.get('brier_delta')})")
        lines.append(f"  DM clustered : stat {m.get('dm_stat')}  p {m.get('dm_p')}  "
                     f"clusters {m.get('n_clusters')}")
        lines.append(f"  fold consist : {m.get('folds_layer_better')}/"
                     f"{m.get('n_folds')} folds layer<best  "
                     f"consistent={m.get('fold_sign_consistent')}")
        for f in v.per_fold:
            lines.append(f"    fold {f['fold']}  n={f['n']:5d}  "
                         f"{f['brier_best']:.4f} -> {f['brier_layer']:.4f}  "
                         f"delta {f['delta']:+.5f}  better={f['layer_beats_best']}")
        lines.append(f"  WHY          : {v.why}")
        lines.append("-" * 70)
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    verdicts = run()
    p = write(verdicts)
    print(_report(verdicts))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
