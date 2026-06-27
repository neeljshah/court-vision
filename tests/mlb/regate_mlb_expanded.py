"""tests.mlb.regate_mlb_expanded -- EXPANDED-CORPUS re-gate of the MLB in-game
pregame-prior layer over 4 seasons (2021-2024), to SOLIDIFY or REFUTE the prior
BORDERLINE 2-season (2023/2024) REPLICATED verdict.

Background: the 2-season MLB gate was the smallest/most borderline cross-corpus
result on the platform (A->B DM p~0.025, B->A p~4e-6, Brier delta ~+0.001-0.002).
This driver ingests 2021+2022 in-game half-inning states and RE-GATES the prior-
beats-base question on the EXPANDED pool with three fold designs:

  FOLD-PARITY : A={2021,2023} <-> B={2022,2024}  (matches ingame_serve.pool_split_ab
                sorted-index parity over the 4 corpus files -- the EXACT split the
                living refresh loop / server uses, now with 4 files not 2).
  FOLD-TIME   : train={2021,2022} -> test={2023,2024} (train-early/test-late) and
                reverse (test-early) -- the hardest generalization (temporal shift).
  PAIRS       : each adjacent single-season pair (granular replication check).

DISCIPLINE (reused verbatim from the proven generic gate -- NOT re-derived here):
  * cross_direction() fits BASE slope (a,b) + blend weight-surface on the WHOLE train
    pool ONLY, scores BASE vs +PRIOR on the held-out test pool -> leak-free.
  * DM CLUSTERED BY game_id (per-state iid SE inflates significance ~3x).
  * degenerate-base guard: a +PRIOR beat over a vacuous (state,time) BASE is NOT an
    in-game conditioning win -> decide() caps such a fold below REPLICATED.
  * REPLICATED iff +PRIOR<BASE Brier AND DM p<eps in BOTH directions of a fold.

VERDICT LOGIC (STRENGTHEN vs WEAKEN):
  STRENGTHENED if the expanded FOLD-PARITY stays REPLICATED with DM p <= the 2-season
  p in the WEAK direction (A->B, the 0.025 one) AND consistent positive Brier delta
  in both directions; WEAKENED if the borderline direction loses significance (p>eps)
  or flips sign on the larger pool (the borderline A->B was noise).

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
INVARIANTS: edits only domains/mlb/** + tests/**; reads (never edits) the platformkit
gate; <=300 LOC; ASCII-only; numpy/stdlib + pandas.
CLI: python -m tests.mlb.regate_mlb_expanded
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Optional, Tuple

from scripts.platformkit.ingame.ingame_gate_generic import cross_direction, decide
from scripts.platformkit.ingame.ingame_gate_generic_models import load_states

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_EPS = 0.05

# The prior 2-season borderline numbers (from data/frontend/ingame/gate_mlb.json) --
# the bar the expanded re-gate must clear to count as STRENGTHENED.
_PRIOR_2SEASON = {
    "a_to_b": {"dm_p": 0.0247, "brier_delta": 0.00114},
    "b_to_a": {"dm_p": 4e-06, "brier_delta": 0.00216},
}


def _season_path(season: int) -> str:
    return os.path.join(_STATE_DIR, f"mlb_states__{season}.parquet")


def available_seasons() -> List[int]:
    out = []
    for p in sorted(glob.glob(os.path.join(_STATE_DIR, "mlb_states__*.parquet"))):
        try:
            out.append(int(os.path.basename(p).split("__")[1].split(".")[0]))
        except (IndexError, ValueError):
            continue
    return out


def _load_seasons(seasons: List[int]) -> List[dict]:
    pool: List[dict] = []
    for s in seasons:
        path = _season_path(s)
        if os.path.exists(path):
            pool.extend(load_states(path))
    return pool


def _coverage(states: List[dict]) -> Dict[str, int]:
    return {"states": len(states), "games": len({s["game_id"] for s in states})}


def _slim(d: Dict) -> Dict:
    """Keep only the load-bearing fields from a cross_direction result."""
    keys = ("brier_base", "brier_prior", "brier_delta", "dm_p", "dm_stat",
            "prior_beats_base", "base_degenerate", "n_test_games")
    return {k: d.get(k) for k in keys}


def run_fold(train: List[dict], test: List[dict], rev_train: List[dict],
             rev_test: List[dict], *, eps: float = _EPS) -> Dict:
    """Run a both-directions fold; return slim a_to_b/b_to_a + decide() verdict."""
    a_to_b = cross_direction(train, test, eps=eps)
    b_to_a = cross_direction(rev_train, rev_test, eps=eps)
    return {
        "verdict": decide(a_to_b, b_to_a),
        "a_to_b": _slim(a_to_b),
        "b_to_a": _slim(b_to_a),
    }


def regate(seasons: Optional[List[int]] = None, *, eps: float = _EPS) -> Dict:
    """Run the three fold designs over the available MLB seasons; return a report dict."""
    seasons = sorted(seasons or available_seasons())
    rep: Dict = {
        "sport": "mlb", "seasons": seasons, "eps": eps,
        "coverage": {str(s): _coverage(_load_seasons([s])) for s in seasons},
        "vs_close": "UNPROVEN -- CALIBRATION (held-out Brier) only, not a market edge",
        "folds": {},
    }
    even = [s for i, s in enumerate(seasons) if i % 2 == 0]
    odd = [s for i, s in enumerate(seasons) if i % 2 == 1]
    if even and odd:
        a, b = _load_seasons(even), _load_seasons(odd)
        rep["folds"]["parity"] = {
            "A_seasons": even, "B_seasons": odd,
            "A": _coverage(a), "B": _coverage(b),
            **run_fold(a, b, b, a, eps=eps),
        }
    if len(seasons) >= 4:
        early, late = seasons[: len(seasons) // 2], seasons[len(seasons) // 2:]
        e, l = _load_seasons(early), _load_seasons(late)
        rep["folds"]["time"] = {
            "early_seasons": early, "late_seasons": late,
            "early": _coverage(e), "late": _coverage(l),
            **run_fold(e, l, l, e, eps=eps),
        }
    pairs = {}
    for i in range(len(seasons) - 1):
        s0, s1 = seasons[i], seasons[i + 1]
        a, b = _load_seasons([s0]), _load_seasons([s1])
        pairs[f"{s0}_{s1}"] = run_fold(a, b, b, a, eps=eps)
    rep["folds"]["pairs"] = pairs
    rep["solidify"] = _solidify(rep)
    return rep


def _solidify(rep: Dict) -> Dict:
    """STRENGTHENED vs WEAKENED vs PARTIAL, judged on the expanded parity fold.

    STRENGTHENED: parity fold REPLICATED, the borderline (weaker) direction's DM p is
    no worse than the 2-season weak p AND both Brier deltas stay positive (same sign).
    WEAKENED: parity fold drops below REPLICATED OR the weak direction loses
    significance / flips Brier sign on the larger pool.
    """
    par = rep.get("folds", {}).get("parity")
    if not par:
        return {"status": "INSUFFICIENT_DATA",
                "reason": "no parity fold (need both even/odd seasons)"}
    a, b = par["a_to_b"], par["b_to_a"]
    repl = par["verdict"] == "REPLICATED"
    # weaker (borderline) direction = the larger-p one of the two
    weak = a if (a.get("dm_p", 1.0) >= b.get("dm_p", 1.0)) else b
    weak_name = "a_to_b" if weak is a else "b_to_a"
    prior_weak_p = max(_PRIOR_2SEASON["a_to_b"]["dm_p"],
                       _PRIOR_2SEASON["b_to_a"]["dm_p"])
    both_positive = (a.get("brier_delta", 0) > 0) and (b.get("brier_delta", 0) > 0)
    p_ok = weak.get("dm_p", 1.0) <= prior_weak_p
    if repl and both_positive and p_ok:
        status = "STRENGTHENED"
    elif repl and both_positive:
        status = "REPLICATED_STABLE"  # still replicated but weak-p not tighter
    else:
        status = "WEAKENED"
    return {
        "status": status,
        "parity_verdict": par["verdict"],
        "weak_direction": weak_name,
        "weak_dm_p_expanded": weak.get("dm_p"),
        "weak_dm_p_2season": round(prior_weak_p, 6),
        "both_brier_delta_positive": bool(both_positive),
        "weak_p_tighter_than_2season": bool(p_ok),
    }


def _fmt(rep: Dict) -> str:
    L = ["=" * 72, "MLB IN-GAME EXPANDED-CORPUS RE-GATE (prior vs base)", "=" * 72,
         f"seasons : {rep['seasons']}"]
    for s in rep["seasons"]:
        c = rep["coverage"][str(s)]
        L.append(f"  {s}: {c['games']} games / {c['states']} states")
    L.append("-" * 72)
    for name in ("parity", "time"):
        f = rep["folds"].get(name)
        if not f:
            continue
        L.append(f"FOLD {name.upper()}: verdict={f['verdict']}")
        for d in ("a_to_b", "b_to_a"):
            x = f[d]
            L.append(f"  {d}: BASE {x['brier_base']} +PRIOR {x['brier_prior']} "
                     f"delta {x['brier_delta']} DM_p {x['dm_p']} "
                     f"beats={x['prior_beats_base']} degen={x['base_degenerate']} "
                     f"({x['n_test_games']} games)")
    L.append("-" * 72)
    L.append("PAIRS:")
    for k, f in rep["folds"].get("pairs", {}).items():
        L.append(f"  {k}: {f['verdict']} | A->B p={f['a_to_b']['dm_p']} "
                 f"d={f['a_to_b']['brier_delta']} | B->A p={f['b_to_a']['dm_p']} "
                 f"d={f['b_to_a']['brier_delta']}")
    L.append("-" * 72)
    s = rep["solidify"]
    L.append(f"SOLIDIFY: {s['status']}  (parity={s.get('parity_verdict')}, "
             f"weak={s.get('weak_direction')} p={s.get('weak_dm_p_expanded')} "
             f"vs 2-season {s.get('weak_dm_p_2season')})")
    L.append("=" * 72)
    return "\n".join(L)


def main() -> int:
    rep = regate()
    print(_fmt(rep))
    out = os.path.join(_STATE_DIR, "mlb_regate_expanded.json")
    with open(out, "w", encoding="ascii") as f:
        json.dump(rep, f, indent=2, sort_keys=True)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
