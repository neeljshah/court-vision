"""scripts.platformkit.ingame.ingame_shooterprofile_gate_nba -- pre-registered
H_A/H_B in-game conditioning gates (basketball_truth_spec.json wave-26/27,
"ingame_hypotheses"). Clone of ingame_layer_gate_nba.py's walk-forward pattern
with a --layer {hot_night,scheme_fit} flag, exactly as pre-registered. State
construction + TRAIN-only gating + planted-null shuffles live in the companion
ingame_shooterprofile_gate_nba_io.py (kept <=300 LOC/file); this file holds the
sport-blind walk-forward/DM verdict driver shared by both layers.

THE QUESTIONS (both condition the GAME-level (margin,time) BASE win-prob model on
an AS-OF PLAYER-PROFILE prior -- no player-level in-game scoring feed exists on
disk, per the spec's data_constraint):

  H_A hot_night : does a team's top shooter/scorer_quality_v1 prior, ACTIVE ONLY
                  on a hot-team-shooting-night (team eFG% above its own season-
                  to-date mean by the 60th-pct TRAIN-fold threshold), beat the
                  (margin,time) BASE on held-out Brier?
  H_B scheme_fit: does the offense's top-scorer by_scheme TS% against the
                  defense's dominant coverage scheme, ACTIVE ONLY in the top/
                  bottom TRAIN-fold tercile of scheme-fit, beat BASE?

BASE   = p_live(score_diff, frac_elapsed)          # margin+time only, no prior
+PRIOR = blend(p0, p_live, w(time,margin))         # w fit on TRAIN fold ONLY
         p0 = the layer's conditioning prior, ACTIVE only on the gated condition;
         off-condition states get a NEUTRAL p0=0.5 so the gate isolates the
         CONDITIONAL lift the spec claims, not an unconditional main effect.

DISCIPLINE (inherited verbatim from ingame_layer_gate_nba.py):
  * >=3 expanding-window walk-forward folds; w fit on TRAIN only.
  * Pooled OOS Brier; DM clustered by game_id, p<0.05; sign >=2/3 folds.
  * PLANTED NULL (binding, pre-registered): shuffle the conditioning assignment
    (H_A: player-profile across teams; H_B: opponent-scheme assignment), re-run
    the SAME gate, confirm the shuffled prior's Brier-delta CI includes 0. If the
    shuffled prior ALSO "wins", the real result is a flexibility artifact -> REJECT.
  * GATE-COMPARABILITY: real and planted-null runs share the identical start
    state, corpus slice, and eval path -- only the conditioning assignment differs.

CAVEAT (carried honestly, same framing the spec itself uses for the pregame
indices): shooter_quality_v1/scorer_quality_v1 and the scheme atlas are SEASON-
LEVEL snapshots (as_of a single date spanning the whole disk window), not
per-game walk-forward-recomputed priors -- a season-level caveat, not a
per-game leak. The (margin,time) BASE and the outcome labels ARE leak-free
(no walk-forward Elo used here; BASE only reads realized as-of score).

VERDICT: CALIBRATION only (held-out Brier), never a $ edge. REJECT/NOT_TESTABLE
is a fully valid, logged result.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy+pandas+stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_shooterprofile_gate_nba --layer hot_night
     python -m scripts.platformkit.ingame.ingame_shooterprofile_gate_nba --layer scheme_fit
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.ingame_blend import blended_predictions, fit_weight_surface
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_shooterprofile_gate_nba_io import (
    apply_hot_night_gate,
    apply_scheme_tercile_gate,
    bridge_games,
    build_states_hot_night,
    build_states_scheme_fit,
    load_boxscores,
    load_linescores,
    shuffle_hot_night,
    shuffle_scheme_fit,
    team_game_efg,
    team_top_quality_by_game,
    write,
)

_MIN_CELL = 20
_N_FOLDS = 3
_MIN_STATES_PER_CONDITION = 100  # spec floor; reported, not silently downgraded

_LAYERS = {
    "hot_night": (build_states_hot_night, apply_hot_night_gate, shuffle_hot_night),
    "scheme_fit": (build_states_scheme_fit, apply_scheme_tercile_gate, shuffle_scheme_fit),
}


# ------------------------------------------------------------- walk-forward gate
@dataclass
class HypothesisVerdict:
    verdict: str
    layer: str
    metrics: Dict[str, object] = field(default_factory=dict)
    planted_null: Dict[str, object] = field(default_factory=dict)
    per_fold: List[Dict[str, float]] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {"verdict": self.verdict, "layer": self.layer,
                "vs_close": "UNPROVEN -- no in-play odds; CALIBRATION only, never a market edge",
                "metrics": self.metrics, "planted_null": self.planted_null,
                "per_fold": self.per_fold, "caveats": list(self.caveats)}


def _fold_order(states: List[dict]) -> List[int]:
    """Chronological unique game_ids in first-seen order (bridge is date-sorted)."""
    seen, order = set(), []
    for s in states:
        if s["game_id"] not in seen:
            seen.add(s["game_id"]); order.append(s["game_id"])
    return order


def _walk_forward_folds(states: List[dict], order: List[int], gate_fn, n_folds: int = 3):
    n = len(order)
    if n < (n_folds + 1) * 2:
        n_folds = max(1, n // 2 - 1)
    bounds = [int(round(i * n / (n_folds + 1))) for i in range(n_folds + 2)]
    by_game: Dict[int, List[int]] = {}
    for i, s in enumerate(states):
        by_game.setdefault(s["game_id"], []).append(i)
    folds = []
    for k in range(1, n_folds + 1):
        train_games, test_games = order[:bounds[k]], order[bounds[k]:bounds[k + 1]]
        if not train_games or not test_games:
            continue
        train_idx = [i for g in train_games for i in by_game[g]]
        test_idx = [i for g in test_games for i in by_game[g]]
        gated, thresh = gate_fn(states, train_idx)
        train = [gated[i] for i in train_idx]
        test = [gated[i] for i in test_idx]
        folds.append((train, test, thresh))
    return folds


def run_gate(states: List[dict], gate_fn, n_folds: int = _N_FOLDS) -> Tuple[str, Dict, List[Dict]]:
    """Expanding-window walk-forward: w fit on TRAIN only (gate_fn also sets the
    TRAIN-only threshold/tercile), pooled OOS Brier(BASE) vs Brier(+PRIOR), DM
    clustered by game_id. NOT_TESTABLE if folds or the gated-state floor fail;
    else SHIP_CONDITIONAL_PRIOR / REJECT on the honest Brier+DM+sign gate."""
    order = _fold_order(states)
    folds = _walk_forward_folds(states, order, gate_fn, n_folds=n_folds)
    if not folds:
        return "NOT_TESTABLE", {"reason": "no usable walk-forward folds"}, []

    per_fold, n_better, n_gated_total = [], 0, 0
    ys_parts, bases_parts, priors_parts, gids_all = [], [], [], []
    for i, (train, test, thresh) in enumerate(folds):
        surf = fit_weight_surface(train, min_cell=_MIN_CELL)
        y = np.array([s["outcome"] for s in test], float)
        base = np.array([s["p_live"] for s in test], float)
        prior = blended_predictions(test, surf)
        gids = [s["game_id"] for s in test]
        gated_n = sum(1 for s in test if s["gated_on"])
        bb, bp = float(brier(base, y)), float(brier(prior, y))
        d = (base - y) ** 2 - (prior - y) ** 2
        dm = diebold_mariano(d, gids)
        better = bp < bb
        n_better += int(better)
        n_gated_total += gated_n
        per_fold.append({
            "fold": i, "n": int(len(y)), "n_gated": gated_n,
            "brier_base": round(bb, 4), "brier_prior": round(bp, 4),
            "delta": round(bb - bp, 5), "dm_p": round(dm.p_value, 6),
            "threshold": thresh if not isinstance(thresh, tuple) else list(thresh),
            "prior_beats_base": bool(better),
        })
        ys_parts.append(y); bases_parts.append(base); priors_parts.append(prior)
        gids_all += gids

    ys, bases, priors = np.concatenate(ys_parts), np.concatenate(bases_parts), np.concatenate(priors_parts)
    bb, bp = float(brier(bases, ys)), float(brier(priors, ys))
    d = (bases - ys) ** 2 - (priors - ys) ** 2
    dm = diebold_mariano(d, gids_all)
    consistent = n_better >= int(np.ceil(2 * len(folds) / 3.0))
    ship = (bp < bb) and (dm.p_value < 0.05) and consistent
    floor_ok = n_gated_total >= _MIN_STATES_PER_CONDITION

    metrics = {
        "n_states": int(len(ys)), "n_folds": len(folds), "n_gated_states": n_gated_total,
        "meets_min_gated_floor": floor_ok,
        "brier_base": round(bb, 4), "brier_prior": round(bp, 4),
        "brier_delta": round(bb - bp, 5), "dm_stat": round(dm.dm_stat, 4),
        "dm_p": round(dm.p_value, 6), "dm_ci95": [round(dm.ci95[0], 5), round(dm.ci95[1], 5)],
        "n_clusters": dm.n_clusters, "folds_prior_better": n_better,
        "fold_sign_consistent": bool(consistent),
    }
    verdict = "NOT_TESTABLE" if not floor_ok else (
        "SHIP_CONDITIONAL_PRIOR" if ship else "REJECT")
    return verdict, metrics, per_fold


def _planted_null_dies(delta_ci: Tuple[float, float]) -> bool:
    """True iff the planted null did NOT significantly beat BASE in the PRIOR's
    favor -- i.e. the Brier-delta CI includes 0, OR is significant in the WRONG
    direction (base beats the shuffled prior, delta_ci entirely negative). Only
    a CI entirely POSITIVE (shuffled prior significantly beats base) counts as
    "survived" -- the flexibility-artifact failure mode the planted null guards
    against. A significant loss for the shuffled prior is not a survival."""
    lo, hi = delta_ci
    return not (lo > 0.0 and hi > 0.0)


# ------------------------------------------------------------------- driver
def run(layer: str) -> HypothesisVerdict:
    if layer not in _LAYERS:
        raise ValueError(f"unknown layer {layer!r}; must be one of {sorted(_LAYERS)}")
    build_fn, gate_fn, shuffle_fn = _LAYERS[layer]

    lines = load_linescores()
    box_all = load_boxscores()
    box = box_all[box_all["season"] == "2025-26"].copy()
    bridge = bridge_games(lines, box)
    caveats = [
        "BRIDGE: linescores (ESPN event_id) joined to player_boxscores (NBA game_id) "
        "on (home/away tricode, date) after normalizing 6 divergent ESPN<->NBA-stats "
        "abbreviations; a deterministic, outcome-free join key, restricted to the "
        "2025-26 overlap window.",
        "CAVEAT (season-level, same framing as spec Section 3a): shooter_quality_v1/"
        "scorer_quality_v1 and the scheme atlas are single as_of snapshots spanning "
        "the whole disk window, not per-game walk-forward-recomputed priors.",
        "Off-condition states get a NEUTRAL p0=0.5 so the gate isolates the "
        "CONDITIONAL lift the spec claims, not an unconditional main effect.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier), never a market "
        "edge. No $ anywhere.",
    ]
    if layer == "hot_night":
        quality = team_top_quality_by_game(box)
        efg_df = team_game_efg(box)
        states = build_fn(bridge, box, quality, efg_df)
    else:
        states = build_fn(bridge, box)

    verdict, metrics, per_fold = run_gate(states, gate_fn)

    # PLANTED NULL: identical corpus/machinery/eval path (GATE-COMPARABILITY RULE),
    # only the conditioning assignment is shuffled.
    shuffled_states = shuffle_fn(states, seed=0)
    pn_verdict, pn_metrics, _ = run_gate(shuffled_states, gate_fn)
    pn_dies = _planted_null_dies(tuple(pn_metrics.get("dm_ci95", (0.0, 0.0)))) \
        if "dm_ci95" in pn_metrics else True
    planted_null = {
        "verdict": pn_verdict, "brier_delta": pn_metrics.get("brier_delta"),
        "dm_p": pn_metrics.get("dm_p"), "dm_ci95": pn_metrics.get("dm_ci95"),
        "planted_null_dies": bool(pn_dies),
    }

    final_verdict = verdict
    if verdict == "SHIP_CONDITIONAL_PRIOR" and not pn_dies:
        final_verdict = "REJECT"
        caveats.append(
            "PLANTED NULL SURVIVED: the shuffled conditioning prior ALSO beat BASE "
            "(delta CI excludes 0) -- the real result is a flexibility artifact, not "
            "a genuine conditional signal. Downgraded SHIP -> REJECT per pre-registration.")

    return HypothesisVerdict(final_verdict, layer, metrics, planted_null, per_fold, caveats)


def _report(v: HypothesisVerdict) -> str:
    m = v.metrics
    lines = ["=" * 72, f"IN-GAME H_A/H_B GATE (NBA): layer={v.layer}", "=" * 72,
             f"verdict          : {v.verdict}",
             f"pooled OOS Brier : BASE {m.get('brier_base')}  +PRIOR {m.get('brier_prior')}"
             f"  (delta {m.get('brier_delta')})",
             f"DM (clustered)   : stat {m.get('dm_stat')}  p {m.get('dm_p')}  "
             f"ci95 {m.get('dm_ci95')}",
             f"fold consistency : {m.get('folds_prior_better')}/{m.get('n_folds')} "
             f"consistent={m.get('fold_sign_consistent')}",
             f"gated states     : {m.get('n_gated_states')}  "
             f"meets_floor({_MIN_STATES_PER_CONDITION})={m.get('meets_min_gated_floor')}",
             "-" * 72, "PLANTED NULL (shuffle conditioning assignment):",
             f"  verdict={v.planted_null.get('verdict')}  "
             f"delta={v.planted_null.get('brier_delta')}  "
             f"dm_p={v.planted_null.get('dm_p')}  "
             f"dies={v.planted_null.get('planted_null_dies')}", "-" * 72]
    for f in v.per_fold:
        lines.append(f"  fold {f['fold']}  n={f['n']:4d} gated={f['n_gated']:4d}  "
                     f"{f['brier_base']:.4f} -> {f['brier_prior']:.4f}  "
                     f"delta {f['delta']:+.5f}  p={f['dm_p']:.4f}")
    for cv in v.caveats:
        lines.append(f"  - {cv}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="H_A/H_B in-game conditioning gate (NBA).")
    ap.add_argument("--layer", choices=["hot_night", "scheme_fit"], required=True)
    a = ap.parse_args(argv)
    v = run(a.layer)
    print(_report(v))
    path = write(v.to_dict(), f"ingame_hypothesis_{a.layer}.json")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
