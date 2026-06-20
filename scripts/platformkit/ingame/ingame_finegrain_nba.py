"""scripts.platformkit.ingame.ingame_finegrain_nba -- does the +PRIOR detail layer still
beat the (margin,time) BASE at FINE in-game time resolution, not just the 3 Q-boundaries?

The Q-boundary gate + cross-corpus replication proved a pregame-Elo PRIOR layer beats a
(margin,time) BASE on held-out NBA Brier, evaluated at end-Q1/Q2/Q3. But the model SERVES at
any clock / any margin. This module deepens "use EVERY detail" by reconstructing as-of states
at ~2-minute regulation intervals (domains.basketball_nba.ingest_pbp_states) and re-running
the SAME true cross-corpus design at fine resolution:

  BASE   = p_live(margin, frac_elapsed)                 # (margin,time) only, NO prior
  +PRIOR = blend(p0_elo, p_live, w(time,margin))        # w fit on the WHOLE train season
           p0 = leak-free strictly-pregame Elo snapshot (reused from _io, per game).

DESIGN (no fold logic duplicated -- reuses ingame_crossval_nba.cross_direction):
  * fit w on ALL of season A's FINE states, test on season B's fine states; and reverse.
  * pooled OOS Brier(BASE) vs Brier(+PRIOR); DM CLUSTERED BY game_id (many states per game
    now, so per-state iid SE would massively over-state significance -- clustering is the
    load-bearing guard at fine resolution).
  * REPLICATED iff +PRIOR<BASE with DM p<0.05 in BOTH directions.
  * Brier by ELAPSED-TIME bucket: does the prior still help MOST early and fade late (the
    real early-game team-strength tell), as it did at the Q-boundaries?

NO $ anywhere; verdict is CALIBRATION (Brier), never a market edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; numpy/pandas + stdlib.
CLI: python -m scripts.platformkit.ingame.ingame_finegrain_nba
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_crossval_nba import cross_direction, decide
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    leakfree_elo_p0,
    load_linescores,
    p_live_from_margin,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DATA = os.path.join(_REPO, "data", "domains", "basketball_nba")
_CACHE = os.path.join(_REPO, "data", "cache", "ingame")
LINES_A = os.path.join(_DATA, "linescores_2024_25.parquet")   # 2024-25
LINES_B = os.path.join(_DATA, "linescores.parquet")            # 2025-26
PBP_A = os.path.join(_CACHE, "pbp_states_2024_25.parquet")
PBP_B = os.path.join(_CACHE, "pbp_states_2025_26.parquet")
OUT = os.path.join(_REPO, "data", "frontend", "ingame", "finegrain_nba.json")

_REG_SEC = 2880.0
# Elapsed-time buckets (fraction of regulation elapsed) for the early->late breakdown.
_ELAPSED_EDGES = (0.0, 0.25, 0.5, 0.75, 1.0)
_ELAPSED_LABELS = ("q1", "q2", "q3", "q4")


def _period_of(seconds_remaining: float) -> int:
    """Regulation period (1..4) for a seconds-remaining value (for the reused per-quarter
    breakdown in cross_direction; the elapsed-bucket read is the primary fine-res view)."""
    elapsed = _REG_SEC - max(0.0, min(_REG_SEC, seconds_remaining))
    return min(4, 1 + int(elapsed // 720.0))


def states_from_pbp(pbp_path: str, lines_path: str) -> List[dict]:
    """Build leak-free fine-grained state dicts from a PBP-states parquet.

    p0 = the season's STRICTLY-pregame Elo snapshot (leakfree_elo_p0 over its linescores),
    joined per event_id. p_live = BASE (margin, frac_elapsed). outcome = realized home_win.
    Each row is one as-of grid point (~2-min). Games whose event_id has no Elo p0 are
    dropped (cannot form a leak-free prior). Returns a flat list of state dicts.
    """
    pbp = pd.read_parquet(pbp_path)
    lines = load_linescores(lines_path)
    p0_map = leakfree_elo_p0(lines)
    out: List[dict] = []
    for r in pbp.itertuples(index=False):
        gid = int(r.event_id)
        if gid not in p0_map:
            continue
        sr = float(r.seconds_remaining)
        diff = float(r.home_margin)
        frac = 1.0 - sr / _REG_SEC
        out.append({
            "game_id": gid,
            "seconds_remaining": sr,
            "score_diff": diff,
            "frac_elapsed": frac,
            "period": _period_of(sr),
            "p0": float(p0_map[gid]),
            "p_live": p_live_from_margin(diff, frac),
            "outcome": int(r.home_win),
        })
    return out


def _elapsed_breakdown(states: List[dict], surf) -> Dict[str, Dict[str, float]]:
    """Pooled Brier(BASE) vs Brier(+PRIOR) by ELAPSED-time bucket (q1..q4 = freshness).

    Recomputes blended predictions per bucket using the SAME fitted surface so the
    early->late pattern is read on the held-out test states. Returns delta>0 = prior helps.
    """
    from scripts.platformkit.eval_gate.ingame_blend import blended_predictions
    y = np.array([s["outcome"] for s in states], float)
    base = np.array([s["p_live"] for s in states], float)
    prior = blended_predictions(states, surf)
    frac = np.array([s["frac_elapsed"] for s in states], float)
    out: Dict[str, Dict[str, float]] = {}
    for k, lab in enumerate(_ELAPSED_LABELS):
        lo, hi = _ELAPSED_EDGES[k], _ELAPSED_EDGES[k + 1]
        m = (frac >= lo) & (frac < hi) if k < len(_ELAPSED_LABELS) - 1 else (frac >= lo) & (frac <= hi)
        if not m.any():
            continue
        bb, bp = float(brier(base[m], y[m])), float(brier(prior[m], y[m]))
        out[lab] = {"brier_base": round(bb, 4), "brier_prior": round(bp, 4),
                    "delta": round(bb - bp, 5), "n": int(m.sum())}
    return out


def _direction_with_buckets(train: List[dict], test: List[dict]) -> Dict:
    """cross_direction (Brier/DM/quarter_pattern) PLUS an elapsed-time breakdown on TEST.

    Reuses the crossval helper for the pooled gate (no fold logic re-implemented), then fits
    the surface once more for the per-bucket read (cheap, same fit) so we can show the
    early->late freshness pattern at fine resolution.
    """
    from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
    res = cross_direction(train, test)
    surf = fit_weight_surface(train, min_cell=20)
    res["elapsed_breakdown"] = _elapsed_breakdown(test, surf)
    res["early_helps_most"] = _early_helps_most(res["elapsed_breakdown"])
    return res


def _early_helps_most(buckets: Dict[str, Dict[str, float]]) -> bool:
    """True if the prior helps MORE early (q1) than late (q4) and is positive early."""
    d_early = buckets.get("q1", {}).get("delta")
    d_late = buckets.get("q4", {}).get("delta")
    if d_early is None or d_late is None:
        return False
    return bool(d_early > d_late and d_early > 0.0)


@dataclass
class FineVerdict:
    verdict: str
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict,
            "resolution": "FINE (~2-min as-of grid from ESPN PBP), not 3 Q-boundaries",
            "design": "true cross-corpus A<->B: fit w on whole train season FINE states, "
                      "test on held-out other season FINE states; DM clustered by game_id",
            "layer": "pregame_elo_prior",
            "base_model": "p_live(margin,time) only -- NO team prior",
            "vs_close": "UNPROVEN -- no in-play odds; CALIBRATION only, not a market edge",
            "a_to_b": self.a_to_b,
            "b_to_a": self.b_to_a,
            "coverage": self.coverage,
            "caveats": list(self.caveats),
        }


def run_fine(states_a: List[dict], states_b: List[dict],
             caveats: Optional[List[str]] = None) -> FineVerdict:
    """Run both A->B and B->A at fine resolution; return an honest replication verdict."""
    a_to_b = _direction_with_buckets(states_a, states_b)   # train A, test B
    b_to_a = _direction_with_buckets(states_b, states_a)   # train B, test A
    # Verdict on Brier+DM both directions (quarter_pattern not required at fine res --
    # the elapsed_breakdown / early_helps_most is the descriptive freshness read).
    verdict = decide(a_to_b, b_to_a, require_quarter_pattern=False)
    cov = {
        "a_states": len(states_a), "a_games": len({s["game_id"] for s in states_a}),
        "b_states": len(states_b), "b_games": len({s["game_id"] for s in states_b}),
        "states_per_game_a": round(len(states_a) / max(1, len({s["game_id"] for s in states_a})), 1),
        "states_per_game_b": round(len(states_b) / max(1, len({s["game_id"] for s in states_b})), 1),
    }
    return FineVerdict(verdict, a_to_b, b_to_a, cov, list(caveats or []))


def run(pbp_a: str = PBP_A, pbp_b: str = PBP_B,
        lines_a: str = LINES_A, lines_b: str = LINES_B) -> FineVerdict:
    """Load both fine-grained PBP corpora + leak-free Elo priors, run the cross-corpus gate."""
    states_a = states_from_pbp(pbp_a, lines_a)
    states_b = states_from_pbp(pbp_b, lines_b)
    caveats = [
        "Fine resolution: ~2-min as-of grid reconstructed from ESPN PBP cumulative scores; "
        "each grid margin is strictly the PAST (last play at-or-before that moment).",
        "True cross-corpus: w fit on WHOLE train season, tested on the held-out OTHER season "
        "-- disjoint games, leak-free by construction; p0 = strictly-pregame Elo per corpus.",
        "DM clustered by game_id -- with ~23 states/game an iid SE would over-state "
        "significance by ~5x; clustering is the load-bearing guard here.",
        "No in-play odds -> verdict is CALIBRATION (held-out Brier) vs a (margin,time) BASE, "
        "never a market edge. No $ anywhere.",
    ]
    return run_fine(states_a, states_b, caveats)


def write(verdict: FineVerdict, out: str = OUT) -> str:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii") as f:
        json.dump(verdict.to_dict(), f, indent=2, sort_keys=True)
    return out


def _dir_report(name: str, d: Dict) -> List[str]:
    lines = [
        f"  {name}: train n={d.get('n_train_states')} -> test n={d.get('n_test_states')} "
        f"({d.get('n_test_games')} games)",
        f"    pooled OOS Brier : BASE {d.get('brier_base')}  +PRIOR {d.get('brier_prior')}"
        f"  (delta {d.get('brier_delta')})",
        f"    DM (clustered)   : stat {d.get('dm_stat')}  p {d.get('dm_p')}",
        f"    prior_beats_base : {d.get('prior_beats_base')}   "
        f"early_helps_most : {d.get('early_helps_most')}",
        "    elapsed buckets (delta = base-prior, >0 = prior helps):",
    ]
    for lab in _ELAPSED_LABELS:
        r = (d.get("elapsed_breakdown") or {}).get(lab)
        if r:
            lines.append(f"      {lab} n={r['n']:6d}  base {r['brier_base']:.4f} -> "
                         f"prior {r['brier_prior']:.4f}  delta {r['delta']:+.5f}")
    return lines


def _report(v: FineVerdict) -> str:
    c = v.coverage
    lines = ["=" * 72,
             "IN-GAME DETAIL-LAYER FINE-RESOLUTION CROSS-CORPUS (NBA): Elo prior vs base",
             "=" * 72,
             f"VERDICT  : {v.verdict}",
             f"coverage : A {c.get('a_games')} games / {c.get('a_states')} states "
             f"({c.get('states_per_game_a')}/game) ; "
             f"B {c.get('b_games')} games / {c.get('b_states')} states "
             f"({c.get('states_per_game_b')}/game)",
             "-" * 72]
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
