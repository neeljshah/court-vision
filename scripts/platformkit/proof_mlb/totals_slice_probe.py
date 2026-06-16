"""scripts.platformkit.proof_mlb.totals_slice_probe -- HUNT D totals slice probe (read-only).

Question (HUNT D): is there ANY market/regime SLICE where our calibrated totals number
measurably BEATS the devigged closing O/U line on >=2 independent corpora with
Diebold-Mariano p<0.05 AND N>=200?

Corpora (>=2, no contrivance): MLB home_league NL (n~1679) vs AL (n~1679) -- the close O/U
line is non-null on 3,358 games (seasons 2020-2021, book sbro_archive). Each league clears
N>=200 on its own. Regime slices tested WITHIN each corpus: early-season (first 40% of each
season by date) vs late-season; plus the full corpus.

Anti-p-hack rails honored here:
  - Leak-free walk-forward run-total model: EW runs-scored / runs-allowed per team, snapshot
    BEFORE update; plus leak-free as-of park factor (asof_park.parquet) and as-of SP run-allowed
    (asof_features.parquet). No future info. sigma fit on a TRAIN prefix only.
  - Devig the close: the O/U close carries ONE price (closeou_odds = OVER side by sbro convention).
    We pair it with the symmetric under price implied by a fixed book hold and SHIN-devig the pair
    to a no-vig P(over). (Single-price -> we use the standard two-sided hold reconstruction; this is
    the same devig the scoreboard uses for MLB totals.)
  - Skill score = per-game over/under log-loss. Beat = our mean log-loss LOWER than the close's,
    tested by Diebold-Mariano on the per-game loss differential, SE clustered by game DATE.
  - A lift on one league with a drop on the other = overfit signature = REJECT.
  - Honest REJECT / "market efficient here" is the SUCCESS outcome and is what we expect.

NOT an edge claim: even an in-sample DM win is reported as "needs forward CLV", never a $ claim.

Run:
    python -m scripts.platformkit.proof_mlb.totals_slice_probe
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_MLB = _REPO / "data" / "domains" / "mlb"
_ALPHA = 0.06            # EW update rate for run-rate
_INIT_RPG = 4.55         # ~half league mean total (~9.1)
_HOLD = 0.045            # assumed two-sided book hold for devig reconstruction
_TRAIN_FRAC = 0.5        # sigma fit prefix
_MIN_N = 200


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _am_to_p(am: float) -> float:
    """American odds -> implied prob (with vig)."""
    am = float(am)
    if am < 0:
        return (-am) / ((-am) + 100.0)
    return 100.0 / (am + 100.0)


def _devig_over(p_over_raw: float) -> float:
    """Reconstruct no-vig P(over) from the single over-side implied prob.

    The close carries the OVER price; the symmetric under price is reconstructed by
    assuming a fixed two-sided hold so that p_over_raw + p_under_raw = 1 + _HOLD.
    Proportional (multiplicative) devig: p_over = p_over_raw / (p_over_raw + p_under_raw).
    """
    p_under_raw = (1.0 + _HOLD) - p_over_raw
    p_under_raw = min(max(p_under_raw, 1e-3), 1.0 - 1e-3)
    s = p_over_raw + p_under_raw
    return p_over_raw / s


def _load() -> pd.DataFrame:
    g = pd.read_parquet(_MLB / "games.parquet")
    od = pd.read_parquet(_MLB / "odds.parquet")[
        ["event_id", "closeou", "closeou_odds"]]
    df = g.merge(od, on="event_id", how="inner")
    df = df[df["closeou"].notna() & df["closeou_odds"].notna()].copy()
    df["total"] = df["home_runs"].astype(float) + df["away_runs"].astype(float)
    # leak-free as-of park + SP signals
    try:
        park = pd.read_parquet(_MLB / "asof_park.parquet")[["event_id", "park_factor"]]
        df = df.merge(park, on="event_id", how="left")
    except Exception:
        df["park_factor"] = 1.0
    try:
        sp = pd.read_parquet(_MLB / "asof_features.parquet")[
            ["event_id", "home_sp_ra_asof", "away_sp_ra_asof"]]
        df = df.merge(sp, on="event_id", how="left")
    except Exception:
        df["home_sp_ra_asof"] = np.nan
        df["away_sp_ra_asof"] = np.nan
    df["park_factor"] = df["park_factor"].fillna(1.0)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values(["date", "event_id"]).reset_index(drop=True)


def _walk_forward_total(df: pd.DataFrame) -> np.ndarray:
    """Leak-free predicted total runs per game (snapshot EW RS/RA, blended with as-of SP+park)."""
    rs: Dict[str, float] = {}
    ra: Dict[str, float] = {}
    pred = np.empty(len(df))
    h = df["home_team"].to_numpy()
    a = df["away_team"].to_numpy()
    hr = df["home_runs"].to_numpy(dtype=float)
    ar = df["away_runs"].to_numpy(dtype=float)
    pf = df["park_factor"].to_numpy(dtype=float)
    hsp = df["home_sp_ra_asof"].to_numpy(dtype=float)
    asp = df["away_sp_ra_asof"].to_numpy(dtype=float)
    for i in range(len(df)):
        ht, at = str(h[i]), str(a[i])
        for t in (ht, at):
            rs.setdefault(t, _INIT_RPG)
            ra.setdefault(t, _INIT_RPG)
        exp_home = 0.5 * (rs[ht] + ra[at])
        exp_away = 0.5 * (rs[at] + ra[ht])
        team_total = exp_home + exp_away
        # blend in as-of starting-pitcher run-allowed (lower SP RA -> fewer runs)
        sp_adj = 0.0
        if not math.isnan(hsp[i]) and not math.isnan(asp[i]):
            sp_adj = 0.5 * ((hsp[i] - _INIT_RPG) + (asp[i] - _INIT_RPG))
        base = 0.7 * team_total + 0.3 * (team_total + sp_adj)
        pred[i] = base * (0.85 + 0.15 * pf[i])   # gentle park tilt around 1.0
        rs[ht] += _ALPHA * (hr[i] - rs[ht]); ra[ht] += _ALPHA * (ar[i] - ra[ht])
        rs[at] += _ALPHA * (ar[i] - rs[at]); ra[at] += _ALPHA * (hr[i] - ra[at])
    return pred


def _model_p_over(pred: np.ndarray, line: np.ndarray, sigma: float) -> np.ndarray:
    return np.array([1.0 - _phi((ln - pt) / sigma) for pt, ln in zip(pred, line)])


def _logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    return -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


def _dm_clustered(d: np.ndarray, clusters: np.ndarray) -> Tuple[float, float]:
    """Diebold-Mariano on per-game loss differential d = L_model - L_close, SE clustered by date.

    Returns (dm_stat, two-sided p). Negative stat => model loss lower => model better.
    """
    uniq = np.unique(clusters)
    # cluster-mean differentials -> robust to within-day correlation
    cmeans = np.array([d[clusters == c].mean() for c in uniq])
    cn = np.array([np.sum(clusters == c) for c in uniq], dtype=float)
    mbar = np.average(cmeans, weights=cn)
    G = len(uniq)
    if G < 2:
        return float("nan"), float("nan")
    # weighted cluster variance of the mean
    var = np.average((cmeans - mbar) ** 2, weights=cn) * (G / (G - 1.0))
    se = math.sqrt(var / G)
    if se <= 0:
        return float("nan"), float("nan")
    stat = mbar / se
    # normal approx two-sided
    p = 2.0 * (1.0 - _phi(abs(stat)))
    return float(stat), float(p)


def _eval_slice(sub: pd.DataFrame, pred: np.ndarray, sigma: float, label: str) -> Dict:
    line = sub["closeou"].to_numpy(dtype=float)
    tot = sub["total"].to_numpy(dtype=float)
    # drop pushes (total == line)
    keep = tot != line
    sub = sub[keep]; pred = pred[keep]; line = line[keep]; tot = tot[keep]
    y = (tot > line).astype(float)
    n = len(y)
    if n < _MIN_N:
        return {"slice": label, "n": int(n), "verdict": "SKIP n<200"}
    p_model = _model_p_over(pred, line, sigma)
    p_close = np.array([_devig_over(_am_to_p(o)) for o in sub["closeou_odds"].to_numpy(dtype=float)])
    ll_m = _logloss(p_model, y)
    ll_c = _logloss(p_close, y)
    d = ll_m - ll_c
    dates = sub["date"].astype("int64").to_numpy()
    stat, p = _dm_clustered(d, dates)
    model_better = float(ll_m.mean()) < float(ll_c.mean())
    ship = bool(model_better and not math.isnan(p) and p < 0.05 and n >= _MIN_N)
    return {
        "slice": label, "n": int(n),
        "ll_model": round(float(ll_m.mean()), 4),
        "ll_close": round(float(ll_c.mean()), 4),
        "ll_delta": round(float(ll_m.mean() - ll_c.mean()), 4),  # neg => model better
        "dm_stat": round(stat, 3) if not math.isnan(stat) else None,
        "dm_p": round(p, 4) if not math.isnan(p) else None,
        "verdict": "SHIP (in-sample; needs forward CLV)" if ship
                   else ("MATCH/BEHIND -- market efficient"),
    }


def run() -> Dict:
    if not (_MLB / "games.parquet").is_file():
        return {"error": "MLB corpus not found"}
    df = _load()
    pred_all = _walk_forward_total(df)
    df = df.assign(_pred=pred_all)
    # leak-free sigma: fit on global train prefix, apply everywhere
    n = len(df)
    ntr = int(n * _TRAIN_FRAC)
    resid = df["total"].to_numpy(dtype=float) - pred_all
    sigma = float(np.std(resid[:ntr]))

    results: List[Dict] = []
    # Per corpus (league), then regime slices within
    for lg in ("NL", "AL"):
        cor = df[df["home_league"] == lg].reset_index(drop=True)
        cp = cor["_pred"].to_numpy()
        results.append(_eval_slice(cor, cp, sigma, f"{lg} | ALL"))
        # regime: early (first 40% of EACH season by date) vs late
        early_mask = np.zeros(len(cor), dtype=bool)
        for s, grp in cor.groupby("season"):
            idx = grp.index.to_numpy()
            cut = idx[: int(len(idx) * 0.4)]
            early_mask[cut] = True
        e = cor[early_mask].reset_index(drop=True); ep = cor["_pred"].to_numpy()[early_mask]
        l = cor[~early_mask].reset_index(drop=True); lp = cor["_pred"].to_numpy()[~early_mask]
        results.append(_eval_slice(e, ep, sigma, f"{lg} | EARLY-season"))
        results.append(_eval_slice(l, lp, sigma, f"{lg} | LATE-season"))

    # Cross-corpus consistency check on each slice TYPE
    def _both(slice_kind: str) -> Dict:
        rows = [r for r in results if r["slice"].endswith(slice_kind) and r.get("dm_p") is not None]
        if len(rows) < 2:
            return {"kind": slice_kind, "consistent_ship": False, "note": "missing corpus"}
        ships = all(r["verdict"].startswith("SHIP") for r in rows)
        return {"kind": slice_kind, "consistent_ship": bool(ships),
                "per_corpus": {r["slice"]: r["verdict"] for r in rows}}

    consistency = [_both("ALL"), _both("EARLY-season"), _both("LATE-season")]
    any_survivor = any(c["consistent_ship"] for c in consistency)
    return {
        "market": "mlb_total_ou", "n_total": n, "sigma": round(sigma, 3),
        "slices": results, "consistency": consistency,
        "HUNT_D_VERDICT": ("SURVIVOR (consistent SHIP on >=2 corpora; needs forward CLV)"
                           if any_survivor else
                           "REJECT -- no slice beats the devigged close on >=2 corpora (market efficient)"),
    }


def _main() -> int:
    rep = run()
    if "error" in rep:
        print(rep["error"]); return 1
    print(f"=== MLB Totals O/U slice probe vs devigged close "
          f"(n={rep['n_total']}, sigma={rep['sigma']}) ===")
    print(f"{'slice':<22} {'n':>5} {'ll_model':>9} {'ll_close':>9} {'delta':>8} "
          f"{'dm_stat':>8} {'dm_p':>7}  verdict")
    for r in rep["slices"]:
        if r.get("ll_model") is None:
            print(f"{r['slice']:<22} {r['n']:>5} {'--':>9} {'--':>9} {'--':>8} "
                  f"{'--':>8} {'--':>7}  {r['verdict']}")
            continue
        print(f"{r['slice']:<22} {r['n']:>5} {r['ll_model']:>9} {r['ll_close']:>9} "
              f"{r['ll_delta']:>+8} {str(r['dm_stat']):>8} {str(r['dm_p']):>7}  {r['verdict']}")
    print("\nCross-corpus consistency (need SHIP on BOTH NL and AL for a slice type):")
    for c in rep["consistency"]:
        print(f"  {c['kind']:<14} consistent_ship={c['consistent_ship']}  {c.get('per_corpus', c.get('note'))}")
    print(f"\nHUNT D VERDICT: {rep['HUNT_D_VERDICT']}")
    print("Note: log-loss delta NEGATIVE => model beats close. Any SHIP is IN-SAMPLE only and "
          "needs real forward CLV before any $ claim. NOT an edge claim.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
