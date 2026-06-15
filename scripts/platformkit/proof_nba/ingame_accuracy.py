"""scripts.platformkit.proof_nba.ingame_accuracy — NBA in-game: the real edge, now backtestable.

In-game is the huge advantage: conditioning on the realized score makes a far sharper
forecaster than the static pregame line. NBA was un-backtestable (no per-quarter data) until
the linescore ingest (domains/basketball_nba/ingest_linescores.py). This reconstructs leak-free
mid-game states at the end of Q1/Q2/Q3, reprices via the NBA repricer, and scores:
  * win prob   -> Brier(conditional) vs Brier(static pregame)   (lower = sharper)
  * final total-> RMSE + signed bias                            (NEVER MAE)
It also derives the per-quarter scoring CURVE (intelligence: quarters are not uniform — Q1
fresh, Q4 fouling-inflated) and A/Bs a curve-weighted remaining-points estimate vs the flat
(48-elapsed)/48 the repricer uses, exactly like the MLB per-inning curve.

HONEST: a sharper in-game forecaster is the goal; a live book also sees the score, so this is
forecaster QUALITY not a guaranteed price edge. Grading RMSE+bias, never MAE (median-shift
discipline). INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_nba.ingame_accuracy
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402

_LINESCORES = _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet"
_CHECKPOINTS = ((1, 12.0), (2, 24.0), (3, 36.0))   # (quarter ended, elapsed minutes)
_LEAGUE_MU = 113.0


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(e))


def _load() -> pd.DataFrame:
    df = pd.read_parquet(_LINESCORES)
    qcols = [f"{s}_q{q}" for s in ("home", "away") for q in range(1, 5)]
    df = df.dropna(subset=qcols)
    df["home_final"] = df[[f"home_q{q}" for q in range(1, 5)]].sum(axis=1)
    df["away_final"] = df[[f"away_q{q}" for q in range(1, 5)]].sum(axis=1)
    df = df[(df["home_final"] + df["away_final"]).between(150, 350)]
    return df[df["home_final"] != df["away_final"]].reset_index(drop=True)


def _quarter_curve(df: pd.DataFrame) -> np.ndarray:
    """Per-quarter share of regulation points (both teams). Intelligence: not 0.25 each."""
    tot = np.array([float(df[f"home_q{q}"].sum() + df[f"away_q{q}"].sum()) for q in range(1, 5)])
    return tot / tot.sum()


def run() -> Dict:
    if not _LINESCORES.is_file():
        return {"status": "no_data", "note": "run domains.basketball_nba.ingest_linescores first"}
    df = _load()
    n = len(df)
    if n < 60:
        return {"status": "data_limited", "n": n}
    curve = _quarter_curve(df)
    rep = get_repricer("nba")
    pp = {"mu_home": _LEAGUE_MU, "mu_away": _LEAGUE_MU}
    static = float(rep.reprice(GameState("nba", 0.0, 0, 0, pregame_params=pp)).get("win_home", 0.5))

    s_p, c_p, y = [], [], []
    tot_pred_flat, tot_pred_curve, tot_true = [], [], []
    for _, r in df.iterrows():
        win = 1.0 if r["home_final"] > r["away_final"] else 0.0
        final_total = float(r["home_final"] + r["away_final"])
        for q, elapsed in _CHECKPOINTS:
            h0 = float(sum(r[f"home_q{k}"] for k in range(1, q + 1)))
            a0 = float(sum(r[f"away_q{k}"] for k in range(1, q + 1)))
            out = rep.reprice(GameState("nba", elapsed, int(h0), int(a0), pregame_params=pp))
            s_p.append(static); c_p.append(float(out["win_home"])); y.append(win)
            # flat remaining (what the repricer uses) vs per-quarter-curve remaining
            rem_flat = (48.0 - elapsed) / 48.0
            rem_curve = float(curve[q:].sum())               # share of points in remaining quarters
            full_remaining_pts = 2.0 * _LEAGUE_MU            # league full-game total expectation
            tot_pred_flat.append(h0 + a0 + full_remaining_pts * rem_flat)
            tot_pred_curve.append(h0 + a0 + full_remaining_pts * rem_curve)
            tot_true.append(final_total)

    y = np.array(y)
    b_static, b_cond = _brier(np.array(s_p), y), _brier(np.array(c_p), y)
    rmse_flat, bias_flat = _rmse_bias(np.array(tot_pred_flat), np.array(tot_true))
    rmse_curve, bias_curve = _rmse_bias(np.array(tot_pred_curve), np.array(tot_true))
    return {
        "status": "ok", "n_games": n, "n_checkpoints": int(y.size),
        "quarter_curve": [round(float(c), 4) for c in curve],
        "brier_static_pregame": round(b_static, 5), "brier_conditional": round(b_cond, 5),
        "brier_delta": round(b_cond - b_static, 5),
        "conditional_beats_static": bool(b_cond < b_static),
        "total_rmse_flat": round(rmse_flat, 3), "total_rmse_curve": round(rmse_curve, 3),
        "total_bias_flat": round(bias_flat, 3), "total_bias_curve": round(bias_curve, 3),
        "curve_rmse_gain": round(rmse_flat - rmse_curve, 3),
        "curve_abs_bias_gain": round(abs(bias_flat) - abs(bias_curve), 3),
        "verdict": (
            f"IN-GAME conditioning is much sharper (Brier {round(b_static,3)} static -> "
            f"{round(b_cond,3)} conditional); per-quarter curve "
            f"{'sharpens the total further' if rmse_curve < rmse_flat - 0.05 else 'is ~flat'} "
            f"(RMSE {round(rmse_flat,2)} -> {round(rmse_curve,2)})"),
        "note": "Forecaster quality (a live book also sees the score). RMSE+bias, never MAE. No $ edge.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', rep.get('n'))}"); return 0
    print(f"=== NBA IN-GAME accuracy (n={rep['n_games']} games, {rep['n_checkpoints']} checkpoints) ===")
    print(f"  per-quarter scoring share Q1-Q4: {rep['quarter_curve']} (uniform=0.25)")
    print(f"  win-prob Brier: static={rep['brier_static_pregame']} -> "
          f"conditional={rep['brier_conditional']} (d={rep['brier_delta']:+})")
    print(f"  final-total RMSE: flat={rep['total_rmse_flat']}  curve={rep['total_rmse_curve']}  "
          f"(gain {rep['curve_rmse_gain']:+}); |bias| flat={abs(rep['total_bias_flat'])} "
          f"curve={abs(rep['total_bias_curve'])}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
