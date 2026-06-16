"""scripts.platformkit.proof_mlb.ingame_accuracy — MLB in-game with a REAL pregame prior.

MLB analog of proof_nba/ingame_accuracy.py (W146): the SHARPEST in-game forecaster fuses the
PREGAME MOV-Elo prior with the realized state, beating pregame-only and score-only. LEAK-FREE:
pregame = walk-forward Elo snapshot recorded BEFORE the rating update; mid-game = cumulative
runs through inning k (innings>k NEVER seen). THREE forecasters of final home-win, Brier-scored
on a held-out SECOND HALF: (a) pregame-Elo-static; (b) score-only (neutral 4.5/4.5 prior +
runs); (c) COMBINED (Elo-anchored lambdas, SUM preserved, + runs). CALIBRATION: 10-bin ECE +
reliability slope of the COMBINED on held-out; a recalibrator (temperature/Platt, selected on
TRAIN log-loss) fit on the TRAIN half ONLY, applied to held-out (never refit on eval) ->
ECE_raw -> ECE_recal, confirming Brier does not worsen; ECE < 0.025 -> clean NULL (a success).
HONEST: a live BOOK also sees the score -> forecaster QUALITY, not a $ edge. Markets efficient;
Brier/log-loss never MAE. INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Corpus override: run(corpus=) or $PROOF_CORPUS_ROOT/mlb > real data/domains (default unchanged).
Run: python -m scripts.platformkit.proof_mlb.ingame_accuracy
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.negbinom_engine import _FALLBACK_R  # noqa: E402
from domains.mlb.predictor import _anchor_nb_tiesplit, _nb_tie_adj_ml  # noqa: E402
from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402
from scripts.platformkit.proof_mlb.beat_the_close_ml import (  # noqa: E402
    _HFA, _INIT, _K, _p_home,
)
from scripts.platformkit.recalibration import _ece as _ece10  # 10-bin ECE  # noqa: E402

_GAMES = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_PITCHERS = _REPO / "data" / "domains" / "mlb" / "pitchers.parquet"
_CHECKPOINTS = (3, 5, 7)            # innings at which to reconstruct a mid-game state
_LEAGUE_LAMBDA = 4.5               # neutral pregame run-rate prior (engine default)


def _corpus_from_env() -> Optional[Path]:  # $PROOF_CORPUS_ROOT/mlb if set else None
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return (Path(root) / "mlb") if root else None


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _logit(p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(pc / (1 - pc))


def _irls_logit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """2-param logistic of y on logit-feature x via ridge Newton-IRLS (pure numpy)."""
    X = np.column_stack([np.ones_like(x), x])
    w = np.zeros(2)
    for _ in range(25):
        mu = np.clip(1.0 / (1.0 + np.exp(-(X @ w))), 1e-9, 1 - 1e-9)
        H = (X.T * (mu * (1 - mu))) @ X + 1e-6 * np.eye(2)
        try:
            step = np.linalg.solve(H, X.T @ (mu - y))
        except np.linalg.LinAlgError:
            break
        w -= step
        if np.linalg.norm(step) < 1e-9:
            break
    return w


def _reliability_slope(p: np.ndarray, y: np.ndarray) -> float:
    """Slope of logistic(y ~ logit(p)); 1.0 == calibrated, <1 over-confident, >1 under."""
    return float(_irls_logit(_logit(p), y)[1])


def _fit_apply_recal(p_tr: np.ndarray, y_tr: np.ndarray, p_ho: np.ndarray) -> Tuple[np.ndarray, str]:
    """Fit temperature AND Platt on the TRAIN half ONLY, pick the lower-TRAIN-log-loss
    method (leak-free: selection never sees held-out), apply it to the held-out probs.
    Returns (recalibrated_holdout_probs, method_name). Pure numpy; no refit on eval split."""
    from scripts.platformkit.calibrator_zoo import _fit_temperature  # noqa: PLC0415
    lt, lh = _logit(p_tr), _logit(p_ho)
    t = _fit_temperature(p_tr, y_tr)                       # temperature scaling
    temp_tr, temp_ho = (1.0 / (1.0 + np.exp(-(z / t))) for z in (lt, lh))
    w = _irls_logit(lt, y_tr)                              # Platt on logit
    sig = lambda z: 1.0 / (1.0 + np.exp(-(np.column_stack([np.ones_like(z), z]) @ w)))
    cands = {"temperature": (temp_tr, temp_ho), "platt": (sig(lt), sig(lh)),
             "identity": (p_tr, p_ho)}
    best = min(cands, key=lambda k: _logloss(cands[k][0], y_tr))   # selected on TRAIN
    return np.clip(cands[best][1], 0.0, 1.0), best


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


def _walk_forward_elo(games) -> np.ndarray:
    """Leak-free as-of pregame P(home win) per game (chronological), SAME engine/params as
    beat_the_close_ml._replay: snapshot recorded BEFORE the rating update."""
    rat: Dict[str, float] = {}
    p = np.empty(len(games))
    h = games["home_team"].to_numpy()
    a = games["away_team"].to_numpy()
    hr = games["home_runs"].to_numpy(float)
    ar = games["away_runs"].to_numpy(float)
    for i in range(len(games)):
        ht, at = str(h[i]), str(a[i])
        rat.setdefault(ht, _INIT)
        rat.setdefault(at, _INIT)
        ph = _p_home(rat[ht], rat[at])
        p[i] = ph                                   # leak-free: recorded pre-update
        s = 1.0 if hr[i] > ar[i] else 0.0
        elo_diff = (rat[ht] - rat[at] + _HFA) * (1 if s else -1)
        mov = np.log(abs(hr[i] - ar[i]) + 1.0) * (2.2 / (elo_diff * 0.001 + 2.2))
        delta = _K * mov * (s - ph)
        rat[ht] += delta
        rat[at] -= delta
    return p


def _reprice_winhome(rep, h0: int, a0: int, ck: int, lam_h: float, lam_a: float,
                     r_h: float, r_a: float) -> float:
    """ml_home from the MLB repricer given cumulative runs through inning ck and lambdas."""
    out = rep.reprice(GameState(
        "mlb", 0.0, h0, a0,
        pregame_params={"lam_home": lam_h, "lam_away": lam_a, "r_home": r_h, "r_away": r_a},
        extra={"innings_played": float(ck)}))
    return float(out.get("ml_home", 0.5))


def run(corpus: Optional[Path] = None) -> Dict:
    import pandas as pd  # noqa: PLC0415
    root = corpus or _corpus_from_env()
    games_path = (root / "games.parquet") if root else _GAMES
    pit_path = (root / "pitchers.parquet") if root else _PITCHERS
    if not games_path.is_file() or not pit_path.is_file():
        return {"status": "no_data", "note": "games.parquet / pitchers.parquet missing"}
    games = pd.read_parquet(games_path)
    pit = pd.read_parquet(pit_path)[["event_id", "home_innings", "away_innings"]]
    df = games.merge(pit, on="event_id", how="inner")
    df = df.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    df["p_pre"] = _walk_forward_elo(df)            # leak-free pregame Elo prior per game
    rep = get_repricer("mlb")
    r_h = r_a = _FALLBACK_R                         # repricer default dispersion (parity)
    # NEUTRAL-prior static ML (flat 4.5/4.5, no score) = the score-only forecaster's prior.
    neutral_static = _nb_tie_adj_ml(_LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a)

    # (a) pregame Elo; (b) score-only (neutral prior + runs); (c) combined (Elo prior + runs).
    pre_p: List[float] = []; score_p: List[float] = []; comb_p: List[float] = []
    y: List[float] = []; is_holdout: List[bool] = []

    n = len(df); mid = n // 2; used_games = 0
    hi_arr, ai_arr = df["home_innings"].to_numpy(), df["away_innings"].to_numpy()
    pp_arr = df["p_pre"].to_numpy(float)
    for i in range(n):
        h = _parse_innings(hi_arr[i])
        a = _parse_innings(ai_arr[i])
        if h is None or a is None or len(h) < 1 or len(a) < 1:
            continue
        fh, fa = sum(h), sum(a)
        if fh == fa:                               # regulation tie -> extras, outcome undefined
            continue
        win = 1.0 if fh > fa else 0.0
        p_pre = float(min(max(pp_arr[i], 0.01), 0.99))
        # COMBINED prior: tilt the lambdas (SUM preserved) so the NegBinom matrix ML == Elo p.
        lam_h, lam_a = _anchor_nb_tiesplit(_LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a, p_pre)
        any_ck = False
        for ck in _CHECKPOINTS:
            if len(h) < ck or len(a) < ck:
                continue
            h0, a0 = sum(h[:ck]), sum(a[:ck])
            pre_p.append(p_pre)
            score_p.append(_reprice_winhome(rep, h0, a0, ck, _LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a))
            comb_p.append(_reprice_winhome(rep, h0, a0, ck, lam_h, lam_a, r_h, r_a))
            y.append(win)
            is_holdout.append(i >= mid)
            any_ck = True
        if any_ck:
            used_games += 1

    if not y:
        return {"status": "no_data", "note": "no reconstructable checkpoints"}
    y_arr = np.array(y)
    mask = np.array(is_holdout)
    if mask.sum() < 60:                            # held-out too thin -> score everything
        mask = np.ones_like(mask, dtype=bool)
        holdout_note = "held-out 2nd-half < 60 checkpoints; scored on full corpus"
    else:
        holdout_note = "scored on the held-out SECOND HALF (Elo warms up on the first)"

    pre_a, sc_a, cb_a = (np.array(v)[mask] for v in (pre_p, score_p, comb_p))
    yh = y_arr[mask]
    b_pre, b_score, b_comb = (_brier(p, yh) for p in (pre_a, sc_a, cb_a))
    ll_pre, ll_score, ll_comb = (_logloss(p, yh) for p in (pre_a, sc_a, cb_a))
    # CALIBRATION of COMBINED (leak-free): ECE+slope on held-out; recal fit on TRAIN half only.
    ece_raw = _ece10(cb_a, yh)
    slope_raw = _reliability_slope(cb_a, yh)
    cb_train = np.array(comb_p)[~mask]
    y_train = y_arr[~mask]
    well_calibrated = bool(ece_raw < 0.025)
    if cb_train.size >= 30 and len(np.unique(y_train)) >= 2:
        cb_recal, recal_method = _fit_apply_recal(cb_train, y_train, cb_a)
        ece_recal = _ece10(cb_recal, yh)
        slope_recal = _reliability_slope(cb_recal, yh)
        b_comb_recal = _brier(cb_recal, yh)
        recal_helps = bool(ece_recal < ece_raw - 1e-9)
        brier_ok = bool(b_comb_recal <= b_comb + 5e-4)   # recal must not worsen Brier
    else:
        recal_method = "none"
        ece_recal, slope_recal, b_comb_recal = ece_raw, slope_raw, b_comb
        recal_helps, brier_ok = False, True

    d_vs_pre = round(b_comb - b_pre, 5)            # <0 => combined sharper than pregame
    d_vs_score = round(b_comb - b_score, 5)        # <=0 => combined ties/beats score-only
    combined_best = bool(b_comb <= min(b_pre, b_score) + 1e-9)
    if combined_best and b_comb < b_pre:
        verdict = (f"COMBINED sharpest: pregame {b_pre:.4f} -> score-only {b_score:.4f} -> "
                   f"COMBINED {b_comb:.4f}; fusing prior + realized state beats both (W146).")
    elif b_comb < b_pre and abs(d_vs_score) <= 1e-4:
        verdict = (f"COMBINED ties score-only ({b_comb:.4f} vs {b_score:.4f}), beats pregame "
                   f"{b_pre:.4f}: prior washed out by runs but no worse + far sharper.")
    else:
        verdict = (f"HONEST mixed: pregame {b_pre:.4f}, score-only {b_score:.4f}, combined "
                   f"{b_comb:.4f}; combined NOT strictly best.")
    if well_calibrated:
        cal_verdict = (f"COMBINED ALREADY well-calibrated (ECE {ece_raw:.4f} < 0.025, slope "
                       f"{slope_raw:.2f}); recal ({recal_method}) -> {ece_recal:.4f} adds "
                       f"little. Clean NULL = a success.")
    else:
        tag = "improves" if (recal_helps and brier_ok) else "does not improve"
        cal_verdict = (f"COMBINED miscalibrated (ECE {ece_raw:.4f}, slope {slope_raw:.2f}); "
                       f"TRAIN-fit {recal_method} {tag} ECE -> {ece_recal:.4f}, Brier "
                       f"{b_comb:.4f} -> {b_comb_recal:.4f} (brier_ok={brier_ok}).")

    return {
        "status": "ok",  # in-game CALIBRATION (COMBINED, held-out, leak-free) below
        "n_games": used_games, "n_checkpoints": int(yh.size),
        "ece_raw": round(ece_raw, 5), "ece_recal": round(ece_recal, 5),
        "recal_method": recal_method, "n_train_calib": int(cb_train.size),
        "reliability_slope": round(slope_raw, 4),
        "reliability_slope_recal": round(slope_recal, 4),
        "combined_well_calibrated": well_calibrated, "recal_improves_ece": recal_helps,
        "recal_brier_not_worse": brier_ok, "brier_combined_recal": round(b_comb_recal, 5),
        "calibration_verdict": cal_verdict,  # ---- sharpness (Brier / log-loss) ----
        "brier_pregame": round(b_pre, 5), "brier_scoreonly": round(b_score, 5),
        "brier_combined": round(b_comb, 5), "logloss_pregame": round(ll_pre, 5),
        "logloss_scoreonly": round(ll_score, 5), "logloss_combined": round(ll_comb, 5),
        "delta_combined_vs_pregame": d_vs_pre, "delta_combined_vs_scoreonly": d_vs_score,
        "combined_beats_pregame": bool(b_comb < b_pre), "combined_best": combined_best,
        "neutral_static_pregame": round(neutral_static, 4), "verdict": verdict,
        "note": (f"Leak-free; {holdout_note}. Win-prob graded on Brier/log-loss (never MAE). "
                 f"A live book also sees the score -> forecaster quality, not a $ edge."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', '')}")
        return 0
    print(f"=== MLB IN-GAME accuracy (n={rep['n_games']} games, "
          f"{rep['n_checkpoints']} held-out checkpoints) ===")
    print(f"  (a) pregame-Elo  Brier {rep['brier_pregame']}  LL {rep['logloss_pregame']}")
    print(f"  (b) score-only   Brier {rep['brier_scoreonly']}  LL {rep['logloss_scoreonly']}")
    print(f"  (c) COMBINED     Brier {rep['brier_combined']}  LL {rep['logloss_combined']}")
    print(f"  combined vs pregame {rep['delta_combined_vs_pregame']:+} / vs score-only "
          f"{rep['delta_combined_vs_scoreonly']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print("--- CALIBRATION (COMBINED, held-out, 10-bin) ---")
    print(f"  ECE raw -> recal: {rep['ece_raw']} -> {rep['ece_recal']}  (method "
          f"{rep['recal_method']}, fit on {rep['n_train_calib']} TRAIN checkpoints)")
    print(f"  slope {rep['reliability_slope']} -> {rep['reliability_slope_recal']} "
          f"(1.0=calibrated); Brier {rep['brier_combined']} -> "
          f"{rep['brier_combined_recal']} (not worse: {rep['recal_brier_not_worse']})")
    print(f"  CAL VERDICT: {rep['calibration_verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
