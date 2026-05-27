"""
train_lite_winprob_sbr.py — Iter-22 lite WinProb trained on the SBR 10Y archive.

The production WinProb model in src/prediction/win_probability.py requires
~70 NBA-Stats-derived features (synergy, hustle, lineup, ELO, ref tendencies)
that are NOT cached pre-2022 and cannot be re-fetched on this offline pod.

This script trains a feature-light alternative on the SBR archive
(2011-2021, 13,903 games) so we can:
  - benchmark how much of the 70.9% WinProb signal is in cheap features
  - serve as a universal fallback for any game where heavy caches are missing

Features used (all derivable from finals + close-ML + game-date sequence):
  - ELO_gap        : (home_elo - away_elo) at kickoff, K=20 update
  - rest_home      : days since previous game (cap 7, fillna 7)
  - rest_away      : days since previous game (cap 7, fillna 7)
  - b2b_home       : rest_home == 0
  - b2b_away       : rest_away == 0
  - season_z       : (season - 2016) / 5 — era control
  - vegas_devig    : devigged home-win implied prob from close_ml

Target: home_wins = home_final > away_final.

Splits: train 2011-2019, val 2020 (COVID bubble), test 2021.

CLI: python scripts/train_lite_winprob_sbr.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import pickle
from collections import defaultdict

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

ARCHIVE = os.path.join(
    PROJECT_DIR, "data", "external", "historical_lines",
    "sbr_archive_2011_2021", "nba_archive_10Y.json",
)
MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "lite_winprob")
os.makedirs(MODEL_DIR, exist_ok=True)


# ── 1. Load + clean ─────────────────────────────────────────────────────────

def load_archive() -> pd.DataFrame:
    with open(ARCHIVE, "r", encoding="utf-8") as f:
        rows = json.load(f)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_numeric(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["date"] = df["date"].astype(int).astype(str)
    df["date_iso"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date_iso"]).copy()
    # numeric coercion of finals + MLs
    for c in ("home_final", "away_final", "home_close_ml", "away_close_ml"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["home_final", "away_final"]).copy()
    df["home_wins"] = (df["home_final"] > df["away_final"]).astype(int)
    df = df.sort_values("date_iso").reset_index(drop=True)
    return df


def american_to_prob(ml: float) -> float:
    if pd.isna(ml):
        return np.nan
    if ml < 0:
        return -ml / (-ml + 100.0)
    return 100.0 / (ml + 100.0)


def devig_pair(home_ml: float, away_ml: float) -> float:
    """Return devigged home-win probability (proportional)."""
    ph = american_to_prob(home_ml)
    pa = american_to_prob(away_ml)
    if pd.isna(ph) or pd.isna(pa):
        return np.nan
    s = ph + pa
    if s <= 0:
        return np.nan
    return ph / s


# ── 2. Build features (ELO + rest) ──────────────────────────────────────────

def build_features(df: pd.DataFrame, k: float = 20.0,
                   season_reset: bool = True) -> pd.DataFrame:
    """Walk the sorted game log; compute pre-game ELO + rest per team."""
    elo = defaultdict(lambda: 1500.0)
    last_game_date = {}
    last_game_season = {}

    feats = []
    for _, row in df.iterrows():
        h, a = row["home_team"], row["away_team"]
        season = int(row["season"])
        gd = row["date_iso"]

        if season_reset:
            # carry 75% of prior ELO toward mean at season boundary
            for t in (h, a):
                if last_game_season.get(t) is not None and last_game_season[t] != season:
                    elo[t] = 1500.0 + 0.75 * (elo[t] - 1500.0)

        eh, ea = elo[h], elo[a]
        elo_gap = eh - ea

        rh_prev = last_game_date.get(h)
        ra_prev = last_game_date.get(a)
        rest_home = (gd - rh_prev).days if rh_prev is not None else 7
        rest_away = (gd - ra_prev).days if ra_prev is not None else 7
        rest_home = min(max(rest_home, 0), 14)
        rest_away = min(max(rest_away, 0), 14)
        b2b_home = int(rest_home == 1)  # B2B = 1 day gap; rest_days=0 means same day
        b2b_away = int(rest_away == 1)

        devig = devig_pair(row["home_close_ml"], row["away_close_ml"])

        feats.append({
            "elo_gap": elo_gap,
            "elo_home": eh,
            "elo_away": ea,
            "rest_home": rest_home,
            "rest_away": rest_away,
            "b2b_home": b2b_home,
            "b2b_away": b2b_away,
            "season_z": (season - 2016) / 5.0,
            "vegas_devig": devig,
        })

        # Update ELO with actual outcome (post-game)
        # expected home score from current ELO with 60-pt home edge (≈100 ELO)
        exp_home = 1.0 / (1.0 + 10 ** ((ea - (eh + 60.0)) / 400.0))
        outcome = 1.0 if row["home_wins"] else 0.0
        delta = k * (outcome - exp_home)
        elo[h] = eh + delta
        elo[a] = ea - delta
        last_game_date[h] = gd
        last_game_date[a] = gd
        last_game_season[h] = season
        last_game_season[a] = season

    fdf = pd.DataFrame(feats)
    out = pd.concat([df.reset_index(drop=True), fdf], axis=1)
    return out


# ── 3. Split / train / evaluate ─────────────────────────────────────────────

FEATURES = ["elo_gap", "rest_home", "rest_away", "b2b_home", "b2b_away",
            "season_z", "vegas_devig"]


def split(df: pd.DataFrame):
    tr = df[df["season"].between(2011, 2019)].copy()
    val = df[df["season"] == 2020].copy()
    te = df[df["season"] == 2021].copy()
    return tr, val, te


def metrics(y_true: np.ndarray, p: np.ndarray, label: str) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    hit = float(np.mean((p > 0.5).astype(int) == y_true))
    brier = float(np.mean((p - y_true) ** 2))
    ll = float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))
    return {"label": label, "n": int(len(y_true)), "hit": hit,
            "brier": brier, "log_loss": ll}


def train_lr(tr: pd.DataFrame):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    tr_clean = tr.dropna(subset=FEATURES + ["home_wins"]).copy()
    X = tr_clean[FEATURES].to_numpy(dtype=float)
    y = tr_clean["home_wins"].to_numpy(dtype=int)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    lr = LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs")
    lr.fit(Xs, y)
    return ("lr", scaler, lr)


def train_xgb(tr: pd.DataFrame, val: pd.DataFrame):
    try:
        import xgboost as xgb
    except Exception as e:
        print(f"  xgboost unavailable: {e}")
        return None
    tr_c = tr.dropna(subset=FEATURES + ["home_wins"]).copy()
    val_c = val.dropna(subset=FEATURES + ["home_wins"]).copy()
    X_tr = tr_c[FEATURES].to_numpy(dtype=float)
    y_tr = tr_c["home_wins"].to_numpy(dtype=int)
    X_val = val_c[FEATURES].to_numpy(dtype=float)
    y_val = val_c["home_wins"].to_numpy(dtype=int)
    model = xgb.XGBClassifier(
        n_estimators=400, max_depth=4, learning_rate=0.05,
        subsample=0.85, colsample_bytree=0.85,
        reg_alpha=0.1, reg_lambda=1.0,
        eval_metric="logloss", tree_method="hist",
        early_stopping_rounds=30, verbosity=0,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    return ("xgb", None, model)


def predict(bundle, df: pd.DataFrame) -> np.ndarray:
    kind, scaler, model = bundle
    sub = df.dropna(subset=FEATURES).copy()
    X = sub[FEATURES].to_numpy(dtype=float)
    if kind == "lr":
        X = scaler.transform(X)
        p = model.predict_proba(X)[:, 1]
    else:
        p = model.predict_proba(X)[:, 1]
    out = pd.Series(np.nan, index=df.index, dtype=float)
    out.loc[sub.index] = p
    return out.to_numpy()


# ── 4. Main ─────────────────────────────────────────────────────────────────

def main():
    print("[lite-winprob] loading SBR archive…")
    raw = load_archive()
    print(f"  loaded {len(raw)} games {raw['season'].min()}-{raw['season'].max()}")

    print("[lite-winprob] building ELO + rest features…")
    df = build_features(raw)
    valid = df.dropna(subset=["vegas_devig"])
    print(f"  vegas_devig coverage: {len(valid)}/{len(df)} "
          f"({len(valid)/len(df):.1%})")

    tr, val, te = split(df)
    print(f"  train(2011-19)={len(tr)}  val(2020)={len(val)}  test(2021)={len(te)}")

    # Train both
    lr_bundle = train_lr(tr)
    xgb_bundle = train_xgb(tr, val)

    bundles = {"lr": lr_bundle}
    if xgb_bundle is not None:
        bundles["xgb"] = xgb_bundle

    # Evaluate on splits
    results = {}
    for name, b in bundles.items():
        results[name] = {}
        for split_name, sdf in [("train", tr), ("val", val), ("test", te)]:
            p = predict(b, sdf)
            mask = ~np.isnan(p)
            y = sdf["home_wins"].to_numpy()
            results[name][split_name] = metrics(y[mask], p[mask], f"{name}-{split_name}")

    # Vegas-only baseline
    print("[lite-winprob] vegas-only baseline (devigged close ML)…")
    vegas_results = {}
    for split_name, sdf in [("train", tr), ("val", val), ("test", te)]:
        p = sdf["vegas_devig"].to_numpy()
        y = sdf["home_wins"].to_numpy()
        mask = ~np.isnan(p)
        vegas_results[split_name] = metrics(y[mask], p[mask], f"vegas-{split_name}")

    # ELO-only baseline (no Vegas) — use a logistic on elo_gap alone
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    tr_c = tr.dropna(subset=["elo_gap", "home_wins"]).copy()
    Xe = tr_c[["elo_gap"]].to_numpy(dtype=float)
    ye = tr_c["home_wins"].to_numpy(dtype=int)
    se = StandardScaler().fit(Xe)
    le = LogisticRegression(max_iter=1000).fit(se.transform(Xe), ye)
    elo_only = {}
    for split_name, sdf in [("train", tr), ("val", val), ("test", te)]:
        sub = sdf.dropna(subset=["elo_gap"]).copy()
        X = se.transform(sub[["elo_gap"]].to_numpy(dtype=float))
        p_all = pd.Series(np.nan, index=sdf.index, dtype=float)
        p_all.loc[sub.index] = le.predict_proba(X)[:, 1]
        p = p_all.to_numpy()
        y = sdf["home_wins"].to_numpy()
        mask = ~np.isnan(p)
        elo_only[split_name] = metrics(y[mask], p[mask], f"elo-only-{split_name}")

    # ── No-Vegas variant (the true fallback predictor) ───────────────────
    print("[lite-winprob] training no-vegas LR (ELO+rest only)…")
    NV_FEATS = ["elo_gap", "rest_home", "rest_away", "b2b_home", "b2b_away",
                "season_z"]
    from sklearn.linear_model import LogisticRegression as _LR
    from sklearn.preprocessing import StandardScaler as _SS
    tr_nv = tr.dropna(subset=NV_FEATS + ["home_wins"]).copy()
    Xnv = tr_nv[NV_FEATS].to_numpy(dtype=float)
    ynv = tr_nv["home_wins"].to_numpy(dtype=int)
    snv = _SS().fit(Xnv)
    lrnv = _LR(C=1.0, max_iter=2000).fit(snv.transform(Xnv), ynv)
    nv_results = {}
    for split_name, sdf in [("train", tr), ("val", val), ("test", te)]:
        sub = sdf.dropna(subset=NV_FEATS).copy()
        X = snv.transform(sub[NV_FEATS].to_numpy(dtype=float))
        p_all = pd.Series(np.nan, index=sdf.index, dtype=float)
        p_all.loc[sub.index] = lrnv.predict_proba(X)[:, 1]
        p = p_all.to_numpy()
        y = sdf["home_wins"].to_numpy()
        mask = ~np.isnan(p)
        nv_results[split_name] = metrics(y[mask], p[mask], f"no-vegas-{split_name}")
    nv_coefs = dict(zip(NV_FEATS, lrnv.coef_[0].tolist()))

    # Per-season hit rate (test side — every season's hit rate using the LR model)
    print("[lite-winprob] per-season holdout metrics (LR predicting each season)…")
    season_trend = {}
    lr_b = lr_bundle
    for season in sorted(df["season"].unique()):
        sdf = df[df["season"] == season]
        p = predict(lr_b, sdf)
        mask = ~np.isnan(p)
        y = sdf["home_wins"].to_numpy()
        season_trend[int(season)] = metrics(y[mask], p[mask], f"lr-{season}")

    # Feature importance / coefficients
    fi = {}
    scaler, lrm = lr_bundle[1], lr_bundle[2]
    fi["lr_coefs"] = dict(zip(FEATURES, lrm.coef_[0].tolist()))
    fi["lr_intercept"] = float(lrm.intercept_[0])
    if xgb_bundle is not None:
        _, _, xm = xgb_bundle
        try:
            fi["xgb_gain"] = dict(zip(FEATURES, xm.feature_importances_.tolist()))
        except Exception:
            pass

    # Save model + report
    payload = {
        "model_type": "logistic_regression",
        "features": FEATURES,
        "scaler_mean": lr_bundle[1].mean_.tolist(),
        "scaler_scale": lr_bundle[1].scale_.tolist(),
        "coefs": lrm.coef_[0].tolist(),
        "intercept": float(lrm.intercept_[0]),
        "train_seasons": [2011, 2019],
        "val_season": 2020,
        "test_season": 2021,
        "n_train": int(len(tr)),
        "n_val": int(len(val)),
        "n_test": int(len(te)),
    }
    with open(os.path.join(MODEL_DIR, "model.pkl"), "wb") as f:
        pickle.dump({"lr": lr_bundle, "xgb": xgb_bundle, "payload": payload}, f)
    with open(os.path.join(MODEL_DIR, "model_meta.json"), "w") as f:
        json.dump(payload, f, indent=2)

    report = {
        "lr": results.get("lr", {}),
        "xgb": results.get("xgb", {}) if xgb_bundle else None,
        "vegas_baseline": vegas_results,
        "elo_only_baseline": elo_only,
        "no_vegas_lr": nv_results,
        "no_vegas_lr_coefs": nv_coefs,
        "per_season_lr": season_trend,
        "feature_importance": fi,
    }
    with open(os.path.join(MODEL_DIR, "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print("\n=== LITE WINPROB RESULTS ===")
    for name in ("lr", "xgb"):
        if name not in results:
            continue
        for sn in ("train", "val", "test"):
            r = results[name][sn]
            print(f"  {name:>4}-{sn:<5} n={r['n']:>5}  hit={r['hit']:.4f}  "
                  f"brier={r['brier']:.4f}  ll={r['log_loss']:.4f}")
    print("\n=== VEGAS DEVIG BASELINE ===")
    for sn in ("train", "val", "test"):
        r = vegas_results[sn]
        print(f"  vegas-{sn:<5} n={r['n']:>5}  hit={r['hit']:.4f}  "
              f"brier={r['brier']:.4f}  ll={r['log_loss']:.4f}")
    print("\n=== ELO-ONLY BASELINE (LR(elo_gap)) ===")
    for sn in ("train", "val", "test"):
        r = elo_only[sn]
        print(f"  elo-{sn:<5} n={r['n']:>5}  hit={r['hit']:.4f}  "
              f"brier={r['brier']:.4f}  ll={r['log_loss']:.4f}")
    print("\n=== NO-VEGAS LR (ELO+REST, the true fallback) ===")
    for sn in ("train", "val", "test"):
        r = nv_results[sn]
        print(f"  nv-{sn:<5}  n={r['n']:>5}  hit={r['hit']:.4f}  "
              f"brier={r['brier']:.4f}  ll={r['log_loss']:.4f}")
    print("  no-vegas LR coefs (standardised):")
    for f, c in nv_coefs.items():
        print(f"    {f:>12s}: {c:+.4f}")
    print("\n=== PER-SEASON HIT RATE (LR) ===")
    for s, r in season_trend.items():
        print(f"  {s}  n={r['n']:>5}  hit={r['hit']:.4f}  brier={r['brier']:.4f}")
    print("\n=== FEATURE IMPORTANCE ===")
    print("  LR coefs (standardised):")
    for f, c in fi["lr_coefs"].items():
        print(f"    {f:>12s}: {c:+.4f}")
    if "xgb_gain" in fi:
        print("  XGB gain:")
        for f, c in sorted(fi["xgb_gain"].items(), key=lambda kv: -kv[1]):
            print(f"    {f:>12s}: {c:.4f}")
    print(f"\n[lite-winprob] saved to {MODEL_DIR}")


if __name__ == "__main__":
    main()
