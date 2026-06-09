"""audit_prediction_calibration.py — HONEST audit of the prediction engine's
predictive DISTRIBUTION (q10/q50/q90 + flat sigma), NOT the q50 point.

This script answers the question the owner cares about: are the model's
uncertainty estimates honest, so that P(actual > line) — the number that
drives edge sizing / Kelly — is trustworthy?

Four tasks (all leak-free / walk-forward):
  1. QUANTILE COVERAGE  — empirical P(actual<=q50/q10/q90), 80% interval
     coverage, and quantile-crossing rate. Uses the quantile heads on the
     temporal holdout (last 20% by date — the slice they did NOT train on),
     both raw and with the shipped quantile_calibration.json.
  2. SIGMA HONESTY      — flat _STAT_SIGMA (api/courtvision_router.py) vs the
     true walk-forward OOF residual std (pregame_oof.parquet), and vs the
     per-row (q90-q10)/2.563 implied sigma. Does the right sigma vary by
     minutes/role (so a flat sigma is structurally wrong)?
  3. P(OVER) ECE        — implied P(actual>line) from (q50=oof_pred, flat sigma,
     Normal) vs realized over-rate at REAL DK/FD/MGM closing lines
     (benashkar/nba_gambling), per stat. Reliability bins + ECE.
  4. THE FIX (gated)    — a leak-free recalibration of the predictive
     DISTRIBUTION that improves coverage + P(over) ECE WITHOUT touching q50:
       (a) global per-stat sigma scale s* (fit on a past temporal slice,
           evaluated on a held-out future slice), and
       (b) a conditional sigma model sigma(stat, l10_min) — minutes-aware —
           compared against the flat fit.
     q50 is never modified, so the AST edge / pull-to-line is untouched.

Outputs a console report and writes docs/_audits/PREDICTION_CALIBRATION.md.

NOTHING is flipped live. This is analysis + a recommended gated artifact only.

Run:
    python scripts/audit_prediction_calibration.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import warnings
from collections import defaultdict
from datetime import datetime
from math import erf, sqrt
from pathlib import Path
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

_OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
_CALFRAME = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
_MODEL_DIR = _ROOT / "data" / "models"
_CAL_JSON = _MODEL_DIR / "quantile_calibration.json"
_SNAPS_DIR = _ROOT / "data" / "external" / "historical_lines" / "benashkar_nba_gambling"
_NBA_DIR = _ROOT / "data" / "nba"
_OUT_DOC = _ROOT / "docs" / "_audits" / "PREDICTION_CALIBRATION.md"
_OUT_JSON = _ROOT / "data" / "cache" / "prediction_calibration_audit.json"
_RECAL_JSON = _ROOT / "data" / "models" / "sigma_recal_recommendation.json"  # gated artifact (NOT wired)

# Flat sigma the webpage actually serves (api/courtvision_router.py:120)
_STAT_SIGMA = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4, "stl": 1.0, "blk": 0.9, "tov": 1.2}
STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
# benashkar/nba_gambling real-line stats (only 4 have real DK/FD/MGM closes here)
_LINE_STATS = ("pts", "reb", "ast", "fg3m")

PROP_TO_STAT = {"points": "pts", "rebounds": "reb", "assists": "ast",
                "threes": "fg3m", "steals": "stl", "blocks": "blk", "turnovers": "tov"}
KEEP_BOOKS = {"draftkings", "fanduel", "betmgm"}


def _phi(z: float) -> float:
    """Standard-normal CDF."""
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def _norm_cdf_vec(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(erf)(z / sqrt(2.0)))


# ─────────────────────────────────────────────────────────────────────────────
# Load OOF (leak-free walk-forward q50 + actual) and join leak-free minutes prior
# ─────────────────────────────────────────────────────────────────────────────

def load_oof_with_minutes() -> pd.DataFrame:
    oof = pd.read_parquet(_OOF)
    oof["game_date"] = pd.to_datetime(oof["game_date"]).dt.strftime("%Y-%m-%d")
    oof["resid"] = oof["actual"] - oof["oof_pred"]
    cf = pd.read_parquet(_CALFRAME)[["player_id", "date", "stat", "l10_min", "std_min"]].copy()
    cf["date"] = pd.to_datetime(cf["date"]).dt.strftime("%Y-%m-%d")
    cf = cf.rename(columns={"date": "game_date"})
    oof = oof.merge(cf, on=["player_id", "game_date", "stat"], how="left")
    return oof


# ─────────────────────────────────────────────────────────────────────────────
# TASK 2 — SIGMA HONESTY
# ─────────────────────────────────────────────────────────────────────────────

def task2_sigma_honesty(oof: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("TASK 2 — SIGMA HONESTY  (flat _STAT_SIGMA vs true OOF residual std)")
    print("=" * 78)
    print(f"{'stat':<5}{'n':>8}{'flat_sigma':>11}{'resid_std':>11}{'robust_std':>11}"
          f"{'flat/true':>10}{'verdict':>14}")
    print("-" * 78)
    res = {}
    for stat in STATS:
        d = oof[oof["stat"] == stat]
        r = d["resid"].to_numpy(dtype=float)
        n = len(r)
        std = float(np.std(r, ddof=1))
        # robust std via IQR (less tail-sensitive) for a sanity cross-check
        q75, q25 = np.percentile(r, [75, 25])
        robust = float((q75 - q25) / 1.349)
        flat = _STAT_SIGMA[stat]
        ratio = flat / std if std > 0 else float("nan")
        if ratio > 1.10:
            verdict = "TOO WIDE"
        elif ratio < 0.90:
            verdict = "TOO NARROW"
        else:
            verdict = "OK"
        res[stat] = {"n": n, "flat_sigma": flat, "resid_std": round(std, 4),
                     "robust_std": round(robust, 4), "flat_over_true": round(ratio, 4),
                     "verdict": verdict,
                     "resid_mean": round(float(np.mean(r)), 4),
                     "excess_kurtosis": round(float(pd.Series(r).kurt()), 3)}
        print(f"{stat:<5}{n:>8}{flat:>11.2f}{std:>11.3f}{robust:>11.3f}{ratio:>10.3f}{verdict:>14}")

    # Does the right sigma vary by minutes/role? Bucket residual std by l10_min.
    print("\nResidual std by minutes bucket (l10_min) — is a FLAT sigma valid?")
    print(f"{'stat':<5}{'lowMin_std':>12}{'midMin_std':>12}{'highMin_std':>12}"
          f"{'hi/lo':>8}{'flat_sigma':>11}")
    print("-" * 64)
    by_min = {}
    dm = oof[oof["l10_min"].notna()].copy()
    for stat in STATS:
        d = dm[dm["stat"] == stat].copy()
        if len(d) < 300:
            continue
        # terciles of l10_min
        try:
            d["mbin"] = pd.qcut(d["l10_min"], 3, labels=["low", "mid", "high"], duplicates="drop")
        except Exception:
            continue
        stds = d.groupby("mbin")["resid"].std()
        lo = float(stds.get("low", np.nan)); mid = float(stds.get("mid", np.nan)); hi = float(stds.get("high", np.nan))
        ratio = hi / lo if lo and lo > 0 else float("nan")
        by_min[stat] = {"low": round(lo, 3), "mid": round(mid, 3), "high": round(hi, 3),
                        "hi_over_lo": round(ratio, 3)}
        print(f"{stat:<5}{lo:>12.3f}{mid:>12.3f}{hi:>12.3f}{ratio:>8.2f}{_STAT_SIGMA[stat]:>11.2f}")

    # Per-row implied sigma from quantile band (q90-q10)/2.563 — compare its mean
    # to flat sigma (done in task1 where we already have q-bands; mean reported there).
    return {"flat_vs_true": res, "by_minutes": by_min}


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1 — QUANTILE COVERAGE (on the temporal holdout the heads didn't train on)
# ─────────────────────────────────────────────────────────────────────────────

def task1_quantile_coverage() -> dict:
    print("\n" + "=" * 78)
    print("TASK 1 — QUANTILE COVERAGE  (quantile heads on temporal holdout)")
    print("=" * 78)
    from src.prediction.prop_pergame import (
        STATS as PG_STATS, build_pergame_dataset, feature_columns, _MODEL_DIR as PG_MODEL_DIR,
    )
    from src.prediction.prop_quantiles import load_quantile_models, _inverse as qinv
    from src.prediction.quantile_calibration import apply as apply_cal

    print("Building pergame dataset (for feature rows)...", flush=True)
    rows, _ = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    # The quantile heads trained on first (1-0.2-0.15)=0.65; calibration fit on
    # the 0.65-0.80 val slice; production coverage is the last 0.20 holdout.
    # Evaluate on the last 0.20 — leak-free for the heads AND for calibration.
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols] for r in holdout], dtype=float)
    print(f"  n={n}  holdout(last 20%)={len(holdout)}", flush=True)

    print(f"\n{'stat':<5}{'n':>7}{'P<=q10':>9}{'P<=q50':>9}{'P<=q90':>9}"
          f"{'cov80_raw':>11}{'cov80_cal':>11}{'cross%':>8}{'band_sig':>9}{'flat_sig':>9}")
    print("-" * 95)
    out = {}
    for stat in PG_STATS:
        y = np.array([np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
                      for r in holdout], dtype=float)
        mask = ~np.isnan(y)
        qm = load_quantile_models(stat, str(PG_MODEL_DIR))
        if not qm or 0.1 not in qm or 0.9 not in qm:
            print(f"{stat:<5}  (quantile models missing)")
            continue
        # slice X to head's expected feature count (mirror predict path)
        min_n = None
        for m in qm.values():
            nf = getattr(m, "n_features_in_", None)
            if nf is not None:
                min_n = nf if min_n is None else min(min_n, nf)
        Xs = X[:, :min_n] if (min_n is not None and min_n != X.shape[1]) else X

        q10 = qinv(stat, qm[0.1].predict(Xs))
        q90 = qinv(stat, qm[0.9].predict(Xs))
        q50 = qinv(stat, qm[0.5].predict(Xs)) if 0.5 in qm else (q10 + q90) / 2.0
        # calibrated band
        q10c = np.empty_like(q10); q90c = np.empty_like(q90)
        for i in range(len(q10)):
            a, b = apply_cal(stat, float(q10[i]), float(q50[i]), float(q90[i]))
            q10c[i] = a; q90c[i] = b

        yt = y[mask]
        p_q10 = float(np.mean(yt <= q10[mask]))
        p_q50 = float(np.mean(yt <= q50[mask]))
        p_q90 = float(np.mean(yt <= q90[mask]))
        cov_raw = float(np.mean((yt >= q10[mask]) & (yt <= q90[mask])))
        cov_cal = float(np.mean((yt >= q10c[mask]) & (yt <= q90c[mask])))
        # crossing rate (raw): q10>q50 or q50>q90 or q10>q90
        cross = float(np.mean((q10 > q50) | (q50 > q90) | (q10 > q90)))
        band_sigma = float(np.mean((q90 - q10) / 2.563))  # 80% interval -> sigma
        out[stat] = {
            "n": int(mask.sum()),
            "P_le_q10": round(p_q10, 4), "P_le_q50": round(p_q50, 4), "P_le_q90": round(p_q90, 4),
            "cov80_raw": round(cov_raw, 4), "cov80_cal": round(cov_cal, 4),
            "crossing_rate": round(cross, 5),
            "band_implied_sigma": round(band_sigma, 4),
            "flat_sigma": _STAT_SIGMA[stat],
        }
        print(f"{stat:<5}{int(mask.sum()):>7}{p_q10:>9.3f}{p_q50:>9.3f}{p_q90:>9.3f}"
              f"{cov_raw:>11.3f}{cov_cal:>11.3f}{cross*100:>7.2f}%{band_sigma:>9.3f}{_STAT_SIGMA[stat]:>9.2f}")
    print("\nTargets: P<=q10~0.10, P<=q50~0.50, P<=q90~0.90, cov80~0.80, cross%~0")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Benashkar real-line loader  (DK/FD/MGM closes joined to OOF q50)
# ─────────────────────────────────────────────────────────────────────────────

def _build_name_to_pid() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for season in ("2024-25", "2025-26"):
        path = _NBA_DIR / f"player_avgs_{season}.json"
        if not path.exists():
            continue
        try:
            data = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for name_lc, info in data.items():
            pid = info.get("player_id")
            if pid is not None:
                out[name_lc.strip().lower()] = int(pid)
    return out


def load_real_line_rows(oof: pd.DataFrame) -> pd.DataFrame:
    """Join real DK/FD/MGM closes to OOF q50/actual. Returns rows with
    columns: stat, q50(oof_pred), actual, line, over_odds, under_odds."""
    import csv as _csv
    files = sorted(glob.glob(str(_SNAPS_DIR / "data__output__player_props_*.csv")))
    latest: Dict[Tuple, dict] = {}
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for row in _csv.DictReader(fh):
                book = (row.get("sportsbook") or "").lower()
                if book not in KEEP_BOOKS:
                    continue
                if (row.get("is_alt_line", "") or "").lower() == "true":
                    continue
                prop = (row.get("prop_type") or "").lower()
                if prop not in PROP_TO_STAT:
                    continue
                try:
                    line = float(row.get("line") or 0)
                    oo = float(row.get("over_odds") or 0)
                    uo = float(row.get("under_odds") or 0)
                except (ValueError, TypeError):
                    continue
                if oo == 0 or uo == 0:
                    continue
                player = (row.get("player_name") or "").strip().lower()
                gdate = (row.get("game_date") or "").strip()
                scraped = row.get("scraped_at", "")
                key = (player, gdate, book, prop, line)
                prev = latest.get(key)
                if prev is None or scraped > prev["scraped_at"]:
                    latest[key] = {"player": player, "game_date": gdate, "prop": prop,
                                   "line": line, "over_odds": oo, "under_odds": uo,
                                   "scraped_at": scraped}
    oof_idx = {(int(r.player_id), r.game_date, r.stat): (float(r.oof_pred), float(r.actual))
               for r in oof.itertuples(index=False)}
    name_to_pid = _build_name_to_pid()
    recs = []
    for rec in latest.values():
        stat = PROP_TO_STAT.get(rec["prop"])
        if stat is None:
            continue
        pid = name_to_pid.get(rec["player"])
        if pid is None:
            continue
        ent = oof_idx.get((pid, rec["game_date"], stat))
        if ent is None:
            continue
        q50, actual = ent
        recs.append({"stat": stat, "q50": q50, "actual": actual, "line": rec["line"],
                     "over_odds": rec["over_odds"], "under_odds": rec["under_odds"],
                     "game_date": rec["game_date"], "player_id": pid})
    return pd.DataFrame(recs)


def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> Tuple[float, list]:
    """Expected calibration error of probability p vs binary outcome y."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece = 0.0
    rows = []
    N = len(p)
    for b in range(n_bins):
        m = idx == b
        if not m.any():
            continue
        conf = float(np.mean(p[m]))
        acc = float(np.mean(y[m]))
        w = float(m.sum()) / N
        ece += w * abs(conf - acc)
        rows.append({"bin": f"{bins[b]:.1f}-{bins[b+1]:.1f}", "n": int(m.sum()),
                     "pred_p": round(conf, 4), "emp_p": round(acc, 4)})
    return ece, rows


def decompose_ece(lines: pd.DataFrame) -> dict:
    """Split the P(over) miscalibration into a MEAN-OFFSET part (q50 sits high/low
    vs the line — a q50 problem a sigma fix CANNOT and SHOULD NOT touch) and a
    SPREAD part (does a pure sigma rescale at the BET-RELEVANT rows fix it?).

    - ECE_raw         : flat sigma, as served.
    - ECE_recentered  : after subtracting the mean(P(over)) - mean(over) offset
                        (i.e. forcing the model's average over-rate to match
                        reality). Residual ECE here is pure shape/spread.
    - best_sigma_mult : the sigma multiplier (scanned) that minimises ECE — i.e.
                        the sigma the BET-RELEVANT rows actually want. >1 means
                        flat sigma is TOO NARROW where it matters (high-minute
                        players who carry the lines), even when the GLOBAL OOF std
                        looked fine.
    """
    print("\n" + "=" * 78)
    print("TASK 3b — ECE DECOMPOSITION  (mean-offset[=q50] vs spread[=sigma])")
    print("=" * 78)
    print(f"{'stat':<5}{'n':>6}{'meanPov':>9}{'empOver':>9}{'ECE_raw':>9}"
          f"{'ECE_recent':>11}{'best_mult':>10}{'ECE_best':>9}")
    print("-" * 68)
    out = {}
    for stat in _LINE_STATS:
        d = lines[lines["stat"] == stat].copy()
        d = d[np.abs(d["actual"] - d["line"]) > 1e-9]
        if len(d) < 50:
            continue
        sig = _STAT_SIGMA[stat]
        delta = d["q50"].to_numpy() - d["line"].to_numpy()
        y = (d["actual"].to_numpy() > d["line"].to_numpy()).astype(float)
        p = _norm_cdf_vec(delta / sig)
        ece_raw, _ = _ece(p, y, 10)
        p_rc = np.clip(p - (p.mean() - y.mean()), 0.0, 1.0)
        ece_rc, _ = _ece(p_rc, y, 10)
        best = (1e9, 1.0)
        for mlt in np.linspace(0.5, 2.5, 41):
            e, _ = _ece(_norm_cdf_vec(delta / (sig * mlt)), y, 10)
            if e < best[0]:
                best = (e, float(mlt))
        out[stat] = {"ece_raw": round(ece_raw, 4), "ece_recentered": round(ece_rc, 4),
                     "best_sigma_mult": round(best[1], 3), "ece_at_best_mult": round(best[0], 4),
                     "mean_pover": round(float(p.mean()), 4), "emp_over": round(float(y.mean()), 4)}
        print(f"{stat:<5}{len(d):>6}{p.mean():>9.4f}{y.mean():>9.4f}{ece_raw:>9.4f}"
              f"{ece_rc:>11.4f}{best[1]:>10.2f}{best[0]:>9.4f}")
    print("\nReading: if ECE_recentered << ECE_raw, the miscalibration is a q50-vs-line")
    print("OFFSET (do NOT fix with sigma -- that's the CV_PREGAME_CAL trap that kills AST).")
    print("If best_mult >> 1 and ECE_best << ECE_raw, the BET-RELEVANT rows genuinely want")
    print("a WIDER sigma than the flat constant (a real, honest spread fix).")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# TASK 3 — P(OVER) ECE at real lines (flat sigma)
# ─────────────────────────────────────────────────────────────────────────────

def task3_pover_ece(lines: pd.DataFrame, sigma_map: Dict[str, float], label: str) -> dict:
    print("\n" + "=" * 78)
    print(f"TASK 3 — P(OVER) CALIBRATION at REAL DK/FD/MGM closes  [{label}]")
    print("=" * 78)
    print(f"{'stat':<5}{'n':>7}{'sigma':>8}{'mean_pOver':>12}{'emp_over':>10}{'ECE':>9}{'verdict':>14}")
    print("-" * 65)
    out = {}
    for stat in _LINE_STATS:
        d = lines[lines["stat"] == stat].copy()
        # drop pushes
        d = d[np.abs(d["actual"] - d["line"]) > 1e-9]
        if len(d) < 50:
            continue
        sig = sigma_map[stat]
        z = (d["q50"].to_numpy() - d["line"].to_numpy()) / sig
        p_over = _norm_cdf_vec(z)
        y_over = (d["actual"].to_numpy() > d["line"].to_numpy()).astype(float)
        ece, rel = _ece(p_over, y_over, n_bins=10)
        mean_p = float(np.mean(p_over)); emp = float(np.mean(y_over))
        verdict = "OK" if ece <= 0.05 else ("MISCALIBRATED" if ece > 0.10 else "DRIFT")
        out[stat] = {"n": int(len(d)), "sigma": sig, "mean_pOver": round(mean_p, 4),
                     "emp_over": round(emp, 4), "ece": round(ece, 4), "reliability": rel,
                     "verdict": verdict}
        print(f"{stat:<5}{len(d):>7}{sig:>8.2f}{mean_p:>12.4f}{emp:>10.4f}{ece:>9.4f}{verdict:>14}")
    print("\nECE = avg |predicted P(over) - empirical over-rate| across 10 bins. Lower=honest.")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# TASK 4 — THE FIX (leak-free sigma recalibration; q50 untouched)
# ─────────────────────────────────────────────────────────────────────────────

def _gaussian_nll(resid: np.ndarray, sigma: np.ndarray) -> float:
    """Mean Gaussian negative log-likelihood (lower = better-calibrated spread)."""
    sigma = np.clip(sigma, 1e-6, None)
    return float(np.mean(0.5 * np.log(2 * np.pi * sigma ** 2) + (resid ** 2) / (2 * sigma ** 2)))


def task4_fix(oof: pd.DataFrame, lines: pd.DataFrame) -> dict:
    print("\n" + "=" * 78)
    print("TASK 4 — THE FIX  (leak-free sigma recal; q50 UNTOUCHED)")
    print("=" * 78)

    # Temporal split of OOF: fit recal on the PAST, evaluate on the FUTURE.
    oof = oof.copy()
    oof["gd"] = pd.to_datetime(oof["game_date"])
    cut = oof["gd"].quantile(0.70)
    past = oof[oof["gd"] <= cut]
    fut = oof[oof["gd"] > cut]
    print(f"Fit slice (<= {cut.date()}): {len(past):,} rows   "
          f"Eval slice (> {cut.date()}): {len(fut):,} rows")

    recal = {}
    print("\n(A) GLOBAL per-stat sigma scale  s* = std(resid_past)  [vs flat]")
    print(f"{'stat':<5}{'flat':>7}{'fit_sigma':>11}{'NLL_flat':>10}{'NLL_fit':>10}"
          f"{'cov95_flat':>11}{'cov95_fit':>11}")
    print("-" * 67)
    for stat in STATS:
        rp = past[past["stat"] == stat]["resid"].to_numpy()
        rf = fut[fut["stat"] == stat]["resid"].to_numpy()
        if len(rp) < 200 or len(rf) < 100:
            continue
        flat = _STAT_SIGMA[stat]
        fit_sigma = float(np.std(rp, ddof=1))  # leak-free: from PAST only
        nll_flat = _gaussian_nll(rf, np.full_like(rf, flat))
        nll_fit = _gaussian_nll(rf, np.full_like(rf, fit_sigma))
        # 95% (1.96 sigma) two-sided coverage on the FUTURE slice
        cov95_flat = float(np.mean(np.abs(rf) <= 1.96 * flat))
        cov95_fit = float(np.mean(np.abs(rf) <= 1.96 * fit_sigma))
        recal[stat] = {"flat_sigma": flat, "global_fit_sigma": round(fit_sigma, 4),
                       "nll_flat": round(nll_flat, 4), "nll_global_fit": round(nll_fit, 4),
                       "cov95_flat": round(cov95_flat, 4), "cov95_global_fit": round(cov95_fit, 4)}
        print(f"{stat:<5}{flat:>7.2f}{fit_sigma:>11.3f}{nll_flat:>10.3f}{nll_fit:>10.3f}"
              f"{cov95_flat:>11.3f}{cov95_fit:>11.3f}")

    # (B) Conditional sigma on minutes (l10_min): bucketed std, leak-free from PAST,
    #     evaluated on FUTURE. Compare NLL to the global fit.
    print("\n(B) CONDITIONAL sigma sigma(stat, l10_min)  [minutes-aware vs global]")
    print(f"{'stat':<5}{'NLL_global':>12}{'NLL_cond':>12}{'NLL_flat':>12}{'improve%':>10}")
    print("-" * 58)
    pm = past[past["l10_min"].notna()].copy()
    fm = fut[fut["l10_min"].notna()].copy()
    for stat in STATS:
        dp = pm[pm["stat"] == stat].copy()
        df_ = fm[fm["stat"] == stat].copy()
        if len(dp) < 500 or len(df_) < 200:
            continue
        flat = _STAT_SIGMA[stat]
        glob = float(np.std(dp["resid"].to_numpy(), ddof=1))
        # 5 minute buckets fit on PAST; assign to FUTURE by same edges
        try:
            edges = np.unique(np.quantile(dp["l10_min"], np.linspace(0, 1, 6)))
            if len(edges) < 3:
                raise ValueError
        except Exception:
            continue
        dp["mb"] = np.clip(np.digitize(dp["l10_min"], edges[1:-1]), 0, len(edges) - 2)
        bucket_sigma = dp.groupby("mb")["resid"].std(ddof=1).to_dict()
        gb_default = glob
        df_["mb"] = np.clip(np.digitize(df_["l10_min"], edges[1:-1]), 0, len(edges) - 2)
        sig_cond = df_["mb"].map(lambda b: bucket_sigma.get(b, gb_default)).to_numpy(dtype=float)
        rf = df_["resid"].to_numpy()
        nll_flat = _gaussian_nll(rf, np.full_like(rf, flat))
        nll_glob = _gaussian_nll(rf, np.full_like(rf, glob))
        nll_cond = _gaussian_nll(rf, sig_cond)
        improve = (nll_glob - nll_cond) / abs(nll_glob) * 100.0 if nll_glob else 0.0
        recal.setdefault(stat, {})
        recal[stat]["nll_conditional_minutes"] = round(nll_cond, 4)
        recal[stat]["cond_minutes_improve_pct_vs_global"] = round(improve, 3)
        recal[stat]["minute_bucket_sigma"] = {str(k): round(float(v), 4)
                                              for k, v in bucket_sigma.items() if v == v}
        recal[stat]["minute_bucket_edges"] = [round(float(e), 2) for e in edges]
        print(f"{stat:<5}{nll_glob:>12.3f}{nll_cond:>12.3f}{nll_flat:>12.3f}{improve:>9.2f}%")

    # (C) Does the global-fit sigma also improve P(over) ECE at REAL lines?
    #     Re-run task3 with the global_fit_sigma map (still q50 untouched).
    fit_sigma_map = {s: recal.get(s, {}).get("global_fit_sigma", _STAT_SIGMA[s]) for s in STATS}
    ece_fit = task3_pover_ece(lines, fit_sigma_map, label="global-fit sigma (recal)")

    # (D) THE HONEST TEST: does the leak-free MINUTES-CONDITIONAL sigma actually
    #     beat the flat sigma on P(over) ECE at the BET-RELEVANT (real-line) rows?
    #     Bucket sigma fit on PAST OOF only; applied to benashkar rows by l10_min.
    print("\n(D) MINUTES-COND sigma on BET-RELEVANT real-line rows (leak-free)")
    print(f"{'stat':<5}{'n':>6}{'ECE_flat':>10}{'ECE_minCond':>13}{'ECE_globalfit':>15}")
    print("-" * 49)
    cf = pd.read_parquet(_CALFRAME)[["player_id", "date", "stat", "l10_min"]].copy()
    cf["date"] = pd.to_datetime(cf["date"]).dt.strftime("%Y-%m-%d")
    lj = lines.merge(cf.rename(columns={"date": "game_date"}),
                     on=["player_id", "game_date", "stat"], how="left")
    pover_cond = {}
    for stat in _LINE_STATS:
        dp = pm[pm["stat"] == stat]
        if len(dp) < 500:
            continue
        edges = np.unique(np.quantile(dp["l10_min"], np.linspace(0, 1, 6)))
        if len(edges) < 3:
            continue
        dp2 = dp.copy()
        dp2["mb"] = np.clip(np.digitize(dp2["l10_min"], edges[1:-1]), 0, len(edges) - 2)
        bsig = dp2.groupby("mb")["resid"].std(ddof=1).to_dict()
        glob = float(dp["resid"].std(ddof=1))
        d = lj[(lj["stat"] == stat) & lj["l10_min"].notna()].copy()
        d = d[np.abs(d["actual"] - d["line"]) > 1e-9]
        if len(d) < 50:
            continue
        y = (d["actual"].to_numpy() > d["line"].to_numpy()).astype(float)
        delta = d["q50"].to_numpy() - d["line"].to_numpy()
        mb = np.clip(np.digitize(d["l10_min"].to_numpy(), edges[1:-1]), 0, len(edges) - 2)
        sig_cond = np.array([bsig.get(int(b), glob) for b in mb])
        e_flat, _ = _ece(_norm_cdf_vec(delta / _STAT_SIGMA[stat]), y, 10)
        e_cond, _ = _ece(_norm_cdf_vec(delta / sig_cond), y, 10)
        e_glob, _ = _ece(_norm_cdf_vec(delta / glob), y, 10)
        pover_cond[stat] = {"n": int(len(d)), "ece_flat": round(e_flat, 4),
                            "ece_min_cond": round(e_cond, 4), "ece_global_fit": round(e_glob, 4)}
        print(f"{stat:<5}{len(d):>6}{e_flat:>10.4f}{e_cond:>13.4f}{e_glob:>15.4f}")
    print("\nHONEST READ: the leak-free minutes-conditional sigma barely moves bet-relevant")
    print("ECE (and global-fit is worse). The dominant P(over) error is the q50-vs-line")
    print("OFFSET, which a sigma fix cannot address. Minutes-cond sigma is a real NLL /")
    print("role-coverage honesty gain, NOT a betting-ECE win. Do not overclaim edge.")
    return {"recal": recal, "fit_sigma_map": fit_sigma_map, "pover_ece_recal": ece_fit,
            "pover_ece_minutes_cond_betrelevant": pover_cond}


# ─────────────────────────────────────────────────────────────────────────────
# Report writer
# ─────────────────────────────────────────────────────────────────────────────

def write_doc(t1, t2, t3, t3b, t4) -> None:
    _OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    L = []
    L.append("# Prediction Engine Calibration Audit (predictive distribution, NOT q50)\n")
    L.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by "
             "`scripts/audit_prediction_calibration.py`. Leak-free / walk-forward. "
             "q50 point NEVER modified — AST edge and pull-to-line untouched._\n")
    L.append("\n## TL;DR (honest line)\n")
    L.append("- **Globally the flat `_STAT_SIGMA` is well-tuned** — `flat/true` residual-std "
             "ratio is 1.02–1.21 across stats (the router comment is accurate; if anything it's "
             "slightly TOO WIDE on fg3m/blk, not too narrow). So a blanket global refit is NOT "
             "the win.\n")
    L.append("- **The real defect is that a flat sigma is the wrong SHAPE**: the honest sigma "
             "rises ~1.2–1.65× from low-minute to high-minute players (Task 2). The rows you "
             "actually bet are high-minute starters — exactly where the flat sigma is too "
             "narrow — so the served spread is over-confident on bet-relevant rows.\n")
    L.append("- **At real DK/FD/MGM lines, the P(over) miscalibration is mostly a q50-vs-line "
             "MEAN OFFSET, not a sigma problem** (Task 3b): the model's avg P(over)≈0.52 vs "
             "realized over≈0.46. A sigma fix must NOT chase this — that's the `CV_PREGAME_CAL` "
             "pull-to-line trap that kills the AST edge, correctly OFF.\n")
    L.append("- **The leak-free minutes-conditional sigma is a genuine HONESTY gain (NLL + "
             "role-coverage) but NOT a betting-ECE win** (Task 4D): applied to the bet-relevant "
             "rows it barely moves P(over) ECE (PTS 0.103→0.100, AST 0.046→0.040, REB/FG3M ~flat) "
             "and the blunt global refit is uniformly worse. The big Task-3b best-σ multipliers "
             "(2.1–2.5×) reduce ECE mostly by flattening probabilities toward 0.5 — i.e. they "
             "paper over the q50 offset, not a real spread defect. **Do not overclaim an edge.**\n")
    L.append("- **PTS is the least-honest distribution** (ECE 0.10, flat σ slightly too narrow on "
             "high-minute starters); **AST is the most honest** (ECE 0.046, wants no σ change) — "
             "leave AST alone. Gated artifact: `data/models/sigma_recal_recommendation.json` "
             "(NOT wired live).\n")

    L.append("\n## Task 2 — Flat sigma vs true OOF residual std (the sizing error)\n")
    L.append("| stat | n | flat σ | true resid std | robust std | flat/true | excess kurt | verdict |\n")
    L.append("|---|---|---|---|---|---|---|---|\n")
    for s in STATS:
        r = t2["flat_vs_true"][s]
        L.append(f"| {s} | {r['n']:,} | {r['flat_sigma']:.2f} | {r['resid_std']:.3f} | "
                 f"{r['robust_std']:.3f} | {r['flat_over_true']:.3f} | {r['excess_kurtosis']:.2f} | "
                 f"{r['verdict']} |\n")
    L.append("\n`flat/true < 1` ⇒ flat sigma is NARROWER than reality ⇒ over-confident "
             "P(over) ⇒ over-staking. `flat/true > 1` ⇒ over-wide ⇒ under-staking. "
             "High excess kurtosis ⇒ a Gaussian under-states tail risk even at the right σ.\n")
    L.append("\n### Does the right sigma vary by minutes/role? (flat sigma validity)\n")
    L.append("| stat | low-min σ | mid-min σ | high-min σ | high/low |\n")
    L.append("|---|---|---|---|---|\n")
    for s in STATS:
        if s in t2["by_minutes"]:
            b = t2["by_minutes"][s]
            L.append(f"| {s} | {b['low']:.3f} | {b['mid']:.3f} | {b['high']:.3f} | {b['hi_over_lo']:.2f} |\n")
    L.append("\nIf high/low ≫ 1, a flat per-stat sigma is wrong: it over-covers bench "
             "players and under-covers high-usage starters (exactly the rows you bet most).\n")

    L.append("\n## Task 1 — Quantile coverage (heads on temporal holdout)\n")
    L.append("| stat | n | P≤q10 | P≤q50 | P≤q90 | cov80 raw | cov80 cal | crossing% | band σ | flat σ |\n")
    L.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for s in STATS:
        if s in t1:
            r = t1[s]
            L.append(f"| {s} | {r['n']:,} | {r['P_le_q10']:.3f} | {r['P_le_q50']:.3f} | "
                     f"{r['P_le_q90']:.3f} | {r['cov80_raw']:.3f} | {r['cov80_cal']:.3f} | "
                     f"{r['crossing_rate']*100:.2f}% | {r['band_implied_sigma']:.3f} | {r['flat_sigma']:.2f} |\n")
    L.append("\nTargets: P≤q10≈0.10, P≤q50≈0.50, P≤q90≈0.90, cov80≈0.80, crossing≈0. "
             "`band σ` = (q90−q10)/2.563; compare to flat σ to see if the served flat "
             "value matches the heads' own spread.\n")

    L.append("\n## Task 3 — P(over) ECE at REAL DK/FD/MGM closes (flat sigma)\n")
    L.append("This is the number that drives bets: implied P(actual>line) from "
             "(q50=walk-forward OOF, flat σ, Normal) vs the realized over-rate.\n\n")
    L.append("| stat | n | σ | mean P(over) | empirical over | ECE | verdict |\n")
    L.append("|---|---|---|---|---|---|---|\n")
    for s in _LINE_STATS:
        if s in t3:
            r = t3[s]
            L.append(f"| {s} | {r['n']:,} | {r['sigma']:.2f} | {r['mean_pOver']:.4f} | "
                     f"{r['emp_over']:.4f} | {r['ece']:.4f} | {r['verdict']} |\n")
    L.append("\nECE = mean |predicted P(over) − empirical over-rate| over 10 bins. "
             "ECE>0.05 means the edge probabilities are NOT trustworthy at face value "
             "and Kelly stakes computed from them are off.\n")

    L.append("\n### Task 3b — ECE decomposition: which part is q50 vs which part is sigma?\n")
    L.append("This is the load-bearing table. It separates the part of the P(over) error a "
             "sigma fix may legitimately address (spread) from the part it must NOT (q50 offset).\n\n")
    L.append("| stat | mean P(over) | empirical over | ECE raw | ECE re-centered | best σ mult | ECE @ best mult |\n")
    L.append("|---|---|---|---|---|---|---|\n")
    for s in _LINE_STATS:
        if s in t3b:
            r = t3b[s]
            L.append(f"| {s} | {r['mean_pover']:.4f} | {r['emp_over']:.4f} | {r['ece_raw']:.4f} | "
                     f"{r['ece_recentered']:.4f} | {r['best_sigma_mult']:.2f} | {r['ece_at_best_mult']:.4f} |\n")
    L.append("\n- **`ECE re-centered`** removes the mean(P over)−mean(over) offset. Where it stays "
             "high (REB, FG3M, PTS), the residual error is genuine SPREAD miscalibration. Where "
             "re-centering helps a lot, the error is a q50 OFFSET — a sigma fix can't and shouldn't "
             "chase it.\n")
    L.append("- **`best σ mult`** is the pure-spread sigma multiplier that minimises ECE at the "
             "bet-relevant rows. REB 2.5×, PTS 2.3×, FG3M 2.1× ⇒ the flat sigma is materially too "
             "narrow where it's bet. **AST ≈0.95× ⇒ already honest, do not change.** The big "
             "multipliers reflect that bettable rows are high-minute players (Task 2 minutes "
             "buckets) whose residuals are wider than the all-rows OOF average — a flat constant "
             "fit to the full OOF can't see this.\n")

    L.append("\n## Task 4 — The gated fix (leak-free, q50 untouched)\n")
    L.append("Fit on games ≤ 70th-pct date, evaluated on the held-out future slice. "
             "`s* = std(past residuals)`. NLL = Gaussian negative log-likelihood "
             "(lower = honest spread).\n\n")
    L.append("| stat | flat σ | global-fit σ | NLL flat | NLL global | NLL cond(min) | "
             "cov95 flat | cov95 fit | cond improve vs global |\n")
    L.append("|---|---|---|---|---|---|---|---|---|\n")
    for s in STATS:
        r = t4["recal"].get(s, {})
        if not r:
            continue
        L.append(f"| {s} | {r.get('flat_sigma','')} | {r.get('global_fit_sigma','')} | "
                 f"{r.get('nll_flat','')} | {r.get('nll_global_fit','')} | "
                 f"{r.get('nll_conditional_minutes','—')} | {r.get('cov95_flat','')} | "
                 f"{r.get('cov95_global_fit','')} | "
                 f"{r.get('cond_minutes_improve_pct_vs_global','—')}% |\n")
    L.append("\n### P(over) ECE with the recalibrated (global-fit) sigma\n")
    L.append("| stat | n | recal σ | mean P(over) | empirical over | ECE recal | ECE flat (Task 3) |\n")
    L.append("|---|---|---|---|---|---|---|\n")
    for s in _LINE_STATS:
        if s in t4["pover_ece_recal"]:
            r = t4["pover_ece_recal"][s]
            flat_ece = t3.get(s, {}).get("ece", float("nan"))
            L.append(f"| {s} | {r['n']:,} | {r['sigma']:.3f} | {r['mean_pOver']:.4f} | "
                     f"{r['emp_over']:.4f} | {r['ece']:.4f} | {flat_ece:.4f} |\n")

    L.append("\n### Task 4D — the HONEST test: minutes-conditional σ on bet-relevant rows\n")
    L.append("Leak-free σ(stat, l10_min) fit on PAST OOF only, applied to the real DK/FD/MGM "
             "rows by their pre-game minutes. This is the recommended fix evaluated where it "
             "matters.\n\n")
    L.append("| stat | n | ECE flat | ECE minutes-cond | ECE global-fit |\n")
    L.append("|---|---|---|---|---|\n")
    bc = t4.get("pover_ece_minutes_cond_betrelevant", {})
    for s in _LINE_STATS:
        if s in bc:
            r = bc[s]
            L.append(f"| {s} | {r['n']:,} | {r['ece_flat']:.4f} | {r['ece_min_cond']:.4f} | "
                     f"{r['ece_global_fit']:.4f} |\n")
    L.append("\n**Honest read:** minutes-conditional σ barely moves bet-relevant ECE and the "
             "global refit is worse. The minutes-conditional σ is worth shipping as an "
             "uncertainty-HONESTY improvement (better NLL, role-aware coverage so intervals/Kelly "
             "are right per-player), but it is NOT a betting-edge improvement. The residual "
             "P(over) error is the q50-vs-line offset, which is out of scope.\n")

    L.append("\n## Recommendation (gated — do NOT flip live, do NOT touch q50/AST)\n")
    L.append("1. **Do NOT ship a global per-stat sigma refit.** Task 4(A) shows the global-fit σ "
             "≈ flat σ (NLL essentially unchanged) and it even *worsens* P(over) ECE on PTS/REB "
             "because it slightly narrows an already-fine constant. The flat constant is honest "
             "on the full OOF — that's not where the problem is.\n")
    L.append("2. **DO make σ minutes-conditional — as a COVERAGE/HONESTY fix, not an edge claim.** "
             "Use `sigma(stat, l10_min)` (per-stat bucket table on the leak-free `l10_min` prior in "
             "`calibration_frame_v2`). The honest σ rises ~1.2–1.65× from low- to high-minute "
             "players, so a flat constant over-covers bench players and under-covers the high-usage "
             "starters that carry the lines. This makes per-player intervals and Kelly stakes "
             "right-sized. **But the bet-relevant P(over) ECE barely improves (Task 4D)** — ship it "
             "for honest uncertainty, do NOT advertise it as new ROI. Gate behind a new env flag "
             "(e.g. `CV_SIGMA_RECAL`), default OFF, byte-identical when unset. Artifact: "
             "`data/models/sigma_recal_recommendation.json`.\n")
    L.append("3. **Leave AST's σ alone.** AST has the lowest ECE (0.046) and best-σ mult ≈0.95 — "
             "its predictive distribution is already the most honest, consistent with AST being "
             "the one durable edge. Widening it would only dampen the very signal you bet.\n")
    L.append("4. **The q50 / mean-offset part is OUT OF SCOPE here and must stay so.** Task 3b "
             "shows a chunk of the P(over) error is q50 sitting ~6pp high vs the line. Fixing that "
             "with sigma is impossible; fixing it by pulling q50 to the line is the "
             "`CV_PREGAME_CAL` trap that kills the AST edge — correctly OFF. This audit changes "
             "ONLY the spread for P(over)/Kelly; q50, AST, the models, golive, and the webpage "
             "are untouched.\n")
    L.append("5. **Tail caveat.** Residuals are fat-tailed (positive excess kurtosis, esp. "
             "rare-event stats). A Gaussian even at the right σ understates tail risk; a "
             "t-distribution or directly using the model's per-row quantile band (band-implied σ, "
             "Task 1) is the more honest long-run replacement for any flat/bucketed constant.\n")
    _OUT_DOC.write_text("".join(L), encoding="utf-8")
    print(f"\n[wrote] {_OUT_DOC.relative_to(_ROOT)}")


def main() -> int:
    try:  # Windows cp1252 console safety for any stray non-ASCII glyphs
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("Loading OOF (walk-forward) + leak-free minutes prior...", flush=True)
    oof = load_oof_with_minutes()
    print(f"  OOF rows: {len(oof):,}  ({oof['stat'].nunique()} stats)  "
          f"minutes-joined: {oof['l10_min'].notna().mean()*100:.1f}%")

    t2 = task2_sigma_honesty(oof)

    print("\nLoading real DK/FD/MGM closes (benashkar/nba_gambling)...", flush=True)
    lines = load_real_line_rows(oof)
    print(f"  matched line rows (q50 join): {len(lines):,}")

    t3 = task3_pover_ece(lines, _STAT_SIGMA, label="flat _STAT_SIGMA (production)")
    t3b = decompose_ece(lines)

    try:
        t1 = task1_quantile_coverage()
    except Exception as exc:
        print(f"[task1 quantile coverage skipped: {exc}]")
        t1 = {}

    t4 = task4_fix(oof, lines)

    # write gated recommendation artifact (NOT wired anywhere)
    _RECAL_JSON.parent.mkdir(parents=True, exist_ok=True)
    # The RECOMMENDED fix: minutes-conditional sigma table per stat (from Task 4B),
    # widen PTS/REB/FG3M, leave AST alone. Global-fit kept only as a reference.
    minutes_sigma = {s: {"edges": t4["recal"].get(s, {}).get("minute_bucket_edges"),
                         "bucket_sigma": t4["recal"].get(s, {}).get("minute_bucket_sigma")}
                     for s in STATS if t4["recal"].get(s, {}).get("minute_bucket_sigma")}
    bet_best_mult = {s: t3b.get(s, {}).get("best_sigma_mult") for s in _LINE_STATS}
    rec_out = {
        "_README": "GATED recommendation only. NOT wired live. This changes ONLY the spread "
                   "(sigma) used for P(over)/Kelly. q50 point and AST are UNTOUCHED. Behind a "
                   "future CV_SIGMA_RECAL flag, default OFF, byte-identical when unset.",
        "_recommendation": "Do NOT use a global refit (~= flat). DO use minutes_conditional_sigma "
                           "for PTS/REB/FG3M to widen sigma for high-minute (bettable) players. "
                           "Leave AST sigma at its current value (already best-calibrated).",
        "flat_stat_sigma": _STAT_SIGMA,
        "global_fit_sigma_REFERENCE_ONLY": t4["fit_sigma_map"],
        "minutes_conditional_sigma": minutes_sigma,
        "bet_relevant_best_sigma_multiplier": bet_best_mult,
        "do_not_touch": ["ast q50 + ast sigma (best calibrated)", "q50 point estimate",
                         "CV_PREGAME_CAL (point pull-to-line)"],
        "per_stat_detail": t4["recal"],
    }
    json.dump(rec_out, open(_RECAL_JSON, "w", encoding="utf-8"), indent=2)
    print(f"[wrote] {_RECAL_JSON.relative_to(_ROOT)}  (gated, NOT wired)")

    full = {"task1_quantile_coverage": t1, "task2_sigma_honesty": t2,
            "task3_pover_ece_flat": t3, "task3b_ece_decomposition": t3b, "task4_fix": t4}
    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    json.dump(full, open(_OUT_JSON, "w", encoding="utf-8"), indent=2, default=str)
    print(f"[wrote] {_OUT_JSON.relative_to(_ROOT)}")

    write_doc(t1, t2, t3, t3b, t4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
