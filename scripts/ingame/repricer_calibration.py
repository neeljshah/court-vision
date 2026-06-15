"""scripts/ingame/repricer_calibration.py — leak-free in-game repricer back-test.

Roadmap item #4 (MLB edge map, line 19): reconstruct synthetic mid-game states from
EXISTING on-disk data, reprice via get_repricer(sport), and score
    Brier(conditional-on-realized-state) < Brier(static-pregame)
plus RMSE + signed BIAS (NEVER MAE) on the realized final.

LEAK-FREE reconstruction (this is the whole point — only TRUE per-period data is used,
nothing is back-filled from the final score):
  * MLB    : pitchers.parquet `home_innings`/`away_innings` are real per-inning run
             strings. At checkpoint inning N the cumulative runs through N are a genuine
             mid-game observable; the repricer NEVER sees innings > N. Final = full sum.
  Sports WITHOUT a leak-free per-period reconstruction on disk are reported as
  'no_leakfree_reconstruction' rather than FABRICATED — inventing a split would leak:
    - NBA    : no per-quarter linescore on disk.
    - SOCCER : no per-minute goal timeline on disk.
    - TENNIS : matches.parquet `score` is ordered WINNER-first (verified: set-1-leader vs
               match-winner agreement ~0.52 in p1/p2 frame), so it does NOT preserve the
               p1-vs-p2 set sequence — reconstructing a mid-match (sets_1, sets_2) state
               from it would LEAK the eventual winner. Excluded until a p1/p2-ordered
               per-set source exists.
  Honest about coverage; only the one truly leak-free per-period sport is scored.

THE GRADING DISCIPLINE: the win/result is a PROBABILITY, graded on Brier. The realized
final TOTAL/MARGIN is graded on RMSE + signed bias. MAE is deliberately NOT used (the
MAE-vs-RMSE median-shift artifact memory). Conditioning on realized state is mechanically
expected to beat a static pregame line — a PASS here is the EXPECTED, honest outcome.

HONEST: this scores re-pricing MACHINERY. A conditional-beats-static result is a
CALIBRATION fact, NOT a market edge — it does not beat a live BOOK that also sees the
score. Markets are efficient; no edge is claimed. DEFAULT-OFF tooling: changes nothing served.
INVARIANTS: never edit src/ or kernel/; pure numpy/pandas; <=300 LOC; per-sport read only.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402

_MLB_CHECKPOINTS = (3, 5, 7)        # innings at which to reconstruct a mid-game state
_MLB_LEAGUE_LAMBDA = 4.5            # leak-free pregame prior: league-avg runs/team (engine default)


# ---------------------------------------------------------------------------
# Metric helpers (Brier for the result; RMSE + signed bias for the total)
# ---------------------------------------------------------------------------

def _brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    err = pred - truth
    return float(np.sqrt(np.mean(err ** 2))), float(np.mean(err))


# ---------------------------------------------------------------------------
# MLB — real per-inning linescores
# ---------------------------------------------------------------------------

def _parse_innings(s: Any) -> Optional[List[int]]:
    if not isinstance(s, str):
        return None
    out: List[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok in ("", "x", "X"):
            continue
        try:
            out.append(int(tok))
        except ValueError:
            return None
    return out or None


def _eval_mlb(limit: Optional[int]) -> Optional[Dict[str, Any]]:
    path = os.path.join(ROOT, "data", "domains", "mlb", "pitchers.parquet")
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path, columns=["home_innings", "away_innings"])
    rep = get_repricer("mlb")
    pp = {"lam_home": _MLB_LEAGUE_LAMBDA, "lam_away": _MLB_LEAGUE_LAMBDA}

    # Static pregame ML (inning 0, no runs) — identical for every game/checkpoint.
    static_p = float(rep.reprice(GameState(
        "mlb", 0.0, 0, 0, pregame_params=pp, extra={"innings_played": 0})).get("ml_home", 0.5))

    s_p, c_p, y, tot_pred, tot_true = [], [], [], [], []
    tot_pred_homo = []   # homogeneous (9-n)/9 baseline, for the per-inning-curve A/B
    n = 0
    for hi, ai in zip(df["home_innings"], df["away_innings"]):
        h, a = _parse_innings(hi), _parse_innings(ai)
        if h is None or a is None or len(h) < 1 or len(a) < 1:
            continue
        fh, fa = sum(h), sum(a)
        if fh == fa:           # extra-innings tie in regulation: outcome undefined here
            continue
        win = 1.0 if fh > fa else 0.0
        for ck in _MLB_CHECKPOINTS:
            if len(h) < ck or len(a) < ck:
                continue
            h0, a0 = sum(h[:ck]), sum(a[:ck])
            out = rep.reprice(GameState(
                "mlb", 0.0, h0, a0, pregame_params=pp,
                extra={"innings_played": float(ck)}))
            homo = rep.reprice(GameState(
                "mlb", 0.0, h0, a0, pregame_params=pp,
                extra={"innings_played": float(ck), "homogeneous_frac": True}))
            s_p.append(static_p)
            c_p.append(float(out.get("ml_home", 0.5)))
            y.append(win)
            lam_h = float(out.get("_lam_remaining_home", 0.0))
            lam_a = float(out.get("_lam_remaining_away", 0.0))
            tot_pred.append(h0 + a0 + lam_h + lam_a)   # E[final total | state], per-inning curve
            tot_pred_homo.append(h0 + a0 + float(homo.get("_lam_remaining_home", 0.0))
                                 + float(homo.get("_lam_remaining_away", 0.0)))
            tot_true.append(float(fh + fa))
        n += 1
        if limit and n >= limit:
            break
    if not y:
        return None
    res = _summary("mlb", np.array(s_p), np.array(c_p), np.array(y),
                   np.array(tot_pred), np.array(tot_true), n)
    rmse_h, bias_h = _rmse_bias(np.array(tot_pred_homo), np.array(tot_true))
    res["final_total_rmse_homogeneous"] = round(rmse_h, 4)
    res["final_total_bias_homogeneous"] = round(bias_h, 4)
    res["per_inning_curve_rmse_gain"] = round(rmse_h - res["final_total_rmse"], 4)
    res["per_inning_curve_bias_gain"] = round(abs(bias_h) - abs(res["final_total_bias"]), 4)
    return res


# ---------------------------------------------------------------------------
# Summary + CLI
# ---------------------------------------------------------------------------

def _summary(sport: str, static_p: np.ndarray, cond_p: np.ndarray, y: np.ndarray,
             tot_pred: np.ndarray, tot_true: np.ndarray, n_games: int) -> Dict[str, Any]:
    b_static, b_cond = _brier(static_p, y), _brier(cond_p, y)
    rmse, bias = _rmse_bias(tot_pred, tot_true)
    return {
        "sport": sport,
        "n_games": n_games,
        "n_checkpoints": int(y.size),
        "brier_static_pregame": round(b_static, 5),
        "brier_conditional": round(b_cond, 5),
        "brier_delta": round(b_cond - b_static, 5),
        "conditional_beats_static": bool(b_cond < b_static),
        "final_total_rmse": round(rmse, 4),
        "final_total_bias": round(bias, 4),
    }


_EVALUATORS = {"mlb": _eval_mlb}
_NO_LEAKFREE = {
    "nba": "no per-quarter linescore on disk; final-score split would leak",
    "soccer": "no per-minute goal timeline on disk; final-score split would leak",
    "tennis": "score string is winner-ordered (set1-leader vs match-winner ~0.52 in "
              "p1/p2 frame); reconstructing (sets_1,sets_2) would leak the winner",
}


def run(sport: str, limit: Optional[int]) -> List[Dict[str, Any]]:
    sports = (list(_EVALUATORS) + list(_NO_LEAKFREE)) if sport == "all" else [sport]
    rows: List[Dict[str, Any]] = []
    for sp in sports:
        if sp in _NO_LEAKFREE:
            rows.append({"sport": sp, "status": "no_leakfree_reconstruction",
                         "note": _NO_LEAKFREE[sp]})
            continue
        ev = _EVALUATORS.get(sp)
        res = ev(limit) if ev else None
        rows.append(res or {"sport": sp, "status": "no_data"})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sport", default="all",
                    choices=["all", "mlb", "tennis", "nba", "soccer"])
    ap.add_argument("--limit", type=int, default=None,
                    help="max games per sport (smoke-test).")
    args = ap.parse_args()
    print("=" * 74)
    print("REPRICER CALIBRATION — leak-free conditional vs static-pregame (RMSE+bias, not MAE)")
    print("GOAL: the sharpest in-game forecaster. Conditioning on realized state makes a "
          "much better predictor than the static line; the per-inning curve sharpens it further. "
          "A live book also sees the score, so this is forecaster QUALITY, not a guaranteed "
          "price edge — but better predictions are the point.")
    print("=" * 74)
    for r in run(args.sport, args.limit):
        if r.get("status"):
            print(f"  {r['sport']:7s}  {r['status']:28s}  {r.get('note', '')}")
            continue
        verdict = "PASS (expected)" if r["conditional_beats_static"] else "no-improvement"
        print(f"  {r['sport']:7s}  n={r['n_games']:6d} ck={r['n_checkpoints']:7d}  "
              f"Brier static={r['brier_static_pregame']:.5f} -> cond={r['brier_conditional']:.5f} "
              f"(d={r['brier_delta']:+.5f}) {verdict}")
        print(f"           final-total  RMSE={r['final_total_rmse']:.4f}  "
              f"bias={r['final_total_bias']:+.4f}  (MAE deliberately NOT reported)")
        if "per_inning_curve_rmse_gain" in r:
            print(f"           per-inning curve vs homogeneous: "
                  f"RMSE {r['final_total_rmse_homogeneous']:.4f} -> {r['final_total_rmse']:.4f} "
                  f"(gain {r['per_inning_curve_rmse_gain']:+.4f}), "
                  f"|bias| {abs(r['final_total_bias_homogeneous']):.4f} -> "
                  f"{abs(r['final_total_bias']):.4f} (gain {r['per_inning_curve_bias_gain']:+.4f})")


if __name__ == "__main__":
    main()
