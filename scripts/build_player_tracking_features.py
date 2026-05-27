"""
build_player_tracking_features.py
Parse player-tracking variant JSONs (Drives, Passing, CatchShoot) and emit
a combined per-(player_id, season) parquet.

Source files:  data/nba/player_tracking_{Drives,Passing,CatchShoot}_{YYYY-YY}.json
Output:        data/cache/player_tracking_features.parquet
Keys:          player_id, player_name, season

Shape: per-season rows (one row per player per season per variant joined wide).
If a player appears in only one variant for a season that row is still present;
missing-variant columns are NaN.

Idempotent — rerunning overwrites the parquet.
"""

import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (forward-slash, relative-to-script-friendly but always resolved)
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
DATA_NBA = REPO / "data" / "nba"
OUT_DIR = REPO / "data" / "cache"
OUT_PATH = OUT_DIR / "player_tracking_features.parquet"

# ---------------------------------------------------------------------------
# Feature column selections per variant
# ---------------------------------------------------------------------------
DRIVES_COLS = [
    "drives",
    "drive_fgm",
    "drive_fga",
    "drive_fg_pct",
    "drive_pts",
    "drive_pts_pct",
    "drive_passes",
    "drive_ast",
    "drive_ast_pct",
    "drive_tov",
    "drive_tov_pct",
]

PASSING_COLS = [
    "passes_made",
    "passes_received",
    "ast",
    "ft_ast",
    "secondary_ast",
    "potential_ast",
    "ast_points_created",
    "ast_to_pass_pct",
    "ast_to_pass_pct_adj",
]

CATCHSHOOT_COLS = [
    "catch_shoot_fgm",
    "catch_shoot_fga",
    "catch_shoot_fg_pct",
    "catch_shoot_pts",
    "catch_shoot_fg3m",
    "catch_shoot_fg3a",
    "catch_shoot_fg3_pct",
    "catch_shoot_efg_pct",
]

# variant_name -> (glob_pattern_prefix, feature_columns)
VARIANTS = {
    "Drives":     ("player_tracking_Drives_", DRIVES_COLS),
    "Passing":    ("player_tracking_Passing_", PASSING_COLS),
    "CatchShoot": ("player_tracking_CatchShoot_", CATCHSHOOT_COLS),
}

KEY_COLS = ["player_id", "player_name", "season", "team_abbreviation", "gp", "min"]


def load_variant(name: str, prefix: str, feature_cols: list[str]) -> pd.DataFrame:
    """Load all season JSONs for one variant; return a tidy DataFrame."""
    files = sorted(DATA_NBA.glob(f"{prefix}*.json"))
    if not files:
        log.warning("Variant %s — no data files found in %s — skipped", name, DATA_NBA)
        return pd.DataFrame()

    dfs = []
    for fp in files:
        # Extract season from filename, e.g. player_tracking_Drives_2024-25.json
        season = fp.stem.replace(prefix, "")
        try:
            with open(fp, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:
            log.warning("Variant %s | %s — JSON load failed: %s — skipped", name, fp.name, exc)
            continue

        if not isinstance(raw, list):
            log.warning("Variant %s | %s — unexpected root type %s — skipped", name, fp.name, type(raw))
            continue

        if not raw:
            log.warning("Variant %s | %s — empty list — skipped", name, fp.name)
            continue

        try:
            df = pd.DataFrame(raw)
        except Exception as exc:
            log.warning("Variant %s | %s — DataFrame creation failed: %s — skipped", name, fp.name, exc)
            continue

        # Ensure season key (some files embed _season; override with filename-derived value)
        df["season"] = season

        # Keep only needed columns that actually exist in this file
        keep = [c for c in KEY_COLS if c in df.columns] + [c for c in feature_cols if c in df.columns]
        missing = [c for c in feature_cols if c not in df.columns]
        if missing:
            log.warning("Variant %s | %s — missing feature cols: %s", name, fp.name, missing)

        df = df[keep].copy()
        dfs.append(df)
        log.info("Variant %s | %s — %d rows, %d feature cols", name, fp.name, len(df), len(feature_cols) - len(missing))

    if not dfs:
        log.warning("Variant %s — all files skipped, no data produced", name)
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    log.info("Variant %s — total %d rows across %d season files", name, len(combined), len(dfs))
    return combined


def derive_features(drives: pd.DataFrame, passing: pd.DataFrame, catchshoot: pd.DataFrame) -> pd.DataFrame:
    """
    Compute derived per-season features and merge all three variants on
    (player_id, season).

    All source values are already per-game averages (the NBA playerdashpt
    endpoint returns per-game rates), so we surface them directly.
    Derived columns:
      - drives_per_g           = drives (already per-g)
      - drive_pts_per_drive    = drive_pts / drives  (clip to [0, inf])
      - drive_ast_per_drive    = drive_ast / drives
      - passes_made_per_g      = passes_made (already per-g)
      - ast_per_pass           = ast / passes_made
      - ast_pct                = ast_to_pass_pct (rename)
      - cs_3p_pct              = catch_shoot_fg3_pct (rename)
      - cs_3pa_per_g           = catch_shoot_fg3a (already per-g)
      - cs_efg_pct             = catch_shoot_efg_pct (rename)
    """
    merge_keys = ["player_id", "season"]

    dfs_to_merge = []

    # --- DRIVES ---
    if not drives.empty:
        d = drives.copy()
        # Rename gp/min to drives_gp/drives_min to avoid collisions in merge
        d = d.rename(columns={"gp": "drives_gp", "min": "drives_min",
                               "team_abbreviation": "drives_team"})
        # Derived
        eps = 1e-6
        d["drives_per_g"] = d.get("drives", float("nan"))
        d["drive_pts_per_drive"] = (
            d.get("drive_pts", float("nan")) / (d.get("drives", float("nan")) + eps)
        ).clip(lower=0)
        d["drive_ast_per_drive"] = (
            d.get("drive_ast", float("nan")) / (d.get("drives", float("nan")) + eps)
        ).clip(lower=0)

        feat_cols_out = (
            merge_keys
            + ["player_name", "drives_gp", "drives_min", "drives_team"]
            + DRIVES_COLS
            + ["drives_per_g", "drive_pts_per_drive", "drive_ast_per_drive"]
        )
        # only keep cols that exist
        feat_cols_out = [c for c in feat_cols_out if c in d.columns]
        dfs_to_merge.append(d[feat_cols_out])

    # --- PASSING ---
    if not passing.empty:
        p = passing.copy()
        p = p.rename(columns={"gp": "passing_gp", "min": "passing_min",
                               "team_abbreviation": "passing_team"})
        eps = 1e-6
        p["passes_made_per_g"] = p.get("passes_made", float("nan"))
        p["ast_per_pass"] = (
            p.get("ast", float("nan")) / (p.get("passes_made", float("nan")) + eps)
        ).clip(lower=0)
        p["ast_pct"] = p.get("ast_to_pass_pct", float("nan"))

        feat_cols_out = (
            merge_keys
            + ["player_name", "passing_gp", "passing_min", "passing_team"]
            + PASSING_COLS
            + ["passes_made_per_g", "ast_per_pass", "ast_pct"]
        )
        feat_cols_out = [c for c in feat_cols_out if c in p.columns]
        dfs_to_merge.append(p[feat_cols_out])

    # --- CATCHSHOOT ---
    if not catchshoot.empty:
        cs = catchshoot.copy()
        cs = cs.rename(columns={"gp": "cs_gp", "min": "cs_min",
                                 "team_abbreviation": "cs_team"})
        cs["cs_3p_pct"] = cs.get("catch_shoot_fg3_pct", float("nan"))
        cs["cs_3pa_per_g"] = cs.get("catch_shoot_fg3a", float("nan"))
        cs["cs_efg_pct"] = cs.get("catch_shoot_efg_pct", float("nan"))

        feat_cols_out = (
            merge_keys
            + ["player_name", "cs_gp", "cs_min", "cs_team"]
            + CATCHSHOOT_COLS
            + ["cs_3p_pct", "cs_3pa_per_g", "cs_efg_pct"]
        )
        feat_cols_out = [c for c in feat_cols_out if c in cs.columns]
        dfs_to_merge.append(cs[feat_cols_out])

    if not dfs_to_merge:
        log.error("No variant data at all — nothing to output.")
        return pd.DataFrame()

    # Merge all three on player_id + season (outer so we keep every row)
    result = dfs_to_merge[0]
    for other in dfs_to_merge[1:]:
        # player_name may appear in multiple frames; suffix to avoid collision
        shared_non_key = [c for c in other.columns if c in result.columns and c not in merge_keys]
        player_name_in_other = "player_name" in other.columns
        if player_name_in_other and "player_name" not in merge_keys:
            other = other.rename(columns={"player_name": "_player_name_r"})
        result = result.merge(other, on=merge_keys, how="outer", suffixes=("", "_dup"))
        # Coalesce player_name
        if "_player_name_r" in result.columns:
            result["player_name"] = result["player_name"].combine_first(result["_player_name_r"])
            result = result.drop(columns=["_player_name_r"])
        # Drop _dup suffix columns
        dup_cols = [c for c in result.columns if c.endswith("_dup")]
        if dup_cols:
            result = result.drop(columns=dup_cols)

    # Canonical column order: keys first, then all features
    id_front = [c for c in ["player_id", "player_name", "season"] if c in result.columns]
    rest = [c for c in result.columns if c not in id_front]
    result = result[id_front + rest]

    result = result.sort_values(["player_id", "season"]).reset_index(drop=True)
    return result


def print_diagnostics(df: pd.DataFrame) -> None:
    """Print rowcount per variant column group and null rates."""
    log.info("=== OUTPUT DIAGNOSTICS ===")
    log.info("Total rows: %d | columns: %d", len(df), len(df.columns))

    groups = {
        "DRIVES features":     DRIVES_COLS + ["drives_per_g", "drive_pts_per_drive", "drive_ast_per_drive"],
        "PASSING features":    PASSING_COLS + ["passes_made_per_g", "ast_per_pass", "ast_pct"],
        "CATCHSHOOT features": CATCHSHOOT_COLS + ["cs_3p_pct", "cs_3pa_per_g", "cs_efg_pct"],
    }

    for grp_name, cols in groups.items():
        present = [c for c in cols if c in df.columns]
        if not present:
            log.info("  %s — no columns present", grp_name)
            continue
        non_null = df[present].notna().all(axis=1).sum()
        log.info("  %s — rows with ALL cols non-null: %d / %d", grp_name, non_null, len(df))
        for col in present:
            null_rate = df[col].isna().mean()
            if null_rate > 0:
                log.info("    %-40s null_rate=%.3f", col, null_rate)
            else:
                log.info("    %-40s null_rate=0.000", col)

    # Print sample row for Stephen Curry (201939)
    curry = df[df["player_id"] == 201939]
    if not curry.empty:
        log.info("--- Sample: Stephen Curry (201939) latest season ---")
        latest = curry.sort_values("season").iloc[-1]
        for k, v in latest.items():
            log.info("  %-40s = %s", k, v)
    else:
        # Fall back to Damian Lillard (203081)
        lillard = df[df["player_id"] == 203081]
        if not lillard.empty:
            log.info("--- Sample: Damian Lillard (203081) latest season ---")
            latest = lillard.sort_values("season").iloc[-1]
            for k, v in latest.items():
                log.info("  %-40s = %s", k, v)
        else:
            log.info("--- No known scorer found; first row sample ---")
            log.info(df.iloc[0].to_dict())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load each variant
    drives_df = load_variant(
        "Drives",
        VARIANTS["Drives"][0],
        VARIANTS["Drives"][1],
    )
    passing_df = load_variant(
        "Passing",
        VARIANTS["Passing"][0],
        VARIANTS["Passing"][1],
    )
    catchshoot_df = load_variant(
        "CatchShoot",
        VARIANTS["CatchShoot"][0],
        VARIANTS["CatchShoot"][1],
    )

    log.info("Raw row counts — Drives: %d | Passing: %d | CatchShoot: %d",
             len(drives_df), len(passing_df), len(catchshoot_df))

    # Derive features and merge
    out = derive_features(drives_df, passing_df, catchshoot_df)

    if out.empty:
        log.error("Empty output DataFrame — aborting without writing parquet.")
        sys.exit(1)

    # Write parquet (idempotent overwrite)
    out.to_parquet(str(OUT_PATH), index=False, engine="pyarrow")
    log.info("Written: %s  (%d rows x %d cols)", OUT_PATH, len(out), len(out.columns))

    print_diagnostics(out)


if __name__ == "__main__":
    main()
