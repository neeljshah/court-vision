#!/usr/bin/env python3
"""build_clutch_cv.py -- INT-23: Per-player clutch vs non-clutch CV intelligence.

Splits each game's tracking frames into:
  - clutch     : last 10% of frames (approximation -- scoreboard OCR confirmed broken)
  - non_clutch : first 80% of frames (middle 10% dropped as buffer)

Aggregates per-player CV features in each context, computes delta and z-score
across all games, then classifies each player as ELEVATOR / SHRINKER / NEUTRAL.

Outputs:
  data/intelligence/clutch_cv_split.parquet   -- per-player profiles
  data/intelligence/clutch_rankings.json      -- top 25 elevators/shrinkers/neutrals
  vault/Intelligence/Clutch_Atlas.md          -- human-readable atlas

Usage:
    python scripts/build_clutch_cv.py
    python scripts/build_clutch_cv.py --min-clutch-frames 50
    python scripts/build_clutch_cv.py --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT         = Path(r"C:\Users\neelj\nba-ai-system")
TRACKING_DIR = ROOT / "data" / "tracking"
INTEL_DIR    = ROOT / "data" / "intelligence"
VAULT_DIR    = ROOT / "vault" / "Intelligence"

OUT_PARQUET  = INTEL_DIR / "clutch_cv_split.parquet"
OUT_JSON     = INTEL_DIR / "clutch_rankings.json"
OUT_ATLAS    = VAULT_DIR / "Clutch_Atlas.md"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_TOTAL_ROWS        = 5_000   # skip tiny/incomplete games
MIN_CLUTCH_FRAMES     = 50      # floor per player for clutch signal
MIN_NON_CLUTCH_FRAMES = 200     # floor per player for non-clutch signal
CLUTCH_TAIL_PCT       = 0.10    # last 10% of frames
NON_CLUTCH_END_PCT    = 0.80    # first 80% of frames
BUFFER_PCT            = 0.10    # 10% middle buffer (80-90%) dropped

# CV features to compute per context (columns available in tracking_data.csv)
# Raw tracking columns available in all games without features.csv dependency
CV_FEATURES = {
    "velocity":           "avg_velocity",
    "acceleration":       "avg_acceleration",
    "ball_possession":    "ball_possession_rate",
    "distance_to_ball":   "avg_dist_to_ball",
    "dist_to_basket_ft":  "avg_dist_to_basket",
    "paint_touches":      "paint_touch_rate",
    "drive_flag":         "drive_rate",
    "off_ball_distance":  "avg_off_ball_dist",
    "team_spacing":       "avg_team_spacing",
    "vel_toward_basket":  "avg_vel_toward_basket",
    "dribble_count":      "avg_dribble_count",
    "jump_detected":      "jump_rate",
}

# Features interpreted as RATES (binary 0/1 mean or >0 rate)
RATE_FEATURES = {"ball_possession", "paint_touches", "drive_flag", "jump_detected"}

# Key usage features for ELEVATOR/SHRINKER classification
ELEVATOR_FEATURES = [
    "paint_touch_rate",
    "ball_possession_rate",
    "drive_rate",
    "avg_vel_toward_basket",
    "avg_velocity",
]

FEAT_COLS = list(CV_FEATURES.values())

# ---------------------------------------------------------------------------
# NBA personId resolver
# ---------------------------------------------------------------------------
_SUFFIX_RE = re.compile(r"\b(Jr\.?|Sr\.?|II|III|IV|V)\b\.?", flags=re.IGNORECASE)


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _build_resolver():
    """Build (cache_dict, resolve_fn) for name -> NBA personId lookup."""
    try:
        from nba_api.stats.static import players as _nba_players
        roster = _nba_players.get_players()
        by_norm: dict[str, list[dict]] = {}
        for p in roster:
            by_norm.setdefault(_norm_name(p["full_name"]), []).append(p)

        cache: dict[str, Optional[int]] = {}

        def resolve(name: Optional[str]) -> Optional[int]:
            if name is None:
                return None
            s = str(name)
            if not s or "#?" in s:
                return None
            if s in cache:
                return cache[s]
            try:
                res = _nba_players.find_players_by_full_name(s)
            except Exception:
                res = []
            if not res:
                res = by_norm.get(_norm_name(s), [])
            pid: Optional[int] = None
            if res:
                active = [p for p in res if p.get("is_active")]
                chosen = active[0] if active else res[0]
                pid = int(chosen["id"])
            cache[s] = pid
            return pid

        return cache, resolve
    except ImportError:
        cache: dict[str, Optional[int]] = {}

        def resolve(name: Optional[str]) -> Optional[int]:
            return None

        return cache, resolve


def _load_jersey_map(jm_path: Path) -> dict[str, str]:
    """Return {jersey_str: player_name} flat map.

    Handles both old format (flat dict) and new format (with by_team/flat keys).
    """
    if not jm_path.exists():
        return {}
    try:
        with open(jm_path, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict) and "flat" in raw:
            return {str(k): str(v) for k, v in raw["flat"].items()}
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, str)}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Per-game clutch frame split
# ---------------------------------------------------------------------------

def _identify_clutch_frames(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split df into (non_clutch_df, clutch_df) using last-10% approximation.

    Frame range is computed per game (max - min). Middle 10% buffer excluded.
    """
    frames  = pd.to_numeric(df["frame"], errors="coerce")
    f_min   = frames.min()
    f_max   = frames.max()
    f_range = f_max - f_min

    if f_range <= 0:
        return pd.DataFrame(), pd.DataFrame()

    clutch_start   = f_min + int(f_range * (1.0 - CLUTCH_TAIL_PCT))
    non_clutch_end = f_min + int(f_range * NON_CLUTCH_END_PCT)

    mask_clutch     = frames >= clutch_start
    mask_non_clutch = frames <= non_clutch_end

    return df[mask_non_clutch].copy(), df[mask_clutch].copy()


def _compute_cv_features(g: pd.DataFrame) -> dict:
    """Compute CV feature means for one player's frame subset."""
    out: dict[str, float] = {"n_frames": len(g)}

    for col, feat_name in CV_FEATURES.items():
        if col not in g.columns:
            out[feat_name] = np.nan
            continue

        vals = pd.to_numeric(g[col], errors="coerce")

        if col in RATE_FEATURES:
            if col == "paint_touches":
                out[feat_name] = float((vals > 0).mean()) if len(vals) > 0 else np.nan
            else:
                out[feat_name] = float(vals.fillna(0).mean())
        else:
            valid = vals.dropna()
            if col == "off_ball_distance":
                valid = valid[valid > 0]
            out[feat_name] = float(valid.mean()) if len(valid) > 0 else np.nan

    return out


def _process_one_game(game_id: str, resolve_fn, verbose: bool = False) -> list[dict]:
    """Load tracking_data.csv, split into clutch/non-clutch, aggregate per player.

    Returns list of row dicts, one per (game_id, player_name).
    """
    gdir    = TRACKING_DIR / game_id
    td_path = gdir / "tracking_data.csv"
    jm_path = gdir / "jersey_name_map.json"

    if not td_path.exists():
        return []

    try:
        df = pd.read_csv(td_path, low_memory=False)
    except Exception as e:
        if verbose:
            print("  [" + game_id + "] load error: " + str(e), file=sys.stderr)
        return []

    if len(df) < MIN_TOTAL_ROWS:
        return []

    jersey_map = _load_jersey_map(jm_path)

    nc_df, clutch_df = _identify_clutch_frames(df)

    if nc_df.empty or clutch_df.empty:
        return []

    group_key = "player_name" if "player_name" in df.columns else "player_id"

    rows = []

    for player_key, player_nc in nc_df.groupby(group_key, dropna=False):
        if not player_key or (isinstance(player_key, float) and np.isnan(player_key)):
            continue
        player_key_str = str(player_key)
        if "#?" in player_key_str or player_key_str.strip() == "":
            continue

        person_id = resolve_fn(player_key_str)

        player_clutch = clutch_df[clutch_df[group_key] == player_key]

        n_nc     = len(player_nc)
        n_clutch = len(player_clutch)

        if n_clutch < MIN_CLUTCH_FRAMES or n_nc < MIN_NON_CLUTCH_FRAMES:
            continue

        nc_feats     = _compute_cv_features(player_nc)
        clutch_feats = _compute_cv_features(player_clutch)

        # Get team info safely
        if "team_abbrev" in player_nc.columns and len(player_nc) > 0:
            mode_res = player_nc["team_abbrev"].dropna().mode()
            team = str(mode_res.iloc[0]) if len(mode_res) > 0 else ""
        else:
            team = ""

        if "jersey_number" in player_nc.columns and player_nc["jersey_number"].notna().any():
            mode_res = player_nc["jersey_number"].dropna().mode()
            jersey = str(int(mode_res.iloc[0])) if len(mode_res) > 0 else ""
        else:
            jersey = ""

        display_name = player_key_str
        if jersey and display_name.endswith("#?"):
            display_name = jersey_map.get(jersey, player_key_str)

        row = {
            "game_id":             game_id,
            "player_name":         display_name,
            "nba_person_id":       person_id,
            "team":                team,
            "jersey":              jersey,
            "n_clutch_frames":     n_clutch,
            "n_non_clutch_frames": n_nc,
        }

        for feat in FEAT_COLS:
            row["clutch_"     + feat] = clutch_feats.get(feat, np.nan)
            row["non_clutch_" + feat] = nc_feats.get(feat, np.nan)

        rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Cross-game aggregation
# ---------------------------------------------------------------------------

def _build_player_profiles(game_rows: list[dict]) -> pd.DataFrame:
    """Aggregate per-game rows into per-player clutch profiles with delta + z."""
    if not game_rows:
        return pd.DataFrame()

    gdf = pd.DataFrame(game_rows)

    def canonical_name(subdf: pd.DataFrame) -> str:
        names = subdf["player_name"].dropna()
        names = names[~names.str.contains(r"#\?", regex=True)]
        if len(names) == 0:
            return str(subdf["player_name"].iloc[0])
        return str(names.mode().iloc[0])

    rows = []

    # Players with resolved personId
    has_pid = gdf["nba_person_id"].notna().any()
    if has_pid:
        pid_groups = gdf[gdf["nba_person_id"].notna()].groupby("nba_person_id")
        for pid, sub in pid_groups:
            n_games        = len(sub)
            tot_clutch     = int(sub["n_clutch_frames"].sum())
            tot_non_clutch = int(sub["n_non_clutch_frames"].sum())
            name           = canonical_name(sub)
            mode_res       = sub["team"].dropna().mode()
            team           = str(mode_res.iloc[0]) if len(mode_res) > 0 else ""

            row = {
                "player_id":           int(pid),
                "player_name":         name,
                "team":                team,
                "n_games":             n_games,
                "n_clutch_frames":     tot_clutch,
                "n_non_clutch_frames": tot_non_clutch,
            }
            for feat in FEAT_COLS:
                c_vals  = pd.to_numeric(sub["clutch_"     + feat], errors="coerce").dropna()
                nc_vals = pd.to_numeric(sub["non_clutch_" + feat], errors="coerce").dropna()
                row["clutch_"     + feat] = float(c_vals.mean())  if len(c_vals)  > 0 else np.nan
                row["non_clutch_" + feat] = float(nc_vals.mean()) if len(nc_vals) > 0 else np.nan
            rows.append(row)

        unresolved = gdf[gdf["nba_person_id"].isna()]
    else:
        unresolved = gdf

    # Players without resolved personId -- group by name
    for name, sub in unresolved.groupby("player_name"):
        if "#?" in str(name):
            continue
        n_games        = len(sub)
        tot_clutch     = int(sub["n_clutch_frames"].sum())
        tot_non_clutch = int(sub["n_non_clutch_frames"].sum())
        mode_res       = sub["team"].dropna().mode()
        team           = str(mode_res.iloc[0]) if len(mode_res) > 0 else ""

        row = {
            "player_id":           None,
            "player_name":         str(name),
            "team":                team,
            "n_games":             n_games,
            "n_clutch_frames":     tot_clutch,
            "n_non_clutch_frames": tot_non_clutch,
        }
        for feat in FEAT_COLS:
            c_vals  = pd.to_numeric(sub["clutch_"     + feat], errors="coerce").dropna()
            nc_vals = pd.to_numeric(sub["non_clutch_" + feat], errors="coerce").dropna()
            row["clutch_"     + feat] = float(c_vals.mean())  if len(c_vals)  > 0 else np.nan
            row["non_clutch_" + feat] = float(nc_vals.mean()) if len(nc_vals) > 0 else np.nan
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    pdf = pd.DataFrame(rows)

    # Compute delta and z-score per feature
    for feat in FEAT_COLS:
        delta = pd.to_numeric(pdf["clutch_" + feat], errors="coerce") - \
                pd.to_numeric(pdf["non_clutch_" + feat], errors="coerce")
        pdf["delta_" + feat] = delta

        mu    = delta.mean()
        sigma = delta.std()
        if sigma > 0:
            pdf["z_" + feat] = (delta - mu) / sigma
        else:
            pdf["z_" + feat] = 0.0

    return pdf


# ---------------------------------------------------------------------------
# Clutch classification
# ---------------------------------------------------------------------------

def _classify_player(row: pd.Series) -> str:
    """Return ELEVATOR / SHRINKER / NEUTRAL based on z-score votes."""
    elevator_votes = 0
    shrinker_votes = 0
    total_valid    = 0

    for feat in ELEVATOR_FEATURES:
        z_col = "z_" + feat
        if z_col not in row.index:
            continue
        z = row[z_col]
        if not np.isfinite(z):
            continue
        total_valid += 1
        if z > 0.5:
            elevator_votes += 1
        elif z < -0.5:
            shrinker_votes += 1

    if total_valid == 0:
        return "NEUTRAL"
    if elevator_votes >= 3 and elevator_votes > shrinker_votes:
        return "ELEVATOR"
    if shrinker_votes >= 3 and shrinker_votes > elevator_votes:
        return "SHRINKER"
    return "NEUTRAL"


def _top_feature(row: pd.Series, direction: str = "up") -> tuple:
    """Find the feature with highest absolute z-score in given direction."""
    best_feat = "--"
    best_z    = 0.0
    for feat in FEAT_COLS:
        z_col = "z_" + feat
        if z_col not in row.index:
            continue
        z = row[z_col]
        if not np.isfinite(z):
            continue
        if direction == "up" and z > best_z:
            best_z    = z
            best_feat = feat
        elif direction == "down" and z < best_z:
            best_z    = z
            best_feat = feat
    return best_feat, best_z


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

def _build_rankings(pdf: pd.DataFrame) -> dict:
    """Build top-25 elevators / shrinkers / neutrals ranking dict."""
    if pdf.empty:
        return {"elevators": [], "shrinkers": [], "neutrals": []}

    pdfx = pdf.copy()
    pdfx["clutch_class"] = pdfx.apply(_classify_player, axis=1)

    z_cols = ["z_" + f for f in ELEVATOR_FEATURES if "z_" + f in pdfx.columns]
    pdfx["elevator_score"] = pdfx[z_cols].mean(axis=1)

    elevators = pdfx[pdfx["clutch_class"] == "ELEVATOR"].sort_values("elevator_score", ascending=False)
    shrinkers = pdfx[pdfx["clutch_class"] == "SHRINKER"].sort_values("elevator_score", ascending=True)
    neutrals  = pdfx[pdfx["clutch_class"] == "NEUTRAL"].sort_values("n_clutch_frames", ascending=False)

    def to_records(subdf: pd.DataFrame, top_n: int = 25, direction: str = "up") -> list:
        recs = []
        for _, row in subdf.head(top_n).iterrows():
            top_feat, top_z = _top_feature(row, direction=direction)
            rec = {
                "player_name":           row.get("player_name", ""),
                "player_id":             int(row["player_id"]) if pd.notna(row.get("player_id")) else None,
                "team":                  row.get("team", ""),
                "n_clutch_frames":       int(row["n_clutch_frames"]),
                "n_non_clutch_frames":   int(row["n_non_clutch_frames"]),
                "n_games":               int(row["n_games"]),
                "clutch_class":          row["clutch_class"],
                "elevator_score":        round(float(row["elevator_score"]), 3) if np.isfinite(row["elevator_score"]) else None,
                "top_feature":           top_feat,
                "top_z":                 round(float(top_z), 3) if np.isfinite(top_z) else None,
            }
            # Key deltas
            for delta_feat in ["ball_possession_rate", "paint_touch_rate", "drive_rate", "avg_velocity"]:
                col = "delta_" + delta_feat
                rec["delta_" + delta_feat] = round(float(row[col]), 4) if col in row.index and np.isfinite(row[col]) else None
            recs.append(rec)
        return recs

    return {
        "elevators": to_records(elevators, 25, "up"),
        "shrinkers": to_records(shrinkers, 25, "down"),
        "neutrals":  to_records(neutrals,  25, "up"),
    }


def _build_atlas(pdf: pd.DataFrame, rankings: dict,
                 total_clutch: int, total_non_clutch: int,
                 n_players: int) -> str:
    """Generate the Clutch_Atlas.md content."""
    avg_clutch = total_clutch / n_players if n_players > 0 else 0

    elevators = rankings.get("elevators", [])
    shrinkers = rankings.get("shrinkers", [])

    def fmt_table(players: list, direction: str) -> str:
        header = "| Player | Team | Games | Top Feature | z | Interp |"
        sep    = "|---|---|---|---|---|---|"
        rows   = [header, sep]
        for p in players[:10]:
            feat  = p["top_feature"].replace("_", " ")
            z_val = p["top_z"] or 0.0
            sign  = "up" if direction == "up" else "down"
            interp = sign + " " + feat + " in clutch"
            rows.append(
                "| " + p["player_name"] + " | " + p["team"] + " | "
                + str(p["n_games"]) + " | " + feat + " | "
                + str(round(z_val, 2)) + " | " + interp + " |"
            )
        return "\n".join(rows)

    notable = []
    if elevators:
        e = elevators[0]
        ef = e["top_feature"].replace("_", " ")
        notable.append(
            "**" + e["player_name"] + " (" + e["team"] + ")** is the strongest clutch ELEVATOR. "
            + "Their `" + ef + "` rises z=" + str(e["top_z"]) + " in clutch situations across "
            + str(e["n_games"]) + " tracked games."
        )
    if len(elevators) >= 2:
        e2 = elevators[1]
        ef2 = e2["top_feature"].replace("_", " ")
        notable.append(
            "**" + e2["player_name"] + " (" + e2["team"] + ")** also elevates consistently "
            + "-- `" + ef2 + "` z=" + str(e2["top_z"]) + ", suggesting a strong late-game role."
        )
    if shrinkers:
        s = shrinkers[0]
        sf = s["top_feature"].replace("_", " ")
        notable.append(
            "**" + s["player_name"] + " (" + s["team"] + ")** shows the strongest SHRINKAGE. "
            + "`" + sf + "` drops z=" + str(s["top_z"]) + " -- usage collapses under pressure."
        )
    if len(shrinkers) >= 2:
        s2 = shrinkers[1]
        sf2 = s2["top_feature"].replace("_", " ")
        notable.append(
            "**" + s2["player_name"] + " (" + s2["team"] + ")** also shrinks (z="
            + str(s2["top_z"]) + " on `" + sf2 + "`)."
        )
    if len(elevators) >= 5:
        e5 = elevators[4]
        notable.append(
            "**" + e5["player_name"] + " (" + e5["team"] + ")** rounds out the top-5 elevators; "
            + "strong live OVER candidate in close 4th quarters."
        )

    notable_md = "\n".join("- " + n for n in notable) if notable else "- Insufficient data for notable findings."

    n_elev = len(elevators)
    n_shrk = len(shrinkers)

    atlas = (
        "# CV Clutch vs Non-Clutch Atlas\n\n"
        "## Methodology\n"
        "- **Clutch frames**: last 10% of game frames (approximation -- scoreboard OCR is 100% broken per audits; "
        "true last-5-min + margin < 5 not available)\n"
        "- **Non-clutch frames**: first 80% of game frames (middle 10% buffer excluded to avoid transition noise)\n"
        "- **Player floor**: >= " + str(MIN_CLUTCH_FRAMES) + " clutch frames AND >= " + str(MIN_NON_CLUTCH_FRAMES) + " non-clutch frames\n"
        "- **Aggregation**: per-game clutch means averaged across all CV-tracked games per player\n"
        "- **z-score**: cross-player standardization of (clutch_mean - non_clutch_mean) delta per feature\n"
        "- **Classification**: ELEVATOR = >=3/5 key usage features with z > 0.5; "
        "SHRINKER = >=3/5 with z < -0.5\n\n"
        "## Coverage\n"
        "- **Players profiled**: " + str(n_players) + "\n"
        "- **Total clutch frames**: " + str(total_clutch) + "\n"
        "- **Total non-clutch frames**: " + str(total_non_clutch) + "\n"
        "- **Avg clutch frames per player**: " + str(round(avg_clutch)) + "\n"
        "- **Elevators**: " + str(n_elev) + "  |  **Shrinkers**: " + str(n_shrk) + "\n\n"
        "## Top 10 Clutch ELEVATORS\n"
        + fmt_table(elevators, "up") + "\n\n"
        "## Top 10 Clutch SHRINKERS\n"
        + fmt_table(shrinkers, "down") + "\n\n"
        "## Notable Findings\n"
        + notable_md + "\n\n"
        "## Betting Implications\n"
        "- **Clutch elevator + close game expected** -> upsize Kelly on volume stats (points, assists, drives). "
        "CV signal shows these players actively seek the ball and attack late.\n"
        "- **Clutch shrinker + close game expected** -> downsize, lean UNDER on PTS/AST/paint touches. "
        "Usage collapses in pressure situations.\n"
        "- **Live betting**: H2 + close margin (< 5 pts) + elevator profile -> OVER bias on volume stats that elevate\n"
        "- **Avoid**: combining shrinker player with clutch-heavy game script -- "
        "prop lines set pre-game don't price in clutch role collapse\n"
        "- **Stack signal**: if both primary ball-handler and secondary mover are elevators, "
        "offensive clustering increases -- good for prop stacks\n\n"
        "## Honest Caveats\n"
        "- **Clutch detection is approximate**: 'last 10% of frames' is NOT real "
        "'last 5 min + margin < 5'. Until scoreboard OCR is fixed this is the best available approximation.\n"
        "- **Phantom slot risk**: players tracked as TEAM#? are excluded, but poorly-tracked players "
        "may contaminate neighboring slots and inflate z-scores.\n"
        "- **ISSUE-022 still open**: defender_distance = 200.0 sentinel corrupts nearest_opponent-based signals; "
        "those features are excluded from the clutch classification vote.\n"
        "- **Small N for some players**: players with few CV-tracked games may have unstable z-scores. "
        "Check n_games in rankings.\n"
        "- **Frame-rate variation**: games with clip truncations have proportionally smaller clutch windows. "
        "Last-10% is frame-count-relative, not absolute minutes.\n\n"
        "## Files\n"
        "- `data/intelligence/clutch_cv_split.parquet` -- full per-player profile table\n"
        "- `data/intelligence/clutch_rankings.json` -- top-25 elevators / shrinkers / neutrals\n"
        "- `scripts/build_clutch_cv.py` -- rebuild script\n\n"
        "*Generated by INT-23 Clutch CV Intelligence on 2026-05-28*\n"
    )
    return atlas


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    print("INT-23 Clutch CV Split -- building player profiles...")

    print("  Building NBA name resolver...")
    _cache, resolve_fn = _build_resolver()

    game_ids = sorted([
        d.name for d in TRACKING_DIR.iterdir()
        if d.is_dir() and d.name.startswith("002")
        and (d / "tracking_data.csv").exists()
        and (d / "jersey_name_map.json").exists()
    ])
    print("  Found " + str(len(game_ids)) + " game directories")

    all_rows: list = []
    skipped   = 0
    processed = 0

    for i, gid in enumerate(game_ids, 1):
        if args.verbose:
            print("  [" + str(i) + "/" + str(len(game_ids)) + "] " + gid + " ...", end=" ", flush=True)
        rows = _process_one_game(gid, resolve_fn, verbose=args.verbose)
        if rows:
            all_rows.extend(rows)
            processed += 1
            if args.verbose:
                print(str(len(rows)) + " player-contexts")
        else:
            skipped += 1
            if args.verbose:
                print("skipped")

    print("\n  Processed " + str(processed) + " games, skipped " + str(skipped))
    print("  Total per-game player rows: " + str(len(all_rows)))

    if not all_rows:
        print("ERROR: No data collected. Check tracking directory and MIN_TOTAL_ROWS threshold.")
        sys.exit(1)

    print("  Aggregating cross-game player profiles...")
    pdf = _build_player_profiles(all_rows)

    if pdf.empty:
        print("ERROR: Player profile aggregation yielded empty DataFrame.")
        sys.exit(1)

    pdf["clutch_class"] = pdf.apply(_classify_player, axis=1)

    n_players    = len(pdf)
    total_clutch = int(pdf["n_clutch_frames"].sum())
    total_nc     = int(pdf["n_non_clutch_frames"].sum())

    n_elev = int((pdf["clutch_class"] == "ELEVATOR").sum())
    n_shrk = int((pdf["clutch_class"] == "SHRINKER").sum())
    n_neut = int((pdf["clutch_class"] == "NEUTRAL").sum())

    print("\n  Players profiled:        " + str(n_players))
    print("  Total clutch frames:     " + str(total_clutch))
    print("  Total non-clutch frames: " + str(total_nc))
    print("  Elevators: " + str(n_elev) + "  |  Shrinkers: " + str(n_shrk) + "  |  Neutrals: " + str(n_neut))

    # Save parquet
    pdf.to_parquet(OUT_PARQUET, index=False)
    print("\n  Saved parquet: " + str(OUT_PARQUET))

    # Build and save rankings
    rankings = _build_rankings(pdf)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rankings, f, indent=2, default=str)
    print("  Saved rankings: " + str(OUT_JSON))

    # Build and save atlas
    atlas_content = _build_atlas(pdf, rankings, total_clutch, total_nc, n_players)
    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write(atlas_content)
    print("  Saved atlas: " + str(OUT_ATLAS))

    # Final report
    print("\n" + "=" * 70)
    print("INT-23 Clutch CV Split -- Final Report")
    print("=" * 70)
    print("\nCoverage")
    print("  Players profiled:        " + str(n_players))
    print("  Total clutch frames:     " + str(total_clutch))
    print("  Total non-clutch frames: " + str(total_nc))
    print("  Elevators / Shrinkers / Neutrals: " + str(n_elev) + " / " + str(n_shrk) + " / " + str(n_neut))

    print("\nTop 5 ELEVATORS (clutch features rise)")
    print("  Player                        Feature                      z     Story")
    print("  " + "-" * 76)
    for p in rankings["elevators"][:5]:
        feat  = p["top_feature"].replace("_", " ")
        z_val = p["top_z"] or 0.0
        story = "up " + feat + " (" + str(p["n_games"]) + " games)"
        print("  " + p["player_name"][:28].ljust(30) + feat[:28].ljust(30) + str(round(z_val, 2)).rjust(5) + "  " + story)

    print("\nTop 5 SHRINKERS (clutch features drop)")
    print("  Player                        Feature                      z     Story")
    print("  " + "-" * 76)
    for p in rankings["shrinkers"][:5]:
        feat  = p["top_feature"].replace("_", " ")
        z_val = p["top_z"] or 0.0
        story = "down " + feat + " (" + str(p["n_games"]) + " games)"
        print("  " + p["player_name"][:28].ljust(30) + feat[:28].ljust(30) + str(round(z_val, 2)).rjust(5) + "  " + story)

    print("\nFiles")
    print("  scripts/build_clutch_cv.py")
    print("  vault/Intelligence/Clutch_Atlas.md")
    print("  data/intelligence/clutch_cv_split.parquet")
    print("  data/intelligence/clutch_rankings.json")

    print("\nHow to use")
    print("  Pre-bet close games: check clutch_rankings.json elevators section")
    print("  Shrinker in expected close game -> downsize, lean UNDER on volume")
    print("  Live: H2 + close margin + elevator profile -> OVER bias on elevating stats")

    print("\nHonest Caveats")
    print("  - Clutch detection: last 10% of frames (NOT real last-5-min+margin<5)")
    print("  - Phantom slots may inflate signals for poorly-tracked players")
    print("  - ISSUE-022 defender_distance sentinel still open")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="INT-23 Clutch CV Split")
    parser.add_argument("--min-clutch-frames", type=int, default=MIN_CLUTCH_FRAMES,
                        help="Minimum clutch frames per player (default: " + str(MIN_CLUTCH_FRAMES) + ")")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose game-by-game progress")
    args = parser.parse_args()
    MIN_CLUTCH_FRAMES = args.min_clutch_frames
    main(args)
