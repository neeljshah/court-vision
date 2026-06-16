"""scripts.platformkit.proof_soccer.ingame_ht_accuracy — soccer in-game: the halftime win.

Soccer in-game was un-backtestable (no per-minute timeline on disk), BUT the halftime goal
split IS on disk: match_stats.parquet carries hthg/htag at >99.95% coverage. A halftime score
is a LEAK-FREE minute-45 in-game state — the full-time result (FTHG/FTAG) is the future outcome.
Scores the full-time outcome with 1X2 multiclass Brier sum_{H,D,A}(p-y)^2 and O/U-2.5 two-class
Brier (p_over-y_over)^2, comparing the HT-CONDITIONAL repricer surface (pregame lambdas +
observed HT score) vs the PREGAME-STATIC surface (same lambdas, 0-0 state), on a held-out split.

Pipeline (all leak-free): (1) pregame lambdas via domains/soccer/ratings.walk_forward_goals
(EW Poisson, strict pre-match snapshot before the EW update); (2) reprice at minute=45 with
the observed HT score via the SoccerRepricer (live_repricer.get_repricer('soccer')) — scales
the lambdas to the remaining 45 min and shifts the goals matrix by goals already scored;
(3) score the FULL-TIME outcome on a held-out second-half-of-history split.
Expect conditional < static: conditioning on the realized HT score MECHANICALLY sharpens the
final-outcome forecast. HONEST: forecaster QUALITY not a guaranteed price edge (a live book
also sees the HT score). Brier for win-prob (1X2, O/U). No $ edge.
INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_soccer.ingame_ht_accuracy
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import pandas as pd  # noqa: E402

from domains.soccer.ratings import walk_forward_goals  # noqa: E402
from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402
from scripts.platformkit.calibration_ladder import reliability, _logit  # noqa: E402
from scripts.platformkit.calibrator_zoo import _fit_temperature, _sigmoid  # noqa: E402

_EPS = 1e-12

_MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_STATS = _REPO / "data" / "domains" / "soccer" / "match_stats.parquet"
_FULL_MINUTES = 90.0
_HT_MINUTE = 45.0


def _corpus_from_env() -> Optional[Path]:
    """$PROOF_CORPUS_ROOT/soccer if the env var is set else None (override contract)."""
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(root) / "soccer" if root else None


def _paths(corpus: Optional[Path]) -> Tuple[Path, Path]:
    """(matches, match_stats) by precedence: arg > $PROOF_CORPUS_ROOT/soccer > real default."""
    root = corpus or _corpus_from_env()
    if root is not None:
        return root / "matches.parquet", root / "match_stats.parquet"
    return _MATCHES, _STATS


def _brier_1x2(p_h: np.ndarray, p_d: np.ndarray, p_a: np.ndarray,
               y_h: np.ndarray, y_d: np.ndarray, y_a: np.ndarray) -> float:
    """Multiclass Brier = mean over matches of sum_{H,D,A} (p - y)^2."""
    return float(np.mean((p_h - y_h) ** 2 + (p_d - y_d) ** 2 + (p_a - y_a) ** 2))


def _brier_2c(p_over: np.ndarray, y_over: np.ndarray) -> float:
    """Standard single-event O/U Brier: mean of (p_over - y_over)^2."""
    return float(np.mean((p_over - y_over) ** 2))


def _surface(rep, lam_h: float, lam_a: float, elapsed: float,
             h0: int, a0: int) -> Tuple[float, float, float, float]:
    """Reprice and return (1X2_home, 1X2_draw, 1X2_away, over_2.5)."""
    st = GameState(
        sport="soccer",
        elapsed_minutes=elapsed,
        home_score=h0,
        away_score=a0,
        pregame_params={"lam_home": lam_h, "lam_away": lam_a, "rho": 0.0},
    )
    o = rep.reprice(st)
    return (
        float(o["1X2_home"]),
        float(o["1X2_draw"]),
        float(o["1X2_away"]),
        float(o["over_2.5"]),
    )


def _fit_platt(p_tr: np.ndarray, y_tr: np.ndarray) -> Tuple[float, float]:
    """Fit Platt a*logit(p)+b on TRAIN via numpy Newton-IRLS. Returns (a, b)."""
    z = _logit(np.clip(p_tr, _EPS, 1 - _EPS))
    X = np.column_stack([z, np.ones_like(z)])
    w = np.zeros(2)
    for _ in range(25):
        mu = np.clip(_sigmoid(X @ w), _EPS, 1 - _EPS)
        grad = X.T @ (mu - y_tr)
        H = (X.T * (mu * (1 - mu))) @ X + 1e-6 * np.eye(2)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w -= step
        if np.linalg.norm(step) < 1e-9:
            break
    return float(w[0]), float(w[1])


def _calibrate(p_tr: np.ndarray, y_tr: np.ndarray, p_te: np.ndarray,
               y_te: np.ndarray) -> Dict:
    """Fit temperature AND Platt on TRAIN ONLY, apply to HELD-OUT, SELECT by TRAIN log-loss
    (tie -> temperature). Leak-free: neither recal params nor the method choice see held-out
    outcomes (y_te accepted for caller symmetry; unused). Returns held-out probs + diagnostics."""
    z_tr = _logit(np.clip(p_tr, _EPS, 1 - _EPS))
    z_te = _logit(np.clip(p_te, _EPS, 1 - _EPS))

    T = _fit_temperature(p_tr, y_tr)
    a, b = _fit_platt(p_tr, y_tr)

    def _ll(p: np.ndarray, y: np.ndarray) -> float:
        pc = np.clip(p, _EPS, 1 - _EPS)
        return float(np.mean(-(y * np.log(pc) + (1 - y) * np.log(1 - pc))))

    # Method selection uses TRAIN log-loss ONLY (no held-out peeking).
    ll_temp = _ll(np.clip(_sigmoid(z_tr / T), 0.0, 1.0), y_tr)
    ll_platt = _ll(np.clip(_sigmoid(a * z_tr + b), 0.0, 1.0), y_tr)
    if ll_platt < ll_temp - 1e-9:
        probs = np.clip(_sigmoid(a * z_te + b), 0.0, 1.0)
        return {"method": "platt", "probs": probs, "T": T, "platt_a": a, "platt_b": b}
    probs = np.clip(_sigmoid(z_te / T), 0.0, 1.0)
    return {"method": "temperature", "probs": probs, "T": T, "platt_a": a, "platt_b": b}


def run(corpus: Optional[Path] = None) -> Dict:
    matches_path, stats_path = _paths(corpus)
    if not (matches_path.is_file() and stats_path.is_file()):
        return {"status": "data_missing",
                "note": "need matches.parquet + match_stats.parquet"}

    matches = pd.read_parquet(matches_path)
    stats = pd.read_parquet(stats_path)

    # Leak-free pre-match lambdas (snapshot-before-update EW Poisson).
    wf = walk_forward_goals(matches)
    wf = wf.dropna(subset=["lam_home", "lam_away", "fthg", "ftag"]).copy()

    # Attach the observed halftime score (the leak-free minute-45 in-game state).
    ht = stats.dropna(subset=["hthg", "htag"])[["event_id", "hthg", "htag"]].copy()
    m = wf.merge(ht, on="event_id", how="inner")
    m["date"] = pd.to_datetime(m["date"])
    m = m.sort_values("date", kind="mergesort").reset_index(drop=True)

    # Sanity: HT goals must not exceed FT goals (else the join/state is corrupt).
    ok = (m["hthg"] <= m["fthg"]) & (m["htag"] <= m["ftag"])
    n_drop = int((~ok).sum())
    m = m[ok].reset_index(drop=True)

    n = len(m)
    if n < 200:
        return {"status": "data_limited", "n": n}

    # Chronological held-out split: evaluate on the second half of history only.
    mid = n // 2
    te = m.iloc[mid:].reset_index(drop=True)
    n_te = len(te)

    rep = get_repricer("soccer")

    # Full-time targets on the held-out split.
    fth = te["fthg"].to_numpy(float)
    fta = te["ftag"].to_numpy(float)
    y_h = (fth > fta).astype(float)
    y_d = (fth == fta).astype(float)
    y_a = (fth < fta).astype(float)
    y_over = ((fth + fta) >= 3).astype(float)

    lam_h = te["lam_home"].to_numpy(float)
    lam_a = te["lam_away"].to_numpy(float)
    hthg = te["hthg"].to_numpy(int)
    htag = te["htag"].to_numpy(int)

    sh_h = np.empty(n_te); sh_d = np.empty(n_te); sh_a = np.empty(n_te); sh_o = np.empty(n_te)
    co_h = np.empty(n_te); co_d = np.empty(n_te); co_a = np.empty(n_te); co_o = np.empty(n_te)
    for i in range(n_te):
        # PREGAME-STATIC: same lambdas, kick-off 0-0 state (elapsed=0).
        sh_h[i], sh_d[i], sh_a[i], sh_o[i] = _surface(
            rep, lam_h[i], lam_a[i], 0.0, 0, 0)
        # HT-CONDITIONAL: minute-45 state with the observed HT score.
        co_h[i], co_d[i], co_a[i], co_o[i] = _surface(
            rep, lam_h[i], lam_a[i], _HT_MINUTE, int(hthg[i]), int(htag[i]))

    b_static_1x2 = _brier_1x2(sh_h, sh_d, sh_a, y_h, y_d, y_a)
    b_cond_1x2 = _brier_1x2(co_h, co_d, co_a, y_h, y_d, y_a)
    b_static_ou = _brier_2c(sh_o, y_over)
    b_cond_ou = _brier_2c(co_o, y_over)

    # IN-GAME CALIBRATION (ECE) of the COMBINED (HT-conditional) O/U-2.5 forecaster.
    # Recalibrator fit on the TRAIN half ONLY and applied to the HELD-OUT half ->
    # strictly leak-free (recal params never see held-out outcomes; 1X2 is multiclass).
    tr = m.iloc[:mid].reset_index(drop=True)
    n_tr = len(tr)
    tr_lam_h = tr["lam_home"].to_numpy(float)
    tr_lam_a = tr["lam_away"].to_numpy(float)
    tr_hthg = tr["hthg"].to_numpy(int)
    tr_htag = tr["htag"].to_numpy(int)
    tr_over = ((tr["fthg"].to_numpy(float) + tr["ftag"].to_numpy(float)) >= 3).astype(float)
    tr_o = np.empty(n_tr)
    for i in range(n_tr):
        _, _, _, tr_o[i] = _surface(
            rep, tr_lam_h[i], tr_lam_a[i], _HT_MINUTE, int(tr_hthg[i]), int(tr_htag[i]))

    rel_raw = reliability(co_o, y_over)
    ece_raw = float(rel_raw["ece"])
    slope_raw = float(rel_raw["reliability_slope"])
    cal = _calibrate(tr_o, tr_over, co_o, y_over)
    rel_recal = reliability(cal["probs"], y_over)
    ece_recal = float(rel_recal["ece"])
    brier_recal_ou = float(rel_recal["brier"])  # combined O/U Brier after recal
    recal_method = cal["method"]
    # Honest: well-calibrated already if raw ECE < ~0.025 (recal adds nothing).
    miscalibrated = bool(ece_raw > 0.025)
    brier_not_worse = bool(brier_recal_ou <= b_cond_ou + 1e-6)

    d_1x2 = round(b_cond_1x2 - b_static_1x2, 5)   # <0 => conditional sharper
    d_ou = round(b_cond_ou - b_static_ou, 5)

    cond_wins = bool(b_cond_1x2 < b_static_1x2 and b_cond_ou < b_static_ou)
    verdict = (
        f"IN-GAME (HT) wins: 1X2 Brier {round(b_static_1x2,4)} (static) -> "
        f"{round(b_cond_1x2,4)} (HT-conditional), delta {d_1x2:+}; "
        f"O/U-2.5 Brier {round(b_static_ou,4)} -> {round(b_cond_ou,4)}, delta {d_ou:+}. "
        f"Conditioning on the realized HT score sharpens both markets."
        if cond_wins else
        f"Unexpected: HT-conditional did NOT beat static on both markets "
        f"(1X2 delta {d_1x2:+}, O/U delta {d_ou:+})."
    )

    return {
        "status": "ok",
        "n": n,
        "n_holdout": n_te,
        "n_dropped_ht_gt_ft": n_drop,
        "brier_1x2_static": round(b_static_1x2, 5),
        "brier_1x2_conditional": round(b_cond_1x2, 5),
        "brier_1x2_delta": d_1x2,
        "brier_ou25_static": round(b_static_ou, 5),
        "brier_ou25_conditional": round(b_cond_ou, 5),
        "brier_ou25_delta": d_ou,
        "conditional_beats_static": cond_wins,
        "base_rate_over25": round(float(np.mean(y_over)), 4),
        # In-game CALIBRATION of the COMBINED (HT-conditional) O/U-2.5 forecaster.
        "ece_raw": round(ece_raw, 5),
        "ece_recal": round(ece_recal, 5),
        "recal_method": recal_method,
        "reliability_slope": round(slope_raw, 4),
        "brier_ou25_recal": round(brier_recal_ou, 5),
        "brier_not_worse_after_recal": brier_not_worse,
        "miscalibrated_raw": miscalibrated,
        "n_train_calib": n_tr,
        "verdict": verdict,
        "note": ("Leak-free: pregame lambdas are a strict pre-match EW-Poisson snapshot; the "
                 "minute-45 HT score (hthg/htag) is an OBSERVED in-game state; the full-time "
                 "result (FTHG/FTAG) is the future outcome being scored on a held-out split. "
                 "Forecaster QUALITY (a live book also sees the HT score); Brier graded. No $ edge."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', rep.get('n'))}")
        return 0
    print(f"=== Soccer IN-GAME (halftime) accuracy "
          f"(n={rep['n']}, holdout={rep['n_holdout']}) ===")
    print(f"  {'market':>10}  {'static':>9}  {'HT-cond':>9}  {'delta':>9}")
    print(f"  {'1X2':>10}  {rep['brier_1x2_static']:>9}  "
          f"{rep['brier_1x2_conditional']:>9}  {rep['brier_1x2_delta']:>+9}")
    print(f"  {'O/U-2.5':>10}  {rep['brier_ou25_static']:>9}  "
          f"{rep['brier_ou25_conditional']:>9}  {rep['brier_ou25_delta']:>+9}")
    print(f"  base-rate(over2.5)={rep['base_rate_over25']}  "
          f"dropped(HT>FT)={rep['n_dropped_ht_gt_ft']}")
    print("--- IN-GAME CALIBRATION (COMBINED HT-conditional O/U-2.5 forecaster) ---")
    cal_state = ("MISCALIBRATED (ECE>0.025)" if rep["miscalibrated_raw"]
                 else "already well-calibrated (ECE<=0.025)")
    print(f"  ECE_raw={rep['ece_raw']} -> ECE_recal={rep['ece_recal']} "
          f"(method={rep['recal_method']}, fit on TRAIN n={rep['n_train_calib']})")
    print(f"  reliability_slope(raw)={rep['reliability_slope']}  "
          f"Brier {rep['brier_ou25_conditional']} -> {rep['brier_ou25_recal']} "
          f"(not_worse={rep['brier_not_worse_after_recal']})")
    print(f"  raw forecaster: {cal_state}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
