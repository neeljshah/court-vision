"""
INT-110: Retroactive validation of INT-92's MVN parlay correlation layer.

Tests whether P_joint (MVN bivariate) calibrates better than
P_independent (product of marginals) against empirical 2-leg co-hit rates
from last 6 months of historical lines + OOF predictions.

DO NOT MODIFY: scripts/score_multi_leg_v2.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm, multivariate_normal, ttest_rel

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OOF_PATH = ROOT / "data" / "cache" / "pregame_oof.parquet"
LINES_DIR = ROOT / "data" / "external" / "historical_lines"
CORR_PATH = ROOT / "data" / "intelligence" / "stat_correlation_matrix.parquet"
FP_PATH = ROOT / "data" / "intelligence" / "player_fingerprints.parquet"
PROFILE_PATH = ROOT / "data" / "cache" / "player_profile_features.parquet"

OUT_PARQUET = ROOT / "data" / "intelligence" / "parlay_correlation_retro_validation.parquet"
VAULT_OUT = ROOT / "vault" / "Intelligence" / "INT-110_Parlay_Correlation_Retro.md"
STRATEGY_PATH = ROOT / "vault" / "Improvements" / "cv_master_strategy.md"

TARGET_PAIRS = [("pts", "reb"), ("pts", "ast"), ("pts", "fg3m"), ("reb", "ast")]
LOOKBACK_START = "2025-11-29"  # last 6 months from 2026-05-29

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
print("Loading data...")

oof = pd.read_parquet(OOF_PATH)
oof["game_date"] = pd.to_datetime(oof["game_date"])
oof = oof[oof["game_date"] >= LOOKBACK_START].copy()
print(f"  OOF rows (last 6mo): {len(oof):,}")

# Load all canonical lines files and union them
lines_files = [
    LINES_DIR / "regular_season_2025_26_oddsapi.csv",
    LINES_DIR / "benashkar_2026_canonical.csv",
    LINES_DIR / "extended_oos_canonical.csv",
]
lines_parts = []
for lf in lines_files:
    if lf.exists():
        try:
            df = pd.read_csv(lf)
            df["source"] = lf.stem
            lines_parts.append(df)
        except Exception as e:
            print(f"  Warning: could not read {lf.name}: {e}")

lines = pd.concat(lines_parts, ignore_index=True)
lines["date"] = pd.to_datetime(lines["date"])
lines = lines[lines["date"] >= LOOKBACK_START].copy()
# Normalize stat names
lines["stat"] = lines["stat"].str.lower().str.strip()
lines = lines[lines["stat"].isin(["pts", "reb", "ast", "fg3m"])]
print(f"  Lines rows (last 6mo, target stats): {len(lines):,}")

# Player name -> ID mapping
profile = pd.read_parquet(PROFILE_PATH, columns=["player_id", "player_name"])
# Normalize names for fuzzy matching
profile["player_name_norm"] = profile["player_name"].str.lower().str.strip()
name_to_id = dict(zip(profile["player_name_norm"], profile["player_id"]))
print(f"  Player profiles: {len(profile):,}")

# Correlation matrix
corr_df = pd.read_parquet(CORR_PATH)

# Player fingerprints (archetype)
fp = pd.read_parquet(FP_PATH)

# ---------------------------------------------------------------------------
# Build per-stat sigma from OOF residuals (per-player rolling std)
# ---------------------------------------------------------------------------
print("Computing per-player per-stat sigma from OOF residuals...")

sigma_lookup: dict = {}  # (player_id, stat) -> sigma
for stat in ["pts", "reb", "ast", "fg3m"]:
    sub = oof[oof["stat"] == stat].copy()
    sub["resid"] = sub["actual"] - sub["oof_pred"]
    # Per-player sigma, fallback to global
    global_sigma = float(sub["resid"].std())
    per_player = sub.groupby("player_id")["resid"].std().fillna(global_sigma)
    for pid, s in per_player.items():
        sigma_lookup[(int(pid), stat)] = max(float(s), 0.5)

print(f"  Sigma entries: {len(sigma_lookup):,}")


# ---------------------------------------------------------------------------
# Rho lookup (archetype-conditional)
# ---------------------------------------------------------------------------
def get_rho(archetype: str | None, stat_a: str, stat_b: str) -> float:
    """Return archetype-conditional rho, fallback league."""
    scope = f"archetype:{archetype}" if archetype else "league"
    row = corr_df[
        (corr_df["scope"] == scope)
        & (corr_df["stat_a"] == stat_a)
        & (corr_df["stat_b"] == stat_b)
    ]
    if row.empty:
        row = corr_df[
            (corr_df["scope"] == "league")
            & (corr_df["stat_a"] == stat_a)
            & (corr_df["stat_b"] == stat_b)
        ]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["corr"])


# ---------------------------------------------------------------------------
# Map lines player names -> player_id
# ---------------------------------------------------------------------------
def norm_name(n: str) -> str:
    return str(n).lower().strip()


lines["player_name_norm"] = lines["player"].apply(norm_name)
lines["player_id"] = lines["player_name_norm"].map(name_to_id)
lines_with_id = lines.dropna(subset=["player_id"]).copy()
lines_with_id["player_id"] = lines_with_id["player_id"].astype(int)
print(f"  Lines with matched player_id: {len(lines_with_id):,} / {len(lines):,}")

# De-duplicate: one line per (player_id, date, stat) — prefer DK/oddsapi
lines_with_id = lines_with_id.sort_values(
    "source", ascending=True  # oddsapi files come first alphabetically
).drop_duplicates(subset=["player_id", "date", "stat"], keep="first")
print(f"  After dedup: {len(lines_with_id):,}")

# ---------------------------------------------------------------------------
# Build OOF pivot: (player_id, game_date) -> {stat: oof_pred}
# Also need the actual value but that's in lines (actual_value)
# ---------------------------------------------------------------------------
oof_pivot = oof.pivot_table(
    index=["player_id", "game_date"],
    columns="stat",
    values="oof_pred",
    aggfunc="first",
).reset_index()
oof_pivot.columns.name = None
oof_pivot.columns = [
    "player_id" if c == "player_id" else ("game_date" if c == "game_date" else f"pred_{c}")
    for c in oof_pivot.columns
]
print(f"  OOF pivot rows: {len(oof_pivot):,}")

# ---------------------------------------------------------------------------
# Build 2-leg parlay candidates
# ---------------------------------------------------------------------------
print("Building 2-leg parlay candidates...")

# For each player-date in OOF, join lines for both stats in each pair
records = []
parlay_id = 0

for stat_a, stat_b in TARGET_PAIRS:
    # Lines for stat_a
    la = lines_with_id[lines_with_id["stat"] == stat_a][
        ["player_id", "date", "closing_line", "over_odds", "actual_value"]
    ].rename(columns={
        "closing_line": "line_a",
        "over_odds": "over_odds_a",
        "actual_value": "actual_a",
    })
    # Lines for stat_b
    lb = lines_with_id[lines_with_id["stat"] == stat_b][
        ["player_id", "date", "closing_line", "over_odds", "actual_value"]
    ].rename(columns={
        "closing_line": "line_b",
        "over_odds": "over_odds_b",
        "actual_value": "actual_b",
    })

    # Merge lines on (player_id, date)
    merged_lines = la.merge(lb, on=["player_id", "date"], suffixes=("", ""))
    merged_lines = merged_lines.rename(columns={"date": "game_date"})
    merged_lines["game_date"] = pd.to_datetime(merged_lines["game_date"])

    # Join OOF predictions
    pred_a_col = f"pred_{stat_a}"
    pred_b_col = f"pred_{stat_b}"
    avail_cols = ["player_id", "game_date"] + [
        c for c in [pred_a_col, pred_b_col] if c in oof_pivot.columns
    ]
    if pred_a_col not in oof_pivot.columns or pred_b_col not in oof_pivot.columns:
        print(f"  Skipping {stat_a}x{stat_b}: missing pred columns")
        continue

    joined = merged_lines.merge(
        oof_pivot[avail_cols],
        on=["player_id", "game_date"],
        how="inner",
    )
    joined = joined.dropna(subset=[pred_a_col, pred_b_col, "line_a", "line_b",
                                    "actual_a", "actual_b"])
    print(f"  {stat_a}x{stat_b}: {len(joined)} candidate parlays")

    for _, row in joined.iterrows():
        pid = int(row["player_id"])
        gdate = row["game_date"]

        mu_a = float(row[pred_a_col])
        mu_b = float(row[pred_b_col])
        sigma_a = sigma_lookup.get((pid, stat_a), 6.0 if stat_a == "pts" else 2.5)
        sigma_b = sigma_lookup.get((pid, stat_b), 6.0 if stat_b == "pts" else 2.5)
        line_a = float(row["line_a"])
        line_b = float(row["line_b"])
        actual_a = float(row["actual_a"])
        actual_b = float(row["actual_b"])

        # Archetype lookup
        archetype = None
        if pid in fp.index:
            archetype = fp.loc[pid, "archetype_name"]

        rho = get_rho(archetype, stat_a, stat_b)

        # P_a, P_b (marginal probabilities)
        P_a = float(1.0 - norm.cdf(line_a, loc=mu_a, scale=sigma_a))
        P_b = float(1.0 - norm.cdf(line_b, loc=mu_b, scale=sigma_b))
        P_indep = P_a * P_b

        # P_joint via bivariate MVN
        Sigma = np.array([
            [sigma_a**2, rho * sigma_a * sigma_b],
            [rho * sigma_a * sigma_b, sigma_b**2],
        ])
        # Eigen-clip for PSD
        eigvals, eigvecs = np.linalg.eigh(Sigma)
        eigvals = np.maximum(eigvals, 1e-6)
        Sigma = eigvecs @ np.diag(eigvals) @ eigvecs.T

        try:
            # P(X_a > line_a AND X_b > line_b) = 1 - P(X_a<=line_a) - P(X_b<=line_b) + P(X_a<=line_a AND X_b<=line_b)
            mv = multivariate_normal(mean=[mu_a, mu_b], cov=Sigma)
            p_both_below = float(mv.cdf([line_a, line_b]))
            p_a_below = float(norm.cdf(line_a, loc=mu_a, scale=sigma_a))
            p_b_below = float(norm.cdf(line_b, loc=mu_b, scale=sigma_b))
            P_joint = float(1.0 - p_a_below - p_b_below + p_both_below)
            P_joint = max(0.0, min(1.0, P_joint))
        except Exception:
            P_joint = P_indep  # fallback

        # Actual outcome
        both_hit = int(actual_a > line_a and actual_b > line_b)

        records.append({
            "parlay_id": parlay_id,
            "player_id": pid,
            "game_date": gdate,
            "stat_pair": f"{stat_a}x{stat_b}",
            "stat_a": stat_a,
            "stat_b": stat_b,
            "archetype": archetype,
            "rho": rho,
            "mu_a": mu_a,
            "mu_b": mu_b,
            "sigma_a": sigma_a,
            "sigma_b": sigma_b,
            "line_a": line_a,
            "line_b": line_b,
            "P_a": P_a,
            "P_b": P_b,
            "P_indep": P_indep,
            "P_joint": P_joint,
            "both_hit": both_hit,
        })
        parlay_id += 1

df = pd.DataFrame(records)
print(f"\nTotal 2-leg parlay records: {len(df):,}")
if len(df) == 0:
    print("KILL SWITCH: No scoreable parlays found.")
    sys.exit(1)

print("\nPer stat-pair counts:")
print(df["stat_pair"].value_counts().to_string())

# ---------------------------------------------------------------------------
# G2: Overall calibration
# ---------------------------------------------------------------------------
empirical_cohit = float(df["both_hit"].mean())
mean_P_joint = float(df["P_joint"].mean())
mean_P_indep = float(df["P_indep"].mean())

dev_joint = abs(empirical_cohit - mean_P_joint)
dev_indep = abs(empirical_cohit - mean_P_indep)

g2_pass = dev_joint <= dev_indep
print(f"\n--- G2: Overall Calibration ---")
print(f"  Empirical co-hit rate:  {empirical_cohit:.4f}")
print(f"  Mean P_joint:           {mean_P_joint:.4f}  (|err|={dev_joint:.4f})")
print(f"  Mean P_indep:           {mean_P_indep:.4f}  (|err|={dev_indep:.4f})")
print(f"  G2 PASS (joint beats indep): {g2_pass}")

# ---------------------------------------------------------------------------
# G3: Reliability diagram (10-bucket)
# ---------------------------------------------------------------------------
print("\n--- G3: Reliability Diagram ---")
bucket_results = []
for pred_col, label in [("P_joint", "joint"), ("P_indep", "indep")]:
    df[f"bucket_{label}"] = pd.cut(df[pred_col], bins=np.linspace(0, 1, 11), right=False, include_lowest=True).astype(str)
    bucket_stats = df.groupby(f"bucket_{label}", observed=False).agg(
        n=("both_hit", "count"),
        empirical=("both_hit", "mean"),
        predicted=(pred_col, "mean"),
    ).reset_index()
    bucket_stats["abs_err"] = (bucket_stats["empirical"] - bucket_stats["predicted"]).abs()
    bucket_stats["label"] = label
    bucket_results.append(bucket_stats)
    print(f"\n  {label.upper()} reliability:")
    for _, r in bucket_stats.iterrows():
        if r["n"] > 0:
            print(f"    bucket {str(r[f'bucket_{label}'])[:12]}: n={r['n']:4d} "
                  f"emp={r['empirical']:.3f} pred={r['predicted']:.3f} |err|={r['abs_err']:.3f}")

# Aggregate bucket MAE
joint_bucket_mae = float(bucket_results[0][bucket_results[0]["n"] > 0]["abs_err"].mean())
indep_bucket_mae = float(bucket_results[1][bucket_results[1]["n"] > 0]["abs_err"].mean())
g3_pass = joint_bucket_mae <= 0.10
print(f"\n  Joint bucket MAE: {joint_bucket_mae:.4f} (<=0.10? {g3_pass})")
print(f"  Indep bucket MAE: {indep_bucket_mae:.4f}")

# ---------------------------------------------------------------------------
# G4: Paired t-test
# ---------------------------------------------------------------------------
err_joint = (df["P_joint"] - df["both_hit"]).abs().values
err_indep = (df["P_indep"] - df["both_hit"]).abs().values

from scipy.stats import ttest_rel
t_stat, p_val = ttest_rel(err_joint, err_indep)
g4_pass = p_val < 0.05
print(f"\n--- G4: Paired t-test ---")
print(f"  t-stat: {t_stat:.4f}  p-value: {p_val:.4f}")
print(f"  Mean |err_joint|: {err_joint.mean():.4f}")
print(f"  Mean |err_indep|: {err_indep.mean():.4f}")
print(f"  G4 PASS (p<0.05): {g4_pass}")
print(f"  Direction: {'joint BETTER (lower error)' if t_stat < 0 else 'joint WORSE (higher error)'}")

# ---------------------------------------------------------------------------
# G5: Per-pair breakdown
# ---------------------------------------------------------------------------
print("\n--- G5: Per-pair breakdown ---")
pair_results = []
for pair, grp in df.groupby("stat_pair"):
    emp = grp["both_hit"].mean()
    pj = grp["P_joint"].mean()
    pi = grp["P_indep"].mean()
    dj = abs(emp - pj)
    di = abs(emp - pi)
    ej = (grp["P_joint"] - grp["both_hit"]).abs()
    ei = (grp["P_indep"] - grp["both_hit"]).abs()
    pair_winner = "joint" if dj <= di else "indep"
    # Per-pair t-test if enough data
    if len(grp) >= 20:
        t, p = ttest_rel(ej, ei)
        pair_sig = p < 0.05
    else:
        t, p = float("nan"), float("nan")
        pair_sig = False
    print(f"  {pair}: n={len(grp)} emp={emp:.4f} P_joint={pj:.4f} P_indep={pi:.4f} "
          f"winner={pair_winner} t={t:.3f} p={p:.3f}")
    pair_results.append({
        "stat_pair": pair,
        "n": len(grp),
        "rho_mean": grp["rho"].mean(),
        "empirical_cohit": emp,
        "mean_P_joint": pj,
        "mean_P_indep": pi,
        "dev_joint": dj,
        "dev_indep": di,
        "t_stat": t,
        "p_val": p,
        "winner": pair_winner,
    })
pair_df = pd.DataFrame(pair_results)

# ---------------------------------------------------------------------------
# G1 check
# ---------------------------------------------------------------------------
g1_pass = len(df) >= 100
print(f"\n--- G1: Sample size >= 100 ---")
print(f"  n={len(df)}  PASS: {g1_pass}")

# ---------------------------------------------------------------------------
# Overall verdict
# ---------------------------------------------------------------------------
if not g1_pass:
    verdict = "SCOPED-SHIP"
    verdict_detail = f"Small sample (n={len(df)}). G2/G3/G4 results noted but not conclusive."
elif g2_pass and g4_pass and t_stat < 0:
    verdict = "VALIDATED"
    verdict_detail = "INT-92 MVN correlation layer improves 2-leg co-hit calibration vs independence assumption."
elif not g2_pass and t_stat > 0:
    verdict = "INVALIDATED"
    verdict_detail = "P_indep outperforms P_joint. Correlation layer is hurting calibration."
elif not g4_pass:
    verdict = "INSUFFICIENT_EVIDENCE"
    verdict_detail = f"G2 {'PASS' if g2_pass else 'FAIL'} but p-value={p_val:.3f} >= 0.05. Not statistically significant."
else:
    verdict = "VALIDATED" if g2_pass else "INVALIDATED"
    verdict_detail = f"G2={'PASS' if g2_pass else 'FAIL'}, G4 p={p_val:.3f}"

print(f"\n=== VERDICT: {verdict} ===")
print(f"  {verdict_detail}")

# ---------------------------------------------------------------------------
# Write output parquet
# ---------------------------------------------------------------------------
OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
df.to_parquet(OUT_PARQUET, index=False)
print(f"\nWrote {len(df)} rows to {OUT_PARQUET}")

# Append bucket rows
bucket_df = pd.concat(bucket_results, ignore_index=True)
bucket_out = OUT_PARQUET.parent / "parlay_correlation_retro_buckets.parquet"
bucket_df.to_parquet(bucket_out, index=False)

# ---------------------------------------------------------------------------
# Write vault markdown
# ---------------------------------------------------------------------------
VAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
md_lines = [
    "# INT-110: Parlay Correlation Retro Validation",
    "",
    f"**Date:** 2026-05-29  ",
    f"**Status: {verdict}**  ",
    f"**Lookback:** {LOOKBACK_START} → 2026-05-29 (last 6 months)  ",
    f"**Validates:** INT-92 MVN bivariate correlation layer  ",
    "",
    "## Summary",
    "",
    f"Tested INT-92's core claim: for positively correlated stat pairs, P_joint (bivariate MVN) should",
    f"outperform P_independent (product of marginals) in calibrating to empirical 2-leg co-hit rates.",
    "",
    "## Gate Results",
    "",
    "| Gate | Metric | Value | Pass? |",
    "|------|--------|-------|-------|",
    f"| G1 (sample) | 2-leg parlays | n={len(df)} | {'YES' if g1_pass else 'NO'} |",
    f"| G2 (calibration) | |emp-P_joint|={dev_joint:.4f} vs |emp-P_indep|={dev_indep:.4f} | {'YES' if g2_pass else 'NO'} |",
    f"| G3 (bucket MAE) | Joint bucket MAE={joint_bucket_mae:.4f} vs Indep={indep_bucket_mae:.4f} | <=0.10? | {'YES' if g3_pass else 'NO'} |",
    f"| G4 (t-test) | t={t_stat:.3f}, p={p_val:.4f} | p<0.05? | {'YES' if g4_pass else 'NO'} |",
    f"| G5 (per-pair) | See table below | — | — |",
    "",
    "## Overall Calibration (G2)",
    "",
    f"| Metric | Value |",
    "|--------|-------|",
    f"| Empirical co-hit rate | {empirical_cohit:.4f} |",
    f"| Mean P_joint | {mean_P_joint:.4f} |",
    f"| Mean P_indep | {mean_P_indep:.4f} |",
    f"| |err_joint| | {dev_joint:.4f} |",
    f"| |err_indep| | {dev_indep:.4f} |",
    f"| Winner | {'**P_joint (INT-92)**' if g2_pass else '**P_indep (independence)**'} |",
    "",
    "## Paired t-test (G4)",
    "",
    f"| Metric | Value |",
    "|--------|-------|",
    f"| t-statistic | {t_stat:.4f} |",
    f"| p-value | {p_val:.4f} |",
    f"| Mean |err_joint| | {err_joint.mean():.4f} |",
    f"| Mean |err_indep| | {err_indep.mean():.4f} |",
    f"| Significant (p<0.05) | {'YES' if g4_pass else 'NO'} |",
    "",
    "## Per-Pair Breakdown (G5)",
    "",
    "| Pair | n | rho | emp_cohit | P_joint | P_indep | Winner | p-val |",
    "|------|---|-----|-----------|---------|---------|--------|-------|",
]
for _, r in pair_df.iterrows():
    md_lines.append(
        f"| {r['stat_pair']} | {r['n']} | {r['rho_mean']:.3f} | {r['empirical_cohit']:.4f} | "
        f"{r['mean_P_joint']:.4f} | {r['mean_P_indep']:.4f} | {r['winner']} | {r['p_val']:.3f} |"
    )

md_lines += [
    "",
    "## Reliability Diagram (G3)",
    "",
    "| Bucket | n | Empirical | P_joint | P_indep | |err_joint| | |err_indep| |",
    "|--------|---|-----------|---------|---------|------------|------------|",
]

# Merge bucket stats
bj = bucket_results[0][["bucket_joint", "n", "empirical", "predicted", "abs_err"]].rename(
    columns={"bucket_joint": "bucket", "predicted": "pred_joint", "abs_err": "err_joint"}
).copy()
bi = bucket_results[1][["bucket_indep", "n", "empirical", "predicted", "abs_err"]].rename(
    columns={"bucket_indep": "bucket", "predicted": "pred_indep", "abs_err": "err_indep"}
).copy()
bmerge = bj.merge(bi[["bucket", "pred_indep", "err_indep"]], on="bucket", how="outer")
for _, r in bmerge.iterrows():
    if r["n"] > 0:
        md_lines.append(
            f"| {str(r['bucket'])[:14]} | {int(r['n'])} | {r['empirical']:.3f} | "
            f"{r['pred_joint']:.3f} | {r['pred_indep']:.3f} | "
            f"{r['err_joint']:.3f} | {r['err_indep']:.3f} |"
        )

md_lines += [
    "",
    f"## Verdict: {verdict}",
    "",
    verdict_detail,
    "",
    "## Files",
    "",
    f"- `data/intelligence/parlay_correlation_retro_validation.parquet` — {len(df)} per-parlay rows",
    f"- `data/intelligence/parlay_correlation_retro_buckets.parquet` — reliability diagram data",
    "",
    "---",
    "*Generated by scripts/validate_parlay_correlation_retro.py (INT-110)*",
]

VAULT_OUT.write_text("\n".join(md_lines), encoding="utf-8")
print(f"Wrote vault note: {VAULT_OUT}")

# ---------------------------------------------------------------------------
# Append to cv_master_strategy.md
# ---------------------------------------------------------------------------
if STRATEGY_PATH.exists():
    existing = STRATEGY_PATH.read_text(encoding="utf-8", errors="replace")
    banner = "<!-- INT-110 parlay correlation retro -->"
    if banner not in existing:
        line = (
            f"\n{banner} INT-110 (2026-05-29): 2-leg parlay correlation retro — "
            f"n={len(df)}, verdict={verdict}, "
            f"G2={'PASS' if g2_pass else 'FAIL'} (P_joint={mean_P_joint:.4f} vs P_indep={mean_P_indep:.4f} vs emp={empirical_cohit:.4f}), "
            f"G4 p={p_val:.4f} ({'sig' if g4_pass else 'ns'})\n"
        )
        STRATEGY_PATH.write_text(existing + line, encoding="utf-8", errors="replace")
        print(f"Appended banner to {STRATEGY_PATH}")
    else:
        print(f"Banner already present in {STRATEGY_PATH}, skipping append.")
else:
    print(f"Warning: {STRATEGY_PATH} not found, skipping banner append.")

print("\nINT-110 complete.")
