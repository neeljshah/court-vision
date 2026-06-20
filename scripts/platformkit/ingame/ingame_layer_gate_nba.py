"""scripts.platformkit.ingame.ingame_layer_gate_nba -- GATE one DETAIL LAYER vs a
simpler BASE in-game win-prob model, leak-free + walk-forward, on held-out Brier.

THE QUESTION (P3): does adding the PREGAME PRIOR as a detail layer beat a pure
(margin, time) BASE in-game win-prob model on held-out NBA Brier? Ship the layer
ONLY if it improves OOS calibration with significance.

TWO MODELS over the reconstructed end-Q1/Q2/Q3 states:
  BASE   = p_live(score_diff, frac_elapsed)            # (margin,time) only, NO prior
  +PRIOR = blend(p0, p_live, w(time,margin))           # BASE + leak-free Elo p0, w fit
           where p0 = strictly-pregame Elo prob (per game, as-of date) and the weight
           surface w is fit on the TRAIN fold ONLY (never the test fold).

DISCIPLINE (hard-learned -- single-fold lifts are artifacts):
  * MULTIPLE expanding-window walk-forward cutoffs (>=3), not one split.
  * w is fit ONLY on train states each fold; predictions on held-out test states.
  * Pooled OOS Brier across folds + per-fold Brier for stability.
  * DM clustered by game_id (a naive iid SE manufactures fake significance).

VERDICT (honest, gated): SHIP_PRIOR_LAYER iff Brier(+PRIOR) < Brier(BASE) AND DM
p<0.05 AND the +PRIOR-beats-BASE sign holds on >=2/3 folds. Else REJECT (the prior
layer does not beat base OOS -- a valid, honest result). Per-quarter breakdown is
reported: the prior helping MOST at end-Q1 and LEAST at end-Q3 is the tell the gain
is a REAL early-game team-strength signal, not a shrink-to-current artifact.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_layer_gate_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import (
    blended_predictions,
    fit_weight_surface,
)
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    OUT,
    leakfree_elo_p0,
    load_linescores,
    states_for_games,
)


# --------------------------------------------------------------------------- folds
def _fold_predictions(train: List[dict], test: List[dict]):
    """Fit the weight surface on TRAIN states only, predict BASE and +PRIOR on TEST.

    BASE   = p_live (margin,time only).  +PRIOR = blend(p0, p_live, w) with w fit on
    TRAIN. Returns (y, base_pred, prior_pred, game_ids) for the held-out test states.
    Leak-free: the surface never sees a test outcome.
    """
    surf = fit_weight_surface(train, min_cell=20)
    y = np.array([s["outcome"] for s in test], float)
    base = np.array([s["p_live"] for s in test], float)
    prior = blended_predictions(test, surf)
    gids = [s["game_id"] for s in test]
    periods = [s["period"] for s in test]
    return y, base, prior, gids, periods


def walk_forward(states_by_game: Dict[int, List[dict]], order: List[int],
                 n_folds: int = 3):
    """Expanding-window walk-forward over games in chronological `order`.

    Splits the game sequence into n_folds+1 contiguous blocks. Fold k fits on all games
    BEFORE block k+1 and tests on block k+1 (so every test block is strictly later than
    its train window). Yields per-fold (y, base, prior, game_ids, periods).
    """
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
        folds.append(_fold_predictions(train, test))
    return folds


# --------------------------------------------------------------------------- verdict
@dataclass
class LayerVerdict:
    verdict: str
    metrics: Dict[str, object] = field(default_factory=dict)
    per_fold: List[Dict[str, float]] = field(default_factory=list)
    per_quarter: Dict[str, Dict[str, float]] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layer": "pregame_elo_prior",
            "base_model": "p_live(margin,time) only -- NO team prior",
            "prior_model": "blend(p0_elo, p_live, w(time,margin)); w fit on TRAIN only",
            "baseline": "in_game_base_margin_time",
            "vs_close": "UNPROVEN -- no in-play odds; CALIBRATION only, not a market edge",
            "metrics": self.metrics,
            "per_fold": self.per_fold,
            "per_quarter": self.per_quarter,
            "caveats": list(self.caveats),
        }


def _per_quarter(y, base, prior, periods) -> Dict[str, Dict[str, float]]:
    """Pooled OOS Brier(BASE) vs Brier(+PRIOR) split by as-of quarter (1/2/3)."""
    out: Dict[str, Dict[str, float]] = {}
    periods = np.asarray(periods)
    for q in (1, 2, 3):
        m = periods == q
        if not m.any():
            continue
        bb, bp = brier(base[m], y[m]), brier(prior[m], y[m])
        out[f"endQ{q}"] = {
            "brier_base": round(float(bb), 4), "brier_prior": round(float(bp), 4),
            "delta": round(float(bb - bp), 5), "n": int(m.sum()),
        }
    return out


def gate(states_by_game: Dict[int, List[dict]], order: List[int],
         n_folds: int = 3, caveats: Optional[List[str]] = None) -> LayerVerdict:
    """Run the walk-forward gate and return an honest SHIP/REJECT LayerVerdict."""
    folds = walk_forward(states_by_game, order, n_folds=n_folds)
    if not folds:
        return LayerVerdict("REJECT", {"reason": "no usable folds"}, [], {}, caveats or [])

    ys, bases, priors, gids, periods = [], [], [], [], []
    per_fold: List[Dict[str, float]] = []
    n_prior_better = 0
    for i, (y, base, prior, g, per) in enumerate(folds):
        bb, bp = brier(base, y), brier(prior, y)
        better = bp < bb
        n_prior_better += int(better)
        per_fold.append({
            "fold": i, "n": int(len(y)),
            "brier_base": round(float(bb), 4), "brier_prior": round(float(bp), 4),
            "delta": round(float(bb - bp), 5),
            "prior_beats_base": bool(better),
        })
        ys.append(y); bases.append(base); priors.append(prior)
        gids += list(g); periods += list(per)
    y = np.concatenate(ys); base = np.concatenate(bases); prior = np.concatenate(priors)

    per_q = _per_quarter(y, base, prior, periods)

    brier_base = float(brier(base, y))
    brier_prior = float(brier(prior, y))
    d = (base - y) ** 2 - (prior - y) ** 2          # +ve => prior layer beats base
    dm = diebold_mariano(d, gids)

    consistent = n_prior_better >= int(np.ceil(2 * len(folds) / 3.0))
    ship = (brier_prior < brier_base) and (dm.p_value < 0.05) and consistent
    verdict = "SHIP_PRIOR_LAYER" if ship else "REJECT"

    metrics = {
        "n_states": int(len(y)), "n_folds": len(folds),
        "brier_base": round(brier_base, 4), "brier_prior": round(brier_prior, 4),
        "brier_delta": round(brier_base - brier_prior, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "n_clusters": dm.n_clusters,
        "folds_prior_better": int(n_prior_better),
        "fold_sign_consistent": bool(consistent),
    }
    return LayerVerdict(verdict, metrics, per_fold, per_q, list(caveats or []))


# --------------------------------------------------------------------------- driver
def run(path=None) -> LayerVerdict:
    """Load the real NBA linescore corpus, build leak-free states, run the gate."""
    df = load_linescores(path) if path else load_linescores()
    p0_map = leakfree_elo_p0(df)
    states = states_for_games(df, p0_map)
    by_game: Dict[int, List[dict]] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    # chronological game order (df already date-sorted)
    order = [int(r["event_id"]) for _, r in df.iterrows() if int(r["event_id"]) in by_game]
    caveats = [
        "Leak-free: p0 = STRICTLY pregame Elo snapshot (walk_forward_elo) -- a game "
        "never sees its own or any later outcome; w fit on TRAIN fold only.",
        "Single real season (2025-26) of linescores on disk -> expanding-window "
        "walk-forward WITHIN the season (>=3 folds), not cross-season OOS.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (margin,time) "
        "BASE, never a market edge. No $ anywhere.",
    ]
    return gate(by_game, order, n_folds=3, caveats=caveats)


def write(verdict: LayerVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _report(v: LayerVerdict) -> str:
    m = v.metrics
    lines = ["=" * 64, "IN-GAME DETAIL-LAYER GATE (NBA): pregame Elo prior vs base",
             "=" * 64,
             f"verdict           : {v.verdict}",
             f"pooled OOS Brier  : BASE {m.get('brier_base')}  +PRIOR {m.get('brier_prior')}"
             f"  (delta {m.get('brier_delta')})",
             f"DM (clustered)    : stat {m.get('dm_stat')}  p {m.get('dm_p')}"
             f"  clusters {m.get('n_clusters')}",
             f"fold consistency  : {m.get('folds_prior_better')}/{m.get('n_folds')} "
             f"folds prior<base  consistent={m.get('fold_sign_consistent')}",
             "-" * 64, "per-fold (BASE -> +PRIOR Brier):"]
    for f in v.per_fold:
        lines.append(f"  fold {f['fold']}  n={f['n']:5d}  "
                     f"{f['brier_base']:.4f} -> {f['brier_prior']:.4f}  "
                     f"delta {f['delta']:+.5f}  prior_better={f['prior_beats_base']}")
    lines.append("-" * 64)
    lines.append("per-quarter pooled OOS (prior expected to help MOST at endQ1):")
    for q, d in v.per_quarter.items():
        lines.append(f"  {q}  n={d['n']:5d}  base {d['brier_base']:.4f} -> "
                     f"prior {d['brier_prior']:.4f}  delta {d['delta']:+.5f}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
