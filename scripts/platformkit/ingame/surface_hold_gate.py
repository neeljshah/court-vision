"""scripts.platformkit.ingame.surface_hold_gate -- GATE the tennis SURFACE-SPECIFIC
hold% detail layer vs the surface-BLIND hold% baseline, leak-free + walk-forward, on
held-out Brier. Clone of ingame_layer_gate_nba.py's fold/DM/verdict machinery, adapted
to compare TWO PRIORS (blind vs surface) instead of BASE-vs-PRIOR.

THE QUESTION (intelligence_program.json rank 5 / tennis_truth_spec.json H1): does
blending in the SURFACE-SPECIFIC as-of hold% prior (p1/p2_hold_pct_{surface}_asof)
beat the surface-BLIND as-of hold% prior (p1/p2_hold_pct_asof) as a detail layer atop
the same frozen (state_diff, frac_elapsed) BASE in-game model?

TWO ARMS over the same leak-free in-game states (end-of-set asof ticks):
  BLIND     = blend(p0_blind,    p_live, w(time,margin))   # surface-pooled hold prior
  SURFACE   = blend(p0_surface,  p_live, w(time,margin))   # surface-specific hold prior
  w is fit PER ARM on the TRAIN fold only (never the test fold) via the shared
  fit_weight_surface/blended_predictions (scripts.platformkit.eval_gate.ingame_blend).

DISCIPLINE (identical to the NBA reference gate):
  * >=3 expanding-window walk-forward folds where the corpus allows (else record the
    exact n and return INSUFFICIENT -- not a forced REJECT).
  * DM clustered by game_id (naive iid SE manufactures fake significance).
  * PLANTED-NULL: shuffle the surface label assignment across matches before deriving
    p0_surface -- if the "surface" layer still beats blind, it is an artifact, not a
    real surface effect -> verdict must fall back to NOT_TESTABLE for that run.
  * Runs BOTH corpora independently: ATP (asof_hold.parquet) and WTA
    (asof_hold_wta.parquet) -- ship requires the sign to replicate on both tours.

VERDICT: SHIP_SURFACE_LAYER iff (per tour) Brier(SURFACE) < Brier(BLIND) AND DM
p<0.05 AND fold-sign-consistent, on BOTH tours, AND the planted-null does NOT ship.
Else REJECT (honest, not a failure). INSUFFICIENT if either tour cannot form
>=3 folds at the min_states_per_surface_cell floor -- record exact n, never fabricate.

Pregame framing: MATCH-not-beat expected (market efficient); this is a CALIBRATION
gate (held-out Brier), never a $ edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.surface_hold_gate
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
from scripts.platformkit.ingame.surface_hold_gate_io import (
    MIN_STATES_PER_SURFACE_CELL,
    OUT,
    chronological_game_order,
    states_with_priors,
)

MIN_FOLDS = 3


# --------------------------------------------------------------------------- folds
def _arm_states(states: List[dict], p0_key: str) -> List[dict]:
    """Project the shared state list onto ONE arm's prior (p0=p0_blind or p0_surface)
    so it can be fed straight into the shared fit_weight_surface/blended_predictions."""
    return [{**s, "p0": s[p0_key]} for s in states]


def _fold_predictions(train: List[dict], test: List[dict]):
    """Fit BOTH arms' weight surfaces on TRAIN only, predict on TEST. Returns
    (y, blind_pred, surface_pred, game_ids)."""
    surf_blind = fit_weight_surface(_arm_states(train, "p0_blind"), min_cell=20)
    surf_spec = fit_weight_surface(_arm_states(train, "p0_surface"), min_cell=20)
    y = np.array([s["outcome"] for s in test], float)
    blind = blended_predictions(_arm_states(test, "p0_blind"), surf_blind)
    spec = blended_predictions(_arm_states(test, "p0_surface"), surf_spec)
    gids = [s["game_id"] for s in test]
    return y, blind, spec, gids


def walk_forward(states_by_game: Dict[str, List[dict]], order: List[str],
                 n_folds: int = MIN_FOLDS):
    """Expanding-window walk-forward over games in chronological `order`. Identical
    fold-boundary logic to ingame_layer_gate_nba.walk_forward."""
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
class SurfaceHoldVerdict:
    verdict: str
    metrics: Dict[str, object] = field(default_factory=dict)
    per_fold: List[Dict[str, float]] = field(default_factory=list)
    per_tour: Dict[str, Dict] = field(default_factory=dict)
    planted_null: Dict[str, object] = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "layer": "surface_specific_hold_pct_prior",
            "baseline": "surface_blind_hold_pct_prior",
            "hypothesis": "H1_surface_hold_pregame_conditioning",
            "vs_close": "MATCH-not-beat expected (pregame); this arm is CALIBRATION "
                        "(held-out Brier vs the surface-blind prior), never a market edge",
            "metrics": self.metrics,
            "per_fold": self.per_fold,
            "per_tour": self.per_tour,
            "planted_null": self.planted_null,
            "caveats": list(self.caveats),
        }


def _one_tour_gate(states: List[dict], n_folds: int = MIN_FOLDS) -> Dict:
    """Run the walk-forward gate for ONE tour's states; returns a metrics dict
    (not yet the final cross-tour verdict)."""
    by_game: Dict[str, List[dict]] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    order = chronological_game_order(states)
    n_games = len(order)
    if n_games < (MIN_FOLDS + 1) * 2 or len(states) < MIN_STATES_PER_SURFACE_CELL:
        return {
            "verdict": "INSUFFICIENT", "n_games": n_games, "n_states": len(states),
            "reason": f"n_games={n_games} states={len(states)} below floor "
                      f"(need >={(MIN_FOLDS + 1) * 2} games and "
                      f">={MIN_STATES_PER_SURFACE_CELL} states)",
        }
    folds = walk_forward(by_game, order, n_folds=n_folds)
    if not folds:
        return {"verdict": "INSUFFICIENT", "n_games": n_games, "n_states": len(states),
                "reason": "no usable folds"}

    ys, blinds, specs, gids_all = [], [], [], []
    per_fold: List[Dict[str, float]] = []
    n_spec_better = 0
    for i, (y, blind, spec, gids) in enumerate(folds):
        bb, bs = brier(blind, y), brier(spec, y)
        better = bs < bb
        n_spec_better += int(better)
        per_fold.append({
            "fold": i, "n": int(len(y)),
            "brier_blind": round(float(bb), 4), "brier_surface": round(float(bs), 4),
            "delta": round(float(bb - bs), 5), "surface_beats_blind": bool(better),
        })
        ys.append(y); blinds.append(blind); specs.append(spec); gids_all += list(gids)
    y = np.concatenate(ys); blind = np.concatenate(blinds); spec = np.concatenate(specs)

    brier_blind = float(brier(blind, y))
    brier_surface = float(brier(spec, y))
    d = (blind - y) ** 2 - (spec - y) ** 2   # +ve => surface layer beats blind
    dm = diebold_mariano(d, gids_all)
    consistent = n_spec_better >= int(np.ceil(2 * len(folds) / 3.0))
    ship = (brier_surface < brier_blind) and (dm.p_value < 0.05) and consistent

    return {
        "verdict": "SHIP" if ship else "REJECT",
        "n_games": n_games, "n_states": int(len(y)), "n_folds": len(folds),
        "brier_blind": round(brier_blind, 4), "brier_surface": round(brier_surface, 4),
        "brier_delta": round(brier_blind - brier_surface, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "n_clusters": dm.n_clusters, "folds_surface_better": int(n_spec_better),
        "fold_sign_consistent": bool(consistent), "per_fold": per_fold,
    }


def _planted_null_gate(states: List[dict], seed: int = 0,
                       n_folds: int = MIN_FOLDS) -> Dict:
    """Shuffle p0_surface assignment ACROSS MATCHES (break the surface<->prior link)
    before running the identical gate. A real surface effect must die; if it still
    ships, the real result is an artifact -> caller marks NOT_TESTABLE."""
    rng = np.random.default_rng(seed)
    by_game: Dict[str, List[dict]] = {}
    for s in states:
        by_game.setdefault(s["game_id"], []).append(s)
    game_ids = list(by_game.keys())
    shuffled_ids = rng.permutation(game_ids)
    surf_map = {g: by_game[old][0]["p0_surface"] for g, old in zip(game_ids, shuffled_ids)}
    shuffled_states = [{**s, "p0_surface": surf_map[s["game_id"]]} for s in states]
    return _one_tour_gate(shuffled_states, n_folds=n_folds)


def gate_tour(tour: str, n_folds: int = MIN_FOLDS, seed: int = 0) -> Dict:
    """Real gate + planted-null for one tour ('atp' or 'wta')."""
    states = states_with_priors(tour)
    real = _one_tour_gate(states, n_folds=n_folds)
    null = (_planted_null_gate(states, seed=seed, n_folds=n_folds)
            if real["verdict"] in ("SHIP", "REJECT") else
            {"verdict": "SKIPPED", "reason": "real arm INSUFFICIENT"})
    return {"tour": tour, "n_states_total": len(states), "real": real,
            "planted_null": null}


def gate(n_folds: int = MIN_FOLDS, seed: int = 0) -> SurfaceHoldVerdict:
    """Run BOTH tours (ATP + WTA as independent corpora), roll up the honest
    cross-tour verdict."""
    caveats = [
        "Leak-free: p0_blind/p0_surface are strictly as-of hold-pct priors from "
        "asof_hold*.parquet (own future-leak assertion enforced at build time); "
        "w fit on TRAIN fold only per arm.",
        "Both priors squashed via the SAME fixed (never-fit) logistic k=4.0 -- only "
        "the source hold-pct column differs between arms.",
        "Carpet/Unknown-surface rows excluded (no surface-specific column exists), "
        "never imputed.",
        "No in-play tennis odds backfill -> verdict is CALIBRATION (held-out Brier), "
        "never a market edge. MATCH-not-beat is the honest pregame expectation.",
    ]
    per_tour = {}
    for tour in ("atp", "wta"):
        per_tour[tour] = gate_tour(tour, n_folds=n_folds, seed=seed)

    reals = {t: per_tour[t]["real"] for t in per_tour}
    nulls = {t: per_tour[t]["planted_null"] for t in per_tour}
    insufficient = [t for t, r in reals.items() if r["verdict"] == "INSUFFICIENT"]

    if insufficient:
        verdict = "INSUFFICIENT"
        metrics = {"insufficient_tours": insufficient,
                   "detail": {t: reals[t] for t in insufficient}}
        return SurfaceHoldVerdict(verdict, metrics, [], per_tour, nulls, caveats)

    both_ship = all(reals[t]["verdict"] == "SHIP" for t in reals)
    null_dies = all(nulls[t].get("verdict") != "SHIP" for t in nulls if "verdict" in nulls[t])

    if both_ship and not null_dies:
        verdict = "NOT_TESTABLE"
        caveats.append("Planted-null (shuffled surface label) also SHIPPED -- the real "
                        "result cannot be distinguished from an artifact.")
    elif both_ship and null_dies:
        verdict = "SHIP_SURFACE_LAYER"
    else:
        verdict = "REJECT"

    metrics = {
        "atp_verdict": reals["atp"]["verdict"], "wta_verdict": reals["wta"]["verdict"],
        "atp_brier_delta": reals["atp"].get("brier_delta"),
        "wta_brier_delta": reals["wta"].get("brier_delta"),
        "atp_dm_p": reals["atp"].get("dm_p"), "wta_dm_p": reals["wta"].get("dm_p"),
        "null_atp_verdict": nulls["atp"].get("verdict"),
        "null_wta_verdict": nulls["wta"].get("verdict"),
        "both_tours_ship": both_ship, "planted_null_dies": null_dies,
    }
    return SurfaceHoldVerdict(verdict, metrics, [], per_tour, nulls, caveats)


def write(verdict: SurfaceHoldVerdict, out: str = OUT) -> str:
    import datetime
    os.makedirs(os.path.dirname(out), exist_ok=True)
    d = verdict.to_dict()
    d["pre_registered_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(out, "w", encoding="ascii") as f:
        json.dump(d, f, indent=2, sort_keys=True)
    return out


def _report(v: SurfaceHoldVerdict) -> str:
    lines = ["=" * 64, "TENNIS SURFACE-HOLD IN-GAME DETAIL-LAYER GATE (H1)", "=" * 64,
             f"verdict: {v.verdict}"]
    for t, d in v.per_tour.items():
        r = d["real"]
        lines.append(f"-- {t.upper()} -- verdict={r['verdict']} "
                     f"n_games={r.get('n_games')} n_states={r.get('n_states')}")
        if r["verdict"] not in ("INSUFFICIENT",):
            lines.append(f"   Brier blind {r['brier_blind']} -> surface {r['brier_surface']}"
                         f"  delta {r['brier_delta']:+.5f}  DM p={r['dm_p']}")
        n = d["planted_null"]
        lines.append(f"   planted-null verdict={n.get('verdict')}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main() -> None:
    v = gate()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
