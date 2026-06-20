"""scripts.platformkit.ingame.ingame_crossval_nba -- CROSS-CORPUS replication of the
in-game DETAIL-LAYER beat (pregame Elo prior vs a (margin,time) BASE).

WHY: a single-season within-fold lift is a PROBABLE ARTIFACT until it replicates on an
INDEPENDENT corpus. The within-season gate (ingame_layer_gate_nba) proved the +PRIOR
layer beats BASE on 2025-26 OOS Brier. This module closes the proof-rail gap with a TRUE
A->B cross-corpus design: fit the blend weight surface on ALL of corpus A, then TEST it on
the HELD-OUT corpus B (leak-free by construction -- B's states never touch the fit), and
the reverse B->A. REPLICATED only if +PRIOR beats BASE with DM p<0.05 in BOTH directions.

LEAK-FREENESS:
  * p0 is each corpus's STRICTLY-pregame Elo snapshot (leakfree_elo_p0), computed
    independently per corpus -- a game never sees its own or any later outcome, and
    corpus A's Elo never sees corpus B (different seasons / disjoint games).
  * The weight surface w is fit on the ENTIRE train corpus and EVALUATED on the OTHER
    corpus -- the documented overfitting trap (never fit + evaluate w on the same data)
    is avoided structurally: train and test corpora are disjoint seasons.

REUSE: the existing gate's _io (load/leakfree_elo_p0/states_for_games) + eval_gate blend
(fit_weight_surface/blended_predictions) + scoring (brier) + dm_test. No fold logic is
duplicated here -- this is a single A->B train/test, NOT expanding-window folds.

VERDICT: REPLICATED iff +PRIOR<BASE Brier AND DM p<0.05 in BOTH A->B and B->A AND the
per-quarter pattern (prior helps MOST at endQ1, LEAST at endQ3 -- a real early-game
team-strength tell, not a shrink-to-current artifact) holds in both. Else PARTIAL/NOT.

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_crossval_nba
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
    leakfree_elo_p0,
    load_linescores,
    states_for_games,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_REPO, "data", "domains", "basketball_nba")
CORPUS_A = os.path.join(_DATA, "linescores_2024_25.parquet")  # 2024-25
CORPUS_B = os.path.join(_DATA, "linescores.parquet")           # 2025-26
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "crossval_nba.json")


# --------------------------------------------------------------------------- states
def states_from_path(path: str) -> List[dict]:
    """Load one linescore corpus and reconstruct its leak-free as-of in-game states.

    p0 is the corpus's OWN strictly-pregame Elo snapshot -- self-contained per season.
    Returns a flat list of state dicts (3 per game: end-Q1/Q2/Q3).
    """
    df = load_linescores(path)
    p0_map = leakfree_elo_p0(df)
    return states_for_games(df, p0_map)


def states_from_frame(df) -> List[dict]:
    """States from an already-loaded frame (used by the offline synthetic test path)."""
    p0_map = leakfree_elo_p0(df)
    return states_for_games(df, p0_map)


# --------------------------------------------------------------------------- one direction
def _per_quarter(y, base, prior, periods) -> Dict[str, Dict[str, float]]:
    """Pooled Brier(BASE) vs Brier(+PRIOR) split by as-of quarter (1/2/3)."""
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


def _quarter_pattern_holds(per_q: Dict[str, Dict[str, float]]) -> bool:
    """The tell: prior helps MOST at endQ1 and LEAST at endQ3 (delta monotone down)."""
    d1 = per_q.get("endQ1", {}).get("delta")
    d3 = per_q.get("endQ3", {}).get("delta")
    if d1 is None or d3 is None:
        return False
    # most help early, least help late; endQ1 delta must exceed endQ3 delta and be positive
    return bool(d1 > d3 and d1 > 0.0)


def cross_direction(train: List[dict], test: List[dict], min_cell: int = 20) -> Dict:
    """Fit the weight surface on the ENTIRE train corpus, score BASE vs +PRIOR on TEST.

    Leak-free: the surface never sees a test state (train/test are disjoint seasons).
    Returns pooled Brier(BASE/+PRIOR), clustered DM (by game_id), per-quarter pattern.
    """
    surf = fit_weight_surface(train, min_cell=min_cell)
    y = np.array([s["outcome"] for s in test], float)
    base = np.array([s["p_live"] for s in test], float)
    prior = blended_predictions(test, surf)
    gids = [s["game_id"] for s in test]
    periods = [s["period"] for s in test]

    bb, bp = float(brier(base, y)), float(brier(prior, y))
    d = (base - y) ** 2 - (prior - y) ** 2      # +ve => prior beats base
    dm = diebold_mariano(d, gids)
    per_q = _per_quarter(y, base, prior, periods)
    prior_beats = (bp < bb) and (dm.p_value < 0.05)
    return {
        "n_train_states": len(train), "n_test_states": len(test),
        "n_test_games": dm.n_clusters,
        "brier_base": round(bb, 4), "brier_prior": round(bp, 4),
        "brier_delta": round(bb - bp, 5),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "prior_beats_base": bool(prior_beats),
        "per_quarter": per_q,
        "quarter_pattern_holds": _quarter_pattern_holds(per_q),
    }


# --------------------------------------------------------------------------- verdict
@dataclass
class CrossVerdict:
    verdict: str
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "design": "true cross-corpus A<->B: fit w on whole train season, "
                      "test on held-out other season (NOT within-season folds)",
            "layer": "pregame_elo_prior",
            "base_model": "p_live(margin,time) only -- NO team prior",
            "corpus_a": "linescores_2024_25.parquet (2024-25)",
            "corpus_b": "linescores.parquet (2025-26)",
            "vs_close": "UNPROVEN -- no in-play odds; CALIBRATION only, not a market edge",
            "a_to_b": self.a_to_b,
            "b_to_a": self.b_to_a,
            "caveats": list(self.caveats),
        }


def decide(a_to_b: Dict, b_to_a: Dict, require_quarter_pattern: bool = True) -> str:
    """REPLICATED iff prior beats base (Brier + DM p<0.05) in BOTH directions, and
    (if required) the per-quarter pattern holds in both. PARTIAL if exactly one
    direction beats; NOT_REPLICATED if neither.
    """
    a_beat = bool(a_to_b.get("prior_beats_base"))
    b_beat = bool(b_to_a.get("prior_beats_base"))
    if a_beat and b_beat:
        if require_quarter_pattern and not (
            a_to_b.get("quarter_pattern_holds") and b_to_a.get("quarter_pattern_holds")
        ):
            return "PARTIAL"
        return "REPLICATED"
    if a_beat or b_beat:
        return "PARTIAL"
    return "NOT_REPLICATED"


def run_cross(states_a: List[dict], states_b: List[dict],
              require_quarter_pattern: bool = True,
              caveats: Optional[List[str]] = None) -> CrossVerdict:
    """Run both A->B and B->A and return an honest replication verdict."""
    a_to_b = cross_direction(states_a, states_b)   # train A, test B
    b_to_a = cross_direction(states_b, states_a)   # train B, test A
    verdict = decide(a_to_b, b_to_a, require_quarter_pattern)
    return CrossVerdict(verdict, a_to_b, b_to_a, list(caveats or []))


# --------------------------------------------------------------------------- driver
def run(path_a: str = CORPUS_A, path_b: str = CORPUS_B,
        require_quarter_pattern: bool = True) -> CrossVerdict:
    """Load both real corpora, build leak-free states, run the cross-corpus replication."""
    states_a = states_from_path(path_a)
    states_b = states_from_path(path_b)
    caveats = [
        "True cross-corpus: w fit on the WHOLE train season, tested on the held-out "
        "OTHER season -- disjoint games, leak-free by construction.",
        "p0 = STRICTLY pregame Elo snapshot per corpus; no game sees its own / a later "
        "outcome, and corpus A's Elo never sees corpus B.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (margin,time) "
        "BASE, never a market edge. No $ anywhere.",
        "REPLICATED requires +PRIOR<BASE with DM p<0.05 in BOTH directions; a single "
        "direction is PARTIAL (downgrades the beat to unreplicated).",
    ]
    return run_cross(states_a, states_b, require_quarter_pattern, caveats)


def write(verdict: CrossVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _dir_report(name: str, d: Dict) -> List[str]:
    pq = d.get("per_quarter", {})
    lines = [
        f"  {name}: train n={d.get('n_train_states')} -> test n={d.get('n_test_states')} "
        f"({d.get('n_test_games')} games)",
        f"    pooled OOS Brier : BASE {d.get('brier_base')}  +PRIOR {d.get('brier_prior')}"
        f"  (delta {d.get('brier_delta')})",
        f"    DM (clustered)   : stat {d.get('dm_stat')}  p {d.get('dm_p')}",
        f"    prior_beats_base : {d.get('prior_beats_base')}   "
        f"quarter_pattern_holds : {d.get('quarter_pattern_holds')}",
        "    per-quarter (delta = base-prior, >0 = prior helps):",
    ]
    for q in ("endQ1", "endQ2", "endQ3"):
        if q in pq:
            r = pq[q]
            lines.append(f"      {q} n={r['n']:5d}  base {r['brier_base']:.4f} -> "
                         f"prior {r['brier_prior']:.4f}  delta {r['delta']:+.5f}")
    return lines


def _report(v: CrossVerdict) -> str:
    lines = ["=" * 70,
             "IN-GAME DETAIL-LAYER CROSS-CORPUS REPLICATION (NBA): Elo prior vs base",
             "=" * 70,
             f"VERDICT : {v.verdict}",
             "-" * 70]
    lines += _dir_report("A->B (train 2024-25, test 2025-26)", v.a_to_b)
    lines.append("-" * 70)
    lines += _dir_report("B->A (train 2025-26, test 2024-25)", v.b_to_a)
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    v = run()
    p = write(v)
    print(_report(v))
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
