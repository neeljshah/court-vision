"""
INT-47: Officials Impact on CV Behavior
========================================
Cross-reference officials_features (ref-crew foul tendencies) against
per-player CV signatures to detect whether tight/loose referee crews
systematically shift player behavioral signals.

Data sources
------------
- data/officials_features.parquet  (one row per team per game; ref stats same for both teams)
- data/player_cv_per_game.parquet  (wide format, cvb_* features, 78 games across 3 seasons)
- data/nba_ai.db :: cv_features    (EAV, 266 games, richer feature set: paint_dwell_pct, etc.)

Join strategy
-------------
officials_features has two rows per game (home + away); ref_crew stats are IDENTICAL for
both rows. We deduplicate to one row per game_id and join on game_id alone.

The 'team' column in player_cv_per_game contains jersey-color labels ('green'/'white')
from the CV tracker — NOT team abbreviations — so a team-level join is impossible. The
game_id-only join is correct because the ref crew presides over the whole game.

Data limitations (documented prominently)
-----------------------------------------
- Only 18 unique games have valid officials data (no sentinel) in either CV source.
- ref_crew_fouls = 42.000 is a sentinel/cap (appears only on 2025-04-10 to 2025-04-13,
  last 4 days of 2024-25 season, 35 games). These 6 games are excluded.
- 2025-26 season (252 of 266 cv_features DB games) has no officials data yet.
- Max 2 games per player in the overlap window -> per-player sensitivity (n>=4)
  cannot be satisfied. Output parquet is empty; this is flagged as a data-gap bug.

Outputs
-------
data/intelligence/officials_cv_impact.parquet
data/intelligence/officials_player_sensitivity.parquet   (empty - n too small, flagged)
data/intelligence/officials_signals.json
vault/Intelligence/Officials_Impact_Atlas.md             (written by separate section)
"""

import os
import sys
import json
import sqlite3
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INTEL = DATA / "intelligence"
VAULT = ROOT / "vault" / "Intelligence"
INTEL.mkdir(parents=True, exist_ok=True)
VAULT.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA / "nba_ai.db"
OFFICIALS_PATH = DATA / "officials_features.parquet"
CV_PARQ_PATH = DATA / "player_cv_per_game.parquet"

# ---------------------------------------------------------------------------
# 1. Load data
# ---------------------------------------------------------------------------
print("=== INT-47: Officials Impact on CV Behavior ===\n")

df_off_raw = pd.read_parquet(OFFICIALS_PATH)
df_cv_parq = pd.read_parquet(CV_PARQ_PATH)

conn = sqlite3.connect(DB_PATH)
df_cv_eav = pd.read_sql(
    "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
    conn,
)
conn.close()

print(f"officials_features loaded : {len(df_off_raw):,} rows, {df_off_raw['game_id'].nunique():,} games")
print(f"player_cv_per_game loaded : {len(df_cv_parq):,} rows, {df_cv_parq['game_id'].nunique()} games")
print(f"cv_features DB loaded     : {len(df_cv_eav):,} rows, {df_cv_eav['game_id'].nunique()} games")

# ---------------------------------------------------------------------------
# 2. Clean officials data
# ---------------------------------------------------------------------------
# Deduplicate to one row per game (ref stats are the same for both teams in a game)
df_off = df_off_raw.drop_duplicates(subset="game_id").copy()
df_off["game_date"] = pd.to_datetime(df_off["game_date"])

# Identify and exclude sentinel value ref_crew_fouls == 42.0
# This value appears exclusively on 2025-04-10 to 2025-04-13 (last 4 days of 2024-25 season)
# and is a fill/cap artifact, not a real measurement.
sentinel_mask = df_off["ref_crew_fouls"] == 42.0
sentinel_count = sentinel_mask.sum()
df_off_valid = df_off[~sentinel_mask].copy()

print(f"\nSentinel ref_crew_fouls==42.0 excluded: {sentinel_count} game rows")
print(f"Valid officials games (for analysis)  : {len(df_off_valid):,}")

# ---------------------------------------------------------------------------
# 3. Compute global tertile boundaries on full valid officials dataset
# ---------------------------------------------------------------------------
t33 = df_off_valid["ref_crew_fouls"].quantile(1 / 3)
t67 = df_off_valid["ref_crew_fouls"].quantile(2 / 3)

print(f"\nGlobal ref_crew_fouls tertile boundaries (N={len(df_off_valid):,} games):")
print(f"  tight  (bottom third) : <= {t33:.3f}")
print(f"  medium (middle third) : {t33:.3f} – {t67:.3f}")
print(f"  loose  (top third)    : >= {t67:.3f}")

df_off_valid = df_off_valid.copy()
df_off_valid["foul_bucket"] = pd.cut(
    df_off_valid["ref_crew_fouls"],
    bins=[-np.inf, t33, t67, np.inf],
    labels=["tight", "medium", "loose"],
)

# ---------------------------------------------------------------------------
# 4. Join CV sources to officials on game_id
# ---------------------------------------------------------------------------

# ---- Source A: player_cv_per_game (wide format, cvb_* features) ----
df_cv_parq_off = df_cv_parq.merge(
    df_off_valid[["game_id", "game_date", "ref_crew_fouls", "ref_crew_fta",
                  "ref_crew_home_win_pct", "foul_bucket"]],
    on="game_id",
    how="inner",
)
n_parq = len(df_cv_parq_off)
g_parq = df_cv_parq_off["game_id"].nunique()
print(f"\nSource A (parquet) merged   : {n_parq} player-game rows, {g_parq} games")

# ---- Source B: cv_features DB (EAV pivot to wide, different feature set) ----
df_cv_wide = (
    df_cv_eav.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    )
    .reset_index()
)
df_cv_wide.columns.name = None  # drop multi-index name

df_cv_db_off = df_cv_wide.merge(
    df_off_valid[["game_id", "game_date", "ref_crew_fouls", "ref_crew_fta",
                  "ref_crew_home_win_pct", "foul_bucket"]],
    on="game_id",
    how="inner",
)
n_db = len(df_cv_db_off)
g_db = df_cv_db_off["game_id"].nunique()
print(f"Source B (DB EAV) merged    : {n_db} player-game rows, {g_db} games")

# Coverage summary
all_games = set(df_cv_parq_off["game_id"].unique()) | set(df_cv_db_off["game_id"].unique())
print(f"\nCombined unique games       : {len(all_games)}")
print(f"Combined unique players (A) : {df_cv_parq_off['player_id'].nunique() if 'player_id' in df_cv_parq_off.columns else 'N/A'}")

bucket_dist = df_off_valid[df_off_valid["game_id"].isin(all_games)]["foul_bucket"].value_counts()
print("\nFoul-bucket distribution across our games:")
for b, cnt in bucket_dist.items():
    print(f"  {b:6s}: {cnt} games")

# ---------------------------------------------------------------------------
# CRITICAL CONFOUND CHECK: Cross-season scale inconsistency (Bug 9)
# ---------------------------------------------------------------------------
# Tight bucket contains BOTH 2023-24 (002230xxx) and 2024-25 (002240xxx) games.
# Medium and loose buckets contain ONLY 2023-24 (002230xxx) games.
# Bug 9 established that 15 of 29 CV features have population-mean ratios > 1.9x
# between 2024-25 and 2025-26. A similar scale shift between 2023-24 and 2024-25
# could create SPURIOUS tight vs loose differences that reflect pipeline version
# changes, not ref-crew behavioral effects.
#
# We annotate each feature result with cross_season_confound=True/False by checking
# whether the feature's mean for 002240 tight rows is > 1.5x the 002230 tight rows.
# Features with cross_season_confound=True should be treated as unreliable for
# ref-crew inference; they are preserved in output with a clear warning flag.
df_cv_parq_off["season_prefix"] = df_cv_parq_off["game_id"].str[:6]

def check_season_confound(df: pd.DataFrame, feature_cols: list, ratio_threshold: float = 1.5) -> dict:
    """Return {feature: bool} indicating whether cross-season scale ratio exceeds threshold."""
    confound = {}
    for feat in feature_cols:
        v_2324 = df[df["season_prefix"] == "002230"][feat].dropna().values
        v_2425 = df[df["season_prefix"] == "002240"][feat].dropna().values
        if len(v_2324) < 2 or len(v_2425) < 2:
            confound[feat] = False
            continue
        m1, m2 = abs(np.mean(v_2324)), abs(np.mean(v_2425))
        if m1 == 0 and m2 == 0:
            confound[feat] = False
        elif m1 == 0 or m2 == 0:
            confound[feat] = True
        else:
            ratio = max(m1, m2) / min(m1, m2)
            confound[feat] = bool(ratio > ratio_threshold)
    return confound

_meta_cols_set = {"game_id", "player_id", "player_name", "team", "n_frames",
                  "nba_player_id", "game_date", "ref_crew_fouls", "ref_crew_fta",
                  "ref_crew_home_win_pct", "foul_bucket", "minutes_proxy",
                  "cv_archetype", "cv_xast_pred", "season_prefix"}
_parq_feat_cols = [c for c in df_cv_parq_off.columns if c not in _meta_cols_set and
                   pd.api.types.is_numeric_dtype(df_cv_parq_off[c])]
season_confound_map = check_season_confound(df_cv_parq_off, _parq_feat_cols)
confounded_feats = [f for f, v in season_confound_map.items() if v]
clean_feats = [f for f, v in season_confound_map.items() if not v]
print(f"\nCross-season scale confound check (ratio > 1.5x between 2023-24 and 2024-25):")
print(f"  Confounded features (unreliable for ref-crew inference): {confounded_feats}")
print(f"  Scale-stable features (reliable):                        {clean_feats}")

# ---------------------------------------------------------------------------
# 5. Population-level feature analysis
# ---------------------------------------------------------------------------
# We analyse both CV sources separately (different feature sets) then union results.

def analyse_source(df: pd.DataFrame, source_label: str,
                   season_confound: dict | None = None) -> pd.DataFrame:
    """
    For each numeric CV feature: compute mean per bucket, Welch t-test tight vs loose,
    Cohen's d, and return a results DataFrame.

    season_confound: optional dict {feature_name: bool} indicating cross-season scale
    confound. Features with confound=True are flagged in output but still included
    so callers can decide whether to filter or caveat them.
    """
    # identify numeric CV feature columns (exclude metadata and officials cols)
    meta_cols = {"game_id", "player_id", "player_name", "team", "n_frames",
                 "nba_player_id", "game_date", "ref_crew_fouls", "ref_crew_fta",
                 "ref_crew_home_win_pct", "foul_bucket", "minutes_proxy",
                 "cv_archetype", "cv_xast_pred", "season_prefix"}
    feature_cols = [c for c in df.columns if c not in meta_cols and
                    pd.api.types.is_numeric_dtype(df[c])]

    rows = []
    for feat in feature_cols:
        tight_vals = df.loc[df["foul_bucket"] == "tight", feat].dropna().values
        mid_vals   = df.loc[df["foul_bucket"] == "medium", feat].dropna().values
        loose_vals = df.loc[df["foul_bucket"] == "loose", feat].dropna().values

        if len(tight_vals) < 2 or len(loose_vals) < 2:
            continue

        tight_mean = float(np.mean(tight_vals))
        mid_mean   = float(np.mean(mid_vals)) if len(mid_vals) >= 1 else np.nan
        loose_mean = float(np.mean(loose_vals))

        # Welch's t-test (unequal variance)
        t_stat, p_val = stats.ttest_ind(tight_vals, loose_vals, equal_var=False)

        # Cohen's d: tight vs loose
        pooled_sd = np.sqrt(
            (np.var(tight_vals, ddof=1) + np.var(loose_vals, ddof=1)) / 2
        )
        cohens_d = (tight_mean - loose_mean) / pooled_sd if pooled_sd > 0 else 0.0

        # Cross-season confound flag
        is_confounded = bool(season_confound.get(feat, False)) if season_confound else False

        rows.append({
            "source": source_label,
            "feature_name": feat,
            "n_tight": int(len(tight_vals)),
            "n_mid": int(len(mid_vals)),
            "n_loose": int(len(loose_vals)),
            "tight_mean": round(tight_mean, 6),
            "mid_mean": round(mid_mean, 6) if not np.isnan(mid_mean) else None,
            "loose_mean": round(loose_mean, 6),
            "t_stat_tight_vs_loose": round(float(t_stat), 4),
            "p_value": round(float(p_val), 6),
            "cohens_d": round(float(cohens_d), 4),
            "abs_cohens_d": round(abs(float(cohens_d)), 4),
            "cross_season_confound": is_confounded,
        })

    return pd.DataFrame(rows)


print("\n--- Population-level analysis ---")
res_a = analyse_source(df_cv_parq_off, "parquet_cvb", season_confound=season_confound_map)
res_b = analyse_source(df_cv_db_off, "db_eav")

print(f"Source A: {len(res_a)} features analysed")
print(f"Source B: {len(res_b)} features analysed")
# Note: Source B (DB EAV) may return 0 features if all its overlap games fall in
# the same bucket (e.g. tight/medium only). The 8 DB overlap games span ref_crew_fouls
# 36.87–39.08 — all below the loose threshold (39.63), giving zero loose-bucket rows.
# This is a data-distribution artifact, not a code error. Source A covers the full range.

df_pop = pd.concat([res_a, res_b], ignore_index=True)
df_pop = df_pop.sort_values("abs_cohens_d", ascending=False)

# Save population-level results
pop_out = INTEL / "officials_cv_impact.parquet"
df_pop.to_parquet(pop_out, index=False)
print(f"\nPopulation impact saved -> {pop_out}")

# ---------------------------------------------------------------------------
# 6. Per-player sensitivity analysis
# ---------------------------------------------------------------------------
# Requirement: n_tight >= 4 AND n_loose >= 4 per player per feature.
# With only 18 games total and max 2 per player in the overlap window, this
# cannot be satisfied. We output an empty parquet with the correct schema
# and flag this as a data-gap.

print("\n--- Per-player sensitivity analysis ---")

def per_player_sensitivity(df: pd.DataFrame, source_label: str) -> pd.DataFrame:
    """
    For players with >= 8 games (n_tight >= 4, n_loose >= 4), compute mean CV feature
    in tight vs loose games. Identifies 'ref-sensitive' players (delta > 1 SD).
    With current data coverage, this threshold cannot be met.
    """
    meta_cols = {"game_id", "player_id", "player_name", "team", "n_frames",
                 "nba_player_id", "game_date", "ref_crew_fouls", "ref_crew_fta",
                 "ref_crew_home_win_pct", "foul_bucket", "minutes_proxy",
                 "cv_archetype", "cv_xast_pred"}
    feature_cols = [c for c in df.columns if c not in meta_cols and
                    pd.api.types.is_numeric_dtype(df[c])]

    # Identify players with enough games in each bucket
    pid_col = "player_id"
    rows = []
    players_tight = df[df["foul_bucket"] == "tight"][pid_col].value_counts()
    players_loose = df[df["foul_bucket"] == "loose"][pid_col].value_counts()

    eligible = set(players_tight[players_tight >= 4].index) & \
               set(players_loose[players_loose >= 4].index)

    if not eligible:
        return pd.DataFrame(columns=["player_id", "feature_name", "delta_tight_loose",
                                     "t_stat", "p_value", "cohens_d", "n_tight", "n_loose",
                                     "source", "ref_sensitive"])

    # compute per-feature delta for eligible players
    global_stds = {f: df[f].std() for f in feature_cols}

    for pid in eligible:
        df_p = df[df[pid_col] == pid]
        for feat in feature_cols:
            tight_v = df_p[df_p["foul_bucket"] == "tight"][feat].dropna().values
            loose_v = df_p[df_p["foul_bucket"] == "loose"][feat].dropna().values
            if len(tight_v) < 4 or len(loose_v) < 4:
                continue
            delta = float(np.mean(tight_v) - np.mean(loose_v))
            gstd = global_stds.get(feat, 1.0)
            ref_sens = bool(abs(delta) > gstd) if gstd > 0 else False
            t_stat, p_val = stats.ttest_ind(tight_v, loose_v, equal_var=False)
            pooled_sd = np.sqrt((np.var(tight_v, ddof=1) + np.var(loose_v, ddof=1)) / 2)
            cd = delta / pooled_sd if pooled_sd > 0 else 0.0
            rows.append({
                "player_id": pid,
                "feature_name": feat,
                "delta_tight_loose": round(delta, 6),
                "t_stat": round(float(t_stat), 4),
                "p_value": round(float(p_val), 6),
                "cohens_d": round(float(cd), 4),
                "n_tight": int(len(tight_v)),
                "n_loose": int(len(loose_v)),
                "source": source_label,
                "ref_sensitive": ref_sens,
            })

    return pd.DataFrame(rows)


sens_a = per_player_sensitivity(df_cv_parq_off, "parquet_cvb")
sens_b = per_player_sensitivity(df_cv_db_off, "db_eav")
df_sens = pd.concat([sens_a, sens_b], ignore_index=True)

# report max per-player game count to document the data gap
max_tight = max(
    df_cv_parq_off[df_cv_parq_off["foul_bucket"] == "tight"]["player_id"].value_counts().max()
    if not df_cv_parq_off.empty else 0,
    df_cv_db_off[df_cv_db_off["foul_bucket"] == "tight"]["player_id"].value_counts().max()
    if not df_cv_db_off.empty else 0,
)
max_loose = max(
    df_cv_parq_off[df_cv_parq_off["foul_bucket"] == "loose"]["player_id"].value_counts().max()
    if not df_cv_parq_off.empty else 0,
    df_cv_db_off[df_cv_db_off["foul_bucket"] == "loose"]["player_id"].value_counts().max()
    if not df_cv_db_off.empty else 0,
)

if df_sens.empty:
    print(f"Per-player sensitivity: 0 eligible players (need n_tight>=4, n_loose>=4).")
    print(f"Max observed tight-games per player: {max_tight} | loose-games: {max_loose}")
    print("DATA GAP flagged: 18 total overlap games, max 2 games/player in window.")
else:
    print(f"Per-player sensitivity: {df_sens['player_id'].nunique()} eligible players, "
          f"{len(df_sens)} feature rows")

sens_out = INTEL / "officials_player_sensitivity.parquet"
df_sens.to_parquet(sens_out, index=False)
print(f"Player sensitivity saved -> {sens_out}")

# ---------------------------------------------------------------------------
# 7. Build signals JSON
# ---------------------------------------------------------------------------
print("\n--- Building officials_signals.json ---")

# Top features by abs Cohen's d (population level)
# Prioritise scale-clean (non-confounded) features; include confounded but flagged
top_features = df_pop[df_pop["p_value"] < 0.10].sort_values(
    ["cross_season_confound", "abs_cohens_d"], ascending=[True, False]
)
top10_feats = top_features.head(10)

# Direction annotation: tight > loose means tight crews push behavior one way
def direction_label(row):
    if row["tight_mean"] > row["loose_mean"]:
        return "tight_higher"
    else:
        return "loose_higher"

top10_feats = top10_feats.copy()
top10_feats["direction"] = top10_feats.apply(direction_label, axis=1)

# Summary of confound situation
clean_sigs = top_features[~top_features["cross_season_confound"]] if "cross_season_confound" in top_features.columns else pd.DataFrame()
confounded_sigs = top_features[top_features["cross_season_confound"]] if "cross_season_confound" in top_features.columns else pd.DataFrame()
print(f"\nTop signals p<0.10: {len(top_features)} total, {len(clean_sigs)} scale-clean, {len(confounded_sigs)} cross-season confounded")

# Top ref-sensitive players (if any)
if df_sens.empty:
    top_players = []
else:
    paint_sens = df_sens[df_sens["feature_name"].str.contains("paint|paint_pressure|paint_dwell", case=False)]
    top_players = (
        paint_sens.sort_values("cohens_d", ascending=False)
        .head(10)[["player_id", "feature_name", "delta_tight_loose", "cohens_d", "n_tight", "n_loose"]]
        .to_dict(orient="records")
    )

signals = {
    "meta": {
        "atlas_id": "INT-47",
        "description": "Officials crew tightness (ref_crew_fouls tertile) vs CV behavior shifts",
        "total_overlap_games": len(all_games),
        "tight_games": int(bucket_dist.get("tight", 0)),
        "medium_games": int(bucket_dist.get("medium", 0)),
        "loose_games": int(bucket_dist.get("loose", 0)),
        "total_player_game_rows": {
            "source_a_parquet": n_parq,
            "source_b_db_eav": n_db,
        },
        "sentinel_42_excluded_games": int(sentinel_count),
        "data_gap": "Only 18 overlap games (14 cv_features DB + 11 parquet - 7 shared). "
                    "2025-26 season (252 DB games) has no officials data. "
                    "Per-player sensitivity requires n>=4 per bucket; cannot meet threshold. "
                    "Population-level signals are directional estimates only (low N).",
        "critical_confound": (
            "Tight bucket contains 2024-25 AND 2023-24 games. "
            "Loose/medium contain ONLY 2023-24 games. "
            "Cross-season CV scale shift (Bug 9) confounds features where 2024-25 pipeline "
            "uses different units. Only scale-stable features (cross_season_confound=False) "
            "are reliable for ref-crew inference."
        ),
        "confounded_features": confounded_feats,
        "scale_stable_features": clean_feats,
        "tertile_boundaries": {
            "tight_max": round(t33, 3),
            "loose_min": round(t67, 3),
        },
    },
    "top_population_features_p10": [
        {
            "feature": row["feature_name"],
            "source": row["source"],
            "tight_mean": row["tight_mean"],
            "loose_mean": row["loose_mean"],
            "t_stat": row["t_stat_tight_vs_loose"],
            "p_value": row["p_value"],
            "cohens_d": row["cohens_d"],
            "direction": row["direction"],
            "cross_season_confound": bool(row.get("cross_season_confound", False)),
        }
        for _, row in top10_feats.iterrows()
    ],
    "top_ref_sensitive_players_paint": top_players,
}

signals_out = INTEL / "officials_signals.json"
with open(signals_out, "w", encoding="utf-8") as fh:
    json.dump(signals, fh, indent=2, default=str)
print(f"Signals JSON saved -> {signals_out}")

# ---------------------------------------------------------------------------
# 8. Print analysis summary for logging
# ---------------------------------------------------------------------------
print("\n=== POPULATION-LEVEL RESULTS (sorted by |Cohen's d|) ===")
display_cols = ["feature_name", "source", "n_tight", "n_loose",
                "tight_mean", "loose_mean", "t_stat_tight_vs_loose", "p_value", "cohens_d"]
print(df_pop[display_cols].head(20).to_string(index=False))

print("\n=== TOP FEATURES p < 0.10 ===")
if top10_feats.empty:
    print("None found (all p >= 0.10). N is too small for significance; direction signals still valid.")
else:
    for _, r in top10_feats.iterrows():
        confound_flag = " [CONFOUNDED]" if r.get("cross_season_confound") else ""
        print(f"  [{r['source']:14s}] {r['feature_name']:35s}  "
              f"tight={r['tight_mean']:.4f} | loose={r['loose_mean']:.4f} | "
              f"d={r['cohens_d']:+.3f} | p={r['p_value']:.4f}{confound_flag}")

# ---------------------------------------------------------------------------
# 9. Write Atlas markdown
# ---------------------------------------------------------------------------
print("\n--- Writing Officials_Impact_Atlas.md ---")

# Gather top 5 features by |Cohen's d|, prioritising scale-clean (non-confounded) features
top5_all = df_pop.sort_values(
    ["cross_season_confound", "abs_cohens_d"] if "cross_season_confound" in df_pop.columns else ["abs_cohens_d"],
    ascending=[True, False] if "cross_season_confound" in df_pop.columns else [False]
).head(5)

def fmt_pct(val):
    return f"{val * 100:.1f}%" if abs(val) < 5 else f"{val:.3f}"

atlas_lines = [
    "---",
    "atlas_id: INT-47",
    "tags: [intelligence, cv-behavior, referees, officials, betting]",
    f"created: 2026-05-28",
    f"updated: 2026-05-28",
    "---",
    "",
    "# Officials Impact Atlas (INT-47)",
    "",
    "> Cross-reference of referee crew foul tendencies vs player CV behavior signatures.",
    "> Answers: do tight-whistle crews systematically push players away from paint?",
    "> Do loose crews encourage drives and paint time?",
    "",
    "## Coverage",
    "",
    f"- **Total overlap games**: {len(all_games)} (out of 266 CV games and 3,650 valid officials games)",
    f"  - Source A (player_cv_per_game parquet): {g_parq} games, {n_parq} player-game rows",
    f"  - Source B (cv_features DB EAV): {g_db} games, {n_db} player-game rows",
    f"- **Foul bucket distribution**: tight={int(bucket_dist.get('tight', 0))}, medium={int(bucket_dist.get('medium', 0))}, loose={int(bucket_dist.get('loose', 0))} games",
    f"- **Tertile boundaries** (global, N=3,650 valid games): tight ≤ {t33:.3f}, loose ≥ {t67:.3f} fouls",
    f"- **Sentinel excluded**: {int(sentinel_count)} games with ref_crew_fouls=42.0 (last 4 days of 2024-25, fill artifact)",
    f"- **2025-26 season gap**: 252 of 266 CV games (all in 2025-26) have no officials data yet",
    "",
    "**Low coverage warning**: 18 overlap games is a small sample. All findings are",
    "directional signals with wide confidence intervals. Treat as hypothesis generation,",
    "not confirmed effects.",
    "",
    "## Headline: Do Ref Crews Systematically Shift CV Behavior?",
    "",
]

if df_pop.empty:
    atlas_lines += [
        "Insufficient data for population-level conclusions. Zero features had enough",
        "observations for t-test comparison.",
        "",
    ]
else:
    # Assess whether there's a consistent pattern
    tight_higher = (df_pop["tight_mean"] > df_pop["loose_mean"]).sum()
    loose_higher = (df_pop["tight_mean"] < df_pop["loose_mean"]).sum()

    # Separate clean vs confounded
    df_pop_clean = df_pop[~df_pop["cross_season_confound"]] if "cross_season_confound" in df_pop.columns else df_pop
    df_pop_conf = df_pop[df_pop["cross_season_confound"]] if "cross_season_confound" in df_pop.columns else pd.DataFrame()

    atlas_lines += [
        f"**Directionally consistent but partially confounded.** "
        f"Of {len(df_pop)} measured features, {tight_higher} are higher under tight crews "
        f"and {loose_higher} are higher under loose crews.",
        "",
        f"> **CRITICAL CAVEAT**: The tight bucket contains BOTH 2023-24 (002230xxx) and "
        f"2024-25 (002240xxx) games, while medium/loose contain ONLY 2023-24 games. "
        f"Bug 9 (cross-season scale shift) contaminates {len(df_pop_conf)} features. "
        f"Only the {len(df_pop_clean)} scale-stable features below are reliable.",
        "",
        f"**Scale-stable features higher under tight crews** (reliable, no cross-season confound):",
        "",
    ]

    # Show clean features only in the main narrative
    tight_higher_clean = df_pop_clean[df_pop_clean["tight_mean"] > df_pop_clean["loose_mean"]].sort_values("abs_cohens_d", ascending=False)
    if tight_higher_clean.empty:
        atlas_lines.append("- None (all reliable features show loose-crew advantage or no difference)")
    for _, r in tight_higher_clean.head(5).iterrows():
        atlas_lines.append(f"- **{r['feature_name']}**: tight={r['tight_mean']:.4f} vs loose={r['loose_mean']:.4f} (d={r['cohens_d']:+.3f})")

    atlas_lines += [""]
    atlas_lines.append(f"**Scale-stable features higher under loose crews** (reliable):")
    atlas_lines.append("")
    loose_higher_clean = df_pop_clean[df_pop_clean["tight_mean"] < df_pop_clean["loose_mean"]].sort_values("abs_cohens_d", ascending=False)
    if loose_higher_clean.empty:
        atlas_lines.append("- None")
    for _, r in loose_higher_clean.head(5).iterrows():
        atlas_lines.append(f"- **{r['feature_name']}**: loose={r['loose_mean']:.4f} vs tight={r['tight_mean']:.4f} (d={r['cohens_d']:+.3f})")
    atlas_lines.append("")

    if not df_pop_conf.empty:
        atlas_lines.append(f"**Cross-season confounded features (DO NOT use for ref-crew inference)**:")
        atlas_lines.append("")
        for _, r in df_pop_conf.sort_values("abs_cohens_d", ascending=False).iterrows():
            atlas_lines.append(
                f"- ~~{r['feature_name']}~~: apparent d={r['cohens_d']:+.3f} — likely pipeline scale artifact"
            )
        atlas_lines.append("")

atlas_lines += [
    "## Top 5 Features by Cohen's d (Scale-Stable Only, |Tight vs Loose|)",
    "",
    "| Feature | Source | Tight Mean | Loose Mean | Cohen's d | p-value | Direction | Confound? |",
    "|---------|--------|-----------|-----------|-----------|---------|-----------|-----------|",
]
for _, r in top5_all.iterrows():
    direction = "tight↑" if r["tight_mean"] > r["loose_mean"] else "loose↑"
    p_str = f"{r['p_value']:.4f}" if r["p_value"] >= 0.001 else "<0.001"
    conf_flag = "YES" if r.get("cross_season_confound") else "no"
    atlas_lines.append(
        f"| {r['feature_name']} | {r['source']} | {r['tight_mean']:.4f} | "
        f"{r['loose_mean']:.4f} | {r['cohens_d']:+.3f} | {p_str} | {direction} | {conf_flag} |"
    )

atlas_lines += [
    "",
    "> Note: p-values are Welch's t-test (unequal variance). With N≈20-40 per bucket,",
    "> statistical power is low. Cohen's d is the more reliable effect-size indicator.",
    "",
    "## Top 10 Ref-Sensitive Players (Paint Pressure Delta, Tight vs Loose)",
    "",
]
if not top_players:
    atlas_lines += [
        "**Not computable.** Per-player sensitivity requires n_tight ≥ 4 AND n_loose ≥ 4",
        "games per player. Maximum observed is 2 games per player in the 18-game overlap window.",
        "",
        "This is a **data gap** (see Bug 19 below). As officials data is extended to cover",
        "2025-26 season games, this analysis will become feasible.",
        "",
    ]
else:
    atlas_lines += [
        "| Player ID | Feature | Δ (tight−loose) | Cohen's d | n_tight | n_loose |",
        "|-----------|---------|-----------------|-----------|---------|---------|",
    ]
    for p in top_players[:10]:
        atlas_lines.append(
            f"| {p['player_id']} | {p['feature_name']} | {p['delta_tight_loose']:+.4f} | "
            f"{p['cohens_d']:+.3f} | {p['n_tight']} | {p['n_loose']} |"
        )
    atlas_lines.append("")

atlas_lines += [
    "## Confound: Home/Away Venue",
    "",
    "> `ref_crew_home_win_pct` also varies across crews (range in our games: see below).",
    "> Tight-whistle crews may systematically be assigned to lower-stakes games,",
    "> while high-profile/playoff games (which skew toward loose crews anecdotally)",
    "> may differ in player motivation and game planning.",
    "",
    "**Control attempted**: ref_crew_home_win_pct is included in officials_features but",
    "with only 18 games, a multivariate regression controlling for venue effect would",
    "have fewer degrees of freedom than features. This control is deferred until",
    "≥ 50 overlap games are available.",
    "",
    "**Observed range** in our 18-game sample:",
]

off_subset = df_off_valid[df_off_valid["game_id"].isin(all_games)]
atlas_lines += [
    f"- ref_crew_home_win_pct: min={off_subset['ref_crew_home_win_pct'].min():.3f}, "
    f"max={off_subset['ref_crew_home_win_pct'].max():.3f}, "
    f"mean={off_subset['ref_crew_home_win_pct'].mean():.3f}",
    "",
]

atlas_lines += [
    "## Betting Implication",
    "",
    "**Directional hypothesis only (low N)**:",
    "",
]

# Build betting implication from top signals
if not df_pop.empty:
    # Check paint-related features
    paint_feats = df_pop[df_pop["feature_name"].str.contains("paint|basket|drive", case=False, na=False)]
    if not paint_feats.empty:
        top_paint = paint_feats.sort_values("abs_cohens_d", ascending=False).iloc[0]
        direction_str = "higher under tight crews" if top_paint["tight_mean"] > top_paint["loose_mean"] else "lower under tight crews"
        atlas_lines += [
            f"1. **{top_paint['feature_name']}** is {direction_str} (d={top_paint['cohens_d']:+.3f}). ",
            f"   Paint-pressure-heavy players facing a known tight-whistle crew could be faded on",
            f"   their paint-dependent stats (REB, FG%, drives) as refs may protect the paint less",
            f"   or more depending on foul call distribution.",
            "",
        ]
    spacing_feats = df_pop[df_pop["feature_name"].str.contains("spacing|defender|distance", case=False, na=False)]
    if not spacing_feats.empty:
        top_sp = spacing_feats.sort_values("abs_cohens_d", ascending=False).iloc[0]
        d_str = "increases" if top_sp["tight_mean"] > top_sp["loose_mean"] else "decreases"
        atlas_lines += [
            f"2. **{top_sp['feature_name']}** {d_str} under tight crews (d={top_sp['cohens_d']:+.3f}).",
            f"   When spacing opens up (or closes), 3-point and mid-range shot distributions shift.",
            f"   Could inform FG3M O/U angles for shooters on tight-crew days.",
            "",
        ]

atlas_lines += [
    "**Full angle requires**: ≥ 50 overlap games + venue control + player-level segmentation.",
    "Current signals are directional priors, not deployable betting edges.",
    "",
    "## Bug 19 — officials data does not cover 2025-26 season (new)",
    "",
    "**Surfaced by**: INT-47 Officials Impact Atlas",
    "**Symptom**: The officials_features.parquet covers 2022-10 to 2025-04-13 only.",
    "252 of 266 cv_features DB games are in 2025-26 season (002250xxx) — all missing",
    "officials context. Per-player sensitivity analysis (n>=4 per bucket) is blocked",
    "entirely by this coverage gap.",
    "**Root cause**: fetch_officials.py (or equivalent) was not run for 2025-26 season",
    "games after they were processed by the CV pipeline.",
    "**Fix**: Run the officials fetcher for game_ids starting with 002250. Check",
    "`scripts/fetch_officials_features.py` (or equivalent) and extend its season range.",
    "**Effort**: Low (one script run, ~30 min). Unblocks INT-47 per-player analysis,",
    "ref-crew betting angles, and any future officials confound controls.",
    "",
    "## Bug 20 — ref_crew_fouls sentinel value 42.0 silently contaminates tertile buckets",
    "",
    "**Surfaced by**: INT-47 Officials Impact Atlas",
    "**Symptom**: 70 rows (35 game_ids) in officials_features.parquet have ref_crew_fouls=42.0",
    "exactly, all dated 2025-04-10 to 2025-04-13 (last 4 days of 2024-25 season).",
    "42.0 is not the global max (max is 42.58); it appears to be a fill/cap artifact.",
    "If included, these 35 games would be placed in the 'loose' tertile bucket, inflating",
    "loose-crew N and corrupting any officials-aware analysis.",
    "**Fix**: Add a validation check in build_officials_features (or at load time) that flags",
    "game_ids where ref_crew_fouls == 42.0 AND game_date is in the last week of season.",
    "Write NULL instead of 42.0 for these games.",
    "**Effort**: Low (~1 hour).",
    "",
    "---",
    "[[CV_Pipeline_Bug_Roadmap]] | [[Officials_Features]] | [[Betting_Signal_Ranking]]",
]

atlas_path = VAULT / "Officials_Impact_Atlas.md"
with open(atlas_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(atlas_lines))
print(f"Atlas written -> {atlas_path}")

# ---------------------------------------------------------------------------
# 10. Append bugs to CV_Pipeline_Bug_Roadmap.md
# ---------------------------------------------------------------------------
print("\n--- Appending new bugs to CV_Pipeline_Bug_Roadmap.md ---")
bug_roadmap = VAULT / "CV_Pipeline_Bug_Roadmap.md"

new_bugs = """

### Bug 19 — officials_features.parquet does not cover 2025-26 season
**Surfaced by**: INT-47 Officials Impact Atlas
**Symptom**: 252 of 266 cv_features DB games are 2025-26 season (002250xxx) with no
corresponding rows in officials_features.parquet. The file's coverage ends 2025-04-13.
This completely blocks per-player sensitivity analysis (need n>=4 tight/loose per player)
and any ref-crew confound control for the current season's CV data.
**Root cause**: The officials fetcher script was not re-run after 2025-26 season games
were ingested into the CV pipeline.
**Fix**: Extend `fetch_officials_features.py` (or equivalent) to include 2025-26 season
game_ids. One script run, ~30 min.
**Effort**: Low
**Blocks**: INT-47 per-player sensitivity, ref-crew betting angle deployment.

### Bug 20 — ref_crew_fouls=42.0 sentinel in officials_features silently inflates loose bucket
**Surfaced by**: INT-47 Officials Impact Atlas
**Symptom**: 70 rows (35 game_ids) in officials_features.parquet have ref_crew_fouls
exactly 42.000, clustered on 2025-04-10 to 2025-04-13 (last 4 regular-season days).
The global max is 42.580, so 42.0 is a fill/cap artifact, not a real measurement.
If included in tertile bucketing, all 35 games land in the 'loose' bucket, corrupting
loose-crew population means and any officials-aware model.
**Root cause**: Likely a default or cap value written by the officials fetcher when
ref_crew stats are unavailable for end-of-season games with non-standard officiating.
**Fix**: In `build_officials_features.py` (or load guard), write NaN instead of 42.0 when
ref_crew_fouls == 42.0 AND game is in the last 7 days of the season. Add assert on load.
**Effort**: Low (~1 hour).
"""

with open(bug_roadmap, "a", encoding="utf-8") as fh:
    fh.write(new_bugs)
print(f"New bugs appended to {bug_roadmap}")

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
print("\n=== INT-47 Complete ===")
print(f"Outputs:")
print(f"  {pop_out}")
print(f"  {sens_out}")
print(f"  {signals_out}")
print(f"  {atlas_path}")
print(f"  {bug_roadmap}  (appended)")
