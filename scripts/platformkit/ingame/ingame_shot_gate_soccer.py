"""scripts.platformkit.ingame.ingame_shot_gate_soccer -- SOCCER-SPECIFIC in-game
SHOT-PRESSURE detail-layer gate.

THE QUESTION: the proven soccer in-game champion is the goal-diff base+pregame-prior
(ingame_gate_generic REPLICATED). Does adding an IN-GAME SHOT-PRESSURE signal
(cumulative shot_diff or xgproxy_diff, as-of-minute, leak-free) beat that champion on
held-out Brier, REPLICATED in BOTH cross-corpus directions, DM clustered by game_id,
without tripping the degenerate-base honesty guard?

CHAMPION (control, fit on TRAIN only):
  p_champ = blend(p0, BASE_goal, w(time,margin))     # the PROVEN base+prior
            BASE_goal = sigmoid((a + b*frac)*goal_diff)

CANDIDATE (fit on TRAIN only):
  p_cand  = blend(p0, BASE_aug,  w(time,margin))
            BASE_aug  = sigmoid((a + b*frac)*goal_diff + c*shot_feat)
  c FIT on TRAIN by Brier (1-D grid) given the already-fit (a,b); the SAME prior
  surface w is refit on BASE_aug so the comparison isolates the shot term, not the
  blend. shot_feat in {shot_diff, xgproxy_diff}, standardized by TRAIN spread.

DISCIPLINE (inherited, hard-learned):
  * TRUE cross-corpus A<->B (disjoint games); leak-free by construction.
  * DM CLUSTERED BY game_id (per-state iid SE over-states significance).
  * REPLICATED iff cand<champ Brier AND DM p<eps in BOTH directions; else PARTIAL/REJECT.
  * DEGENERATE-BASE GUARD: if the goal BASE is vacuous on a direction, that direction
    cannot yield a genuine in-game conditioning win (reuses base_is_degenerate).
  * GRACEFUL DEGRADE: a noise shot_feat fits c->0 -> cand==champ -> REJECT.

NO $ anywhere; verdict is CALIBRATION (held-out Brier), never a market edge.
INVARIANTS: never edit src/kernel; <=300 LOC; ASCII-only; numpy/stdlib + reuse.
CLI: python -m scripts.platformkit.ingame.ingame_shot_gate_soccer [shot_diff|xgproxy_diff]
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.ingame.ingame_gate_generic_models import (
    base_is_degenerate,
    base_predict,
    fit_base,
    fit_prior_surface,
    prior_predict,
)

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")
_OUT_DIR = os.path.join(_REPO, "data", "frontend", "ingame")
_SINGLE = ("eng1", "esp1", "ger1", "ita1")


# --------------------------------------------------------------------------- load
def load_joined(label: str) -> List[dict]:
    """Load goal-diff states JOINED with shot-pressure states by (game_id, asof_idx).

    Only rows present in BOTH (a shot corpus exists for the game) are kept, so the
    candidate and champion see the SAME rows -> a fair head-to-head.
    """
    base = pd.read_parquet(os.path.join(_STATE_DIR, f"soccer_states__{label}.parquet"))
    shot = pd.read_parquet(os.path.join(_STATE_DIR, f"soccer_shotstates__{label}.parquet"))
    base["game_id"] = base["game_id"].astype(str)
    shot["game_id"] = shot["game_id"].astype(str)
    df = base.merge(shot[["game_id", "asof_idx", "shot_diff", "xgproxy_diff"]],
                    on=["game_id", "asof_idx"], how="inner")
    out: List[dict] = []
    for r in df.itertuples(index=False):
        out.append({
            "game_id": str(r.game_id), "state_diff": float(r.state_diff),
            "frac_elapsed": float(r.frac_elapsed), "p0": float(r.p0),
            "outcome": int(r.outcome), "shot_diff": float(r.shot_diff),
            "xgproxy_diff": float(r.xgproxy_diff),
        })
    return out


# ------------------------------------------------------------------- augmented base
def fit_shot_coef(train: List[dict], ab: Tuple[float, float], feat: str) -> Tuple[float, float]:
    """1-D grid-fit shot coef c for sigmoid((a+b*frac)*goal + c*z_shot) on TRAIN.

    z_shot is feat standardized by its TRAIN spread (scale-free). Returns (c, spread).
    """
    a, b = ab
    gd = np.array([s["state_diff"] for s in train], float)
    fe = np.array([s["frac_elapsed"] for s in train], float)
    y = np.array([s["outcome"] for s in train], float)
    sf = np.array([s[feat] for s in train], float)
    spread = float(np.std(sf)) or 1.0
    z = sf / spread
    lin0 = (a + b * fe) * gd
    best_c, best_s = 0.0, float(np.mean((1.0 / (1.0 + np.exp(-lin0)) - y) ** 2))
    for c in np.linspace(-1.5, 1.5, 31):
        p = 1.0 / (1.0 + np.exp(-(lin0 + c * z)))
        sc = float(np.mean((p - y) ** 2))
        if sc < best_s:
            best_s, best_c = sc, float(c)
    return best_c, spread


def aug_predict(states: List[dict], ab: Tuple[float, float], feat: str,
                c: float, spread: float) -> np.ndarray:
    a, b = ab
    gd = np.array([s["state_diff"] for s in states], float)
    fe = np.array([s["frac_elapsed"] for s in states], float)
    z = np.array([s[feat] for s in states], float) / (spread or 1.0)
    return 1.0 / (1.0 + np.exp(-((a + b * fe) * gd + c * z)))


# --------------------------------------------------------------------- one direction
def cross_direction(train: List[dict], test: List[dict], feat: str,
                    eps: float = 0.05) -> Dict:
    """Champion (goal base+prior) vs candidate (shot-aug base+prior) on held-out TEST."""
    ab = fit_base(train)
    base_tr = base_predict(train, ab)
    surf_champ = fit_prior_surface(train, base_tr)
    c, spread = fit_shot_coef(train, ab, feat)
    aug_tr = aug_predict(train, ab, feat, c, spread)
    surf_cand = fit_prior_surface(train, aug_tr)

    y = np.array([s["outcome"] for s in test], float)
    base_te = base_predict(test, ab)
    aug_te = aug_predict(test, ab, feat, c, spread)
    p_champ = prior_predict(test, base_te, surf_champ)
    p_cand = prior_predict(test, aug_te, surf_cand)
    gids = [s["game_id"] for s in test]
    bc, ba = float(brier(p_champ, y)), float(brier(p_cand, y))
    d = (p_champ - y) ** 2 - (p_cand - y) ** 2     # +ve => candidate beats champion
    dm = diebold_mariano(d, gids)
    degen = base_is_degenerate(ab, train, base_te, y)
    cand_beats = bool((ba < bc) and (dm.p_value < eps) and not degen["degenerate"])
    return {
        "feat": feat, "shot_coef": round(c, 5),
        "n_train": len(train), "n_test": len(test), "n_test_games": dm.n_clusters,
        "brier_champ": round(bc, 5), "brier_cand": round(ba, 5),
        "brier_delta": round(bc - ba, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "cand_beats_champ": cand_beats,
        "base_degenerate": bool(degen["degenerate"]),
    }


def decide(a2b: Dict, b2a: Dict) -> str:
    a, b = bool(a2b.get("cand_beats_champ")), bool(b2a.get("cand_beats_champ"))
    if a2b.get("base_degenerate") or b2a.get("base_degenerate"):
        return "PARTIAL" if (a or b) else "INVALID_BASE"
    if a and b:
        return "REPLICATED"
    return "PARTIAL" if (a or b) else "REJECT"


@dataclass
class ShotVerdict:
    verdict: str
    feat: str = ""
    a_to_b: Dict = field(default_factory=dict)
    b_to_a: Dict = field(default_factory=dict)
    coverage: Dict = field(default_factory=dict)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "verdict": self.verdict, "sport": "soccer",
            "layer": f"ingame_shot_pressure[{self.feat}]",
            "champion": "blend(p0, sigmoid((a+b*frac)*goal_diff), w) -- PROVEN base+prior",
            "candidate": "blend(p0, sigmoid((a+b*frac)*goal_diff + c*z_shot), w)",
            "design": "true cross-corpus A<->B; DM clustered by game_id; degen guard",
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge",
            "a_to_b": self.a_to_b, "b_to_a": self.b_to_a,
            "coverage": self.coverage, "caveats": list(self.caveats),
        }


def gate(states_a: List[dict], states_b: List[dict], feat: str,
         label_a: str = "A", label_b: str = "B",
         eps: float = 0.05, min_ticks: int = 200) -> ShotVerdict:
    cov = {
        f"{label_a}_states": len(states_a),
        f"{label_a}_games": len({s["game_id"] for s in states_a}),
        f"{label_b}_states": len(states_b),
        f"{label_b}_games": len({s["game_id"] for s in states_b}),
    }
    cav = [
        "Champion = the PROVEN goal-diff base+pregame-prior; candidate ADDS only an "
        "in-game shot term -> isolates whether shots add beyond goals+prior.",
        "Shot side-attribution via roster player names (commentary.team is None); "
        "as-of-minute cumulative, leak-free; boxscore final totals NEVER used.",
        "DM clustered by game_id; degenerate-base guard inherited.",
        "No in-play odds -> CALIBRATION verdict (held-out Brier), never a market edge.",
    ]
    thin = (len(states_a) < min_ticks or len(states_b) < min_ticks
            or len({s["game_id"] for s in states_a}) < 8
            or len({s["game_id"] for s in states_b}) < 8)
    if thin:
        return ShotVerdict("INSUFFICIENT_DATA", feat, {}, {}, cov,
                           cav + ["corpus too thin to gate"])
    a2b = cross_direction(states_a, states_b, feat, eps)
    b2a = cross_direction(states_b, states_a, feat, eps)
    return ShotVerdict(decide(a2b, b2a), feat, a2b, b2a, cov, cav)


# --------------------------------------------------------------------------- CLI
def _avail() -> List[str]:
    return [lb for lb in _SINGLE
            if os.path.exists(os.path.join(_STATE_DIR, f"soccer_shotstates__{lb}.parquet"))]


def _dir_lines(name: str, d: Dict) -> List[str]:
    if not d:
        return [f"  {name}: (none)"]
    return [
        f"  {name}: train {d['n_train']} -> test {d['n_test']} ({d['n_test_games']} games)"
        f"  shot_coef={d['shot_coef']}",
        f"    OOS Brier: CHAMP {d['brier_champ']}  CAND {d['brier_cand']}"
        f"  (delta {d['brier_delta']})",
        f"    DM(clustered): stat {d['dm_stat']}  p {d['dm_p']}   "
        f"cand_beats_champ={d['cand_beats_champ']}  degen={d['base_degenerate']}",
    ]


def run(feat: str = "shot_diff") -> ShotVerdict:
    av = _avail()
    os.makedirs(_OUT_DIR, exist_ok=True)
    if len(av) < 2:
        v = ShotVerdict("INSUFFICIENT_DATA", feat, {}, {},
                        {"shot_corpora_found": len(av)},
                        [f"need 2 shot corpora; found {len(av)}: {av}"])
    else:
        la, lb = av[0], av[1]
        v = gate(load_joined(la), load_joined(lb), feat, la, lb)
    out = os.path.join(_OUT_DIR, f"shot_gate_soccer_{feat}.json")
    with open(out, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    print("=" * 72)
    print(f"IN-GAME SHOT-PRESSURE GATE [soccer / {feat}]")
    print("=" * 72)
    print(f"VERDICT : {v.verdict}")
    print(f"coverage: {v.coverage}")
    print("-" * 72)
    for ln in _dir_lines("A->B", v.a_to_b):
        print(ln)
    print("-" * 72)
    for ln in _dir_lines("B->A", v.b_to_a):
        print(ln)
    print("=" * 72)
    print(f"wrote {out}")
    return v


def main() -> None:
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else "shot_diff")


if __name__ == "__main__":
    main()
