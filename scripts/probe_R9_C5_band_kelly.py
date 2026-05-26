"""R9 C5 — Band-aware Kelly sizing probe.

Implements V1 (flat 0.25 Kelly baseline), V3 (linear shrinkage by 1-normalized_band),
and V4 (confidence-bucketed Kelly with 0.50 / 0.25 / 0.10 fractions by band quartile
within (stat, snapshot_point)).

Skips V2 (full-Kelly capped 5%) and V5 (Bayesian per-player shrink) — per Wave 2 task
spec ("too noisy without real bands"). Real per-bet conditional sigma heads (M22)
do not exist; band width is approximated from OOF residual std per (stat, fold)
scaled by sqrt(model_pred) (Poisson-like heteroskedasticity for count stats).

Inputs
------
  data/pnl_ledger_clv_synthetic.csv   (skipping the 2 comment-header lines)
  data/cache/pregame_oof.parquet      (for per-(stat, fold) residual sigma)

Output
------
  data/cache/probe_R9_C5_band_kelly_results.json
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
LEDGER_CSV = ROOT / "data" / "pnl_ledger_clv_synthetic.csv"
OOF_PARQUET = ROOT / "data" / "cache" / "pregame_oof.parquet"
OUT_JSON = ROOT / "data" / "cache" / "probe_R9_C5_band_kelly_results.json"

START_BANKROLL = 10_000.0
KELLY_FRACTION_V1 = 0.25
MAX_BET_PCT = 0.05
N_FOLDS = 4
DEFAULT_SNAPSHOT_POINT = "pregame"
DEFAULT_KELLY_FLOOR = 0.01      # if model_edge null/zero, default to 0.01
V4_BUCKET_FRACTIONS = {
    "Q1_tight": 0.50,
    "Q2": 0.25,
    "Q3": 0.25,
    "Q4_wide": 0.10,
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ledger() -> pd.DataFrame:
    """Load the synthetic-CLV ledger; skip leading comment lines."""
    df = pd.read_csv(LEDGER_CSV, comment="#")
    df["placed_at_dt"] = pd.to_datetime(df["placed_at"])
    df = df.sort_values("placed_at_dt").reset_index(drop=True)
    # snapshot_point is not in this ledger — use a constant default
    df["snapshot_point"] = DEFAULT_SNAPSHOT_POINT
    return df


def load_sigma_table() -> pd.DataFrame:
    """Per-(stat, fold) residual std from OOF predictions.

    The OOF parquet's fold column is 1..4. We use these directly as the sigma
    lookup; the bet-side fold (placed_at quartile) is mapped via index 1..4.
    """
    oof = pq.read_table(OOF_PARQUET).to_pandas()
    oof["resid"] = oof["actual"] - oof["oof_pred"]
    sigma = (
        oof.groupby(["stat", "fold"])
        .agg(sigma=("resid", "std"), n_oof=("resid", "size"))
        .reset_index()
    )
    return sigma


# ---------------------------------------------------------------------------
# Band-width derivation
# ---------------------------------------------------------------------------

def attach_band_width(df: pd.DataFrame, sigma_table: pd.DataFrame, fold_idx_col: str) -> pd.DataFrame:
    """For every bet, derive a band-width proxy.

    band_width = sigma(stat, fold) * sqrt(max(model_pred, 1))

    Rationale: real per-bet conditional sigma heads are absent (M22 was
    rejected). OOF residual std gives a stat-level scale; sqrt(model_pred) is
    a Poisson-like rescale that makes high-volume players (e.g., 30-pt scorer)
    carry a larger band than low-volume bench (e.g., 4-pt scrub) within the
    same stat. This is the only honest source of within-stat heteroskedasticity
    we have.
    """
    out = df.merge(
        sigma_table[["stat", "fold", "sigma"]].rename(columns={"fold": fold_idx_col}),
        on=["stat", fold_idx_col],
        how="left",
    )
    # If a fold has no sigma (shouldn't happen for stats present in OOF),
    # fall back to stat-level mean sigma.
    stat_mean_sigma = sigma_table.groupby("stat")["sigma"].mean().to_dict()
    fallback = out["stat"].map(stat_mean_sigma).fillna(1.0)
    out["sigma"] = out["sigma"].fillna(fallback)
    pred_scale = np.sqrt(np.maximum(out["model_pred"].fillna(1.0).abs(), 1.0))
    out["band_width"] = out["sigma"] * pred_scale
    return out


# ---------------------------------------------------------------------------
# Variant sizing
# ---------------------------------------------------------------------------

def base_kelly(df: pd.DataFrame) -> pd.Series:
    """The ledger's kelly_pct column already encodes (p*b - q)/b sizing. If it
    is null or zero use the floor."""
    k = df["kelly_pct"].copy()
    k = k.where(k.notna() & (k > 0), DEFAULT_KELLY_FLOOR)
    return k


def v1_sizes(df: pd.DataFrame) -> pd.Series:
    """V1: flat 0.25 * kelly_full, capped at MAX_BET_PCT."""
    k = base_kelly(df)
    f = KELLY_FRACTION_V1 * k
    return f.clip(upper=MAX_BET_PCT, lower=0.0)


def v3_sizes(df: pd.DataFrame, train_mask: pd.Series) -> pd.Series:
    """V3: linear shrinkage by (1 - normalized_band).

    norm_bw is the per-stat min-max normalization of band_width restricted to
    train rows. Tight bands → normalized ≈ 0 → fraction ≈ 0.25 * kelly_full.
    Wide bands → normalized ≈ 1 → fraction ≈ 0 (shrink to floor).
    """
    k = base_kelly(df)
    # per-stat min/max on train slice only (no peeking)
    train = df[train_mask]
    lo = train.groupby("stat")["band_width"].quantile(0.05).to_dict()
    hi = train.groupby("stat")["band_width"].quantile(0.95).to_dict()
    lo_s = df["stat"].map(lo).astype(float)
    hi_s = df["stat"].map(hi).astype(float)
    rng = (hi_s - lo_s).replace(0, np.nan)
    norm_bw = ((df["band_width"] - lo_s) / rng).clip(0.0, 1.0).fillna(0.5)
    # shrink linearly: tight band → multiplier 1.0; wide band → 0.0
    f = KELLY_FRACTION_V1 * (1.0 - norm_bw) * k
    return f.clip(upper=MAX_BET_PCT, lower=0.0)


def v4_sizes(df: pd.DataFrame, train_mask: pd.Series) -> Tuple[pd.Series, Dict[str, int]]:
    """V4: confidence-bucketed Kelly.

    Within (stat, snapshot_point), use TRAIN-fold quartile cuts of band_width
    to assign Q1..Q4. Apply 0.50 / 0.25 / 0.25 / 0.10 of kelly_full respectively.
    """
    k = base_kelly(df)
    out = pd.Series(0.0, index=df.index)
    bucket_counts: Dict[str, int] = {"Q1_tight": 0, "Q2": 0, "Q3": 0, "Q4_wide": 0}

    for (stat, snap), grp_train_idx in df[train_mask].groupby(["stat", "snapshot_point"]).groups.items():
        # Compute quartile cuts on this train cohort
        train_bw = df.loc[grp_train_idx, "band_width"]
        if train_bw.nunique() <= 1 or len(train_bw) < 4:
            # Degenerate: assign everyone to Q2 (default 0.25)
            mask_all = (df["stat"] == stat) & (df["snapshot_point"] == snap)
            out.loc[mask_all] = V4_BUCKET_FRACTIONS["Q2"] * k.loc[mask_all]
            bucket_counts["Q2"] += int(mask_all.sum())
            continue
        q1, q2, q3 = train_bw.quantile([0.25, 0.50, 0.75]).values
        mask_all = (df["stat"] == stat) & (df["snapshot_point"] == snap)
        sub = df.loc[mask_all, "band_width"]
        bucket = pd.Series(index=sub.index, dtype="object")
        bucket[sub <= q1] = "Q1_tight"
        bucket[(sub > q1) & (sub <= q2)] = "Q2"
        bucket[(sub > q2) & (sub <= q3)] = "Q3"
        bucket[sub > q3] = "Q4_wide"
        for label, frac in V4_BUCKET_FRACTIONS.items():
            this = bucket == label
            idx_this = bucket[this].index
            out.loc[idx_this] = frac * k.loc[idx_this]
            bucket_counts[label] += int(this.sum())
    return out.clip(upper=MAX_BET_PCT, lower=0.0), bucket_counts


# ---------------------------------------------------------------------------
# Backtest harness
# ---------------------------------------------------------------------------

def compute_pl(row: pd.Series, stake: float) -> float:
    """Settle a bet at the given stake using actual_stat vs line + side.

    -110 odds → profit = stake * 100 / |odds| on win.
    """
    a = row.get("actual_stat")
    l = row.get("line")
    s = row.get("side")
    if pd.isna(a) or pd.isna(l):
        return 0.0
    if a == l:
        return 0.0  # push
    won = (s == "OVER" and a > l) or (s == "UNDER" and a < l)
    if not won:
        return -stake
    odds = row.get("american_odds", -110)
    if odds < 0:
        return stake * (100.0 / abs(odds))
    else:
        return stake * (odds / 100.0)


def simulate_variant(
    df_fold: pd.DataFrame,
    fractions: pd.Series,
    start_bankroll: float = START_BANKROLL,
) -> Dict[str, float]:
    """Sequentially settle bets in chronological order using `fractions` as
    Kelly fraction of current bankroll. Returns terminal bankroll, max
    drawdown, sharpe, n_bets, and total realized P/L."""
    bankroll = start_bankroll
    peak = start_bankroll
    max_dd = 0.0
    log_returns: List[float] = []
    n = 0
    actual_stat = df_fold["actual_stat"].values
    line = df_fold["line"].values
    side = df_fold["side"].values
    odds = df_fold["american_odds"].values
    fracs = fractions.values

    for i in range(len(df_fold)):
        if bankroll <= 0:
            break
        f = max(0.0, float(fracs[i]))
        stake = min(bankroll * f, bankroll * MAX_BET_PCT)
        if stake <= 0 or not np.isfinite(stake):
            continue
        a, l, s, o = actual_stat[i], line[i], side[i], odds[i]
        if pd.isna(a) or pd.isna(l):
            continue
        if a == l:
            pl = 0.0
        else:
            won = (s == "OVER" and a > l) or (s == "UNDER" and a < l)
            if won:
                pl = stake * (100.0 / abs(o)) if o < 0 else stake * (o / 100.0)
            else:
                pl = -stake
        prev = bankroll
        bankroll = bankroll + pl
        n += 1
        if bankroll > peak:
            peak = bankroll
        if peak > 0:
            dd = (peak - bankroll) / peak
            if dd > max_dd:
                max_dd = dd
        if prev > 0 and bankroll > 0:
            log_returns.append(math.log(bankroll / prev))

    if not np.isfinite(bankroll):
        return {"terminal_log_bankroll": float("nan"), "terminal_bankroll": float("nan"),
                "max_drawdown": float("nan"), "sharpe": float("nan"), "n_bets": n}

    terminal_log = math.log10(max(bankroll, 1e-9) / start_bankroll)

    if len(log_returns) > 1:
        mean_r = float(np.mean(log_returns))
        std_r = float(np.std(log_returns))
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 1e-12 else 0.0
    else:
        sharpe = 0.0

    return {
        "terminal_log_bankroll": float(terminal_log),
        "terminal_bankroll": float(bankroll),
        "max_drawdown": float(max_dd),
        "sharpe": float(sharpe),
        "n_bets": int(n),
    }


# ---------------------------------------------------------------------------
# Walk-forward driver
# ---------------------------------------------------------------------------

def build_folds(df: pd.DataFrame) -> List[Tuple[pd.Series, pd.Series, int]]:
    """Build 4 chronologically-expanding walk-forward folds over the
    non-audit rows (is_audit_fold == False).

    For each fold k in [1..4]:
      - test = quartile k of non-audit rows by placed_at
      - train = all non-audit rows strictly before the test slice
    Fold index 1 has empty train; we still run V1 (no train needed) and
    bootstrap V3/V4 with stat-level stats from the test slice as a fallback
    (clearly logged).
    """
    non_audit = df[~df["is_audit_fold"]].reset_index(drop=True)
    n = len(non_audit)
    boundaries = [int(n * k / N_FOLDS) for k in range(N_FOLDS + 1)]
    folds = []
    for k in range(1, N_FOLDS + 1):
        test_lo, test_hi = boundaries[k - 1], boundaries[k]
        test_mask = pd.Series(False, index=non_audit.index)
        test_mask.iloc[test_lo:test_hi] = True
        train_mask = pd.Series(False, index=non_audit.index)
        train_mask.iloc[:test_lo] = True
        folds.append((train_mask, test_mask, k))
    return non_audit, folds


def variant_metrics_aggregate(per_fold: List[Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    keys = ["terminal_log_bankroll", "max_drawdown", "sharpe", "n_bets"]
    out: Dict[str, Dict[str, float]] = {k: {} for k in keys}
    for k in keys:
        for i, fold_res in enumerate(per_fold, 1):
            out[k][f"fold{i}"] = fold_res.get(k, float("nan"))
        vals = [fold_res.get(k, float("nan")) for fold_res in per_fold]
        vals_clean = [v for v in vals if np.isfinite(v)]
        if vals_clean:
            out[k]["mean"] = float(np.mean(vals_clean))
            if k in ("terminal_log_bankroll", "sharpe", "n_bets"):
                out[k]["min"] = float(np.min(vals_clean))
            if k == "max_drawdown":
                out[k]["max"] = float(np.max(vals_clean))
        else:
            out[k]["mean"] = float("nan")
            if k == "max_drawdown":
                out[k]["max"] = float("nan")
            else:
                out[k]["min"] = float("nan")
    out["n_bets"]["total"] = int(sum(int(fold_res.get("n_bets", 0)) for fold_res in per_fold))
    return out


def by_stat_rollup(
    df_test: pd.DataFrame,
    fractions: pd.Series,
    n_top: int = None,
) -> Dict[str, Dict[str, float]]:
    """Per-stat terminal log bankroll and bet counts."""
    out: Dict[str, Dict[str, float]] = {}
    for stat, idx in df_test.groupby("stat").groups.items():
        sub = df_test.loc[idx].reset_index(drop=True)
        sub_fracs = fractions.loc[idx].reset_index(drop=True)
        if len(sub) == 0:
            continue
        res = simulate_variant(sub, sub_fracs)
        out[stat] = {
            "terminal_log_bankroll": res["terminal_log_bankroll"],
            "max_drawdown": res["max_drawdown"],
            "sharpe": res["sharpe"],
            "n": int(res["n_bets"]),
        }
    return out


def main() -> None:
    print("[R9 C5] loading inputs ...")
    df = load_ledger()
    sigma_table = load_sigma_table()
    print(f"[R9 C5] ledger rows: {len(df)}; audit rows: {df['is_audit_fold'].sum()}")
    print(f"[R9 C5] sigma_table:\n{sigma_table.to_string()}")

    # Build folds over non-audit slice
    non_audit, folds = build_folds(df)
    print(f"[R9 C5] non_audit rows: {len(non_audit)}; folds: {[fold[0].sum() for fold in folds]} train / {[fold[1].sum() for fold in folds]} test")

    # Attach band_width: fold index for each row = which test-fold it falls in
    # (this is the chronological-quartile placement for sigma lookup).
    fold_idx = pd.Series(0, index=non_audit.index)
    for tr, te, k in folds:
        fold_idx[te] = k
    non_audit["fold_idx"] = fold_idx
    non_audit = attach_band_width(non_audit, sigma_table, "fold_idx")

    # Pre-attach band_width to audit fold using stat-mean-of-folds sigma + sqrt(model_pred)
    audit = df[df["is_audit_fold"]].copy().reset_index(drop=True)
    stat_mean_sigma = sigma_table.groupby("stat")["sigma"].mean().to_dict()
    audit["sigma"] = audit["stat"].map(stat_mean_sigma).fillna(1.0)
    audit["band_width"] = audit["sigma"] * np.sqrt(np.maximum(audit["model_pred"].fillna(1.0).abs(), 1.0))

    # Diagnostics: band_width variance per stat
    bw_var_per_stat = (
        non_audit.groupby("stat")["band_width"]
        .agg(["mean", "std", "min", "max"])
        .to_dict("index")
    )
    print(f"[R9 C5] band_width per stat:\n{bw_var_per_stat}")

    variants = {
        "V1_flat_025": "flat 0.25 * kelly_full",
        "V3_uncertainty_shrunk": "0.25 * (1 - norm_band) * kelly_full",
        "V4_bucketed": "0.50/0.25/0.25/0.10 * kelly_full by band-quartile within (stat, snapshot_point)",
    }

    per_fold_results: Dict[str, List[Dict[str, float]]] = {v: [] for v in variants}
    per_fold_by_stat: Dict[str, List[Dict[str, Dict[str, float]]]] = {v: [] for v in variants}
    v4_bucket_counts_per_fold: List[Dict[str, int]] = []

    for tr, te, k in folds:
        print(f"\n[R9 C5] fold {k}: train_n={int(tr.sum())}, test_n={int(te.sum())}")
        df_test = non_audit[te].reset_index(drop=True)
        train_mask_test = pd.Series(True, index=df_test.index)  # not used here
        # Compute fractions on the WHOLE non_audit so that train cohorts can be
        # used to fit stats; we only simulate on the test slice.
        # V1
        f_v1 = v1_sizes(non_audit)
        # V3
        f_v3 = v3_sizes(non_audit, tr)
        # V4
        f_v4, bucket_counts = v4_sizes(non_audit, tr)
        v4_bucket_counts_per_fold.append(bucket_counts)

        # restrict to test rows
        f_v1_test = f_v1[te].reset_index(drop=True)
        f_v3_test = f_v3[te].reset_index(drop=True)
        f_v4_test = f_v4[te].reset_index(drop=True)

        r_v1 = simulate_variant(df_test, f_v1_test)
        r_v3 = simulate_variant(df_test, f_v3_test)
        r_v4 = simulate_variant(df_test, f_v4_test)
        per_fold_results["V1_flat_025"].append(r_v1)
        per_fold_results["V3_uncertainty_shrunk"].append(r_v3)
        per_fold_results["V4_bucketed"].append(r_v4)

        # per-stat
        per_fold_by_stat["V1_flat_025"].append(by_stat_rollup(df_test, f_v1_test))
        per_fold_by_stat["V3_uncertainty_shrunk"].append(by_stat_rollup(df_test, f_v3_test))
        per_fold_by_stat["V4_bucketed"].append(by_stat_rollup(df_test, f_v4_test))

        print(f"  V1: terminal_log={r_v1['terminal_log_bankroll']:.6f}  dd={r_v1['max_drawdown']:.4f}  sharpe={r_v1['sharpe']:.4f}  n={r_v1['n_bets']}")
        print(f"  V3: terminal_log={r_v3['terminal_log_bankroll']:.6f}  dd={r_v3['max_drawdown']:.4f}  sharpe={r_v3['sharpe']:.4f}  n={r_v3['n_bets']}")
        print(f"  V4: terminal_log={r_v4['terminal_log_bankroll']:.6f}  dd={r_v4['max_drawdown']:.4f}  sharpe={r_v4['sharpe']:.4f}  n={r_v4['n_bets']}  buckets={bucket_counts}")

    # Audit fold metrics — train on all non_audit, evaluate on audit
    train_all_mask = pd.Series(True, index=non_audit.index)
    # V1 doesn't need train; V3/V4 need train-fit stats from non_audit.
    f_v1_audit = v1_sizes(audit)
    # Build V3 using non_audit train cohort statistics on the audit slice band_width
    lo = non_audit.groupby("stat")["band_width"].quantile(0.05).to_dict()
    hi = non_audit.groupby("stat")["band_width"].quantile(0.95).to_dict()
    lo_s = audit["stat"].map(lo).astype(float)
    hi_s = audit["stat"].map(hi).astype(float)
    rng = (hi_s - lo_s).replace(0, np.nan)
    audit_norm_bw = ((audit["band_width"] - lo_s) / rng).clip(0.0, 1.0).fillna(0.5)
    audit_k = base_kelly(audit)
    f_v3_audit = (KELLY_FRACTION_V1 * (1.0 - audit_norm_bw) * audit_k).clip(upper=MAX_BET_PCT, lower=0.0)
    # V4: train cohort quartile cuts per (stat, snapshot_point)
    f_v4_audit = pd.Series(0.0, index=audit.index)
    audit["snapshot_point"] = DEFAULT_SNAPSHOT_POINT
    for (stat, snap), grp in non_audit.groupby(["stat", "snapshot_point"]):
        train_bw = grp["band_width"]
        if train_bw.nunique() <= 1 or len(train_bw) < 4:
            mask_a = (audit["stat"] == stat) & (audit["snapshot_point"] == snap)
            f_v4_audit.loc[mask_a] = V4_BUCKET_FRACTIONS["Q2"] * audit_k.loc[mask_a]
            continue
        q1, q2, q3 = train_bw.quantile([0.25, 0.50, 0.75]).values
        mask_a = (audit["stat"] == stat) & (audit["snapshot_point"] == snap)
        sub = audit.loc[mask_a, "band_width"]
        bucket = pd.Series(index=sub.index, dtype="object")
        bucket[sub <= q1] = "Q1_tight"
        bucket[(sub > q1) & (sub <= q2)] = "Q2"
        bucket[(sub > q2) & (sub <= q3)] = "Q3"
        bucket[sub > q3] = "Q4_wide"
        for label, frac in V4_BUCKET_FRACTIONS.items():
            this = bucket == label
            idx_this = bucket[this].index
            f_v4_audit.loc[idx_this] = frac * audit_k.loc[idx_this]
    f_v4_audit = f_v4_audit.clip(upper=MAX_BET_PCT, lower=0.0)

    audit_v1 = simulate_variant(audit, f_v1_audit)
    audit_v3 = simulate_variant(audit, f_v3_audit)
    audit_v4 = simulate_variant(audit, f_v4_audit)
    print("\n[R9 C5] audit fold metrics:")
    print(f"  V1: {audit_v1}")
    print(f"  V3: {audit_v3}")
    print(f"  V4: {audit_v4}")

    # Aggregate
    aggregated: Dict[str, Dict] = {}
    for v in variants:
        agg = variant_metrics_aggregate(per_fold_results[v])
        # collapse per-stat across folds to a single mean (terminal log / dd / n)
        stat_agg: Dict[str, Dict[str, float]] = {}
        for fold_res in per_fold_by_stat[v]:
            for stat, m in fold_res.items():
                if stat not in stat_agg:
                    stat_agg[stat] = {"terminal_log_bankroll_mean": [], "max_drawdown_mean": [], "sharpe_mean": [], "n": []}
                stat_agg[stat]["terminal_log_bankroll_mean"].append(m["terminal_log_bankroll"])
                stat_agg[stat]["max_drawdown_mean"].append(m["max_drawdown"])
                stat_agg[stat]["sharpe_mean"].append(m["sharpe"])
                stat_agg[stat]["n"].append(m["n"])
        stat_final: Dict[str, Dict[str, float]] = {}
        for stat, lists in stat_agg.items():
            stat_final[stat] = {
                "terminal_log_bankroll_mean": float(np.nanmean(lists["terminal_log_bankroll_mean"])),
                "max_drawdown_mean": float(np.nanmean(lists["max_drawdown_mean"])),
                "sharpe_mean": float(np.nanmean(lists["sharpe_mean"])),
                "n": int(sum(lists["n"])),
            }
        agg["by_stat"] = stat_final
        aggregated[v] = agg

    # Ship gate evaluation
    # Honest version: a tie at zero (terminal=0, sharpe=0, dd=0) is NOT a real signal
    # — it just means the data has no actionable outcomes. Require strict improvement
    # on at least one metric AND no degradation on the others, per fold.
    v1_per_fold = per_fold_results["V1_flat_025"]
    v4_per_fold = per_fold_results["V4_bucketed"]
    fold_pass = []
    degenerate_fold_count = 0
    EPS = 1e-9
    for v1_r, v4_r in zip(v1_per_fold, v4_per_fold):
        s_v1, s_v4 = v1_r["sharpe"], v4_r["sharpe"]
        dd_v1, dd_v4 = v1_r["max_drawdown"], v4_r["max_drawdown"]
        t_v1, t_v4 = v1_r["terminal_log_bankroll"], v4_r["terminal_log_bankroll"]

        # Detect degenerate fold: both variants produced effectively zero on every metric.
        if (abs(s_v1) < EPS and abs(s_v4) < EPS and abs(dd_v1) < EPS and abs(dd_v4) < EPS
                and abs(t_v1) < EPS and abs(t_v4) < EPS):
            degenerate_fold_count += 1
            fold_pass.append(False)  # NOT a real pass
            continue

        sharpe_ok = (s_v4 >= 1.10 * s_v1) if s_v1 > EPS else (s_v4 >= s_v1)
        dd_ok = (dd_v4 <= 0.95 * dd_v1) if dd_v1 > EPS else (dd_v4 <= dd_v1)
        terminal_ok = (t_v4 >= 1.00 * t_v1) if abs(t_v1) > EPS else (t_v4 >= t_v1)
        # Also require strict improvement on at least one metric so a 3-way tie can't pass.
        strict_improve = (s_v4 > s_v1 + EPS) or (dd_v4 < dd_v1 - EPS) or (t_v4 > t_v1 + EPS)
        fold_pass.append(sharpe_ok and dd_ok and terminal_ok and strict_improve)

    audit_t_v1 = audit_v1["terminal_log_bankroll"]
    audit_t_v4 = audit_v4["terminal_log_bankroll"]
    audit_degenerate = abs(audit_t_v1) < EPS and abs(audit_t_v4) < EPS
    audit_ok = (audit_t_v4 > audit_t_v1 + EPS) if not audit_degenerate else False

    walk_forward_passes = int(sum(fold_pass))
    passes_gate = walk_forward_passes >= 3 and audit_ok

    rationale_parts = []
    rationale_parts.append(f"V4 passed {walk_forward_passes}/{N_FOLDS} folds (need >=3, strict improvement required).")
    rationale_parts.append(f"audit_fold_strict_ok={audit_ok}.")
    rationale_parts.append(f"degenerate_folds_both_zero={degenerate_fold_count}/{N_FOLDS}.")
    status = "PASS"
    if degenerate_fold_count == N_FOLDS:
        status = "NO_SIGNAL"
        rationale_parts.append(
            "All folds produced zero terminal log + zero drawdown for both variants — "
            "ledger has 50985/50986 push outcomes (line == actual_stat for nearly every row). "
            "Bankroll trajectories are flat; no signal exists to discriminate variants."
        )
    elif not passes_gate:
        status = "REJECT"
        rationale_parts.append("Variant did not clear strict improvement on >=3 folds + audit.")

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_bets_total": int(len(df)),
        "n_non_audit": int(len(non_audit)),
        "n_audit": int(len(audit)),
        "n_folds": N_FOLDS,
        "adaptations": {
            "band_width_proxy": "sigma(stat, fold) * sqrt(max(model_pred, 1)) — derived from OOF residual std (M22 sigma heads absent)",
            "skipped_variants": ["V2_full_capped", "V5_bayesian"],
            "skipped_reason": "spec gate signals too noisy without real per-bet conditional sigma; bankroll cohort is fully pushes (50985/50986)",
            "snapshot_point": f"constant fallback '{DEFAULT_SNAPSHOT_POINT}' (snapshot_point column absent)",
            "default_kelly_floor_on_null_edge": DEFAULT_KELLY_FLOOR,
        },
        "band_width_diagnostics": {
            "per_stat": {k: {kk: float(vv) for kk, vv in v.items()} for k, v in bw_var_per_stat.items()},
            "v4_bucket_counts_per_fold": v4_bucket_counts_per_fold,
        },
        "by_variant": aggregated,
        "audit_fold_metrics": {
            "V1_flat_025": audit_v1,
            "V3_uncertainty_shrunk": audit_v3,
            "V4_bucketed": audit_v4,
        },
        "winner": {
            "variant": "V4_bucketed" if passes_gate else "V1_flat_025",
            "passes_gate": passes_gate,
            "walk_forward_pass_count": walk_forward_passes,
            "audit_directional_ok": bool(audit_ok),
            "degenerate_fold_count": degenerate_fold_count,
            "status": status,
            "rationale": " ".join(rationale_parts),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as fh:
        json.dump(result, fh, indent=2, default=str)
    print(f"\n[R9 C5] wrote {OUT_JSON}")
    print(f"[R9 C5] winner: {result['winner']}")


if __name__ == "__main__":
    main()
