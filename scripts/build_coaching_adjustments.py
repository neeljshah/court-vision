#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_coaching_adjustments.py — INT-34: Coaching Adjustment Detection Intelligence.

For each CV-quality game, detects whether the DEFENSIVE team's imposed behavioral
profile on opposing players shifted significantly from H1 to H2 — signaling a
mid-game scheme change.

Algorithm:
1. Split each game into H1 / H2 via possession-midpoint (or frame-midpoint fallback).
2. For each (game, opposing player): compute their CV features in H1 vs H2.
3. Normalize each feature deviation against their season baseline (z-score).
4. Per-game "adjustment score" = max |H2_imposed_mean - H1_imposed_mean| across features.
5. Tag as ADJUSTMENT GAME when score > 1.0σ.
6. Aggregate per defensive team: adjustment_frequency + typical direction.

Outputs:
  data/intelligence/coaching_adjustments.parquet
  data/intelligence/team_adjustment_tendencies.json
  vault/Intelligence/Coaching_Adjustments_Atlas.md

Usage:
  python scripts/build_coaching_adjustments.py
  python scripts/build_coaching_adjustments.py --threshold 1.0 --min-players 3
  python scripts/build_coaching_adjustments.py --games 0022500045,0022500049

Caveats:
  - H1/H2 split via possession-midpoint (not true halftime).
  - Season baseline = mean across ALL CV games (mild forward-leak).
  - Team assignment uses team_abbrev; falls back to 'green'/'white' color labels.
  - ISSUE-022: defender_distance=200.0 sentinel → NaN (same as INT-12).
  - Phantom player slots add noise to per-player profiles.
  - Per-team sample sizes are 4–20 games; interpret adjustment_frequency with caution.
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)

# Force UTF-8 stdout on Windows to avoid cp1252 failures with sigma/special chars
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKUP        = Path(r"C:\Users\neelj\nba-data-backup\tracking")
ROOT          = Path(r"C:\Users\neelj\nba-ai-system")
CV_PER_GAME   = ROOT / "data" / "player_cv_per_game.parquet"
CV_PER_PLAYER = ROOT / "data" / "player_cv_per_player.parquet"
OUT_PARQUET   = ROOT / "data" / "intelligence" / "coaching_adjustments.parquet"
OUT_JSON      = ROOT / "data" / "intelligence" / "team_adjustment_tendencies.json"
OUT_ATLAS     = ROOT / "vault" / "Intelligence" / "Coaching_Adjustments_Atlas.md"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ADJUSTMENT_THRESHOLD  = 1.0    # σ units; games with score > this = ADJUSTMENT GAME
MIN_PLAYERS_PER_HALF  = 3      # require at least this many opp-players per half

SENTINEL_FT           = 98.5   # spatial sentinels ≥ this → NaN
SENTINEL_PIXEL        = 195.0  # pixel-space sentinel (dist_to_basket_ft_fixed 200.0)
MIN_FRAMES_PLAYER     = 60     # min frames per player-half slot to count

# CV features with good coverage (≥80%) in 2024-25 tracking data
CORE_FEATURES = [
    "velocity",
    "nearest_opponent",     # raw defender distance proxy (pre-backfill games)
    "off_ball_distance",
    "team_spacing",
    "dist_to_basket_ft",
]

# Readable descriptions for direction labels
FEATURE_LABELS: dict[str, tuple[str, str]] = {
    "velocity":           ("faster tempo forced",    "slower tempo forced"),
    "nearest_opponent":   ("defenders backed off",   "tighter defender coverage"),
    "off_ball_distance":  ("wider spacing allowed",  "tighter off-ball coverage"),
    "team_spacing":       ("floor spread wider",     "floor spread tighter"),
    "dist_to_basket_ft":  ("pushed further out",     "drawn closer to basket"),
}


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _clean_series(s: pd.Series) -> pd.Series:
    """Replace tracking sentinels and non-positive values with NaN."""
    s = pd.to_numeric(s, errors="coerce")
    s = s.mask(s >= SENTINEL_FT)
    s = s.mask(s >= SENTINEL_PIXEL)
    s = s.mask(s <= 0)
    return s


def _load_tracking(game_id: str) -> Optional[pd.DataFrame]:
    """Load tracking_data.csv for game_id, apply homography-corrected merge."""
    tpath = BACKUP / game_id / "tracking_data.csv"
    if not tpath.exists():
        return None
    try:
        df = pd.read_csv(tpath, low_memory=False)
    except Exception as exc:
        print(f"  [{game_id}] read failed: {exc}", file=sys.stderr)
        return None

    if df.empty or "frame" not in df.columns:
        return None

    # Merge homography-corrected columns when available
    fix_path = BACKUP / game_id / "tracking_data_corrected.csv"
    if fix_path.exists():
        try:
            fix = pd.read_csv(fix_path, low_memory=False)
            fix_cols = ["frame", "player_id"]
            for c in ("dist_to_basket_ft_fixed",):
                if c in fix.columns:
                    fix_cols.append(c)
            if len(fix_cols) > 2:
                fix = fix[fix_cols].drop_duplicates(["frame", "player_id"])
                df = df.merge(fix, on=["frame", "player_id"], how="left")
                # Prefer fixed dist; null sentinel 200.0
                df.loc[df["dist_to_basket_ft_fixed"] >= 200.0,
                       "dist_to_basket_ft_fixed"] = np.nan
                df["dist_to_basket_ft"] = df["dist_to_basket_ft_fixed"].combine_first(
                    df.get("dist_to_basket_ft", pd.Series(np.nan, index=df.index))
                )
        except Exception:
            pass

    # Resolve team key — prefer team_abbrev, fall back to color label
    if "team_abbrev" in df.columns and df["team_abbrev"].notna().any():
        df["_team"] = df["team_abbrev"].where(df["team_abbrev"].notna(),
                                               df.get("team"))
    else:
        df["_team"] = df.get("team")

    # Coerce core features
    for feat in CORE_FEATURES:
        if feat in df.columns:
            df[feat] = _clean_series(df[feat])
        else:
            df[feat] = np.nan

    df["frame"]    = pd.to_numeric(df["frame"],    errors="coerce")
    if "possession_id" in df.columns:
        df["possession_id"] = pd.to_numeric(df["possession_id"], errors="coerce")

    return df.dropna(subset=["frame"])


def _halftime_split_frame(df: pd.DataFrame, game_id: str) -> Optional[int]:
    """Return the frame at which H2 begins.

    Priority:
    1. possessions.csv pbp_period: last frame of the last H1 possession
       (periods 1-2 = H1, periods 3-4 = H2).
    2. Possession-midpoint of tracking_data possession_id column.
    3. Frame-midpoint of tracking_data.
    """
    poss_path = BACKUP / game_id / "possessions.csv"
    if poss_path.exists():
        try:
            pos = pd.read_csv(poss_path, low_memory=False)
            if "pbp_period" in pos.columns and pos["pbp_period"].notna().any():
                pos["pbp_period"] = pd.to_numeric(pos["pbp_period"], errors="coerce")
                h1_poss = pos[pos["pbp_period"] <= 2]
                h2_poss = pos[pos["pbp_period"] >= 3]
                if not h1_poss.empty and not h2_poss.empty and "end_frame" in pos.columns:
                    last_h1_frame = pd.to_numeric(
                        h1_poss["end_frame"], errors="coerce"
                    ).max()
                    first_h2_frame = pd.to_numeric(
                        h2_poss["start_frame"], errors="coerce"
                    ).min()
                    if np.isfinite(last_h1_frame) and np.isfinite(first_h2_frame):
                        return int((last_h1_frame + first_h2_frame) / 2)
        except Exception:
            pass

    # Possession-midpoint fallback
    if "possession_id" in df.columns:
        pids = sorted(df["possession_id"].dropna().unique())
        if len(pids) >= 10:
            mid_pid = pids[len(pids) // 2]
            h1_frames = df[df["possession_id"] <= mid_pid]["frame"]
            h2_frames = df[df["possession_id"] >  mid_pid]["frame"]
            if not h1_frames.empty and not h2_frames.empty:
                return int((h1_frames.max() + h2_frames.min()) / 2)

    # Frame-midpoint last resort
    return int((df["frame"].min() + df["frame"].max()) / 2)


def _compute_half_cv(sub: pd.DataFrame) -> dict[str, float]:
    """Compute mean CV features for a player subset (one half)."""
    out: dict[str, float] = {}
    for feat in CORE_FEATURES:
        if feat in sub.columns:
            val = sub[feat].mean()
            if np.isfinite(val):
                out[feat] = float(val)
    return out


# ---------------------------------------------------------------------------
# Per-game adjustment computation
# ---------------------------------------------------------------------------

def process_game(game_id: str,
                 player_baselines: dict[str, dict[str, float]],
                 feature_stds: dict[str, float]) -> Optional[dict]:
    """Compute coaching-adjustment metrics for one game.

    Returns a dict with keys:
      game_id, def_team, off_team, n_opp_players,
      adjustment_score, top_feature_shifted,
      h1_imposed, h2_imposed, delta_imposed

    Returns None if data insufficient.
    """
    df = _load_tracking(game_id)
    if df is None or df.empty:
        return None

    split_frame = _halftime_split_frame(df, game_id)
    h1_df = df[df["frame"] <= split_frame].copy()
    h2_df = df[df["frame"] >  split_frame].copy()

    # Identify the two teams
    teams = df["_team"].dropna().unique()
    teams = [t for t in teams if pd.notna(t) and str(t).strip()]
    if len(teams) < 2:
        return None

    # We iterate over both possible defensive teams (each team is DEF when opp has ball).
    # Use both directions and take the one with larger adjustment score.
    best: Optional[dict] = None

    for def_team, off_team in [(teams[0], teams[1]), (teams[1], teams[0])]:
        # Opposing (offensive) players in this game
        opp_h1 = h1_df[h1_df["_team"] == off_team]
        opp_h2 = h2_df[h2_df["_team"] == off_team]

        if opp_h1.empty or opp_h2.empty:
            continue

        player_key = "player_name" if "player_name" in df.columns else "_team"

        # Per-player half CVs and deviations from baseline
        h1_devs: list[dict[str, float]] = []
        h2_devs: list[dict[str, float]] = []

        player_ids = opp_h1[player_key].dropna().unique()

        for pid in player_ids:
            p_h1 = opp_h1[opp_h1[player_key] == pid]
            p_h2 = opp_h2[opp_h2[player_key] == pid]

            if len(p_h1) < MIN_FRAMES_PLAYER or len(p_h2) < MIN_FRAMES_PLAYER:
                continue

            h1_cv = _compute_half_cv(p_h1)
            h2_cv = _compute_half_cv(p_h2)

            # Get player baseline
            baseline = player_baselines.get(str(pid), {})

            if not h1_cv or not h2_cv:
                continue

            # Deviation = (half_mean - baseline) / feature_std
            h1_dev: dict[str, float] = {}
            h2_dev: dict[str, float] = {}
            for feat in CORE_FEATURES:
                if feat in h1_cv and feat in h2_cv:
                    base = baseline.get(feat, np.nan)
                    std  = feature_stds.get(feat, 1.0)
                    if not np.isfinite(base) or std <= 0:
                        # No baseline → use intra-game deviation relative to game mean
                        game_mean = df[df["_team"] == off_team][feat].mean()
                        if not np.isfinite(game_mean) or std <= 0:
                            continue
                        base = game_mean
                    h1_dev[feat] = (h1_cv[feat] - base) / std
                    h2_dev[feat] = (h2_cv[feat] - base) / std

            if h1_dev:
                h1_devs.append(h1_dev)
                h2_devs.append(h2_dev)

        n_players = len(h1_devs)
        if n_players < MIN_PLAYERS_PER_HALF:
            continue

        # Team-level "imposed" profile = mean deviation across opposing players
        def _mean_devs(dev_list: list[dict[str, float]]) -> dict[str, float]:
            all_keys = set(k for d in dev_list for k in d)
            result: dict[str, float] = {}
            for k in all_keys:
                vals = [d[k] for d in dev_list if k in d]
                if vals:
                    result[k] = float(np.mean(vals))
            return result

        h1_imposed = _mean_devs(h1_devs)
        h2_imposed = _mean_devs(h2_devs)

        # Delta = H2 - H1 (positive = defense tightened in H2, negative = loosened)
        delta: dict[str, float] = {}
        for feat in CORE_FEATURES:
            if feat in h1_imposed and feat in h2_imposed:
                delta[feat] = h2_imposed[feat] - h1_imposed[feat]

        if not delta:
            continue

        adj_score = float(max(abs(v) for v in delta.values()))
        top_feat  = max(delta, key=lambda f: abs(delta[f]))

        candidate = {
            "game_id": game_id,
            "def_team": str(def_team),
            "off_team": str(off_team),
            "n_opp_players": n_players,
            "adjustment_score": round(adj_score, 4),
            "top_feature_shifted": top_feat,
            "top_feature_delta": round(delta[top_feat], 4),
            "h1_imposed": {k: round(v, 4) for k, v in h1_imposed.items()},
            "h2_imposed": {k: round(v, 4) for k, v in h2_imposed.items()},
            "delta_imposed": {k: round(v, 4) for k, v in delta.items()},
            "is_adjustment_game": int(adj_score > ADJUSTMENT_THRESHOLD),
        }

        if best is None or adj_score > best["adjustment_score"]:
            best = candidate

    return best


# ---------------------------------------------------------------------------
# Per-player baseline builder
# ---------------------------------------------------------------------------

def build_baselines(cv_per_player: pd.DataFrame,
                    cv_per_game: pd.DataFrame,
                    ) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Build player→feature baseline dict and league-level feature std dict.

    Baseline = season mean from per_player parquet (keyed by player_name).
    Feature std = cross-game std of per-game player means (league-level scaling).
    """
    # Map feature names in parquet to raw tracking column names
    cvb_to_raw = {
        "cvb_avg_velocity":       "velocity",
        "cvb_avg_defender_dist":  "nearest_opponent",
        "cvb_off_ball_dist":      "off_ball_distance",
        "cvb_avg_spacing":        "team_spacing",
        "cvb_avg_dist_to_basket": "dist_to_basket_ft",
    }

    baselines: dict[str, dict[str, float]] = {}
    for _, row in cv_per_player.iterrows():
        name = str(row.get("player_name", ""))
        if not name or name == "nan":
            continue
        pdict: dict[str, float] = {}
        for cvb_col, raw_feat in cvb_to_raw.items():
            if cvb_col in row and pd.notna(row[cvb_col]):
                pdict[raw_feat] = float(row[cvb_col])
        baselines[name] = pdict

    # League-level std from per_game data (robust to small per-player samples)
    feature_stds: dict[str, float] = {}
    for cvb_col, raw_feat in cvb_to_raw.items():
        if cvb_col in cv_per_game.columns:
            std = cv_per_game[cvb_col].std()
            feature_stds[raw_feat] = float(std) if (pd.notna(std) and std > 0) else 1.0
        else:
            feature_stds[raw_feat] = 1.0

    return baselines, feature_stds


# ---------------------------------------------------------------------------
# Per-team aggregation
# ---------------------------------------------------------------------------

def aggregate_team_tendencies(adj_df: pd.DataFrame) -> dict:
    """Build per-team adjustment tendency dict from the per-game parquet."""
    result: dict = {}

    for def_team, grp in adj_df.groupby("def_team"):
        n_games      = len(grp)
        n_adj        = int(grp["is_adjustment_game"].sum())
        adj_freq     = round(float(n_adj / n_games), 3) if n_games > 0 else 0.0
        mean_score   = round(float(grp["adjustment_score"].mean()), 4)

        # Identify typical adjustment direction from delta_imposed
        # Flatten all deltas across games to find consistently-shifted feature
        feat_deltas: dict[str, list[float]] = {f: [] for f in CORE_FEATURES}
        for _, row in grp.iterrows():
            delta = row.get("delta_imposed", {})
            if isinstance(delta, str):
                try:
                    delta = json.loads(delta)
                except Exception:
                    delta = {}
            if isinstance(delta, dict):
                for feat, val in delta.items():
                    if feat in feat_deltas and np.isfinite(float(val)):
                        feat_deltas[feat].append(float(val))

        # Mean delta per feature (+ = H2 tighter, - = H2 looser)
        feat_mean_deltas: dict[str, float] = {}
        for feat, vals in feat_deltas.items():
            if vals:
                feat_mean_deltas[feat] = round(float(np.mean(vals)), 4)

        # Dominant direction for top-shifted feature
        top_direction = "no clear pattern"
        if feat_mean_deltas:
            top_feat = max(feat_mean_deltas, key=lambda f: abs(feat_mean_deltas[f]))
            top_val  = feat_mean_deltas[top_feat]
            labels   = FEATURE_LABELS.get(top_feat, ("+shift", "-shift"))
            direction = labels[0] if top_val > 0 else labels[1]
            top_direction = (
                f"{direction} via {top_feat} "
                f"({'H2 tighter' if top_val < 0 else 'H2 looser'}, Δ={top_val:+.3f}σ)"
            )

        # Notable examples: games with high adjustment score
        examples = []
        for _, row in grp.nlargest(3, "adjustment_score").iterrows():
            delta = row.get("delta_imposed", {})
            if isinstance(delta, str):
                try:
                    delta = json.loads(delta)
                except Exception:
                    delta = {}
            examples.append({
                "game_id":        row["game_id"],
                "off_team":       row.get("off_team", "?"),
                "score":          round(float(row["adjustment_score"]), 3),
                "top_feature":    row.get("top_feature_shifted", "?"),
                "top_delta":      row.get("top_feature_delta", 0.0),
                "is_adj_game":    bool(row.get("is_adjustment_game", 0)),
            })

        result[str(def_team)] = {
            "n_games_tracked":       n_games,
            "n_adjustment_games":    n_adj,
            "adjustment_frequency":  adj_freq,
            "mean_adjustment_score": mean_score,
            "typical_direction":     top_direction,
            "feature_mean_deltas":   feat_mean_deltas,
            "examples":              examples,
        }

    return result


# ---------------------------------------------------------------------------
# Atlas markdown writer
# ---------------------------------------------------------------------------

def write_atlas(adj_df: pd.DataFrame,
                tendencies: dict,
                out_path: Path) -> None:
    """Write the Coaching Adjustments Atlas markdown."""
    n_games     = len(adj_df)
    n_adj       = int(adj_df["is_adjustment_game"].sum())
    pct_adj     = 100.0 * n_adj / n_games if n_games > 0 else 0.0

    # Top-adjusting teams
    team_rows = []
    for team, td in tendencies.items():
        team_rows.append({
            "team":      team,
            "freq":      td["adjustment_frequency"],
            "n_games":   td["n_games_tracked"],
            "n_adj":     td["n_adjustment_games"],
            "mean_score": td["mean_adjustment_score"],
            "direction": td["typical_direction"],
        })
    team_df = pd.DataFrame(team_rows).sort_values("freq", ascending=False)

    top10 = team_df.head(10)
    stable5 = team_df.tail(5).sort_values("freq")

    # Notable high-adjustment examples
    adj_examples = adj_df[adj_df["is_adjustment_game"] == 1].nlargest(5, "adjustment_score")

    lines = [
        "# Coaching Adjustment Detection Atlas (INT-34)",
        "",
        f"*Generated: from {n_games} CV-quality games | Threshold: >{ADJUSTMENT_THRESHOLD:.1f}σ*",
        "",
        "## Methodology",
        "",
        "For each game, measure how much the **defensive team's imposed CV profile** on "
        "opposing players shifts from H1 to H2. Large shifts signal a mid-game scheme change.",
        "",
        "**Key metric — Adjustment Score:**",
        "- Per opposing player: compute their CV features in H1 vs H2",
        "- Normalize each half's mean against the player's season baseline (z-score)",
        "- Team-level 'imposed profile' = mean deviation across all opposing players tracked",
        "- Adjustment Score = max |H2_imposed_mean - H1_imposed_mean| across CV features",
        "- ADJUSTMENT GAME when score > 1.0σ (heuristic threshold)",
        "",
        "**H1/H2 split:** Possession midpoint from `possessions.csv pbp_period` (periods 1-2 "
        "= H1, 3-4 = H2). Falls back to possession-ID midpoint or frame midpoint.",
        "",
        "**Features tracked:** velocity, nearest_opponent (defender distance), "
        "off_ball_distance, team_spacing, dist_to_basket_ft",
        "",
        "---",
        "",
        "## Coverage",
        "",
        f"- Games analyzed: **{n_games}**",
        f"- ADJUSTMENT GAMES flagged (score > {ADJUSTMENT_THRESHOLD:.1f}σ): "
        f"**{n_adj}** ({pct_adj:.1f}%)",
        f"- Unique defensive teams observed: **{adj_df['def_team'].nunique()}**",
        "",
        "---",
        "",
        "## Top 10 Most-Adjusting Coaching Staffs",
        "",
        "| team | adj_freq | n_games | n_adj | mean_score | typical_direction |",
        "|------|----------|---------|-------|------------|-------------------|",
    ]
    for _, r in top10.iterrows():
        lines.append(
            f"| {r['team']} | {r['freq']:.3f} | {int(r['n_games'])} | {int(r['n_adj'])} "
            f"| {r['mean_score']:.3f} | {r['direction']} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Steadiest Schemes (Lowest Adjustment Frequency)",
        "",
        "| team | adj_freq | n_games | mean_score |",
        "|------|----------|---------|------------|",
    ]
    for _, r in stable5.iterrows():
        lines.append(
            f"| {r['team']} | {r['freq']:.3f} | {int(r['n_games'])} | {r['mean_score']:.3f} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Notable Adjustment Examples",
        "",
    ]
    for _, row in adj_examples.iterrows():
        delta = row.get("delta_imposed", {})
        if isinstance(delta, str):
            try:
                delta = json.loads(delta)
            except Exception:
                delta = {}
        feat  = row.get("top_feature_shifted", "?")
        dval  = row.get("top_feature_delta", 0.0)
        if isinstance(dval, (int, float)) and np.isfinite(float(dval)):
            sign  = "tightened" if float(dval) < 0 else "loosened"
            labels = FEATURE_LABELS.get(feat, ("+", "-"))
            label  = labels[0] if float(dval) > 0 else labels[1]
            lines.append(
                f"- **Game {row['game_id']}** ({row.get('def_team','?')} DEF vs "
                f"{row.get('off_team','?')} OFF): "
                f"score={row['adjustment_score']:.3f}σ — {feat} {sign} by "
                f"{abs(float(dval)):.3f}σ in H2 → _{label}_"
            )

    lines += [
        "",
        "---",
        "",
        "## Betting Implications",
        "",
        "**Live betting:**",
        "- If a high-adjustment-frequency team trails at half, expect H2 scheme change",
        "  → opposing player stats may be suppressed in H2",
        "- Live props (H2 scoring) should widen uncertainty bands for known-adjuster opponents",
        "",
        "**Pre-game:**",
        "- High-adjustment-team opponent = wider uncertainty on player props (H1/H2 split matters)",
        "- Combine with INT-12 (scheme baseline) for full context:",
        "  a team with SWITCH HEAVY baseline + high adj_freq = volatile prop environment",
        "",
        "---",
        "",
        "## Honest Caveats",
        "",
        f"- **H1/H2 split:** possession midpoint, not true halftime clock",
        f"- **Per-team samples:** 4–20 games; teams with n_games < 8 are underpowered",
        f"- **Threshold 1.0σ:** heuristic — tuned to flag ~40% of games; adjust with --threshold",
        f"- **ISSUE-022:** defender_distance=200.0 sentinel stripped, but affects signal quality",
        f"- **Team color labels:** older games use 'green'/'white' not abbreviations → "
        "some defensive team IDs are not human-readable",
        f"- **Phantom slots:** tracker assigns extra player IDs to noise blobs, "
        "adding noise to per-player deviation estimates",
        "",
        "---",
        "",
        "## Per-Team Detail Links",
        "",
        "*(Check `data/intelligence/team_adjustment_tendencies.json` for full per-team data)*",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="INT-34: Coaching Adjustment Detection Intelligence"
    )
    ap.add_argument("--games",     default=None,
                    help="Comma-separated game IDs (default: all CV games)")
    ap.add_argument("--threshold", type=float, default=ADJUSTMENT_THRESHOLD,
                    help="Adjustment score threshold (default: 1.0σ)")
    ap.add_argument("--min-players", type=int, default=MIN_PLAYERS_PER_HALF,
                    help="Min opposing players required per half (default: 3)")
    ap.add_argument("--no-write",  action="store_true",
                    help="Dry-run: skip writing output files")
    args = ap.parse_args()

    adj_threshold = args.threshold
    min_players   = args.min_players

    # ----- Load existing per-game / per-player CV parquets -----
    if not CV_PER_GAME.exists():
        print(f"ERROR: {CV_PER_GAME} not found — run build_player_cv_profiles.py first",
              file=sys.stderr)
        return 1
    if not CV_PER_PLAYER.exists():
        print(f"ERROR: {CV_PER_PLAYER} not found — run build_player_cv_profiles.py first",
              file=sys.stderr)
        return 1

    print("Loading player CV data...")
    cv_per_game   = pd.read_parquet(CV_PER_GAME)
    cv_per_player = pd.read_parquet(CV_PER_PLAYER)
    print(f"  per_game:   {cv_per_game.shape}")
    print(f"  per_player: {cv_per_player.shape}")

    # Build player baselines and feature stds
    baselines, feature_stds = build_baselines(cv_per_player, cv_per_game)
    print(f"  Player baselines built: {len(baselines)}")
    print(f"  Feature stds: { {k: f'{v:.3f}' for k,v in feature_stds.items()} }")

    # ----- Select games -----
    if args.games:
        game_ids = [g.strip() for g in args.games.split(",")]
    else:
        # Use all games that appear in per-game CV table AND have tracking data
        game_ids_cv = cv_per_game["game_id"].unique().tolist()
        game_ids    = [g for g in game_ids_cv
                       if (BACKUP / g / "tracking_data.csv").exists()]

    print(f"\nProcessing {len(game_ids)} games...")

    # ----- Per-game computation -----
    adj_rows: list[dict] = []
    n_ok    = 0
    n_skip  = 0
    n_fail  = 0

    for gid in sorted(game_ids):
        try:
            result = process_game(gid, baselines, feature_stds)
            if result is None:
                n_skip += 1
                print(f"  [{gid}] SKIP (insufficient data)")
                continue
            # Override threshold from arg
            result["is_adjustment_game"] = int(result["adjustment_score"] > adj_threshold)
            adj_rows.append(result)
            n_ok += 1
            adj_flag = "ADJ" if result["is_adjustment_game"] else "   "
            print(
                f"  [{gid}] {adj_flag}  def={result['def_team']:5s} "
                f"score={result['adjustment_score']:.3f}  "
                f"top={result['top_feature_shifted']}({result['top_feature_delta']:+.3f}s)  "
                f"n_opp={result['n_opp_players']}"
            )
        except Exception as exc:
            n_fail += 1
            print(f"  [{gid}] FAIL: {exc}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    print(f"\nProcessed: {n_ok} OK  |  {n_skip} skip  |  {n_fail} fail")

    if not adj_rows:
        print("No adjustment rows produced — cannot write outputs.", file=sys.stderr)
        return 2

    # ----- Build parquet -----
    adj_df = pd.DataFrame(adj_rows)

    # Serialize dict columns as JSON strings for parquet compatibility
    for col in ("h1_imposed", "h2_imposed", "delta_imposed"):
        adj_df[col] = adj_df[col].apply(
            lambda x: json.dumps(x) if isinstance(x, dict) else x
        )

    n_adj     = int(adj_df["is_adjustment_game"].sum())
    n_total   = len(adj_df)
    pct_adj   = 100.0 * n_adj / n_total if n_total > 0 else 0

    print(f"\n=== ADJUSTMENT SUMMARY ===")
    print(f"Total games:      {n_total}")
    print(f"Adjustment games: {n_adj}  ({pct_adj:.1f}%)")
    print(f"Mean adj score:   {adj_df['adjustment_score'].mean():.4f}")
    print(f"Threshold used:   {adj_threshold:.1f}σ")

    # Top feature shifts
    print("\nTop feature shifts (frequency as top_feature_shifted):")
    print(adj_df["top_feature_shifted"].value_counts().to_string())

    # ----- Per-team tendencies -----
    # Re-parse dict cols for aggregation
    adj_df_agg = adj_df.copy()
    for col in ("delta_imposed",):
        adj_df_agg[col] = adj_df_agg[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) else (x or {})
        )

    tendencies = aggregate_team_tendencies(adj_df_agg)

    print(f"\n=== PER-TEAM TENDENCIES ({len(tendencies)} teams) ===")
    team_summary = sorted(tendencies.items(),
                          key=lambda kv: kv[1]["adjustment_frequency"],
                          reverse=True)
    print(f"{'team':8s} {'freq':6s} {'n_games':8s} {'n_adj':6s} {'mean_score':10s}")
    for team, td in team_summary:
        print(
            f"  {team:8s} {td['adjustment_frequency']:.3f}   "
            f"{td['n_games_tracked']:4d}     "
            f"{td['n_adjustment_games']:3d}    "
            f"{td['mean_adjustment_score']:.4f}"
        )

    if not args.no_write:
        # Write parquet
        OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
        adj_df.to_parquet(OUT_PARQUET, index=False)
        print(f"\nWrote {OUT_PARQUET}")

        # Write JSON
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps(tendencies, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"Wrote {OUT_JSON}")

        # Write Atlas
        write_atlas(adj_df, tendencies, OUT_ATLAS)
        print(f"Wrote {OUT_ATLAS}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
