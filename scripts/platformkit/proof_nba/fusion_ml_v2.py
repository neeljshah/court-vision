"""scripts.platformkit.proof_nba.fusion_ml_v2 -- pa7: stacked complementary blend NBA ML.

pa7 spec: extend fusion_nba's elo-logit base with TWO complementary schedule/form signals
that are structurally distinct from cumulative Elo:

  1. rest_diff  -- (home days_rest - away days_rest): short-rest advantage is a schedule
     artifact Elo updates DO NOT capture (Elo updates on outcome, not on schedule).
  2. b2b_net    -- (home_b2b_indicator - away_b2b_indicator): back-to-back penalty is the
     most acute rest signal; +1 if home is on B2B-only, -1 if away is.
  3. win10_diff -- rolling 10-game win-rate differential (form): measures RECENT form momentum
     that cumulative Elo may lag on (Elo updates are margin-weighted but slow).

The base `fusion_nba.py` showed that scoring-margin corr(elo_logit, margin_diff)=0.944 --
nearly a relabel of Elo -- hence ABSORBED. The signals above are designed to have LOWER
correlation with elo_logit: schedule effects are PUBLIC information the market prices in
(so honest ABSORB is still the likely verdict), but they are mechanically distinct and
worth testing rigorously.

FUSION = leak-free walk-forward RIDGE logistic on [1, elo_logit, rest_diff, b2b_net, win10_diff].
Weights fit on games [0..i), applied to i (never refit on the eval split).
Scored on the held-out tail: base Brier vs fused Brier vs devigged close Brier.
GATE: fused Brier <= base Brier -> SHIP (absorption/narrowing classified); else ABSORBED.
No $ edge; no flag flipped ON; units only; ASCII; <=300 LOC.

Run: python -m scripts.platformkit.proof_nba.fusion_ml_v2
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import load_box, load_close  # noqa: E402
from scripts.platformkit.proof_nba.ml_accuracy import (  # noqa: E402
    american_to_prob, _brier_logloss, _walk_forward_elo,
)

_ALPHA_WIN = 1.0 / 10.0   # win10: equal weight over 10 games (EW approx)
_MIN_TRAIN = 80            # games before WF logistic starts (same as fusion_nba)
_RIDGE = 1.0               # L2 coefficient (stabilise small-N WF fit)
_MAX_REST = 7              # cap days_rest at 7 (tail games after byes don't extrapolate well)
_B2B_THRESH = 1            # days_rest <= 1 means back-to-back (played yesterday or today)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _walk_forward_rest_b2b(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Leak-free per-team days_rest and B2B indicator, computed from game dates.

    days_rest[i] = calendar days between team's previous game date and game i.
    Capped at _MAX_REST; first appearance gets _MAX_REST (no prior game).
    rest_diff = home_rest - away_rest.
    b2b_net   = int(home_b2b) - int(away_b2b), where b2b = days_rest <= _B2B_THRESH.
    Both computed BEFORE the game date is stored (fully leak-free).
    """
    last_date: Dict[str, pd.Timestamp] = {}
    n = len(df)
    rest_diff = np.empty(n)
    b2b_net = np.empty(n)
    dates = df["date"].to_numpy()
    h = df["home_abbr"].to_numpy()
    a = df["away_abbr"].to_numpy()
    for i in range(n):
        dt = pd.Timestamp(dates[i])
        ht, at = str(h[i]), str(a[i])
        # pre-game snapshot (BEFORE storing today's date)
        h_rest = int(min((dt - last_date[ht]).days, _MAX_REST)) if ht in last_date else _MAX_REST
        a_rest = int(min((dt - last_date[at]).days, _MAX_REST)) if at in last_date else _MAX_REST
        rest_diff[i] = h_rest - a_rest
        b2b_net[i] = float(h_rest <= _B2B_THRESH) - float(a_rest <= _B2B_THRESH)
        # update after snapshot
        last_date[ht] = dt
        last_date[at] = dt
    return rest_diff, b2b_net


def _walk_forward_win10(df: pd.DataFrame) -> np.ndarray:
    """Leak-free rolling ~10-game win-rate differential (home minus away).

    Uses EW update with alpha=1/10 to approximate a 10-game window without a
    circular buffer. Starts at 0.5 for each team (no prior history). Snapshot
    taken BEFORE updating with today's result (leak-free).
    """
    win10: Dict[str, float] = {}
    n = len(df)
    sig = np.empty(n)
    h = df["home_abbr"].to_numpy()
    a = df["away_abbr"].to_numpy()
    hp = df["home_pts"].to_numpy(float)
    ap = df["away_pts"].to_numpy(float)
    for i in range(n):
        ht, at = str(h[i]), str(a[i])
        win10.setdefault(ht, 0.5)
        win10.setdefault(at, 0.5)
        sig[i] = win10[ht] - win10[at]
        hw = 1.0 if hp[i] > ap[i] else 0.0
        win10[ht] += _ALPHA_WIN * (hw - win10[ht])
        win10[at] += _ALPHA_WIN * ((1.0 - hw) - win10[at])
    return sig


def _fit_logistic(X: np.ndarray, y: np.ndarray,
                  iters: int = 300, lr: float = 0.3) -> np.ndarray:
    """Ridge-regularised logistic via gradient descent; intercept (col 0) unpenalised."""
    n, k = X.shape
    w = np.zeros(k)
    for _ in range(iters):
        z = X @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        grad = X.T @ (p - y) / n
        grad[1:] += _RIDGE * w[1:] / n
        w -= lr * grad
    return w


def _walk_forward_fuse(elo_logit: np.ndarray, rest_diff: np.ndarray,
                       b2b_net: np.ndarray, win10_diff: np.ndarray,
                       y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Leak-free WF logistic on [1, elo_logit, rest_diff, b2b_net, win10_diff].

    Features standardised by PRIOR-only mean/std; valid only for i >= _MIN_TRAIN.
    Returns (fused_prob, valid_mask).
    """
    n = len(y)
    fused = np.full(n, np.nan)
    valid = np.zeros(n, dtype=bool)
    feats = np.column_stack([elo_logit, rest_diff, b2b_net, win10_diff])
    for i in range(_MIN_TRAIN, n):
        f_tr, y_tr = feats[:i], y[:i]
        mu = f_tr.mean(axis=0)
        sd = f_tr.std(axis=0) + 1e-9
        Xtr = np.column_stack([np.ones(i), (f_tr - mu) / sd])
        w = _fit_logistic(Xtr, y_tr)
        xi = np.array([1.0, *((feats[i] - mu) / sd)])
        z = float(xi @ w)
        fused[i] = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        valid[i] = True
    return fused, valid


def _load_merge() -> pd.DataFrame:
    """Load box + closing moneyline odds, merge on (date, home, away)."""
    from scripts.platformkit.proof_nba.asof_box_accuracy import _NBA
    box = load_box()
    raw = pd.read_parquet(_NBA / "odds.parquet").rename(
        columns={"home_team": "home_abbr", "away_team": "away_abbr"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.dropna(subset=["home_ml", "away_ml"])
    raw["imp_h"] = raw["home_ml"].map(american_to_prob)
    raw["imp_a"] = raw["away_ml"].map(american_to_prob)
    raw["p_market"] = raw["imp_h"] / (raw["imp_h"] + raw["imp_a"])
    return box.merge(raw[["date", "home_abbr", "away_abbr", "p_market"]],
                     on=["date", "home_abbr", "away_abbr"], how="inner").reset_index(drop=True)


def run() -> Dict:
    """Execute the pa7 stacked complementary blend and return a gate-ready report dict."""
    m = _load_merge()
    n = len(m)
    if n < 120:
        return {"status": "data_limited", "n_overlap": n,
                "note": "Need >=120 overlap games for a stable WF logistic blend."}

    # compute all signals on the MERGED frame (date-sorted, leak-free)
    m["p_elo"] = _walk_forward_elo(m)
    rest_diff, b2b_net = _walk_forward_rest_b2b(m)
    win10_diff = _walk_forward_win10(m)

    y = (m["home_pts"] > m["away_pts"]).to_numpy(float)
    p_elo = m["p_elo"].to_numpy(float)
    p_mkt = m["p_market"].to_numpy(float)
    elo_logit = _logit(p_elo)

    fused, valid = _walk_forward_fuse(elo_logit, rest_diff, b2b_net, win10_diff, y)
    te = valid
    n_hold = int(te.sum())
    if n_hold < 40:
        return {"status": "data_limited", "n_overlap": n, "n_holdout": n_hold,
                "note": "Too few WF-fused games for a held-out comparison."}

    b_base, ll_base = _brier_logloss(p_elo[te], y[te])
    b_fuse, ll_fuse = _brier_logloss(fused[te], y[te])
    b_mkt, ll_mkt = _brier_logloss(p_mkt[te], y[te])

    gap_base = round(b_base - b_mkt, 4)
    gap_fuse = round(b_fuse - b_mkt, 4)
    narrowed = round(gap_base - gap_fuse, 4)
    d_brier = round(b_fuse - b_base, 4)

    # pa7 gate: fused Brier <= base Brier -> SHIP else ABSORB
    gate_pass = b_fuse <= b_base + 1e-9

    # correlations of each new signal with elo_logit (complementarity check)
    mask = te
    c_rest = round(float(np.corrcoef(elo_logit[mask], rest_diff[mask])[0, 1]), 3)
    c_b2b = round(float(np.corrcoef(elo_logit[mask], b2b_net[mask])[0, 1]), 3)
    c_win10 = round(float(np.corrcoef(elo_logit[mask], win10_diff[mask])[0, 1]), 3)

    if narrowed > 0.002 and d_brier < -0.001:
        kind = "narrows_gap"
    elif d_brier < -0.001:
        kind = "calibration_win"
    elif abs(d_brier) <= 0.001:
        kind = "absorbed_null"
    else:
        kind = "absorbed_null"

    verdict_map = {
        "narrows_gap": (
            f"SHIP: stacked blend narrows the gap to the close "
            f"({gap_base:+} -> {gap_fuse:+} Brier); rest/B2B/win10 add info Elo lacked"),
        "calibration_win": (
            f"SHIP: stacked blend sharper than Elo (Brier {b_base:.4f}->{b_fuse:.4f}); "
            f"not vs close gap; a calibration/sharpness gain"),
        "absorbed_null": (
            f"ABSORBED: blend does not beat Elo (Brier {b_base:.4f}->{b_fuse:.4f}); "
            f"market prices rest/B2B/form; honest efficient-market result"),
    }

    return {
        "status": "ok",
        "n_overlap": n,
        "n_holdout": n_hold,
        "base_brier": round(b_base, 4),
        "fused_brier": round(b_fuse, 4),
        "close_brier": round(b_mkt, 4),
        "base_logloss": round(ll_base, 4),
        "fused_logloss": round(ll_fuse, 4),
        "close_logloss": round(ll_mkt, 4),
        "gap_base_to_close": gap_base,
        "gap_fused_to_close": gap_fuse,
        "gap_narrowed_by_fusion": narrowed,
        "fused_minus_base_brier": d_brier,
        "corr_elo_rest": c_rest,
        "corr_elo_b2b": c_b2b,
        "corr_elo_win10": c_win10,
        "gate_pass": gate_pass,
        "verdict_kind": kind,
        "verdict": verdict_map[kind],
        "note": (
            "pa7 stacked complementary blend: MOV-Elo + rest_diff + b2b_net + win10_diff. "
            "Leak-free WF logistic; weights fit on prior games only. No dollar edge. "
            f"Gate: fused<=base -> {'SHIP' if gate_pass else 'ABSORBED/REJECT'}."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n_overlap={rep.get('n_overlap')} -- {rep.get('note')}")
        return 0
    print(f"=== pa7 NBA ML stacked complementary blend (n={rep['n_overlap']}, "
          f"holdout={rep['n_holdout']}) ===")
    print(f"  {'predictor':>16}  {'Brier':>8} {'LogLoss':>8}")
    print(f"  {'devig close':>16}  {rep['close_brier']:>8} {rep['close_logloss']:>8}")
    print(f"  {'Elo (base)':>16}  {rep['base_brier']:>8} {rep['base_logloss']:>8}")
    print(f"  {'stacked fused':>16}  {rep['fused_brier']:>8} {rep['fused_logloss']:>8}")
    print(f"\ngap base->close: {rep['gap_base_to_close']:+}  "
          f"gap fused->close: {rep['gap_fused_to_close']:+}  "
          f"narrowed: {rep['gap_narrowed_by_fusion']:+}")
    print(f"fused - base Brier: {rep['fused_minus_base_brier']:+}")
    print(f"corr(elo, rest_diff)={rep['corr_elo_rest']}  "
          f"corr(elo, b2b_net)={rep['corr_elo_b2b']}  "
          f"corr(elo, win10_diff)={rep['corr_elo_win10']}")
    print(f"GATE pass (fused<=base): {rep['gate_pass']}")
    print(f"VERDICT [{rep['verdict_kind']}]: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())
