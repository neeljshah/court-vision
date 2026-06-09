#!/usr/bin/env python3
"""build_quarter_momentum.py -- INT-41: Per-Quarter Momentum Intelligence.

Splits each game's tracking frames into Q1/Q2/Q3/Q4 using pbp_period from
possessions.csv where available, or frame-quartile fallback otherwise.

Computes per-(player, quarter) CV features, then aggregates across games to:
  - Build a Q1/Q2/Q3/Q4 profile per player
  - Classify each player as CLOSER / FAST_STARTER / FLAT / VARIABLE
  - Document the league-wide fatigue/momentum curve Q1->Q4

Outputs:
  data/intelligence/quarter_profiles.parquet   -- per-player Q1-Q4 means
  data/intelligence/quarter_signatures.json    -- {player: {Q1:..., closer_score, tag}}
  vault/Intelligence/Quarter_Momentum_Atlas.md -- human-readable atlas

Usage:
    python scripts/build_quarter_momentum.py
    python scripts/build_quarter_momentum.py --min-frames 30 --verbose
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

OUT_PARQUET  = INTEL_DIR / "quarter_profiles.parquet"
OUT_JSON     = INTEL_DIR / "quarter_signatures.json"
OUT_ATLAS    = VAULT_DIR / "Quarter_Momentum_Atlas.md"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_TOTAL_ROWS       = 2_000    # skip tiny/incomplete games
MIN_FRAMES_PER_QTR   = 30       # minimum frames for a (player, quarter) to count
MIN_GAMES_FOR_PROFILE = 3       # minimum games across which to aggregate

QUARTERS = [1, 2, 3, 4]

# CV features to compute per quarter (same raw columns as other INT scripts)
CV_FEATURES = {
    "velocity":          "avg_velocity",
    "dist_to_basket_ft": "avg_dist_to_basket",
    "paint_touches":     "paint_touch_rate",
    "drive_flag":        "drive_rate",
    "off_ball_distance": "avg_off_ball_dist",
    "team_spacing":      "avg_team_spacing",
    "ball_possession":   "ball_possession_rate",
    "vel_toward_basket": "avg_vel_toward_basket",
}

RATE_FEATURES  = {"ball_possession", "paint_touches", "drive_flag"}
MEAN_FEATURES  = {"velocity", "dist_to_basket_ft", "off_ball_distance",
                  "team_spacing", "vel_toward_basket"}

# Features used for closer_score computation (higher in Q4 = closer)
CLOSER_FEATURES = [
    "avg_velocity",
    "paint_touch_rate",
    "drive_rate",
    "avg_vel_toward_basket",
    "ball_possession_rate",
]

FEAT_NAMES = list(CV_FEATURES.values())

# ---------------------------------------------------------------------------
# Name normalization (shared with other INT scripts)
# ---------------------------------------------------------------------------
_SUFFIX_RE = re.compile(r"\b(Jr\.?|Sr\.?|II|III|IV|V)\b\.?", flags=re.IGNORECASE)


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


# ---------------------------------------------------------------------------
# Quarter assignment helpers
# ---------------------------------------------------------------------------

def _build_possession_quarter_map(poss_df: pd.DataFrame) -> Optional[dict[int, int]]:
    """Return {frame: quarter} boundary dict using pbp_period from possessions.

    For each possession with pbp_period populated, every frame in
    [start_frame, end_frame] gets that quarter label.
    Returns None if insufficient coverage.
    """
    if "pbp_period" not in poss_df.columns:
        return None

    poss_with_period = poss_df.dropna(subset=["pbp_period"]).copy()
    if len(poss_with_period) < 5:
        return None

    # Build sorted (start_frame, end_frame, period) triples
    intervals = []
    for _, row in poss_with_period.iterrows():
        try:
            sf  = int(row["start_frame"])
            ef  = int(row["end_frame"])
            per = int(float(row["pbp_period"]))
            if per < 1 or per > 4:
                continue
            intervals.append((sf, ef, per))
        except (ValueError, TypeError):
            continue

    if not intervals:
        return None

    # Sort by start_frame
    intervals.sort(key=lambda x: x[0])
    return intervals  # type: ignore[return-value]


def _assign_quarter_frame(frame: int, intervals, f_min: int, f_range: int) -> int:
    """Assign a quarter (1-4) to a given frame.

    Primary: linear scan over pbp_period intervals (from possessions).
    Fallback: quartile of frame position.
    """
    if intervals is not None:
        # Linear search — intervals is sorted by start_frame
        # Use last interval whose start_frame <= frame
        best_q = None
        for (sf, ef, per) in intervals:
            if sf <= frame:
                best_q = per
            else:
                break
        if best_q is not None:
            return best_q

    # Frame-quartile fallback
    if f_range <= 0:
        return 1
    pos = (frame - f_min) / f_range  # 0.0 -> 1.0
    if pos < 0.25:
        return 1
    elif pos < 0.50:
        return 2
    elif pos < 0.75:
        return 3
    else:
        return 4


# ---------------------------------------------------------------------------
# Per-game processing
# ---------------------------------------------------------------------------

def _compute_cv_features_for_group(g: pd.DataFrame) -> dict:
    """Compute CV feature means for one (player, quarter) frame group."""
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


def _process_one_game(game_id: str, verbose: bool = False) -> list[dict]:
    """Load tracking + possessions for one game, return list of
    {game_id, player_id, player_name, team, quarter, n_frames, <features>} rows.
    """
    gdir    = TRACKING_DIR / game_id
    td_path = gdir / "tracking_data.csv"
    poss_path = gdir / "possessions.csv"

    if not td_path.exists():
        return []

    try:
        df = pd.read_csv(td_path, low_memory=False)
    except Exception as e:
        if verbose:
            print(f"  [{game_id}] load error: {e}", file=sys.stderr)
        return []

    if len(df) < MIN_TOTAL_ROWS:
        if verbose:
            print(f"  [{game_id}] too small ({len(df)} rows), skipping")
        return []

    # Load possessions for pbp_period quarter map
    intervals = None
    if poss_path.exists():
        try:
            poss_df = pd.read_csv(poss_path, low_memory=False)
            intervals = _build_possession_quarter_map(poss_df)
        except Exception:
            intervals = None

    # Frame range for fallback — coerce non-numeric frame values to NaN
    df = df.copy()
    df["_frame_num"] = pd.to_numeric(df["frame"], errors="coerce")
    valid_frames = df["_frame_num"].dropna()
    if len(valid_frames) == 0:
        return []
    f_min   = int(valid_frames.min())
    f_range = int(valid_frames.max()) - f_min

    # Assign quarter to each row (NaN frames default to Q1)
    df["_quarter"] = df["_frame_num"].apply(
        lambda f: _assign_quarter_frame(int(f) if pd.notna(f) else f_min,
                                        intervals, f_min, f_range)
    )

    # Resolve player names — prefer player_name column
    if "player_name" not in df.columns:
        df["player_name"] = df["player_id"].astype(str)

    rows = []
    for (player_id, quarter), grp in df.groupby(["player_id", "_quarter"]):
        if len(grp) < MIN_FRAMES_PER_QTR:
            continue

        feats = _compute_cv_features_for_group(grp)
        player_name = (
            grp["player_name"].dropna().mode().iloc[0]
            if "player_name" in grp.columns and grp["player_name"].notna().any()
            else str(player_id)
        )
        team = (
            grp["team"].dropna().mode().iloc[0]
            if "team" in grp.columns and grp["team"].notna().any()
            else "UNK"
        )

        rows.append({
            "game_id":     game_id,
            "player_id":   player_id,
            "player_name": player_name,
            "team":        team,
            "quarter":     int(quarter),
            **feats,
        })

    return rows


# ---------------------------------------------------------------------------
# Cross-game aggregation
# ---------------------------------------------------------------------------

def _aggregate_player_quarter_profiles(game_rows: list[dict]) -> pd.DataFrame:
    """Aggregate across games -> one row per (player_name, quarter).

    player_id is a 1-10 slot number that repeats each game, so cross-game
    identity is resolved via player_name.  Phantom slots (containing '#?')
    are bucketed together and kept for league averages but excluded from
    close/starter classification later.
    """
    if not game_rows:
        return pd.DataFrame()

    df = pd.DataFrame(game_rows)
    feat_cols = FEAT_NAMES

    # Resolve a canonical name key: use player_name, fall back to slot-based label
    df["_name_key"] = df["player_name"].fillna("").apply(
        lambda n: n if n and "#?" not in n else f"slot_{n}"
    )
    # For phantom names like "MIA#?", group them all as "phantom"
    df["_name_key"] = df["_name_key"].apply(
        lambda n: "phantom_slot" if "#?" in str(n) else n
    )

    agg_rows = []
    for (name_key, quarter), grp in df.groupby(["_name_key", "quarter"]):
        n_games = grp["game_id"].nunique()
        if n_games < 1:
            continue

        # Best resolved player_name
        names = grp["player_name"].dropna()
        valid_names = names[~names.str.contains(r"#\?", na=False)]
        player_name = valid_names.mode().iloc[0] if len(valid_names) > 0 else name_key

        # Most common slot player_id (for parquet join convenience)
        player_id = grp["player_id"].mode().iloc[0] if "player_id" in grp.columns else -1

        team = grp["team"].dropna().mode().iloc[0] if grp["team"].notna().any() else "UNK"

        row: dict = {
            "player_id":   player_id,
            "player_name": player_name,
            "name_key":    name_key,
            "team":        team,
            "quarter":     int(quarter),
            "n_games":     n_games,
            "total_frames": int(grp["n_frames"].sum()),
        }
        for fc in feat_cols:
            if fc in grp.columns:
                row[fc] = float(grp[fc].mean(skipna=True))
            else:
                row[fc] = np.nan

        agg_rows.append(row)

    if not agg_rows:
        return pd.DataFrame()

    return pd.DataFrame(agg_rows)


# ---------------------------------------------------------------------------
# Closer / fast-starter classification
# ---------------------------------------------------------------------------

def _compute_closer_scores(profiles_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot to wide (one row per player), compute closer_score, classify.

    Uses name_key (resolved player name) as cross-game identity.
    Returns a DataFrame with per-player Q1-Q4 feature means, closer_score, tag.
    """
    group_col = "name_key" if "name_key" in profiles_df.columns else "player_id"

    # Exclude phantom slots from closer classification
    if group_col == "name_key":
        # Exclude phantom slots and bare slot-number keys (e.g. "3", "10")
        import re as _re
        profiles_df = profiles_df[
            (profiles_df["name_key"] != "phantom_slot") &
            (~profiles_df["name_key"].astype(str).str.match(r"^\d+$"))
        ].copy()

    # Require >= MIN_GAMES_FOR_PROFILE games for Q1 (most common quarter)
    # Q4 threshold is 1 (many clips are partial games; Q4 data is sparse)
    MIN_Q4_GAMES = 1
    valid_players = set()
    for nk, grp in profiles_df.groupby(group_col):
        quarters_seen = set(grp["quarter"].tolist())
        games_q1 = grp[grp["quarter"] == 1]["n_games"].sum() if 1 in quarters_seen else 0
        games_q4 = grp[grp["quarter"] == 4]["n_games"].sum() if 4 in quarters_seen else 0
        if games_q1 >= MIN_GAMES_FOR_PROFILE and games_q4 >= MIN_Q4_GAMES:
            valid_players.add(nk)

    if not valid_players:
        return pd.DataFrame()

    sub = profiles_df[profiles_df[group_col].isin(valid_players)].copy()

    # Compute dataset std for each closer feature (for z-score)
    feat_stds: dict[str, float] = {}
    for feat in CLOSER_FEATURES:
        if feat in sub.columns:
            std = sub[feat].std(skipna=True)
            feat_stds[feat] = max(std, 1e-6)
        else:
            feat_stds[feat] = 1.0

    player_rows = []
    for nk, grp in sub.groupby(group_col):
        q_dict = {int(r["quarter"]): r for _, r in grp.iterrows()}
        if 1 not in q_dict or 4 not in q_dict:
            continue

        # Best name/team
        all_names = grp["player_name"].dropna()
        valid_names = all_names[~all_names.str.contains(r"#\?", na=False)]
        player_name = valid_names.mode().iloc[0] if len(valid_names) > 0 else str(nk)
        team        = grp["team"].dropna().mode().iloc[0] if grp["team"].notna().any() else "UNK"
        pid         = grp["player_id"].mode().iloc[0] if "player_id" in grp.columns else nk

        q1 = q_dict[1]
        q4 = q_dict[4]

        row: dict = {
            "player_id":   pid,
            "player_name": player_name,
            "name_key":    nk,
            "team":        team,
            "n_games_q1":  int(q1.get("n_games", 0)),
            "n_games_q4":  int(q4.get("n_games", 0)),
        }

        # Per-quarter per-feature means
        for q_num in QUARTERS:
            if q_num in q_dict:
                q_row = q_dict[q_num]
                for feat in FEAT_NAMES:
                    if feat in q_row:
                        row[f"Q{q_num}_{feat}"] = q_row[feat]
                    else:
                        row[f"Q{q_num}_{feat}"] = np.nan
            else:
                for feat in FEAT_NAMES:
                    row[f"Q{q_num}_{feat}"] = np.nan

        # Closer score: mean z-score of (Q4 - Q1) across closer features
        delta_zs = []
        dominant_feat = None
        best_dz = 0.0
        for feat in CLOSER_FEATURES:
            v1 = q1.get(feat, np.nan)
            v4 = q4.get(feat, np.nan)
            if pd.isna(v1) or pd.isna(v4):
                continue
            dz = (v4 - v1) / feat_stds.get(feat, 1.0)
            delta_zs.append(dz)
            if abs(dz) > abs(best_dz):
                best_dz    = dz
                dominant_feat = feat

        closer_score = float(np.mean(delta_zs)) if delta_zs else 0.0
        row["closer_score"]    = round(closer_score, 4)
        row["dominant_feature"] = dominant_feat or "n/a"

        # Classification
        if closer_score > 0.25:
            tag = "CLOSER"
        elif closer_score < -0.25:
            tag = "FAST_STARTER"
        else:
            # Check variance across Q1-Q4
            velocity_col = "avg_velocity"
            vel_vals = [q_dict[q].get(velocity_col, np.nan) for q in QUARTERS if q in q_dict]
            vel_vals = [v for v in vel_vals if not pd.isna(v)]
            if len(vel_vals) >= 3 and np.std(vel_vals) > feat_stds.get(velocity_col, 1.0) * 0.3:
                tag = "VARIABLE"
            else:
                tag = "FLAT"

        row["tag"] = tag
        player_rows.append(row)

    if not player_rows:
        return pd.DataFrame()

    return pd.DataFrame(player_rows)


# ---------------------------------------------------------------------------
# League-wide quarter patterns
# ---------------------------------------------------------------------------

def _compute_league_patterns(profiles_df: pd.DataFrame) -> dict:
    """Compute league-average CV features per quarter."""
    patterns: dict[str, dict] = {}

    for q in QUARTERS:
        q_rows = profiles_df[profiles_df["quarter"] == q]
        if len(q_rows) == 0:
            patterns[f"Q{q}"] = {}
            continue
        q_stats: dict[str, float] = {}
        for feat in FEAT_NAMES:
            if feat in q_rows.columns:
                q_stats[feat] = round(float(q_rows[feat].mean(skipna=True)), 4)
        patterns[f"Q{q}"] = q_stats

    # Compute pct change Q1->Q4 for key features
    pct_changes: dict[str, Optional[float]] = {}
    for feat in FEAT_NAMES:
        v1 = patterns.get("Q1", {}).get(feat)
        v4 = patterns.get("Q4", {}).get(feat)
        if v1 is not None and v4 is not None and abs(v1) > 1e-6:
            pct_changes[feat] = round((v4 - v1) / abs(v1) * 100, 2)
        else:
            pct_changes[feat] = None

    return {"per_quarter": patterns, "q1_to_q4_pct_change": pct_changes}


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_parquet(profiles_df: pd.DataFrame, wide_df: pd.DataFrame) -> None:
    """Write quarter_profiles.parquet."""
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    profiles_df.to_parquet(OUT_PARQUET, index=False)
    print(f"  Wrote: {OUT_PARQUET} ({len(profiles_df)} rows)")


def _write_json(wide_df: pd.DataFrame, league_patterns: dict) -> None:
    """Write quarter_signatures.json."""
    signatures: dict = {
        "generated": pd.Timestamp.now().isoformat(),
        "league_patterns": league_patterns,
        "players": {},
    }

    if len(wide_df) == 0:
        INTEL_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(signatures, f, indent=2)
        return

    for _, row in wide_df.iterrows():
        pname = str(row.get("player_name", row["player_id"]))
        entry: dict = {
            "player_id":       row["player_id"],
            "player_name":     pname,
            "team":            row.get("team", ""),
            "n_games_q1":      row.get("n_games_q1", 0),
            "n_games_q4":      row.get("n_games_q4", 0),
            "closer_score":    row.get("closer_score", 0.0),
            "tag":             row.get("tag", "FLAT"),
            "dominant_feature": row.get("dominant_feature", "n/a"),
            "quarter_profiles": {},
        }
        for q in QUARTERS:
            q_feats: dict[str, Optional[float]] = {}
            for feat in FEAT_NAMES:
                col = f"Q{q}_{feat}"
                val = row.get(col, np.nan)
                q_feats[feat] = None if pd.isna(val) else round(float(val), 4)
            entry["quarter_profiles"][f"Q{q}"] = q_feats
        signatures["players"][pname] = entry

    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(signatures, f, indent=2)
    print(f"  Wrote: {OUT_JSON} ({len(signatures['players'])} players)")


def _write_atlas(
    wide_df: pd.DataFrame,
    league_patterns: dict,
    n_pbp_games: int,
    n_fallback_games: int,
    n_total_games: int,
) -> None:
    """Write Quarter_Momentum_Atlas.md."""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    pbp_pct = round(n_pbp_games / max(n_total_games, 1) * 100, 1)

    closers     = wide_df[wide_df["tag"] == "CLOSER"].sort_values("closer_score", ascending=False)
    starters    = wide_df[wide_df["tag"] == "FAST_STARTER"].sort_values("closer_score", ascending=True)
    flat_count  = len(wide_df[wide_df["tag"] == "FLAT"])
    var_count   = len(wide_df[wide_df["tag"] == "VARIABLE"])

    # League velocity curve
    lp = league_patterns.get("per_quarter", {})
    pct = league_patterns.get("q1_to_q4_pct_change", {})
    vel_q1 = lp.get("Q1", {}).get("avg_velocity", None)
    vel_q2 = lp.get("Q2", {}).get("avg_velocity", None)
    vel_q3 = lp.get("Q3", {}).get("avg_velocity", None)
    vel_q4 = lp.get("Q4", {}).get("avg_velocity", None)
    paint_q1 = lp.get("Q1", {}).get("paint_touch_rate", None)
    paint_q4 = lp.get("Q4", {}).get("paint_touch_rate", None)

    def fmt(v) -> str:
        return f"{v:.4f}" if v is not None else "n/a"

    def fmt_pct(v) -> str:
        if v is None:
            return "n/a"
        sign = "+" if v > 0 else ""
        return f"{sign}{v:.1f}%"

    # Top 10 tables
    def player_table(df_sub: pd.DataFrame, n: int = 10) -> str:
        rows = []
        for _, r in df_sub.head(n).iterrows():
            rows.append(
                f"| {r['player_name']} | {r.get('team','?')} "
                f"| {r['closer_score']:+.3f} | {r.get('dominant_feature','n/a')} "
                f"| Q1={fmt(r.get('Q1_avg_velocity'))} Q4={fmt(r.get('Q4_avg_velocity'))} |"
            )
        return "\n".join(rows) if rows else "| (none) | | | | |"

    lines = [
        f"# INT-41 Per-Quarter Momentum Atlas",
        f"",
        f"_Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}_",
        f"",
        f"Splits CV tracking into Q1/Q2/Q3/Q4. Primary source: `pbp_period` from possessions.",
        f"Fallback: frame-quartile (25/50/75/100% of frame range).",
        f"",
        f"## Coverage",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total games processed | {n_total_games} |",
        f"| pbp_period used (primary) | {n_pbp_games} ({pbp_pct}%) |",
        f"| Frame-quartile fallback | {n_fallback_games} |",
        f"| Players profiled (Q1+Q4 ≥3 games) | {len(wide_df)} |",
        f"| Q4 Closers | {len(closers)} |",
        f"| Fast Starters | {len(starters)} |",
        f"| Flat | {flat_count} |",
        f"| Variable | {var_count} |",
        f"",
        f"## League-Wide Quarter Fatigue Curve",
        f"",
        f"| Feature | Q1 | Q2 | Q3 | Q4 | Q1->Q4 Δ |",
        f"|---------|----|----|----|----|---------|",
        f"| avg_velocity | {fmt(vel_q1)} | {fmt(vel_q2)} | {fmt(vel_q3)} | {fmt(vel_q4)} | {fmt_pct(pct.get('avg_velocity'))} |",
        f"| paint_touch_rate | {fmt(paint_q1)} | {fmt(lp.get('Q2',{}).get('paint_touch_rate'))} | {fmt(lp.get('Q3',{}).get('paint_touch_rate'))} | {fmt(paint_q4)} | {fmt_pct(pct.get('paint_touch_rate'))} |",
        f"| drive_rate | {fmt(lp.get('Q1',{}).get('drive_rate'))} | {fmt(lp.get('Q2',{}).get('drive_rate'))} | {fmt(lp.get('Q3',{}).get('drive_rate'))} | {fmt(lp.get('Q4',{}).get('drive_rate'))} | {fmt_pct(pct.get('drive_rate'))} |",
        f"| avg_off_ball_dist | {fmt(lp.get('Q1',{}).get('avg_off_ball_dist'))} | {fmt(lp.get('Q2',{}).get('avg_off_ball_dist'))} | {fmt(lp.get('Q3',{}).get('avg_off_ball_dist'))} | {fmt(lp.get('Q4',{}).get('avg_off_ball_dist'))} | {fmt_pct(pct.get('avg_off_ball_dist'))} |",
        f"",
        f"## Top 10 Q4 Closers",
        f"",
        f"Players whose velocity/activity **rises** from Q1 to Q4 (positive closer_score).",
        f"",
        f"| Player | Team | closer_score | Dominant Feature | Velocity Q1->Q4 |",
        f"|--------|------|-------------|-----------------|----------------|",
        player_table(closers, 10),
        f"",
        f"## Top 10 Fast Starters (Q4 Fade)",
        f"",
        f"Players whose velocity/activity **peaks in Q1** and fades by Q4 (negative closer_score).",
        f"",
        f"| Player | Team | closer_score | Dominant Feature | Velocity Q1->Q4 |",
        f"|--------|------|-------------|-----------------|----------------|",
        player_table(starters, 10),
        f"",
        f"## How to Use for Live Betting",
        f"",
        f"- **Q1 bets**: Fast Starters show peak activity — fade their Q2+ totals",
        f"- **Q4 bets**: Closers reliably elevate — consider prop overs for ball-dominant Q4 roles",
        f"- **Pre-game**: A FAST_STARTER on B2B rest (INT-22) = double-downsize Kelly",
        f"- **Cross-signal**: CLOSER tag + ELEVATOR from INT-23 (clutch) = strongest Q4 stack",
        f"- **Pace adjustment**: combine with INT-26 pace-adjusted CV — high-pace closers are elite",
        f"",
        f"## Cross-Reference",
        f"",
        f"| INT | Signal | Overlap |",
        f"|-----|--------|---------|",
        f"| INT-8 | H1/H2 split | Coarser version of Q1+Q2 vs Q3+Q4 |",
        f"| INT-23 | Clutch (last 10% frames) | Mostly Q4 — closers should overlap |",
        f"| INT-22 | Rest/fatigue | Fast starters + short rest = fade signal |",
        f"| INT-26 | Pace-adjusted CV | Pace normalizes velocity; combine for clean Q-curves |",
        f"",
        f"## Honest Caveats",
        f"",
        f"- `pbp_period` coverage is {pbp_pct}% of games — frame quartiles approximate for the rest",
        f"- Phantom slots (player_id int without name) inflate cross-quarter signals",
        f"- Short clips have less Q4 data — n_games_q4 is lower for late-game-only clips",
        f"- closer_score computed on velocity/paint/drive/vel_toward_basket/possession rates",
        f"- Q4 data quality degrades if games end in blowout (garbage-time tracking)",
        f"",
        f"---",
        f"_Source: `scripts/build_quarter_momentum.py` | INT-41_",
    ]

    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Wrote: {OUT_ATLAS}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="INT-41: Per-quarter CV momentum intelligence")
    parser.add_argument("--min-frames", type=int, default=MIN_FRAMES_PER_QTR,
                        help=f"Min frames per (player, quarter) [default: {MIN_FRAMES_PER_QTR}]")
    parser.add_argument("--min-games", type=int, default=MIN_GAMES_FOR_PROFILE,
                        help=f"Min games to include player in profile [default: {MIN_GAMES_FOR_PROFILE}]")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print("INT-41 Per-Quarter Momentum Intelligence")
    print("=" * 50)

    # Collect all game directories
    if not TRACKING_DIR.exists():
        print(f"ERROR: Tracking dir not found: {TRACKING_DIR}", file=sys.stderr)
        sys.exit(1)

    game_ids = sorted([
        d for d in os.listdir(TRACKING_DIR)
        if os.path.isdir(TRACKING_DIR / d)
    ])
    print(f"Found {len(game_ids)} game directories")

    # Per-game processing
    all_rows: list[dict] = []
    n_processed       = 0
    n_pbp_games       = 0
    n_fallback_games  = 0
    n_skipped         = 0

    for i, gid in enumerate(game_ids):
        gdir    = TRACKING_DIR / gid
        td_path = gdir / "tracking_data.csv"
        poss_path = gdir / "possessions.csv"

        if not td_path.exists():
            n_skipped += 1
            continue

        # Determine quarter-assignment method for stats
        used_pbp = False
        if poss_path.exists():
            try:
                poss_df = pd.read_csv(poss_path, low_memory=False)
                intervals = _build_possession_quarter_map(poss_df)
                used_pbp = intervals is not None
            except Exception:
                pass

        if used_pbp:
            n_pbp_games += 1
        else:
            n_fallback_games += 1

        rows = _process_one_game(gid, verbose=args.verbose)
        if rows:
            all_rows.extend(rows)
            n_processed += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(game_ids)}] processed={n_processed} rows={len(all_rows)}")

    print(f"Processed {n_processed} games ({n_pbp_games} pbp, {n_fallback_games} fallback, {n_skipped} skipped)")
    print(f"Total (game, player, quarter) rows: {len(all_rows)}")

    if not all_rows:
        print("No data collected — aborting", file=sys.stderr)
        sys.exit(1)

    # Aggregate per (player, quarter)
    print("Aggregating per-player quarter profiles...")
    profiles_df = _aggregate_player_quarter_profiles(all_rows)
    print(f"  Per-(player, quarter) rows: {len(profiles_df)}")
    gk = "name_key" if "name_key" in profiles_df.columns else "player_id"
    # Exclude phantom + bare slot-number keys for the diagnostic
    real_count = profiles_df[
        ~profiles_df[gk].astype(str).str.match(r"^\d+$") &
        (profiles_df[gk].astype(str) != "phantom_slot")
    ][gk].nunique()
    print(f"  Unique named players: {real_count}")

    # Closer score + classification
    print("Computing closer scores...")
    wide_df = _compute_closer_scores(profiles_df)
    print(f"  Players with Q1+Q4 profiles: {len(wide_df)}")

    if len(wide_df) > 0:
        tag_counts = wide_df["tag"].value_counts().to_dict()
        for tag, cnt in sorted(tag_counts.items()):
            print(f"    {tag}: {cnt}")

    # League patterns
    print("Computing league-wide patterns...")
    league_patterns = _compute_league_patterns(profiles_df)

    # Print summary to console
    lp = league_patterns.get("per_quarter", {})
    pct = league_patterns.get("q1_to_q4_pct_change", {})
    for feat in ["avg_velocity", "paint_touch_rate", "drive_rate"]:
        delta_pct = pct.get(feat)
        if delta_pct is not None:
            sign = "+" if delta_pct > 0 else ""
            print(f"  League {feat} Q1->Q4: {sign}{delta_pct:.1f}%")

    # Write outputs
    print("Writing outputs...")
    _write_parquet(profiles_df, wide_df)
    _write_json(wide_df, league_patterns)
    _write_atlas(
        wide_df,
        league_patterns,
        n_pbp_games=n_pbp_games,
        n_fallback_games=n_fallback_games,
        n_total_games=n_processed,
    )

    # Final console report
    print()
    print("=" * 50)
    print("INT-41 FINAL REPORT")
    print("=" * 50)
    print(f"Coverage:")
    print(f"  Players profiled (>=3 games Q1+Q4): {len(wide_df)}")
    print(f"  pbp_period coverage: {n_pbp_games}/{n_processed} ({round(n_pbp_games/max(n_processed,1)*100,1)}%)")
    print(f"  Frame-quartile fallback: {n_fallback_games} games")

    if len(wide_df) > 0:
        closers  = wide_df[wide_df["tag"] == "CLOSER"].sort_values("closer_score", ascending=False)
        starters = wide_df[wide_df["tag"] == "FAST_STARTER"].sort_values("closer_score", ascending=True)

        print()
        print("Top 5 Q4 Closers:")
        for _, r in closers.head(5).iterrows():
            score = r["closer_score"]
            feat  = r.get("dominant_feature", "n/a")
            print(f"  {r['player_name']:<24} score={score:+.3f}  dominant={feat}")

        print()
        print("Top 5 Fast Starters (Q4 fade):")
        for _, r in starters.head(5).iterrows():
            score = r["closer_score"]
            feat  = r.get("dominant_feature", "n/a")
            print(f"  {r['player_name']:<24} score={score:+.3f}  dominant={feat}")

    print()
    vel_pct = pct.get("avg_velocity")
    paint_pct = pct.get("paint_touch_rate")
    print(f"League velocity Q1->Q4: {'+' if vel_pct and vel_pct>0 else ''}{vel_pct:.1f}%" if vel_pct is not None else "League velocity: n/a")
    print(f"League paint_touch Q1->Q4: {'+' if paint_pct and paint_pct>0 else ''}{paint_pct:.1f}%" if paint_pct is not None else "League paint_touch: n/a")

    print()
    print("Files written:")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")

    print()
    print("How to use:")
    print("  Live Q1 bet: Identify closers vs starters before Q2/Q3/Q4 props")
    print("  Pre-bet: FAST_STARTER on B2B (INT-22) = double-downsize Kelly")
    print("  Stack: CLOSER + INT-23 ELEVATOR = strongest Q4 signal")


if __name__ == "__main__":
    main()
