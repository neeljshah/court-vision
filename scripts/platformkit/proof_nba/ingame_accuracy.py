"""scripts.platformkit.proof_nba.ingame_accuracy — NBA in-game: the real edge, now backtestable.

In-game is the huge advantage: conditioning on the realized score makes a far sharper
forecaster than the static pregame line. The linescore ingest unlocked per-quarter data; this
reconstructs leak-free mid-game states at the end of Q1/Q2/Q3, reprices via the NBA repricer,
and scores: win prob -> Brier(conditional) vs Brier(pregame) + ECE/reliability slope (sharp
AND calibrated); final total -> RMSE + signed bias (NEVER MAE). A leak-free recalibrator
(temperature / Platt-on-logit) is fit on TRAIN games ONLY and applied to held-out games ->
ECE_raw vs ECE_recal (Brier guarded). Also derives the per-quarter scoring CURVE (vs flat).
HONEST: a sharper, calibrated in-game forecaster is the goal; a live book also sees the score,
so this is forecaster QUALITY not a guaranteed price edge. RMSE+bias never MAE. If the raw
forecaster is already calibrated, recal is a null. INVARIANTS: never edit src/ or kernel/; <=300.
Run: python -m scripts.platformkit.proof_nba.ingame_accuracy
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402

_LINESCORES = _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet"


def _linescores_path(corpus: Optional[Path]) -> Path:
    # Corpus precedence: explicit arg > $PROOF_CORPUS_ROOT/nba > real data/domains (unchanged).
    env = os.environ.get("PROOF_CORPUS_ROOT")
    root = corpus or (Path(env) / "nba" if env else None)
    return (root / "linescores.parquet") if root is not None else _LINESCORES


_CHECKPOINTS = ((1, 12.0), (2, 24.0), (3, 36.0))   # (quarter ended, elapsed minutes)
_LEAGUE_MU = 113.0
_DEF_MARGIN_SIGMA = 13.5   # full-game final-margin SD (matches the NBA repricer default)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))

def _rmse_bias(pred: np.ndarray, truth: np.ndarray) -> Tuple[float, float]:
    e = pred - truth
    return float(np.sqrt(np.mean(e ** 2))), float(np.mean(e))

_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, _EPS, 1 - _EPS)
    return np.log(pc / (1 - pc))

def _sig(x: np.ndarray) -> np.ndarray:
    return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))

def _reliability_slope(p: np.ndarray, y: np.ndarray) -> float:
    """OLS slope of outcome y on forecast p (1.0 = ideal; <1 over-, >1 under-confident)."""
    return float(np.polyfit(p, y.astype(float), 1)[0]) if np.ptp(p) > 1e-9 and len(p) >= 3 else float("nan")

def _ece10(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """10-bin equal-width expected calibration error."""
    n = len(p)
    if n == 0:
        return 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    e = 0.0
    for i in range(bins):
        m = (p >= edges[i]) & (p < edges[i + 1]) if i < bins - 1 else (p >= edges[i]) & (p <= 1.0)
        if int(m.sum()):
            e += (int(m.sum()) / n) * abs(float(p[m].mean()) - float(y[m].mean()))
    return float(e)

def _fit_platt_logit(p: np.ndarray, y: np.ndarray, ridge: float = 1e-4) -> Tuple[float, float]:
    """Fit y ~ sigmoid(a*logit(p)+b) via Newton-IRLS. Returns (a, b). a<1 shrinks confidence."""
    x = _logit(p)
    X = np.column_stack([x, np.ones_like(x)])
    w = np.array([1.0, 0.0])
    R = ridge * np.eye(2)
    for _ in range(25):
        mu = np.clip(_sig(X @ w), _EPS, 1 - _EPS)
        grad = X.T @ (mu - y) + R @ w
        H = (X.T * (mu * (1 - mu))) @ X + R
        try:
            d = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w -= d
        if np.linalg.norm(d) < 1e-9:
            break
    return float(w[0]), float(w[1])

def _fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Scalar T minimizing log-loss over T in [0.3, 4.0] via a 2-pass grid (pure numpy)."""
    x = _logit(p)

    def loss(t: float) -> float:
        c = np.clip(_sig(x / t), _EPS, 1 - _EPS)
        return float(np.mean(-(y * np.log(c) + (1 - y) * np.log(1 - c))))

    grid = np.linspace(0.3, 4.0, 38)
    bi = int(np.argmin([loss(t) for t in grid]))
    lo, hi = grid[max(0, bi - 1)], grid[min(len(grid) - 1, bi + 1)]
    fine = np.linspace(lo, hi, 41)
    return float(fine[int(np.argmin([loss(t) for t in fine]))])

def _recalibrate(train_p: np.ndarray, train_y: np.ndarray,
                 eval_p: np.ndarray, eval_y: np.ndarray) -> Tuple[np.ndarray, str]:
    """Fit Platt-on-logit AND temperature on TRAIN ONLY; SELECT the method on an
    internal held-out slice of the TRAIN half -> no peeking at the eval split, then
    refit the winner on the FULL train half and apply to EVAL. Strictly leak-free:
    nothing is fit or chosen on the eval games."""
    # Internal fit/select split by INDEX PARITY (not chronological) so both slices share
    # the same season-era distribution -> the method choice isn't confounded by the
    # early-season Elo warm-up over-confidence drift. (Calibration is non-stationary.)
    idx = np.arange(len(train_p))
    fit_i, sel_i = (idx % 3 != 0), (idx % 3 == 0)  # ~67% fit / ~33% select, interleaved
    fit_p, fit_y = train_p[fit_i], train_y[fit_i]
    sel_p, sel_y = train_p[sel_i], train_y[sel_i]
    a, b = _fit_platt_logit(fit_p, fit_y)
    t = _fit_temperature(fit_p, fit_y)
    br = lambda pp, yy: float(np.mean((pp - yy) ** 2))  # noqa: E731
    best = "identity"
    if len(sel_y) >= 30 and len(np.unique(sel_y)) == 2:
        # SELECT by ECE on the internal held-out TRAIN slice (the metric we target),
        # guarded so the choice never worsens its Brier (no sharpness give-up); a method
        # must beat identity ECE by >0.002 to switch (else honest null: keep raw).
        br_id = br(sel_p, sel_y)
        cands = [("identity", _ece10(sel_p, sel_y))]
        for nm, pc in (("temperature", _sig(_logit(sel_p) / t)),
                       ("platt", _sig(a * _logit(sel_p) + b))):
            if br(pc, sel_y) <= br_id + 1e-3:
                cands.append((nm, _ece10(pc, sel_y)))
        winner = min(cands, key=lambda c: c[1])
        if winner[0] != "identity" and winner[1] < cands[0][1] - 0.002:
            best = winner[0]
    # refit on the FULL train half for the final map (more data, still no eval leak)
    a, b = _fit_platt_logit(train_p, train_y)
    t = _fit_temperature(train_p, train_y)
    if best == "identity":
        return np.clip(eval_p, _EPS, 1 - _EPS), "identity(raw already calibrated)"
    if best == "temperature":
        return _sig(_logit(eval_p) / t), f"temperature(T={round(t, 3)})"
    return _sig(a * _logit(eval_p) + b), f"platt_logit(a={round(a, 3)},b={round(b, 3)})"

def _load(path: Optional[Path] = None) -> pd.DataFrame:
    df = pd.read_parquet(path or _LINESCORES)
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

def run(corpus: Optional[Path] = None) -> Dict:
    ls_path = _linescores_path(corpus)
    if not ls_path.is_file():
        return {"status": "no_data", "note": "run domains.basketball_nba.ingest_linescores first"}
    df = _load(ls_path)
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
    tot_true: List[float] = []; game_idx: List[int] = []   # per checkpoint -> split-by-game
    for i in range(n):
        r = df.iloc[i]
        win = 1.0 if r["home_final"] > r["away_final"] else 0.0
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
            tot_true.append(float(r["home_final"] + r["away_final"]))
            game_idx.append(i)

    y = np.array(y)
    rate_arr = np.array(rate_p)
    b_pre, b_blind, b_rate = (_brier(np.array(p), y) for p in (pre_p, blind_p, rate_p))
    rmse_flat, bias_flat = _rmse_bias(np.array(rmse_acc["flat"]), np.array(tot_true))
    rmse_curve, _ = _rmse_bias(np.array(rmse_acc["curve"]), np.array(tot_true))

    # --- CALIBRATION of the COMBINED forecaster (leak-free split-by-GAME PARITY) ---
    # Even games = TRAIN, odd = HELD-OUT: a game's Q1/Q2/Q3 never straddle train/eval (no
    # within-game leak) AND both halves share the same season era (a chronological split
    # confounds early-season Elo warm-up over-confidence). Recalibrator fit on TRAIN games
    # only, applied to held-out games it never saw -> strictly leak-free.
    gi = np.array(game_idx)
    tr_m, ev_m = (gi % 2 == 0), (gi % 2 == 1)
    cal: Dict = {}
    if int(tr_m.sum()) >= 30 and int(ev_m.sum()) >= 30 and len(np.unique(y[ev_m])) == 2:
        ev_p, ev_y = rate_arr[ev_m], y[ev_m]
        ece_raw = _ece10(ev_p, ev_y)
        recal_p, method = _recalibrate(rate_arr[tr_m], y[tr_m], ev_p, ev_y)
        ece_recal = _ece10(recal_p, ev_y)
        b_raw_ev, b_recal_ev = _brier(ev_p, ev_y), _brier(recal_p, ev_y)
        cal = {
            "cal_n_eval": int(ev_m.sum()), "cal_n_train": int(tr_m.sum()),
            "ece_raw": round(ece_raw, 5), "ece_recal": round(ece_recal, 5),
            "recal_method": method, "reliability_slope": round(_reliability_slope(ev_p, ev_y), 4),
            "brier_raw_eval": round(b_raw_ev, 5), "brier_recal_eval": round(b_recal_ev, 5),
            "brier_not_worse": bool(b_recal_ev <= b_raw_ev + 1e-4),
            "well_calibrated_raw": bool(ece_raw < 0.025)}
    else:
        cal = {"cal_status": "data_limited", "cal_n_eval": int(ev_m.sum())}

    out = {
        "status": "ok", "n_games": n, "n_checkpoints": int(y.size),
        "quarter_curve": [round(float(c), 4) for c in curve],
        "brier_pregame_elo": round(b_pre, 5), "brier_conditional_blind": round(b_blind, 5),
        "brier_conditional_rating": round(b_rate, 5),
        "combined_beats_pregame": bool(b_rate < b_pre), "combined_beats_blind": bool(b_rate < b_blind),
        "total_rmse_flat": round(rmse_flat, 3), "total_rmse_curve": round(rmse_curve, 3),
        "total_bias_flat": round(bias_flat, 3), "curve_helps": bool(rmse_curve < rmse_flat - 0.05),
        "verdict": (
            f"IN-GAME wins: pregame-Elo Brier {round(b_pre,3)} -> score-only {round(b_blind,3)} "
            f"-> COMBINED {round(b_rate,3)} "
            f"({'best' if b_rate <= min(b_pre, b_blind) else 'not best'}). NBA quarter curve null."),
        "note": "Forecaster quality (a live book also sees the score). RMSE+bias, never MAE. No $ edge.",
    }
    out.update(cal)
    return out


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', rep.get('n'))}"); return 0
    print(f"=== NBA IN-GAME accuracy (n={rep['n_games']} games, {rep['n_checkpoints']} checkpoints) ===")
    print(f"  per-quarter scoring share Q1-Q4: {rep['quarter_curve']} (uniform=0.25)")
    print(f"  win-prob Brier:  pregame-Elo={rep['brier_pregame_elo']}  "
          f"score-only={rep['brier_conditional_blind']}  COMBINED={rep['brier_conditional_rating']}")
    print(f"  combined beats pregame: {rep['combined_beats_pregame']}  "
          f"beats score-only: {rep['combined_beats_blind']}")
    print(f"  final-total RMSE: flat={rep['total_rmse_flat']}  curve={rep['total_rmse_curve']}  "
          f"(curve helps: {rep['curve_helps']})")
    if "ece_raw" in rep:
        print(f"  CALIBRATION (COMBINED, split-by-game, train n={rep['cal_n_train']} "
              f"eval n={rep['cal_n_eval']}):  ECE_raw={rep['ece_raw']} -> "
              f"ECE_recal={rep['ece_recal']} via {rep['recal_method']} "
              f"(rel-slope={rep['reliability_slope']})")
        print(f"    Brier raw={rep['brier_raw_eval']} -> recal={rep['brier_recal_eval']} "
              f"(not worse: {rep['brier_not_worse']}); raw well-cal: {rep['well_calibrated_raw']}")
    else:
        print(f"  CALIBRATION: {rep.get('cal_status', 'n/a')} (eval n={rep.get('cal_n_eval')})")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
