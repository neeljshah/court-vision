"""scripts.platformkit.proof_nba.winprob_feature_challenger -- Q16: does an as-of
team-feature logistic challenger beat Elo (or the close)? Premise check FIRST:
ml_accuracy.run() called directly (exact by construction), diffed vs the packet's
0.208/0.198; a miss > 0.002 is reported, not hidden. This module's OWN held-out
window is NOT the same fold as ml_accuracy's -- season-filter + feature dropna
shrink/shift it; n_ml_accuracy_overlap/n_after_games_join/n_after_feature_dropna
/n_test/test_date_range in every season report show how.

Challenger = logistic regression on [logit(Elo), as-of team-feature diffs], TRAIN
half only, inner TimeSeriesSplit picks C. Blend = sigmoid(w*logit(model) +
(1-w)*logit(close)), w fit OOS on TRAIN. Leak-free: every feature is NaN/unready
until a team has >=1 strictly-prior game/team-season (enforced, raises). Home
flag skipped (every row already IS P(home), collinear with the intercept).
Spec's "trailing-10" net rating/pace (asof_team_adv.parquet) has ZERO 2025-26
rows, so net/pace are this module's own EW (asof_box_accuracy's _ALPHA) over
box possession detail; full NOT VERIFIED list on every season report.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; edge_claimed is always False.
Run: python -m scripts.platformkit.proof_nba.winprob_feature_challenger \
    --seasons 2024-25,2025-26 --out data/cache/winprob_challenger/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.proof_nba.asof_box_accuracy import (  # noqa: E402
    _ALPHA, _possessions, load_box)
from scripts.platformkit.proof_nba.ml_accuracy import (  # noqa: E402
    _brier_logloss, _walk_forward_elo, american_to_prob)
from scripts.platformkit.proof_nba.ml_accuracy import run as ml_accuracy_run  # noqa: E402
from scripts.platformkit.eval_gate.shin import shin_devig  # noqa: E402
from scripts.platformkit.eval_gate.dm_test import diebold_mariano  # noqa: E402

_PACKET = {"model_brier": 0.208, "market_brier": 0.198}
_C_GRID: Tuple[float, ...] = (0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
FEATURES: Tuple[str, ...] = (
    "logit_elo", "home_b2b", "away_b2b", "rest_days_diff_asof",
    "net_rating_diff", "pace_diff", "heavy_min_load_diff_asof",
)

def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))

def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))

def _default_root() -> Path:  # worktree-local data/, else parent repo; reads only
    here = Path(__file__).resolve()
    for c in (here.parents[3] / "data" / "domains" / "basketball_nba",
              here.parents[3].parents[2] / "data" / "domains" / "basketball_nba"):
        if (c / "espn_boxscores.parquet").is_file():
            return c
    raise FileNotFoundError("espn_boxscores.parquet not found (worktree or parent repo).")

def _ew_team_form(box: pd.DataFrame) -> pd.DataFrame:  # as-of EW pace/net-rating diffs, _walk_forward_poss's discipline
    pace: Dict[str, float] = {}; offp: Dict[str, float] = {}; defp: Dict[str, float] = {}
    nprior: Dict[str, int] = {}
    h = box["home_abbr"].to_numpy(); a = box["away_abbr"].to_numpy()
    hp = box["home_pts"].to_numpy(float); ap = box["away_pts"].to_numpy(float)
    gp = 0.5 * (_possessions(box, "home") + _possessions(box, "away"))
    pace_diff = np.empty(len(box)); net_diff = np.empty(len(box))
    ready = np.zeros(len(box), dtype=bool)
    for i in range(len(box)):
        ht, at = str(h[i]), str(a[i])
        for d, init in ((pace, 100.5), (offp, 1.13), (defp, 1.13)):
            d.setdefault(ht, init); d.setdefault(at, init)
        nprior.setdefault(ht, 0); nprior.setdefault(at, 0)
        pace_diff[i] = pace[ht] - pace[at]
        net_diff[i] = (offp[ht] - defp[ht]) - (offp[at] - defp[at])
        ready[i] = nprior[ht] > 0 and nprior[at] > 0
        p = gp[i]
        if np.isfinite(p) and p > 50:
            pace[ht] += _ALPHA * (p - pace[ht]); pace[at] += _ALPHA * (p - pace[at])
            offp[ht] += _ALPHA * (hp[i] / p - offp[ht]); defp[ht] += _ALPHA * (ap[i] / p - defp[ht])
            offp[at] += _ALPHA * (ap[i] / p - offp[at]); defp[at] += _ALPHA * (hp[i] / p - defp[at])
            nprior[ht] += 1; nprior[at] += 1
    return pd.DataFrame({"pace_diff": pace_diff, "net_rating_diff": net_diff, "asof_ready": ready})

def _build_frame(root: Path) -> pd.DataFrame:  # box(+Elo,+EW) x games x odds x carryover_asof
    box = load_box(root)
    box["p_elo"] = _walk_forward_elo(box)
    box = pd.concat([box.reset_index(drop=True), _ew_team_form(box)], axis=1)
    gm = pd.read_parquet(root / "games.parquet")
    gm["date"] = pd.to_datetime(gm["date"])
    gm_cols = ["game_id", "date", "home_team", "away_team", "season", "home_b2b", "away_b2b"]
    m = box.merge(gm[gm_cols], left_on=["date", "home_abbr", "away_abbr"],
                  right_on=["date", "home_team", "away_team"], how="inner")
    od = pd.read_parquet(root / "odds.parquet").dropna(subset=["home_ml", "away_ml"]).copy()
    od["date"] = pd.to_datetime(od["date"])
    od["imp_h"] = od["home_ml"].map(american_to_prob)
    od["imp_a"] = od["away_ml"].map(american_to_prob)
    od["p_market_naive"] = od["imp_h"] / (od["imp_h"] + od["imp_a"])
    od["p_close"] = [shin_devig([r.imp_h, r.imp_a])[0][0] for r in od.itertuples()]
    m = m.merge(od[["date", "home_team", "away_team", "p_close", "p_market_naive"]],
                on=["date", "home_team", "away_team"], how="inner")
    co = pd.read_parquet(root / "carryover_asof.parquet")
    m = m.merge(co[["game_id", "rest_days_diff_asof", "heavy_min_load_diff_asof",
                     "home_n_prior", "away_n_prior"]], on="game_id", how="left")
    m["home_b2b"] = m["home_b2b"].astype(float); m["away_b2b"] = m["away_b2b"].astype(float)
    return m.sort_values("date", kind="mergesort").reset_index(drop=True)

def _assemble(m: pd.DataFrame) -> Tuple[pd.DataFrame, int]:  # -> (rows, n after dropna)
    m = m.copy()
    m["logit_elo"] = _logit(m["p_elo"].to_numpy(float))
    m["y"] = (m["home_pts"] > m["away_pts"]).astype(float)
    m = m.dropna(subset=list(FEATURES) + ["y", "p_close"])
    n_after_dropna = int(len(m))
    m = m[m["asof_ready"]].reset_index(drop=True)  # pace/net use init defaults, never NaN
    if not bool(m["asof_ready"].all()):
        raise ValueError("own EW form feature used a cold-start team-game")
    if not bool((m["home_n_prior"] > 0).all() and (m["away_n_prior"] > 0).all()):
        raise ValueError("carryover feature used a cold-start team-season")
    return m, n_after_dropna

def _fit_challenger(train: pd.DataFrame):  # inner CV picks C; -> model, scaler, C, OOF probs
    X = train[list(FEATURES)].to_numpy(float); y = train["y"].to_numpy(float)
    tscv = TimeSeriesSplit(n_splits=4)
    best_c, best_ll, best_oof = _C_GRID[0], np.inf, None
    for c in _C_GRID:
        lls, oof = [], np.full(len(X), np.nan)
        for tr, va in tscv.split(X):
            sc = StandardScaler().fit(X[tr])
            clf = LogisticRegression(C=c, max_iter=1000).fit(sc.transform(X[tr]), y[tr])
            oof[va] = clf.predict_proba(sc.transform(X[va]))[:, 1]
            lls.append(_brier_logloss(oof[va], y[va])[1])
        if np.mean(lls) < best_ll:
            best_ll, best_c, best_oof = np.mean(lls), c, oof
    if best_oof is None:
        raise ValueError("no candidate C produced a finite CV log-loss")
    scaler = StandardScaler().fit(X)
    model = LogisticRegression(C=best_c, max_iter=1000).fit(scaler.transform(X), y)
    return model, scaler, best_c, best_oof

def fit_blend_w(p_a: np.ndarray, p_b: np.ndarray, y: np.ndarray) -> float:
    """w in [0,1] minimizing log-loss of sigmoid(w*logit(a) + (1-w)*logit(b))."""
    la, lb = _logit(p_a), _logit(p_b)
    best_w, best_ll = 0.5, np.inf
    for w in np.linspace(0.0, 1.0, 101):
        ll = _brier_logloss(_sigmoid(w * la + (1 - w) * lb), y)[1]
        if ll < best_ll:
            best_ll, best_w = ll, w
    return float(best_w)

def blend(p_a: np.ndarray, p_b: np.ndarray, w: float) -> np.ndarray:
    return _sigmoid(w * _logit(p_a) + (1 - w) * _logit(p_b))

def _murphy(p: np.ndarray, y: np.ndarray, bins: int = 10) -> Dict:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    obar = float(y.mean()); rel = res = 0.0; table = []
    for k in range(bins):
        sel = idx == k; nk = int(sel.sum())
        if nk == 0:
            continue
        pk, ok = float(p[sel].mean()), float(y[sel].mean())
        rel += nk * (pk - ok) ** 2; res += nk * (ok - obar) ** 2
        table.append({"bin": k, "n": nk, "mean_pred": round(pk, 4), "mean_actual": round(ok, 4)})
    n = len(p)
    return {"reliability": round(rel / n, 5), "resolution": round(res / n, 5),
            "uncertainty": round(obar * (1 - obar), 5), "table": table,
            "approximate": "10-bin histogram decomposition, not the continuous form"}

def bootstrap_ci(diff: np.ndarray, reps: int = 2000, seed: int = 0) -> Tuple[float, float]:
    # game-clustered bootstrap of the mean loss diff (1 row = 1 game already)
    rng = np.random.default_rng(seed)
    n = len(diff)
    means = np.array([diff[rng.integers(0, n, n)].mean() for _ in range(reps)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

def _pair_stats(loss_base: np.ndarray, loss_new: np.ndarray, game_ids) -> Dict:
    d = loss_base - loss_new  # >0 => new is better
    dm = diebold_mariano(d.tolist(), list(game_ids))
    lo, hi = bootstrap_ci(d)
    verdict = "AHEAD" if lo > 0 else ("BEHIND" if hi < 0 else "UNDERPOWERED")
    return {"mean_diff": round(float(d.mean()), 5), "dm_stat": round(dm.dm_stat, 3),
            "dm_p": round(dm.p_value, 4), "boot_ci95": [round(lo, 5), round(hi, 5)],
            "verdict": verdict}

def premise_check(root: Path) -> Dict:
    stamps = {"as_of": datetime.now(timezone.utc).isoformat(),
              "corpus_max_date": str(load_box(root)["date"].max().date())}
    rep = ml_accuracy_run(corpus=root)
    if rep.get("status") != "ok":
        return {"reproduced": False, "packet": _PACKET, "live": rep, **stamps,
                "reason": f"ml_accuracy.run() status={rep.get('status')}"}
    gm_ = abs(rep["model_brier"] - _PACKET["model_brier"])
    gk_ = abs(rep["market_brier"] - _PACKET["market_brier"])
    ok = gm_ <= 0.002 and gk_ <= 0.002
    reason = None if ok else (f"live n_overlap={rep['n_overlap']}, packet has no recorded n "
        f"(likely a stale snapshot). gaps model={gm_:.4f} market={gk_:.4f} (tol 0.002).")
    return {"reproduced": ok, "packet": _PACKET, "live": rep, **stamps,
            "gap_model": round(gm_, 4), "gap_market": round(gk_, 4), "reason": reason}

def run_season(root: Path, season: str, n_ml_accuracy_overlap: int = None) -> Dict:
    m = _build_frame(root)
    m = m[m["season"] == season].reset_index(drop=True)
    n_after_games_join = int(len(m))
    base = {"season": season, "edge_claimed": False,
            "n_ml_accuracy_overlap": n_ml_accuracy_overlap,
            "n_after_games_join": n_after_games_join}
    if n_after_games_join < 60:
        return {**base, "status": "data_limited", "note": "fewer than 60 odds-joined rows for this season (odds.parquet covers only 2025-26 today) -- NOT ENOUGH DATA."}
    d, n_after_feature_dropna = _assemble(m)
    n = len(d)
    if n < 60:
        return {**base, "status": "data_limited", "n_after_feature_dropna": n_after_feature_dropna,
                "note": "fewer than 60 rows survive the as-of feature dropna."}
    mid = n // 2
    train, test = d.iloc[:mid], d.iloc[mid:]
    if test["game_id"].nunique() != len(test):
        raise ValueError("test rows are not one-per-game; bootstrap assumes 1 row = 1 game")
    model, scaler, best_c, oof = _fit_challenger(train)
    p_test = model.predict_proba(scaler.transform(test[list(FEATURES)].to_numpy(float)))[:, 1]
    y_tr, y_te = train["y"].to_numpy(float), test["y"].to_numpy(float)
    p_close_tr, p_close_te = train["p_close"].to_numpy(float), test["p_close"].to_numpy(float)
    ok = ~np.isnan(oof)
    w = fit_blend_w(oof[ok], p_close_tr[ok], y_tr[ok])
    p_blend_te = blend(p_test, p_close_te, w)
    arms = {"elo": test["p_elo"].to_numpy(float), "challenger": p_test,
            "close": p_close_te, "close_naive": test["p_market_naive"].to_numpy(float),
            "blend": p_blend_te}
    scores = {k: dict(zip(("brier", "logloss"), _brier_logloss(v, y_te))) for k, v in arms.items()}
    murphy = {k: _murphy(v, y_te) for k, v in arms.items()}
    sq = {k: (v - y_te) ** 2 for k, v in arms.items()}
    game_ids = test["game_id"].to_numpy()
    pairs = {  # d = loss_base - loss_new; positive => the SECOND-named arm has LOWER loss
        "elo_minus_challenger": _pair_stats(sq["elo"], sq["challenger"], game_ids),
        "close_minus_challenger": _pair_stats(sq["close"], sq["challenger"], game_ids),
        "close_minus_blend": _pair_stats(sq["close"], sq["blend"], game_ids),
    }
    date_range = [str(test["date"].min().date()), str(test["date"].max().date())]
    not_verified = [
        "asof_team_adv.parquet (spec's L10 net rating/pace) has ZERO 2025-26 rows, and asof_box_extra/asof_features.parquet cover only 74/1156 games; net_rating_diff/pace_diff are this module's own EW proxy, and those two tables are unused.",
        "No injury/roster availability table found; heavy_min_load_diff_asof (fatigue carryover) is the closest as-of proxy, not true availability.",
        "odds.parquet has no 2024-25 rows; that season cannot be scored vs the close.",
    ]
    return {
        **base, "status": "ok", "n_after_feature_dropna": n_after_feature_dropna,
        "n_train": int(mid), "n_test": int(n - mid), "test_date_range": date_range,
        "best_C": best_c, "blend_w": round(w, 3), "features": list(FEATURES),
        "scores": scores, "murphy": murphy, "pairs": pairs,
        "pair_sign_note": "positive mean_diff = the second-named arm has LOWER loss (better)",
        "close_arm_note": "close is Shin-devigged; close_naive matches ml_accuracy's own proportional (non-Shin) devig of the same odds.",
        "not_verified": not_verified, "note": "Calibration only; no monetary claim.",
    }

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2024-25,2025-26")
    ap.add_argument("--out", default="data/cache/winprob_challenger/")
    ap.add_argument("--corpus-root", default=None)
    args = ap.parse_args(argv)
    root = Path(args.corpus_root) if args.corpus_root else _default_root()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pc = premise_check(root)
    print("=== PREMISE CHECK: ml_accuracy.run() vs packet (0.208 / 0.198) ===")
    print(json.dumps(pc, indent=2, default=str))
    (out / "premise_check.json").write_text(json.dumps(pc, indent=2, default=str))
    n_ml = pc.get("live", {}).get("n_overlap")
    md = ["# Q16 win-prob feature challenger vs the close", "", "edge_claimed: false", "",
          "## Premise check", "", "```", json.dumps(pc, indent=2, default=str), "```", ""]
    for season in [s.strip() for s in args.seasons.split(",") if s.strip()]:
        rep = run_season(root, season, n_ml_accuracy_overlap=n_ml)
        (out / f"winprob_challenger_{season}.json").write_text(json.dumps(rep, indent=2, default=str))
        print(f"\n=== {season} ===")
        print(json.dumps(rep, indent=2, default=str))
        md.append(f"## {season}\n")
        if rep["status"] != "ok":
            md.append(f"{rep['status']}: {rep.get('note')} (n_ml_accuracy_overlap={n_ml}, n_after_games_join={rep['n_after_games_join']})\n")
            continue
        md.append(f"n_ml_accuracy_overlap={rep['n_ml_accuracy_overlap']} n_after_games_join={rep['n_after_games_join']} n_after_feature_dropna={rep['n_after_feature_dropna']} n_train={rep['n_train']} n_test={rep['n_test']} test_date_range={rep['test_date_range']} best_C={rep['best_C']} blend_w={rep['blend_w']}\n")
        md.append(rep["close_arm_note"] + "\n")
        md.append("| arm | brier | logloss |\n|---|---|---|")
        md += [f"| {k} | {round(v['brier'], 5)} | {round(v['logloss'], 5)} |" for k, v in rep["scores"].items()]
        md.append("\n" + rep["pair_sign_note"])
        md.append("| pair | mean_diff | dm_p | boot_ci95 | verdict |\n|---|---|---|---|---|")
        md += [f"| {k} | {round(v['mean_diff'], 5)} | {round(v['dm_p'], 5)} | [{round(v['boot_ci95'][0], 5)}, {round(v['boot_ci95'][1], 5)}] | {v['verdict']} |" for k, v in rep["pairs"].items()]
        md.append("")
    (out / "winprob_challenger_report.md").write_text("\n".join(md))
    print(f"\nWrote {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
