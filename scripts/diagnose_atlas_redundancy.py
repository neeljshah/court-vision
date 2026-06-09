"""
INT-78 Cross-Atlas Redundancy Diagnostic
Pairwise Pearson correlation across 11 shipped atlases.
Outputs: atlas_redundancy_matrix.parquet + INT-78_Atlas_Redundancy_Diagnostic.md
"""

from pathlib import Path
import itertools
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
INT_DIR = ROOT / "data" / "intelligence"
VAULT_DIR = ROOT / "vault" / "Intelligence"

# ---------------------------------------------------------------------------
# 1. Load all 11 atlases
# ---------------------------------------------------------------------------
ATLASES = [
    "opp_defensive_intensity",
    "opp_paint_allowance",
    "team_tempo_spacing",
    "defensive_schemes",
    "cv_consistency_kelly",
    "archetype_outlier_signals",
    "player_development_v2",
    "per_player_calibration",
    "garbage_time_player_aggregates",
    "matchup_grid",
    "cv_coverage_gates",
]

raw = {}
for name in ATLASES:
    path = INT_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing atlas: {path}")
    raw[name] = pd.read_parquet(path)
    print(f"  loaded {name}: {raw[name].shape}")


# ---------------------------------------------------------------------------
# 2. Helper: one-hot defensive_schemes; pivot per_player_calibration
# ---------------------------------------------------------------------------

def prep_defensive_schemes(df: pd.DataFrame) -> pd.DataFrame:
    """One-hot dominant_tag, keep numeric cols, add team key."""
    numeric = df.select_dtypes(include=[np.number]).copy()
    if "dominant_tag" in df.columns:
        ohe = pd.get_dummies(df["dominant_tag"], prefix="scheme_tag")
        numeric = pd.concat([numeric, ohe], axis=1)
    if "team" in df.columns:
        numeric["team"] = df["team"]
    return numeric


def pivot_per_player_calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot bias_z_l20 wide: one column per stat per player-asofdate."""
    pivot = df.pivot_table(
        index=["player_id", "asof_date"],
        columns="stat",
        values="bias_z_l20",
        aggfunc="first",
    ).reset_index()
    pivot.columns.name = None
    pivot.columns = [
        f"bias_z_{c}" if c not in ("player_id", "asof_date") else c
        for c in pivot.columns
    ]
    return pivot


def aggregate_to_team_season(df: pd.DataFrame, value_cols: list) -> pd.DataFrame:
    """
    Aggregate player-level or game-level atlas to team-season means
    so it can join with Group T atlases.
    Requires 'team_id' or 'team' col + 'season' or derivable from game_date.
    """
    d = df.copy()
    # normalise team key
    if "team_id" in d.columns:
        team_col = "team_id"
    elif "team" in d.columns:
        team_col = "team"
    elif "opp_team_id" in d.columns:
        team_col = "opp_team_id"
    else:
        return None

    # derive season if needed
    if "season" not in d.columns:
        if "game_date" in d.columns:
            d["season"] = pd.to_datetime(d["game_date"]).dt.year.where(
                pd.to_datetime(d["game_date"]).dt.month >= 10,
                pd.to_datetime(d["game_date"]).dt.year - 1,
            )
        else:
            return None

    d = d[[team_col, "season"] + [c for c in value_cols if c in d.columns]].copy()
    d = d.rename(columns={team_col: "_team"})
    agg = d.groupby(["_team", "season"])[
        [c for c in value_cols if c in d.columns]
    ].mean().reset_index()
    agg = agg.rename(columns={"_team": "team_id"})
    return agg


# ---------------------------------------------------------------------------
# 3. Build join-ready versions per group
# ---------------------------------------------------------------------------

# --- Group T (team-season) join key: team_id + season ---
def load_team_season(name: str) -> pd.DataFrame:
    df = raw[name].copy()
    if "game_date" in df.columns:
        # reduce to team-season by taking mean per team+season
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        key_cols = [c for c in ("team_id", "team", "season") if c in df.columns]
        if not key_cols:
            return df
        # if game_date-level, aggregate
        if "season" not in df.columns:
            df["season"] = pd.to_datetime(df["game_date"]).dt.year.where(
                pd.to_datetime(df["game_date"]).dt.month >= 10,
                pd.to_datetime(df["game_date"]).dt.year - 1,
            )
        team_col = "team_id" if "team_id" in df.columns else "team"
        group_key = [team_col, "season"]
        agg = df.groupby(group_key)[num_cols].mean().reset_index()
        if team_col != "team_id":
            agg = agg.rename(columns={team_col: "team_id"})
        return agg
    else:
        # already season-level (defensive_schemes)
        df2 = prep_defensive_schemes(df)
        return df2


# --- Group P (player-season) join key: player_id + season ---
def load_player_season(name: str) -> pd.DataFrame:
    df = raw[name].copy()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    if name == "per_player_calibration":
        df = pivot_per_player_calibration(df)
        num_cols = [c for c in df.columns if c not in ("player_id", "asof_date")]
        # derive season from asof_date
        df["season"] = pd.to_datetime(df["asof_date"]).dt.year.where(
            pd.to_datetime(df["asof_date"]).dt.month >= 10,
            pd.to_datetime(df["asof_date"]).dt.year - 1,
        )
        # mean per player-season (multiple asof_dates exist)
        agg = df.groupby(["player_id", "season"])[num_cols].mean().reset_index()
        return agg

    if "game_date" in df.columns and "season" not in df.columns:
        df["season"] = pd.to_datetime(df["game_date"]).dt.year.where(
            pd.to_datetime(df["game_date"]).dt.month >= 10,
            pd.to_datetime(df["game_date"]).dt.year - 1,
        )

    player_col = "player_id" if "player_id" in df.columns else None
    if player_col is None:
        return df

    season_col = "season" if "season" in df.columns else None
    group_key = [player_col] + ([season_col] if season_col else [])
    # remove group keys from num_cols to avoid double-column on reset_index
    num_cols_clean = [c for c in num_cols if c not in group_key]
    if not num_cols_clean:
        return df
    agg = df.groupby(group_key)[num_cols_clean].mean().reset_index()
    return agg


# ---------------------------------------------------------------------------
# 4. Compute per-pair correlation
# ---------------------------------------------------------------------------

# Metadata/bookkeeping columns that appear across atlases but are not signals
# Excluding these prevents trivial r=1.0 from build-metadata matches
_META_COLS = frozenset([
    "n_games_window", "data_density", "n_raw_frames", "n_possessions_window",
    "n_opposing_player_games", "n_unique_opponents", "confidence",
    "n_cv_games_in_window", "n_hist_games", "n_window",
    "n_prior_games", "gt_entry_count", "parse_failure_rate", "pid_resolve_rate",
    "n_games_offense_window", "n_games_defense_window",
    "n_prior_cv_games", "n_prior_cv_games_l30d",
    "minutes_played_total", "minutes_in_gt", "pct_minutes_in_gt",
    # matchup_grid prefixed meta cols
    "mg_n_games_offense_window", "mg_n_games_defense_window", "mg_data_density",
])


def compute_pair_corr(df_a: pd.DataFrame, df_b: pd.DataFrame,
                      key_cols: list, name_a: str, name_b: str,
                      suffix_a: str = "_a", suffix_b: str = "_b"):
    """Inner-join on key_cols, compute all numeric pairwise Pearson r.
    Metadata/bookkeeping columns (n_games_window, data_density, etc.)
    are excluded so build-metadata identity does not inflate max_abs_r.
    """
    # Rename value columns before merge to avoid any collision
    # Keep only numeric cols (excluding join keys and metadata)
    num_a_orig = [c for c in df_a.columns if c not in key_cols
                  and c not in _META_COLS
                  and pd.api.types.is_numeric_dtype(df_a[c])]
    num_b_orig = [c for c in df_b.columns if c not in key_cols
                  and c not in _META_COLS
                  and pd.api.types.is_numeric_dtype(df_b[c])]

    if not num_a_orig or not num_b_orig:
        return dict(atlas_a=name_a, atlas_b=name_b,
                    n_rows=0, max_abs_r=np.nan, mean_abs_r=np.nan,
                    argmax_col_a="", argmax_col_b="",
                    flag_insufficient=True)

    # Build renamed frames to prevent any column name collisions
    rename_a = {c: f"{c}{suffix_a}" for c in num_a_orig}
    rename_b = {c: f"{c}{suffix_b}" for c in num_b_orig}
    da = df_a[key_cols + num_a_orig].rename(columns=rename_a)
    db = df_b[key_cols + num_b_orig].rename(columns=rename_b)

    cols_a = list(rename_a.values())
    cols_b = list(rename_b.values())

    # Coerce join key dtypes to string to avoid int32/object mismatches
    for k in key_cols:
        if k in da.columns:
            da = da.copy()
            da[k] = da[k].astype(str)
        if k in db.columns:
            db = db.copy()
            db[k] = db[k].astype(str)
    merged = da.merge(db, on=key_cols, how="inner")
    # drop rows where ALL value cols are NaN
    merged = merged.dropna(subset=cols_a + cols_b, how="all")
    n_rows = len(merged)

    if n_rows < 30:
        return dict(atlas_a=name_a, atlas_b=name_b,
                    n_rows=n_rows, max_abs_r=np.nan, mean_abs_r=np.nan,
                    argmax_col_a="", argmax_col_b="",
                    flag_insufficient=True)

    best_r = 0.0
    best_ca = ""
    best_cb = ""
    all_r = []

    for ca in cols_a:
        for cb in cols_b:
            s_a = merged[ca].dropna()
            s_b = merged[cb].dropna()
            idx = s_a.index.intersection(s_b.index)
            if len(idx) < 30:
                continue
            if s_a.loc[idx].std() == 0 or s_b.loc[idx].std() == 0:
                continue
            r = s_a.loc[idx].corr(s_b.loc[idx])
            if np.isfinite(r):
                all_r.append(abs(r))
                if abs(r) > abs(best_r):
                    best_r = r
                    # strip suffix for readability
                    best_ca = ca.removesuffix(suffix_a)
                    best_cb = cb.removesuffix(suffix_b)

    if not all_r:
        return dict(atlas_a=name_a, atlas_b=name_b,
                    n_rows=n_rows, max_abs_r=np.nan, mean_abs_r=np.nan,
                    argmax_col_a="", argmax_col_b="",
                    flag_insufficient=True)

    return dict(
        atlas_a=name_a, atlas_b=name_b,
        n_rows=n_rows,
        max_abs_r=round(abs(best_r), 4),
        mean_abs_r=round(float(np.mean(all_r)), 4),
        argmax_col_a=best_ca,
        argmax_col_b=best_cb,
        flag_insufficient=False,
    )


# ---------------------------------------------------------------------------
# 5. Build group-ready dataframes
# ---------------------------------------------------------------------------

print("\nBuilding group-ready dataframes...")

T = {name: load_team_season(name)
     for name in ["opp_defensive_intensity", "opp_paint_allowance",
                  "team_tempo_spacing", "defensive_schemes"]}

# defensive_schemes uses 'team' not 'team_id'; normalise
ds = T["defensive_schemes"].copy()
if "team_id" not in ds.columns and "team" in ds.columns:
    ds = ds.rename(columns={"team": "team_id"})
    # no season column in defensive_schemes; assign dummy season=0 for cross-join
    ds["season"] = 0
T["defensive_schemes"] = ds

# For other T atlases set season=0 where no season col
for k in ["opp_defensive_intensity", "opp_paint_allowance", "team_tempo_spacing"]:
    if "season" not in T[k].columns:
        T[k]["season"] = 0

P = {name: load_player_season(name)
     for name in ["cv_consistency_kelly", "archetype_outlier_signals",
                  "player_development_v2", "per_player_calibration",
                  "garbage_time_player_aggregates"]}

# Ensure player_id + season in all P
for k, df in P.items():
    if "season" not in df.columns:
        df = df.copy()
        df["season"] = 0
        P[k] = df

# Group M: matchup_grid → aggregate to team-season, join into Group T
mg = raw["matchup_grid"].copy()
mg_num = [c for c in mg.columns
          if pd.api.types.is_numeric_dtype(mg[c])
          and c not in ("game_id", "season", "team_id", "opp_team_id", "is_home")]
if "season" not in mg.columns:
    mg["season"] = pd.to_datetime(mg["game_date"]).dt.year.where(
        pd.to_datetime(mg["game_date"]).dt.month >= 10,
        pd.to_datetime(mg["game_date"]).dt.year - 1,
    )
mg_agg = mg.groupby(["team_id", "season"])[mg_num].mean().reset_index()
mg_agg.columns = [f"mg_{c}" if c not in ("team_id", "season") else c
                  for c in mg_agg.columns]

# Group G: cv_coverage_gates → aggregate to team? Actually cv_coverage_gates
# has player_id not team_id; aggregate by game_date-season then cross-join on season
ccg = raw["cv_coverage_gates"].copy()
ccg_num = [c for c in ccg.columns
           if pd.api.types.is_numeric_dtype(ccg[c])
           and c not in ("nba_player_id",)]
if "season" not in ccg.columns:
    ccg["season"] = pd.to_datetime(ccg["game_date"]).dt.year.where(
        pd.to_datetime(ccg["game_date"]).dt.month >= 10,
        pd.to_datetime(ccg["game_date"]).dt.year - 1,
    )
# No team_id in cv_coverage_gates — aggregate by season only for team-season merge
ccg_agg = ccg.groupby(["season"])[ccg_num].mean().reset_index()
ccg_agg.columns = [f"ccg_{c}" if c != "season" else c for c in ccg_agg.columns]


# ---------------------------------------------------------------------------
# 6. Define the 24 pairs
# ---------------------------------------------------------------------------

T_NAMES = ["opp_defensive_intensity", "opp_paint_allowance",
           "team_tempo_spacing", "defensive_schemes"]
P_NAMES = ["cv_consistency_kelly", "archetype_outlier_signals",
           "player_development_v2", "per_player_calibration",
           "garbage_time_player_aggregates"]

pairs = []

# Group T — 6 pairs
for a, b in itertools.combinations(T_NAMES, 2):
    pairs.append(("T", a, b))

# Group P — 10 pairs
for a, b in itertools.combinations(P_NAMES, 2):
    pairs.append(("P", a, b))

# Group M — matchup_grid vs each of 4 T atlases (4 bonus pairs)
for t in T_NAMES:
    pairs.append(("M", "matchup_grid", t))

# Group G — cv_coverage_gates vs each of 4 T atlases (4 bonus pairs)
for t in T_NAMES:
    pairs.append(("G", "cv_coverage_gates", t))

print(f"Total pairs: {len(pairs)}")


# ---------------------------------------------------------------------------
# 7. Evaluate every pair
# ---------------------------------------------------------------------------

def verdict(max_abs_r):
    if np.isnan(max_abs_r):
        return "INSUFFICIENT"
    if max_abs_r > 0.85:
        return "REDUNDANT"
    if max_abs_r >= 0.70:
        return "HIGH_OVERLAP"
    if max_abs_r >= 0.40:
        return "MODERATE"
    return "ORTHOGONAL"


results = []

for group, name_a, name_b in pairs:
    print(f"  [{group}] {name_a} x {name_b}")

    if group == "T":
        df_a = T[name_a]
        df_b = T[name_b]
        # defensive_schemes has no real season; use team_id only join
        if "defensive_schemes" in (name_a, name_b):
            # drop season from both for join
            da = df_a.drop(columns=["season"], errors="ignore").copy()
            db = df_b.drop(columns=["season"], errors="ignore").copy()
            key = ["team_id"]
        else:
            da, db = df_a.copy(), df_b.copy()
            key = ["team_id", "season"]
        row = compute_pair_corr(da, db, key, name_a, name_b)

    elif group == "P":
        # garbage_time has game-level granularity; per_player_calibration after pivot
        # both should have player_id + season from load_player_season
        df_a = P[name_a]
        df_b = P[name_b]
        da, db = df_a.copy(), df_b.copy()
        key = ["player_id", "season"]
        # season=0 for those without real season — still valid relative join
        row = compute_pair_corr(da, db, key, name_a, name_b)

    elif group == "M":
        # matchup_grid agg vs T atlas
        t_name = name_b
        df_t = T[t_name].copy()
        if "defensive_schemes" == t_name:
            df_t = df_t.drop(columns=["season"], errors="ignore")
            da = mg_agg.drop(columns=["season"], errors="ignore")
            key = ["team_id"]
        else:
            da = mg_agg.copy()
            key = ["team_id", "season"]
        row = compute_pair_corr(da, df_t, key, "matchup_grid", t_name)

    elif group == "G":
        # cv_coverage_gates agg (season-only) vs T atlas
        t_name = name_b
        df_t = T[t_name].copy()
        # join on season only (no team_id in ccg_agg)
        da = ccg_agg.copy()
        if "defensive_schemes" == t_name:
            # no season in defensive_schemes either — skip, flag insufficient
            row = dict(atlas_a="cv_coverage_gates", atlas_b=t_name,
                       n_rows=0, max_abs_r=np.nan, mean_abs_r=np.nan,
                       argmax_col_a="", argmax_col_b="",
                       flag_insufficient=True)
        else:
            key = ["season"]
            row = compute_pair_corr(da, df_t, key, "cv_coverage_gates", t_name)

    row["group"] = group
    results.append(row)


# ---------------------------------------------------------------------------
# 8. Build output DataFrame
# ---------------------------------------------------------------------------

out_cols = ["atlas_a", "atlas_b", "group", "n_rows",
            "max_abs_r", "mean_abs_r", "argmax_col_a", "argmax_col_b",
            "verdict", "flag_insufficient"]

df_out = pd.DataFrame(results)
df_out["verdict"] = df_out["max_abs_r"].apply(verdict)
df_out["flag_insufficient"] = df_out.get("flag_insufficient", False).fillna(False)
df_out = df_out[out_cols]

out_path = INT_DIR / "atlas_redundancy_matrix.parquet"
df_out.to_parquet(out_path, index=False)
print(f"\nWrote {out_path}")


# ---------------------------------------------------------------------------
# 9. Build markdown report
# ---------------------------------------------------------------------------

band_counts = df_out["verdict"].value_counts().to_dict()
for b in ("REDUNDANT", "HIGH_OVERLAP", "MODERATE", "ORTHOGONAL", "INSUFFICIENT"):
    band_counts.setdefault(b, 0)

# ASCII heatmap helper
def r_to_block(r):
    if np.isnan(r):
        return " "
    if r > 0.85:
        return "█"
    if r >= 0.70:
        return "▓"
    if r >= 0.40:
        return "▒"
    return "░"


def ascii_heatmap(group_label, group_df):
    names_a = group_df["atlas_a"].tolist()
    names_b = group_df["atlas_b"].tolist()
    all_names = list(dict.fromkeys(names_a + names_b))
    lines = [f"Group {group_label} — █>0.85(REDUNDANT) ▓0.70-0.85(HIGH) ▒0.40-0.70(MOD) ░≤0.40(ORTH)"]
    header = "  " + "  ".join(f"{n[:6]:6s}" for n in all_names)
    lines.append(header)
    for na in all_names:
        row_str = f"{na[:12]:12s}|"
        for nb in all_names:
            if na == nb:
                row_str += "  ----  "
                continue
            sub = group_df[
                ((group_df["atlas_a"] == na) & (group_df["atlas_b"] == nb)) |
                ((group_df["atlas_a"] == nb) & (group_df["atlas_b"] == na))
            ]
            if sub.empty:
                row_str += "        "
            else:
                r = sub.iloc[0]["max_abs_r"]
                row_str += f"  {r_to_block(r)}({r:.2f})"
        lines.append(row_str)
    return "\n".join(lines)


# Top 3 highest
sorted_df = df_out[~df_out["flag_insufficient"]].sort_values("max_abs_r", ascending=False)
top3_high = sorted_df.head(3)

# Top 3 most orthogonal
sorted_low = df_out[~df_out["flag_insufficient"]].sort_values("max_abs_r", ascending=True)
top3_low = sorted_low.head(3)

# Recommendations
redundant_pairs = df_out[df_out["verdict"] == "REDUNDANT"]
high_pairs = df_out[df_out["verdict"] == "HIGH_OVERLAP"]

md_lines = [
    "# INT-78 Atlas Redundancy Diagnostic",
    "",
    f"**Build date:** 2026-05-29  |  **Pairs evaluated:** {len(df_out)}  |  "
    f"**Data source:** data/intelligence/*.parquet",
    "",
    "## TL;DR",
    "",
    f"| Verdict | Count |",
    f"|---------|-------|",
    f"| REDUNDANT (>0.85) | {band_counts['REDUNDANT']} |",
    f"| HIGH_OVERLAP (0.70-0.85) | {band_counts['HIGH_OVERLAP']} |",
    f"| MODERATE (0.40-0.70) | {band_counts['MODERATE']} |",
    f"| ORTHOGONAL (<=0.40) | {band_counts['ORTHOGONAL']} |",
    f"| INSUFFICIENT (n<30) | {band_counts['INSUFFICIENT']} |",
    "",
    "> **Advisory only.** Verdict is max Pearson |r| across all numeric column pairs "
    "after inner-join on shared keys. Recommend human review before dropping any parquet.",
    "",
]

# Heatmaps per group
for g in ["T", "P", "M", "G"]:
    gdf = df_out[df_out["group"] == g]
    if not gdf.empty:
        md_lines += ["## ASCII Heatmap — Group " + g, "", "```"]
        md_lines.append(ascii_heatmap(g, gdf))
        md_lines += ["```", ""]

# Per-pair table
md_lines += [
    "## Per-Pair Verdict Table",
    "",
    "| atlas_a | atlas_b | group | n_rows | max_abs_r | mean_abs_r | argmax_col_a | argmax_col_b | verdict |",
    "|---------|---------|-------|--------|-----------|------------|--------------|--------------|---------|",
]
for _, row in df_out.sort_values(["group", "max_abs_r"], ascending=[True, False]).iterrows():
    insuf = " [n<30]" if row["flag_insufficient"] else ""
    md_lines.append(
        f"| {row['atlas_a']} | {row['atlas_b']} | {row['group']} "
        f"| {row['n_rows']} | {row['max_abs_r']:.4f} | {row['mean_abs_r']:.4f} "
        f"| {row['argmax_col_a']} | {row['argmax_col_b']} | {row['verdict']}{insuf} |"
    )

md_lines += [
    "",
    "## Top-3 Highest Correlations",
    "",
]
for _, row in top3_high.iterrows():
    md_lines.append(
        f"- **{row['atlas_a']} x {row['atlas_b']}**: max_abs_r={row['max_abs_r']:.4f}, "
        f"mean_abs_r={row['mean_abs_r']:.4f}  "
        f"(cols: `{row['argmax_col_a']}` vs `{row['argmax_col_b']}`)"
    )

md_lines += [
    "",
    "## Top-3 Most Orthogonal",
    "",
]
for _, row in top3_low.iterrows():
    md_lines.append(
        f"- **{row['atlas_a']} x {row['atlas_b']}**: max_abs_r={row['max_abs_r']:.4f}, "
        f"mean_abs_r={row['mean_abs_r']:.4f}"
    )

# Recommendations
md_lines += ["", "## Recommendations", ""]
if not redundant_pairs.empty:
    md_lines.append("### REDUNDANT pairs — recommend human review before deprecation")
    for _, row in redundant_pairs.iterrows():
        md_lines.append(
            f"- **{row['atlas_a']} x {row['atlas_b']}** "
            f"(max_abs_r={row['max_abs_r']:.4f}): "
            f"likely overlap via `{row['argmax_col_a']}` / `{row['argmax_col_b']}`"
        )
else:
    md_lines.append("No REDUNDANT pairs found.")

if not high_pairs.empty:
    md_lines += ["", "### HIGH_OVERLAP pairs — consider consolidation"]
    for _, row in high_pairs.iterrows():
        md_lines.append(
            f"- **{row['atlas_a']} x {row['atlas_b']}** "
            f"(max_abs_r={row['max_abs_r']:.4f}): "
            f"driver cols `{row['argmax_col_a']}` / `{row['argmax_col_b']}`"
        )

md_lines += [
    "",
    "## Caveats",
    "",
    "- **Pearson only**: non-linear relationships not captured; treat as lower bound on overlap.",
    "- **Aggregation artifacts**: Group M and G atlases are aggregated from game-level to "
    "team-season means before joining; this compresses variance and can inflate or deflate r.",
    "- **per_player_calibration pivot**: 7 bias_z columns (one per stat) dominate "
    "max_abs_r comparisons within Group P; a single stat collision will flag the pair HIGH.",
    "- **cv_coverage_gates + defensive_schemes**: no shared join key possible (no team_id "
    "in cv_coverage_gates; no season in defensive_schemes); flagged INSUFFICIENT.",
    "- **defensive_schemes season=0**: season-free atlas joined on team_id only; "
    "season-averaged counterparts used; reduces join granularity.",
    "- **n_rows < 30 threshold**: sparse atlases (archetype_outlier_signals n=383 players "
    "at game level; player_development_v2 n=78) may have thin cross-joins.",
    "- Verdict is ADVISORY ONLY — **recommend human review before dropping any parquet**.",
]

VAULT_DIR.mkdir(parents=True, exist_ok=True)
md_path = VAULT_DIR / "INT-78_Atlas_Redundancy_Diagnostic.md"
md_path.write_text("\n".join(md_lines), encoding="utf-8")
print(f"Wrote {md_path}")

# ---------------------------------------------------------------------------
# 10. Console summary
# ---------------------------------------------------------------------------
print("\n=== INT-78 Summary ===")
print(f"Pairs: {len(df_out)} total")
for b in ("REDUNDANT", "HIGH_OVERLAP", "MODERATE", "ORTHOGONAL", "INSUFFICIENT"):
    print(f"  {b}: {band_counts[b]}")

print("\nTop-3 highest max_abs_r:")
for _, row in top3_high.iterrows():
    print(f"  {row['atlas_a']} x {row['atlas_b']}: {row['max_abs_r']:.4f} "
          f"({row['argmax_col_a']} / {row['argmax_col_b']})")

print("\nTop-3 most orthogonal:")
for _, row in top3_low.iterrows():
    print(f"  {row['atlas_a']} x {row['atlas_b']}: {row['max_abs_r']:.4f}")
