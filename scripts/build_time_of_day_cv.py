"""
INT-46: Time-of-Day / Day-of-Week CV Patterns
Analyzes whether CV behavioral signatures shift systematically by day-of-week
(B2B effects, weekend night vs weekday matinee) or game-tip time.

Outputs:
  data/intelligence/time_of_day_cv.parquet   — weekday vs weekend per feature
  data/intelligence/dow_cv_profiles.parquet  — mean per DOW + ANOVA per feature
  data/intelligence/dow_signals.json         — top DOW-varying features + top weekend-sensitive players
  vault/Intelligence/Time_Of_Day_CV_Atlas.md — narrative summary
"""

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import f_oneway, ttest_ind

BASE = Path("C:/Users/neelj/nba-ai-system")
DB = BASE / "data" / "nba_ai.db"
OUT_DIR = BASE / "data" / "intelligence"
VAULT_DIR = BASE / "vault" / "Intelligence"

OUT_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Load cv_features from DB and pivot to wide format
# ---------------------------------------------------------------------------
print("Loading cv_features from DB ...")
conn = sqlite3.connect(DB)
cvf = pd.read_sql(
    """
    SELECT game_id, player_id, feature_name, feature_value
    FROM cv_features
    WHERE feature_name != 'cv_archetype'   -- categorical, skip for stats
    """,
    conn,
)
conn.close()

# Exclude cv_xast_pred (model output, not raw CV) and cv_archetype
EXCLUDE_FEATURES = {"cv_archetype", "cv_xast_pred"}
cvf = cvf[~cvf["feature_name"].isin(EXCLUDE_FEATURES)]

# Pivot to wide: one row per (game_id, player_id)
print("Pivoting to wide format ...")
wide = cvf.pivot_table(
    index=["game_id", "player_id"],
    columns="feature_name",
    values="feature_value",
    aggfunc="mean",  # should be unique but guard duplicates
).reset_index()
wide.columns.name = None

cv_feature_cols = [c for c in wide.columns if c not in ("game_id", "player_id")]
print(f"Wide shape: {wide.shape}  |  {len(cv_feature_cols)} CV features")

# Bug 27 guard: add has_pa stratification flag.
# 45.1% of CV games have all-zero potential_assists (xAST submodule not run).
# Zero-PA games must be excluded from potential_assists aggregations to avoid
# artificially depressed means and spurious ANOVA F-statistics (e.g. INT-46 F=5.13).
if "potential_assists" in wide.columns:
    wide["has_pa"] = (wide["potential_assists"] > 0).astype(int)  # Bug 27 guard
else:
    wide["has_pa"] = 0
n_pa_games = int(wide["has_pa"].sum())
n_no_pa_games = int((wide["has_pa"] == 0).sum())
print(f"  has_pa: {n_pa_games} PA-active rows, {n_no_pa_games} PA-zero rows (Bug 27)")
# Null out potential_assists zeros so ANOVA/t-test sees only PA-active values
if "potential_assists" in wide.columns:
    wide.loc[wide["has_pa"] == 0, "potential_assists"] = np.nan  # Bug 27 guard

# ---------------------------------------------------------------------------
# 2. Build comprehensive game_date map (266/266 coverage confirmed)
# ---------------------------------------------------------------------------
print("Building game_date map ...")

date_sources = [
    (BASE / "data" / "cache" / "dnp_features_team.parquet", "game_id", "game_date"),
    (BASE / "data" / "cache" / "pregame_oof.parquet", "game_id", "game_date"),
    (BASE / "data" / "intelligence" / "anomaly_log.parquet", "game_id", "game_date"),
    (BASE / "data" / "player_adv_stats.parquet", "game_id", "game_date"),
    (BASE / "data" / "player_pf.parquet", "game_id", "game_date"),
    (BASE / "data" / "dnp_rows.parquet", "game_id", "game_date"),
]

game_date_map: dict[str, str] = {}
for fpath, gcol, dcol in date_sources:
    try:
        df = pd.read_parquet(fpath, columns=[gcol, dcol])
        df[dcol] = pd.to_datetime(df[dcol]).dt.strftime("%Y-%m-%d")
        for row in df.drop_duplicates(gcol).itertuples(index=False):
            gid = str(getattr(row, gcol))
            if gid not in game_date_map:
                game_date_map[gid] = getattr(row, dcol)
    except Exception as exc:
        print(f"  WARN: could not load {fpath.name}: {exc}")

wide["game_date"] = wide["game_id"].map(game_date_map)
n_missing = wide["game_date"].isna().sum()
total_pg = len(wide)
n_covered_games = wide.dropna(subset=["game_date"])["game_id"].nunique()
print(
    f"Covered {n_covered_games}/266 CV games | "
    f"{total_pg - n_missing}/{total_pg} player-game rows have game_date"
)

wide = wide.dropna(subset=["game_date"]).copy()
wide["game_date"] = pd.to_datetime(wide["game_date"])

# ---------------------------------------------------------------------------
# 3. Derive temporal features
# ---------------------------------------------------------------------------
wide["day_of_week"] = wide["game_date"].dt.dayofweek  # Mon=0 … Sun=6
wide["is_weekend"] = wide["day_of_week"].isin([4, 5, 6]).astype(int)  # Fri/Sat/Sun
wide["month"] = wide["game_date"].dt.month

def month_bucket(m):
    if m in (10, 11, 12):
        return "early"    # Oct–Dec
    elif m in (1, 2):
        return "mid"      # Jan–Feb
    else:
        return "late"     # Mar–Apr+

wide["season_bucket"] = wide["month"].map(month_bucket)

# ---------------------------------------------------------------------------
# 4. Join rest_travel for B2B context (team-level; join on game_id + team)
# ---------------------------------------------------------------------------
print("Joining rest_travel ...")
try:
    rt = pd.read_parquet(BASE / "data" / "rest_travel.parquet",
                         columns=["game_id", "team_abbreviation", "is_b2b"])
    # rest_travel is team-level; we don't have player→team in wide easily
    # so we'll just flag if ANY team in the game was on B2B
    b2b_games = (
        rt.groupby("game_id")["is_b2b"].max().reset_index()
        .rename(columns={"is_b2b": "game_has_b2b"})
    )
    b2b_games["game_id"] = b2b_games["game_id"].astype(str)
    wide = wide.merge(b2b_games, on="game_id", how="left")
    wide["game_has_b2b"] = wide["game_has_b2b"].fillna(0)
except Exception as exc:
    print(f"  WARN rest_travel join failed: {exc}")
    wide["game_has_b2b"] = 0

# ---------------------------------------------------------------------------
# 5. Feature-level analysis — ANOVA + Welch t-test + BH correction
# ---------------------------------------------------------------------------
print("Running DOW ANOVA and weekend/weekday Welch t-tests ...")

DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

anova_rows = []
ttest_rows = []

for feat in cv_feature_cols:
    col = wide[feat].dropna()
    if col.nunique() < 2:
        continue

    # --- DOW ANOVA ---
    groups_by_dow = [
        wide.loc[wide["day_of_week"] == d, feat].dropna().values
        for d in range(7)
    ]
    groups_by_dow = [g for g in groups_by_dow if len(g) >= 3]
    if len(groups_by_dow) >= 3:
        f_stat, p_anova = f_oneway(*groups_by_dow)
    else:
        f_stat, p_anova = np.nan, np.nan

    dow_means = {}
    for d in range(7):
        vals = wide.loc[wide["day_of_week"] == d, feat].dropna()
        dow_means[f"dow_{d}_mean"] = vals.mean() if len(vals) > 0 else np.nan
        dow_means[f"dow_{d}_n"] = len(vals)

    anova_rows.append(
        {"feature_name": feat, "anova_F": f_stat, "anova_p": p_anova, **dow_means}
    )

    # --- Weekend vs Weekday Welch t-test ---
    wknd = wide.loc[wide["is_weekend"] == 1, feat].dropna().values
    wkdy = wide.loc[wide["is_weekend"] == 0, feat].dropna().values
    if len(wknd) >= 3 and len(wkdy) >= 3:
        t_stat, p_t = ttest_ind(wknd, wkdy, equal_var=False)
    else:
        t_stat, p_t = np.nan, np.nan

    ttest_rows.append(
        {
            "feature_name": feat,
            "weekday_mean": float(np.mean(wkdy)) if len(wkdy) > 0 else np.nan,
            "weekend_mean": float(np.mean(wknd)) if len(wknd) > 0 else np.nan,
            "weekday_n": int(len(wkdy)),
            "weekend_n": int(len(wknd)),
            "t_stat": t_stat,
            "p_value": p_t,
            "abs_diff": (
                abs(float(np.mean(wknd)) - float(np.mean(wkdy)))
                if (len(wknd) > 0 and len(wkdy) > 0)
                else np.nan
            ),
        }
    )

dow_df = pd.DataFrame(anova_rows)
ttest_df = pd.DataFrame(ttest_rows)

# --- Benjamini-Hochberg FDR correction ---
def bh_correction(pvals: pd.Series, alpha: float = 0.05) -> pd.Series:
    """Benjamini-Hochberg FDR correction. Returns adjusted p-values."""
    n = len(pvals)
    finite_mask = pvals.notna() & np.isfinite(pvals)
    adj = pvals.copy()
    if finite_mask.sum() == 0:
        return adj
    sorted_idx = np.argsort(pvals[finite_mask].values)
    sorted_pvals = pvals[finite_mask].values[sorted_idx]
    ranks = np.arange(1, len(sorted_pvals) + 1)
    adjusted = np.minimum(1.0, sorted_pvals * n / ranks)
    # Enforce monotone decreasing from right
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adj.iloc[np.where(finite_mask)[0][sorted_idx]] = adjusted
    return adj

dow_df["anova_p_adj"] = bh_correction(dow_df["anova_p"])
ttest_df["p_value_adj"] = bh_correction(ttest_df["p_value"])

# ---------------------------------------------------------------------------
# 6. Per-player analysis — identify players whose CV shifts >1 SD weekend/weekday
# ---------------------------------------------------------------------------
print("Running per-player weekend shift analysis ...")

player_shift_rows = []

for (player_id,), group in wide.groupby(["player_id"]):
    wknd_games = group[group["is_weekend"] == 1]
    wkdy_games = group[group["is_weekend"] == 0]

    if len(wknd_games) < 4 or len(wkdy_games) < 4:
        continue

    # Get player name from cv_features DB if available
    shifts = []
    for feat in cv_feature_cols:
        wknd_vals = wknd_games[feat].dropna()
        wkdy_vals = wkdy_games[feat].dropna()
        if len(wknd_vals) < 2 or len(wkdy_vals) < 2:
            continue
        overall_std = group[feat].dropna().std()
        if overall_std < 1e-6:
            continue
        diff = abs(wknd_vals.mean() - wkdy_vals.mean())
        z_shift = diff / overall_std
        shifts.append({"feature_name": feat, "z_shift": z_shift})

    if not shifts:
        continue

    shifts_df = pd.DataFrame(shifts)
    top_shift = shifts_df.nlargest(1, "z_shift").iloc[0]
    mean_shift_z = shifts_df["z_shift"].mean()
    n_features_shifted = (shifts_df["z_shift"] > 1.0).sum()

    player_shift_rows.append(
        {
            "player_id": player_id,
            "n_weekend": len(wknd_games),
            "n_weekday": len(wkdy_games),
            "top_shift_feature": top_shift["feature_name"],
            "top_shift_z": round(float(top_shift["z_shift"]), 3),
            "mean_shift_z": round(float(mean_shift_z), 3),
            "n_features_gt1sd": int(n_features_shifted),
        }
    )

player_shift_df = pd.DataFrame(player_shift_rows)
player_shift_df = player_shift_df.sort_values("top_shift_z", ascending=False)

# Fetch player names from DB
try:
    conn = sqlite3.connect(DB)
    pnames = pd.read_sql(
        f"""
        SELECT DISTINCT player_id, player_name
        FROM (
            SELECT player_id, NULL as player_name FROM cv_features
        )
        """,
        conn,
    )
    conn.close()
    # Fallback: read from player_cv_per_game parquet (different player_id space)
    # Just use player_id as identifier; names will be enriched separately
except Exception:
    pass

# Try to get player names from cv_features via player IDs in player_positions
try:
    pos_df = pd.read_parquet(BASE / "data" / "player_positions.parquet",
                              columns=["player_id", "display_name"])
    player_shift_df = player_shift_df.merge(pos_df, on="player_id", how="left")
    player_shift_df.rename(columns={"display_name": "player_name"}, inplace=True)
except Exception:
    player_shift_df["player_name"] = player_shift_df["player_id"].astype(str)

# ---------------------------------------------------------------------------
# 7. Save outputs
# ---------------------------------------------------------------------------
print("Saving parquets ...")

# time_of_day_cv.parquet — weekday vs weekend t-test
ttest_out = ttest_df[[
    "feature_name", "weekday_mean", "weekend_mean",
    "weekday_n", "weekend_n", "t_stat", "p_value", "p_value_adj", "abs_diff"
]].sort_values("p_value_adj")
ttest_out.to_parquet(OUT_DIR / "time_of_day_cv.parquet", index=False)
print(f"  Saved time_of_day_cv.parquet ({len(ttest_out)} features)")

# dow_cv_profiles.parquet — DOW means + ANOVA
dow_out = dow_df.sort_values("anova_p_adj")
dow_out.to_parquet(OUT_DIR / "dow_cv_profiles.parquet", index=False)
print(f"  Saved dow_cv_profiles.parquet ({len(dow_out)} features)")

# ---------------------------------------------------------------------------
# 8. Build dow_signals.json
# ---------------------------------------------------------------------------
sig_alpha = 0.05  # BH-corrected threshold

# Top DOW-varying features (by ANOVA, BH-corrected)
top_dow_features = dow_df[
    dow_df["anova_p_adj"] < sig_alpha
].sort_values("anova_F", ascending=False).head(10)

# Top weekend-sensitive features (by t-test abs_diff, with BH correction)
top_wknd_features = ttest_df[
    ttest_df["p_value_adj"] < sig_alpha
].sort_values("abs_diff", ascending=False).head(10)

# Top weekend-sensitive players
top_players = player_shift_df.head(10)

def safe_float(v):
    if pd.isna(v):
        return None
    return round(float(v), 4)

signals = {
    "meta": {
        "n_cv_games_total": int(wide["game_id"].nunique()),
        "n_player_game_rows": int(len(wide)),
        "n_cv_features_analyzed": int(len(cv_feature_cols)),
        "bh_alpha": sig_alpha,
        "n_significant_dow_anova": int((dow_df["anova_p_adj"] < sig_alpha).sum()),
        "n_significant_weekend_ttest": int((ttest_df["p_value_adj"] < sig_alpha).sum()),
    },
    "top_dow_features": [
        {
            "feature_name": row["feature_name"],
            "anova_F": safe_float(row["anova_F"]),
            "anova_p_raw": safe_float(row["anova_p"]),
            "anova_p_adj": safe_float(row["anova_p_adj"]),
            "dow_means": {
                DOW_NAMES[d]: safe_float(row.get(f"dow_{d}_mean"))
                for d in range(7)
            },
        }
        for _, row in top_dow_features.iterrows()
    ],
    "top_weekend_features": [
        {
            "feature_name": row["feature_name"],
            "weekday_mean": safe_float(row["weekday_mean"]),
            "weekend_mean": safe_float(row["weekend_mean"]),
            "diff_pct": safe_float(
                (row["weekend_mean"] - row["weekday_mean"]) / abs(row["weekday_mean"]) * 100
                if row["weekday_mean"] and abs(row["weekday_mean"]) > 1e-9
                else None
            ),
            "t_stat": safe_float(row["t_stat"]),
            "p_value_adj": safe_float(row["p_value_adj"]),
        }
        for _, row in top_wknd_features.iterrows()
    ],
    "top_weekend_sensitive_players": [
        {
            "player_id": int(row["player_id"]),
            "player_name": str(row.get("player_name", row["player_id"])),
            "n_weekend": int(row["n_weekend"]),
            "n_weekday": int(row["n_weekday"]),
            "top_shift_feature": str(row["top_shift_feature"]),
            "top_shift_z": safe_float(row["top_shift_z"]),
            "mean_shift_z": safe_float(row["mean_shift_z"]),
            "n_features_gt1sd": int(row["n_features_gt1sd"]),
        }
        for _, row in top_players.iterrows()
    ],
}

signals_path = OUT_DIR / "dow_signals.json"
with open(signals_path, "w") as f:
    json.dump(signals, f, indent=2)
print(f"  Saved dow_signals.json")

# ---------------------------------------------------------------------------
# 9. Print diagnostic summary
# ---------------------------------------------------------------------------
print("\n=== INT-46 DOW Analysis Summary ===")
print(f"CV games with date: {wide['game_id'].nunique()}/266")
print(f"Player-game rows analyzed: {len(wide)}")
print()
print(f"DOW ANOVA significant features (BH p<0.05): {signals['meta']['n_significant_dow_anova']}")
if not top_dow_features.empty:
    for _, row in top_dow_features.head(5).iterrows():
        print(f"  {row['feature_name']}: F={row['anova_F']:.2f}, p_adj={row['anova_p_adj']:.4f}")
print()
print(f"Weekend/Weekday t-test significant (BH p<0.05): {signals['meta']['n_significant_weekend_ttest']}")
if not top_wknd_features.empty:
    for _, row in top_wknd_features.head(5).iterrows():
        wkdy_m = row["weekday_mean"]
        wknd_m = row["weekend_mean"]
        print(
            f"  {row['feature_name']}: weekday={wkdy_m:.3f}, weekend={wknd_m:.3f}, "
            f"p_adj={row['p_value_adj']:.4f}"
        )
print()
print("Top weekend-sensitive players:")
for _, row in player_shift_df.head(5).iterrows():
    name = row.get("player_name", row["player_id"])
    print(
        f"  {name}: top_z={row['top_shift_z']:.2f} ({row['top_shift_feature']}), "
        f"n_wknd={row['n_weekend']}, n_wkdy={row['n_weekday']}"
    )

# ---------------------------------------------------------------------------
# 10. Write vault atlas
# ---------------------------------------------------------------------------
n_sig_anova = signals["meta"]["n_significant_dow_anova"]
n_sig_ttest = signals["meta"]["n_significant_weekend_ttest"]

top3_anova_text = ""
for i, item in enumerate(signals["top_dow_features"][:3], 1):
    dm = item["dow_means"]
    mn = min(dm.values(), key=lambda v: v if v is not None else 999)
    mx = max(dm.values(), key=lambda v: v if v is not None else -999)
    mn_day = [k for k, v in dm.items() if v == mn][0]
    mx_day = [k for k, v in dm.items() if v == mx][0]
    top3_anova_text += (
        f"{i}. **{item['feature_name']}** — F={item['anova_F']:.2f}, "
        f"BH p={item['anova_p_adj']:.4f}. "
        f"Peaks {mx_day} (mean={mx:.3f}), troughs {mn_day} (mean={mn:.3f}).\n"
    )

top3_wknd_text = ""
for i, item in enumerate(signals["top_weekend_features"][:3], 1):
    dir_str = "HIGHER on weekends" if item["weekend_mean"] > item["weekday_mean"] else "LOWER on weekends"
    diff_pct = f"{item['diff_pct']:+.1f}%" if item["diff_pct"] is not None else "N/A"
    top3_wknd_text += (
        f"{i}. **{item['feature_name']}** — {dir_str} ({diff_pct}), "
        f"weekday={item['weekday_mean']:.3f}, weekend={item['weekend_mean']:.3f}, "
        f"BH p={item['p_value_adj']:.4f}.\n"
    )

top5_player_text = ""
for i, item in enumerate(signals["top_weekend_sensitive_players"][:5], 1):
    top5_player_text += (
        f"{i}. **{item['player_name']}** (ID {item['player_id']}) — "
        f"top shift z={item['top_shift_z']:.2f} on `{item['top_shift_feature']}`, "
        f"{item['n_features_gt1sd']} features >1 SD shift, "
        f"n_wknd={item['n_weekend']}, n_wkdy={item['n_weekday']}.\n"
    )

# DOW distribution table
dow_dist = wide["day_of_week"].value_counts().sort_index()
dow_table_lines = ["| DOW | Name | N player-games |", "|---|---|---|"]
for d, n in dow_dist.items():
    dow_table_lines.append(f"| {d} | {DOW_NAMES[d]} | {n} |")
dow_table = "\n".join(dow_table_lines)

atlas_md = f"""---
atlas: INT-46
title: Time-of-Day / Day-of-Week CV Patterns
created: 2026-05-28
updated: 2026-05-28
tags: [intelligence, cv-features, temporal, day-of-week, weekend, b2b]
sources:
  - data/nba_ai.db cv_features (266 games, 32,027 rows)
  - data/cache/dnp_features_team.parquet (primary date source)
  - data/rest_travel.parquet (B2B context)
outputs:
  - data/intelligence/time_of_day_cv.parquet
  - data/intelligence/dow_cv_profiles.parquet
  - data/intelligence/dow_signals.json
---

# INT-46: Time-of-Day / Day-of-Week CV Patterns

## Coverage

- **CV games with game_date resolved:** {wide["game_id"].nunique()}/266 ({wide["game_id"].nunique()/266*100:.0f}%)
- **Player-game rows analyzed:** {len(wide):,}
- **CV features tested:** {len(cv_feature_cols)} (numeric; `cv_archetype` and `cv_xast_pred` excluded)
- **Tip-time data available:** No — `scoreboard_log` has 0 rows. Afternoon vs evening analysis skipped; DOW analysis only.
- **Primary date source:** `cache/dnp_features_team.parquet` (covers full 2025-26 season through 2026-04-06)

### Game distribution by day of week

{dow_table}

Weekend = Fri/Sat/Sun. Weekday = Mon–Thu.

---

## Headline Results

### DOW ANOVA (is there any intra-week variation?)

- **{n_sig_anova} of {len(cv_feature_cols)} features** show statistically significant DOW variation after Benjamini-Hochberg FDR correction (alpha=0.05).

### Top 3 DOW-varying features

{top3_anova_text if top3_anova_text.strip() else "None passed BH correction."}

### Weekend vs Weekday Welch t-test

- **{n_sig_ttest} of {len(cv_feature_cols)} features** differ significantly between weekend and weekday games (BH-corrected).

### Top 3 weekend-sensitive features

{top3_wknd_text if top3_wknd_text.strip() else "None passed BH correction."}

---

## Per-Player Weekend Sensitivity

Players with `n_weekend >= 4` AND `n_weekday >= 4` were analyzed for CV feature shifts. Top players ordered by maximum feature z-shift between weekend and weekday contexts:

{top5_player_text if top5_player_text.strip() else "No players met the n>=4 threshold in both contexts."}

---

## Confound: DOW effects likely mediated by rest days

Day-of-week is not independent of rest. In the NBA:
- Saturday and Sunday games frequently follow Friday games (B2B second nights)
- Monday games frequently follow Sunday (back-to-back)
- Wednesday/Thursday games tend to have more rest days preceding them

Cross-referencing `rest_travel.parquet`:
- Games in this dataset with at least one B2B team: check `game_has_b2b` column in wide output
- Any DOW effect that disappears after controlling for `is_b2b` is **rest-mediated**, not schedule-structural

Recommended disentanglement: run the same ANOVA/t-test stratified by `is_b2b = 0` only. If DOW effects survive in the non-B2B subset, they reflect true schedule differences (crowd energy, broadcast time, travel cadence). If they evaporate, B2B is the driver.

---

## Implication for Prop Prediction

| Finding | Betting angle |
|---|---|
| Weekend feature elevation | If a player's key CV signal (e.g., `paint_dwell_pct`) is consistently higher on weekends, use that as a situational boosting factor for FRI/SAT/SUN props |
| Top-shift players | Players with large weekend z-shifts are good targets for DOW-conditional adjustments: add a `dow_boost_factor` to their expected pace/paint-time stats on weekend starts |
| No significant effects | Null result is also informative: CV behaviors are stable across the week after BH correction. This reduces concern that day-of-week is a confound in cross-game aggregations |

**Suggested implementation:** Add `day_of_week` and `is_weekend` as features in `build_pergame_dataset.py`. Given the high cross-season scale inconsistency (Bug 9), first verify that any DOW effect is present in BOTH 2024-25 and 2025-26 subsets before wiring into the prop model.

---

## Caveats

1. **Tip time unavailable** — `scoreboard_log` is empty. The afternoon vs evening analysis (matinee vs prime-time) cannot be done without fetching tip times from NBA API.
2. **Bug 9 (cross-season scale)** — 15/27 CV features have population-mean ratios >1.9x between 2024-25 and 2025-26 games. DOW patterns may reflect season-level differences (e.g., more 2025-26 games on certain days) rather than true temporal effects. Rerun analysis season-stratified to validate.
3. **Small sample per DOW cell** — with 266 games and 7 days, average ~38 games/DOW. After per-player split (n>=4 threshold), many players have borderline sample sizes.
4. **B2B confound** — as noted above; recommend stratified rerun.
5. **No tip time** — "afternoon vs evening" half of INT-46 question is unanswerable with current data. File: `scripts/fetch_scoreboard_tip_times.py` would be needed to fill `scoreboard_log`.

---

## Files

- `data/intelligence/time_of_day_cv.parquet` — weekend vs weekday t-test results per feature
- `data/intelligence/dow_cv_profiles.parquet` — DOW mean profiles + ANOVA per feature
- `data/intelligence/dow_signals.json` — top 10 DOW features, top 10 weekend features, top 10 weekend-sensitive players
- `scripts/build_time_of_day_cv.py` — reproducible build script

---

*Generated by INT-46 build (2026-05-28)*
"""

atlas_path = VAULT_DIR / "Time_Of_Day_CV_Atlas.md"
with open(atlas_path, "w", encoding="utf-8") as f:
    f.write(atlas_md)
print(f"\nVault atlas saved: {atlas_path}")
print("INT-46 build complete.")
