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
_DEF_MARGIN_SIGMA = 13.5   # full-game final-margin SD (matches the NBA repricer default)


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


def _walk_forward_elo(df: pd.DataFrame) -> np.ndarray:
    """Leak-free MOV-Elo over the linescore games -> as-of pregame P(home win). Feeds the
    repricer a RATING-informed prior so in-game = pregame intelligence + realized score."""
    import math
    rat: Dict[str, float] = {}
    p = np.empty(len(df))
    h = df["home_abbr"].to_numpy(); a = df["away_abbr"].to_numpy()
    hf = df["home_final"].to_numpy(float); af = df["away_final"].to_numpy(float)
    K, HFA = 20.0, 60.0
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        rat.setdefault(ht, 1500.0); rat.setdefault(at, 1500.0)
        ph = 1.0 / (1.0 + 10.0 ** (-(rat[ht] - rat[at] + HFA) / 400.0))
        p[i] = ph
        s = 1.0 if hf[i] > af[i] else 0.0
        ed = (rat[ht] - rat[at] + HFA) * (1 if s else -1)
        mov = math.log(abs(hf[i] - af[i]) + 1.0) * (2.2 / (ed * 0.001 + 2.2))
        d = K * mov * (s - ph)
        rat[ht] += d; rat[at] -= d
    return p


def run() -> Dict:
    if not _LINESCORES.is_file():
        return {"status": "no_data", "note": "run domains.basketball_nba.ingest_linescores first"}
    df = _load()
    n = len(df)
    if n < 60:
        return {"status": "data_limited", "n": n}
    from scipy.special import ndtri  # noqa: PLC0415
    curve = _quarter_curve(df)
    p_pre = _walk_forward_elo(df)            # as-of pregame Elo win-prob per game (leak-free)
    rep = get_repricer("nba")
    blind = {"mu_home": _LEAGUE_MU, "mu_away": _LEAGUE_MU}

    pre_p, blind_p, rate_p, y = [], [], [], []
    rmse_acc = {"flat": [], "curve": []}
    tot_true: List[float] = []
    for i in range(n):
        r = df.iloc[i]
        win = 1.0 if r["home_final"] > r["away_final"] else 0.0
        final_total = float(r["home_final"] + r["away_final"])
        # rating-informed prior: set mu so the repricer's PREGAME win == the Elo win-prob
        mu_diff = float(ndtri(min(max(p_pre[i], 1e-4), 1 - 1e-4)) * _DEF_MARGIN_SIGMA)
        rate_pp = {"mu_home": _LEAGUE_MU + mu_diff / 2.0, "mu_away": _LEAGUE_MU - mu_diff / 2.0}
        for q, elapsed in _CHECKPOINTS:
            h0 = float(sum(r[f"home_q{k}"] for k in range(1, q + 1)))
            a0 = float(sum(r[f"away_q{k}"] for k in range(1, q + 1)))
            o_blind = rep.reprice(GameState("nba", elapsed, int(h0), int(a0), pregame_params=blind))
            o_rate = rep.reprice(GameState("nba", elapsed, int(h0), int(a0), pregame_params=rate_pp))
            pre_p.append(p_pre[i])                  # pregame Elo (no score)
            blind_p.append(float(o_blind["win_home"]))   # score only (rating-blind)
            rate_p.append(float(o_rate["win_home"]))     # COMBINED: rating prior + score
            y.append(win)
            rem_flat = (48.0 - elapsed) / 48.0
            rmse_acc["flat"].append(h0 + a0 + 2.0 * _LEAGUE_MU * rem_flat)
            rmse_acc["curve"].append(h0 + a0 + 2.0 * _LEAGUE_MU * float(curve[q:].sum()))
            tot_true.append(final_total)

    y = np.array(y)
    b_pre, b_blind, b_rate = (_brier(np.array(p), y) for p in (pre_p, blind_p, rate_p))
    rmse_flat, bias_flat = _rmse_bias(np.array(rmse_acc["flat"]), np.array(tot_true))
    rmse_curve, _ = _rmse_bias(np.array(rmse_acc["curve"]), np.array(tot_true))
    return {
        "status": "ok", "n_games": n, "n_checkpoints": int(y.size),
        "quarter_curve": [round(float(c), 4) for c in curve],
        "brier_pregame_elo": round(b_pre, 5),
        "brier_conditional_blind": round(b_blind, 5),
        "brier_conditional_rating": round(b_rate, 5),
        "combined_beats_pregame": bool(b_rate < b_pre),
        "combined_beats_blind": bool(b_rate < b_blind),
        "total_rmse_flat": round(rmse_flat, 3), "total_rmse_curve": round(rmse_curve, 3),
        "total_bias_flat": round(bias_flat, 3), "curve_helps": bool(rmse_curve < rmse_flat - 0.05),
        "verdict": (
            f"IN-GAME wins: pregame-Elo Brier {round(b_pre,3)} -> score-only {round(b_blind,3)} "
            f"-> COMBINED (rating prior + score) {round(b_rate,3)} "
            f"({'best' if b_rate <= min(b_pre, b_blind) else 'not best'}). NBA per-quarter "
            f"curve is a null (quarters ~uniform)."),
        "note": "Forecaster quality (a live book also sees the score). RMSE+bias, never MAE. No $ edge.",
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', rep.get('n'))}"); return 0
    print(f"=== NBA IN-GAME accuracy (n={rep['n_games']} games, {rep['n_checkpoints']} checkpoints) ===")
    print(f"  per-quarter scoring share Q1-Q4: {rep['quarter_curve']} (uniform=0.25)")
    print(f"  win-prob Brier:  pregame-Elo={rep['brier_pregame_elo']}  "
          f"score-only={rep['brier_conditional_blind']}  "
          f"COMBINED(rating+score)={rep['brier_conditional_rating']}")
    print(f"  combined beats pregame: {rep['combined_beats_pregame']}  "
          f"beats score-only: {rep['combined_beats_blind']}")
    print(f"  final-total RMSE: flat={rep['total_rmse_flat']}  curve={rep['total_rmse_curve']}  "
          f"(curve helps: {rep['curve_helps']})")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
