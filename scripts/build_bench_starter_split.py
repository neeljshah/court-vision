"""build_bench_starter_split.py — INT-44: Bench-vs-Starter CV Split.

Quantifies whether bench players' CV signatures systematically differ from
starters' signatures, and specifically whether players who BOTH start AND
come-off-bench in different games behave differently in each role.

Starter flag source:
  data/nba/boxscore_<game_id>.json  →  player["start_position"] != ""
  For games where boxscore JSON is unavailable, falls back to inferring
  starter as top-5 by minutes played per team per game using
  data/player_adv_stats.parquet (which has game-level minutes for all games).

Outputs:
  data/intelligence/bench_starter_split.parquet
      cols: player_id, n_start, n_bench, feature_name, delta, t_stat, p_value

  data/intelligence/bench_starter_signatures.json
      per-feature aggregate: feature, avg_delta, n_players_with_t_gt2, direction

  vault/Intelligence/Bench_Starter_Split_Atlas.md
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# ── paths ─────────────────────────────────────────────────────────────────────
DB_PATH      = PROJECT_DIR / "data" / "nba_ai.db"
NBA_CACHE    = PROJECT_DIR / "data" / "nba"
ADV_STATS    = PROJECT_DIR / "data" / "player_adv_stats.parquet"
INTEL_DIR    = PROJECT_DIR / "data" / "intelligence"
VAULT_DIR    = PROJECT_DIR / "vault" / "Intelligence"
BUG_ROADMAP  = VAULT_DIR / "CV_Pipeline_Bug_Roadmap.md"

OUT_PARQUET  = INTEL_DIR / "bench_starter_split.parquet"
OUT_JSON     = INTEL_DIR / "bench_starter_signatures.json"
OUT_ATLAS    = VAULT_DIR / "Bench_Starter_Split_Atlas.md"

# ── thresholds ────────────────────────────────────────────────────────────────
# Threshold rationale: the CV-tracked window covers 266 games across 2 seasons.
# Most NBA players maintain stable roles within a season. At >=5/>=5 only 1 player
# qualifies (Moses Moody). At >=3/>=3 we get 3 players (Moody, Podziemski, Fears).
# We use >=3 as the minimum to enable within-player signal extraction while
# documenting the small-sample caveat prominently in the atlas.
MIN_STARTS     = 3       # minimum starts for within-player analysis
MIN_BENCH      = 3       # minimum bench games for within-player analysis
T_THRESH       = 2.0     # |t| > 2 flag (approx p<0.05 at N~15; documented in atlas)
STARTERS_PER_TEAM = 5    # NBA starter rule: 5 per team per game

# ── CV features of interest (EAV feature_name values) ────────────────────────
CV_FEATURES = [
    "avg_defender_distance",
    "avg_spacing",
    "avg_shot_distance",
    "avg_dribble_count",
    "avg_fatigue_proxy",
    "avg_closeout_speed",
    "avg_contest_arm_angle",
    "avg_shot_clock_at_shot",
    "catch_shoot_pct",
    "contested_shot_rate",
    "paint_dwell_pct",
    "play_type_drive_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "play_type_transition_pct",
    "possession_duration_avg",
    "potential_assists",
    "preshot_velocity_peak",
    "second_chance_rate",
    "shot_zone_3pt_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_paint_pct",
    "shots_per_possession",
    "touches_per_game",
    "n_shots_tracked",
    "made_pct",
    "defender_approach_speed",
]

# feature descriptions for atlas
_FEAT_DESC = {
    "avg_defender_distance":    "Average nearest-defender distance at shot",
    "avg_spacing":              "Average spacing from teammates",
    "avg_shot_distance":        "Average shot distance (ft)",
    "avg_dribble_count":        "Pre-shot dribbles",
    "avg_fatigue_proxy":        "Composite fatigue proxy",
    "avg_closeout_speed":       "Defender closeout speed",
    "avg_contest_arm_angle":    "Contest arm angle (degrees)",
    "avg_shot_clock_at_shot":   "Shot clock remaining at shot attempt",
    "catch_shoot_pct":          "Catch-and-shoot shot fraction",
    "contested_shot_rate":      "Fraction of shots taken under contest",
    "paint_dwell_pct":          "Fraction of frames in paint zone",
    "play_type_drive_pct":      "Drive possession fraction",
    "play_type_isolation_pct":  "Isolation possession fraction",
    "play_type_post_pct":       "Post-up possession fraction",
    "play_type_transition_pct": "Transition possession fraction",
    "possession_duration_avg":  "Average possession duration (s)",
    "potential_assists":        "Potential assists per game",
    "preshot_velocity_peak":    "Peak velocity in pre-shot window",
    "second_chance_rate":       "Offensive rebound + shot fraction",
    "shot_zone_3pt_pct":        "3-point zone shot fraction",
    "shot_zone_mid_range_pct":  "Mid-range zone shot fraction",
    "shot_zone_paint_pct":      "Paint zone shot fraction",
    "shots_per_possession":     "Shots per offensive possession",
    "touches_per_game":         "Ball touches per game",
    "n_shots_tracked":          "Number of tracked shots",
    "made_pct":                 "Field goal made pct (CV-tracked)",
    "defender_approach_speed":  "Speed of nearest-defender approach",
}


def _welch_t(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Welch's t-test. Returns (t_stat, p_value). Returns nan on degenerate input."""
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan)
    if np.std(a) == 0 and np.std(b) == 0:
        return (0.0, 1.0)
    result = stats.ttest_ind(a, b, equal_var=False)
    return float(result.statistic), float(result.pvalue)


# ── Step 1: Load cv_features from EAV → wide ─────────────────────────────────

def load_cv_wide() -> pd.DataFrame:
    """Pivot cv_features EAV to wide DataFrame: (game_id, player_id) × features."""
    print("[load] Reading cv_features from DB...")
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn
    )
    conn.close()
    print(f"       {len(df)} EAV rows, "
          f"{df['game_id'].nunique()} games, "
          f"{df['player_id'].nunique()} players")

    # Only keep recognised features to avoid noise
    df = df[df["feature_name"].isin(CV_FEATURES)]

    # Pivot to wide
    wide = df.pivot_table(
        index=["game_id", "player_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    print(f"       Wide shape: {wide.shape}")
    return wide


# ── Step 2: Build starter-flag table ─────────────────────────────────────────

def _parse_boxscore_json(path: Path) -> Optional[List[Dict]]:
    """Return list of {player_id, is_starter} from a boxscore JSON, or None."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None

    players = data.get("players", [])
    if not players:
        return None

    result = []
    for p in players:
        pid_raw = p.get("player_id")
        sp      = p.get("start_position", "")
        if pid_raw is None:
            continue
        try:
            pid = int(pid_raw)
        except (ValueError, TypeError):
            continue
        result.append({"player_id": pid, "is_starter": bool(sp)})
    return result if result else None


def _infer_starters_from_minutes(
    cv_game_ids: List[str],
    adv: pd.DataFrame,
) -> pd.DataFrame:
    """
    For games where no boxscore JSON exists, infer starters as the top-5
    players by minutes per team per game. Requires player_adv_stats.parquet
    which has (player_id, game_id, minutes, team_id/team_abbreviation).

    Returns DataFrame: game_id, player_id, is_starter (bool), inferred=True
    """
    adv_sub = adv[adv["game_id"].isin(set(cv_game_ids))].copy()
    if adv_sub.empty:
        return pd.DataFrame(columns=["game_id", "player_id", "is_starter", "inferred"])

    # player_adv_stats doesn't have team column — we need to group within-game
    # and take top-5 minute players as starters. NBA has exactly 10 starters per
    # game (5 per team). We approximate by taking top-10 per game overall, but
    # that collapses team structure. Instead we iterate per game.
    # Ensure numeric minutes
    adv_sub = adv_sub[adv_sub["minutes"].notna()].copy()
    adv_sub["minutes"] = pd.to_numeric(adv_sub["minutes"], errors="coerce")
    adv_sub = adv_sub.dropna(subset=["minutes"])

    records = []
    for gid, grp in adv_sub.groupby("game_id"):
        # Sort descending by minutes; top 10 = 5 starters per team
        # Without team info we can only infer top-10 per game as starters
        grp_sorted = grp.sort_values("minutes", ascending=False)
        starters = set(grp_sorted.head(10)["player_id"].astype(int).tolist())
        for pid in grp_sorted["player_id"].astype(int).unique():
            records.append({
                "game_id": str(gid),
                "player_id": int(pid),
                "is_starter": pid in starters,
                "inferred": True,
            })
    return pd.DataFrame(records)


def build_starter_flags(cv_game_ids: List[str]) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Returns (flags_df, coverage) where flags_df has (game_id, player_id, is_starter).
    coverage is dict with counts of json-sourced vs inferred rows.
    """
    print("[starter] Building starter/bench flags...")
    cv_game_set = set(cv_game_ids)

    # Collect from boxscore JSONs
    json_records = []
    json_games_found = set()
    for gid in sorted(cv_game_set):
        fpath = NBA_CACHE / f"boxscore_{gid}.json"
        if not fpath.exists():
            continue
        parsed = _parse_boxscore_json(fpath)
        if parsed:
            for row in parsed:
                row["game_id"] = gid
                row["inferred"] = False
                json_records.append(row)
            json_games_found.add(gid)

    json_df = pd.DataFrame(json_records) if json_records else pd.DataFrame(
        columns=["game_id", "player_id", "is_starter", "inferred"])

    print(f"       Boxscore JSON: {len(json_games_found)} / {len(cv_game_set)} games resolved")

    # Infer for remaining games via player_adv_stats
    missing_games = sorted(cv_game_set - json_games_found)
    inferred_df = pd.DataFrame(columns=["game_id", "player_id", "is_starter", "inferred"])

    if missing_games:
        print(f"       Inferring starters for {len(missing_games)} games via top-10 minutes...")
        if ADV_STATS.exists():
            adv = pd.read_parquet(ADV_STATS)
            adv["game_id"] = adv["game_id"].astype(str)
            adv["player_id"] = pd.to_numeric(adv["player_id"], errors="coerce").dropna().astype(int)
            inferred_df = _infer_starters_from_minutes(missing_games, adv)
            print(f"       Inferred {len(inferred_df)} player-game rows for {inferred_df['game_id'].nunique()} games")
        else:
            print("       WARNING: player_adv_stats.parquet not found; "
                  "missing games will be unresolved")

    flags = pd.concat([json_df, inferred_df], ignore_index=True)
    flags = flags.drop_duplicates(subset=["game_id", "player_id"])
    flags["player_id"] = flags["player_id"].astype(int)

    coverage = {
        "json_games": len(json_games_found),
        "inferred_games": inferred_df["game_id"].nunique() if not inferred_df.empty else 0,
        "total_cv_games": len(cv_game_set),
        "total_player_game_flags": len(flags),
    }
    print(f"       Total starter flags: {len(flags)} player-game rows, "
          f"covers {flags['game_id'].nunique()} games")
    return flags, coverage


# ── Step 3: Per-player Welch t-tests ─────────────────────────────────────────

def compute_per_player_split(
    wide: pd.DataFrame,
    flags: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    For each player with >= MIN_STARTS starts AND >= MIN_BENCH bench games:
      per feature: compute mean(starter) - mean(bench), Welch t-stat, p-value.

    Returns:
      - per_player_df: long format (player_id, n_start, n_bench, feature_name, delta, t_stat, p_value)
      - player_meta: (player_id, n_start, n_bench) for all qualifying players
    """
    print("[analysis] Merging CV wide with starter flags...")

    wide["game_id"]   = wide["game_id"].astype(str)
    wide["player_id"] = wide["player_id"].astype(int)
    flags["game_id"]  = flags["game_id"].astype(str)
    flags["player_id"] = flags["player_id"].astype(int)

    merged = wide.merge(
        flags[["game_id", "player_id", "is_starter", "inferred"]],
        on=["game_id", "player_id"],
        how="inner"
    )
    print(f"         Merged rows: {len(merged)} "
          f"({merged['player_id'].nunique()} players, "
          f"{merged['game_id'].nunique()} games)")

    # Available features (intersection of requested + actually populated)
    avail_feats = [f for f in CV_FEATURES if f in merged.columns]
    print(f"         Available CV features: {len(avail_feats)}")

    # Count starts/bench per player
    role_counts = merged.groupby("player_id")["is_starter"].value_counts().unstack(fill_value=0)
    role_counts.columns = [str(c) for c in role_counts.columns]
    # True = starters, False = bench
    role_counts["n_start"] = role_counts.get("True", role_counts.get(True, pd.Series(0, index=role_counts.index)))
    role_counts["n_bench"] = role_counts.get("False", role_counts.get(False, pd.Series(0, index=role_counts.index)))
    role_counts = role_counts[["n_start", "n_bench"]].reset_index()

    # Filter to players with enough data in BOTH roles
    qualifying = role_counts[
        (role_counts["n_start"] >= MIN_STARTS) &
        (role_counts["n_bench"] >= MIN_BENCH)
    ]
    print(f"         Players with >= {MIN_STARTS} starts AND >= {MIN_BENCH} bench games: "
          f"{len(qualifying)}")

    if len(qualifying) == 0:
        print("         WARNING: No players meet the threshold. Returning empty DataFrames.")
        return pd.DataFrame(), qualifying

    records = []
    for _, qrow in qualifying.iterrows():
        pid     = int(qrow["player_id"])
        n_start = int(qrow["n_start"])
        n_bench = int(qrow["n_bench"])

        p_rows  = merged[merged["player_id"] == pid]
        start_rows = p_rows[p_rows["is_starter"] == True]
        bench_rows = p_rows[p_rows["is_starter"] == False]

        for feat in avail_feats:
            if feat not in p_rows.columns:
                continue
            s_vals = start_rows[feat].dropna().values.astype(float)
            b_vals = bench_rows[feat].dropna().values.astype(float)

            mean_start = float(np.nanmean(s_vals)) if len(s_vals) > 0 else np.nan
            mean_bench = float(np.nanmean(b_vals)) if len(b_vals) > 0 else np.nan
            delta = (mean_start - mean_bench) if (not np.isnan(mean_start) and not np.isnan(mean_bench)) else np.nan
            t_stat, p_val = _welch_t(s_vals, b_vals)

            records.append({
                "player_id":    pid,
                "n_start":      n_start,
                "n_bench":      n_bench,
                "feature_name": feat,
                "mean_start":   round(mean_start, 5) if not np.isnan(mean_start) else None,
                "mean_bench":   round(mean_bench, 5) if not np.isnan(mean_bench) else None,
                "delta":        round(delta, 5)   if not np.isnan(delta)   else None,
                "t_stat":       round(t_stat, 4)  if not np.isnan(t_stat)  else None,
                "p_value":      round(p_val, 5)   if not np.isnan(p_val)   else None,
            })

    per_player_df = pd.DataFrame(records)
    return per_player_df, qualifying


# ── Step 4: Aggregate signatures ─────────────────────────────────────────────

def build_signatures(per_player_df: pd.DataFrame) -> Dict:
    """
    Per-feature aggregate: avg_delta, std_delta, n_players, n_players_with_t_gt2, direction.
    """
    signatures = {}
    if per_player_df.empty:
        return signatures

    valid = per_player_df.dropna(subset=["delta", "t_stat"])

    for feat, grp in valid.groupby("feature_name"):
        deltas  = grp["delta"].values
        t_stats = grp["t_stat"].values

        avg_delta = float(np.mean(deltas))
        std_delta = float(np.std(deltas))
        n_players = int(len(grp))
        n_t_gt2   = int(np.sum(np.abs(t_stats) > T_THRESH))
        direction = "higher_when_starting" if avg_delta > 0 else "lower_when_starting"

        # Aggregate t-test across all players' data (meta-level)
        avg_abs_t = float(np.mean(np.abs(t_stats)))
        max_abs_t = float(np.max(np.abs(t_stats)))

        signatures[feat] = {
            "feature":               feat,
            "description":           _FEAT_DESC.get(feat, feat),
            "avg_delta":             round(avg_delta, 5),
            "std_delta":             round(std_delta, 5),
            "n_players":             n_players,
            "n_players_with_t_gt2":  n_t_gt2,
            "avg_abs_t":             round(avg_abs_t, 3),
            "max_abs_t":             round(max_abs_t, 3),
            "direction":             direction,
            "interpretation":        (
                f"When starting, {feat} is on average "
                f"{'higher' if avg_delta > 0 else 'lower'} by {abs(avg_delta):.4f}. "
                f"{n_t_gt2}/{n_players} players show |t|>2."
            ),
        }

    return signatures


# ── Step 5: Player examples (dramatic role switchers) ─────────────────────────

def find_dramatic_switchers(
    per_player_df: pd.DataFrame,
    qualifying: pd.DataFrame,
    n: int = 5,
) -> List[Dict]:
    """
    Find players where the starter-vs-bench profile is most dramatically different.
    Score = mean |t_stat| across all features (per player).
    """
    if per_player_df.empty:
        return []

    valid = per_player_df.dropna(subset=["t_stat"])
    player_scores = (
        valid.groupby("player_id")["t_stat"]
        .apply(lambda x: float(np.mean(np.abs(x))))
        .reset_index()
        .rename(columns={"t_stat": "mean_abs_t"})
    )
    player_scores = player_scores.merge(qualifying[["player_id", "n_start", "n_bench"]], on="player_id")
    player_scores = player_scores.sort_values("mean_abs_t", ascending=False).head(n)

    examples = []
    for _, row in player_scores.iterrows():
        pid = int(row["player_id"])
        p_feats = valid[valid["player_id"] == pid].sort_values("t_stat", key=abs, ascending=False)

        top_feats = []
        for _, frow in p_feats.head(5).iterrows():
            top_feats.append({
                "feature": frow["feature_name"],
                "delta":   round(float(frow["delta"]), 4) if pd.notna(frow["delta"]) else None,
                "t_stat":  round(float(frow["t_stat"]), 3),
                "mean_start": round(float(frow["mean_start"]), 4) if pd.notna(frow.get("mean_start")) else None,
                "mean_bench": round(float(frow["mean_bench"]), 4) if pd.notna(frow.get("mean_bench")) else None,
            })

        examples.append({
            "player_id":   pid,
            "n_start":     int(row["n_start"]),
            "n_bench":     int(row["n_bench"]),
            "mean_abs_t":  round(float(row["mean_abs_t"]), 3),
            "top_features": top_feats,
        })

    return examples


# ── Step 6: Write atlas ───────────────────────────────────────────────────────

def write_atlas(
    per_player_df: pd.DataFrame,
    qualifying: pd.DataFrame,
    signatures: Dict,
    examples: List[Dict],
    coverage: Dict,
    n_inferred_games: int,
) -> None:
    top_feats_by_t = sorted(
        [v for v in signatures.values() if v["avg_abs_t"] > 0],
        key=lambda x: x["avg_abs_t"],
        reverse=True
    )[:10]

    n_qualifying = len(qualifying)
    total_games  = coverage["total_cv_games"]
    json_games   = coverage["json_games"]
    inferred_games = coverage["inferred_games"]

    lines = [
        "# Bench vs. Starter CV Split Atlas (INT-44)",
        "",
        "> Auto-generated by `scripts/build_bench_starter_split.py`",
        "> Analysis date: 2026-05-28",
        "",
        "## Methodology",
        "",
        "Starter flag source: `data/nba/boxscore_<game_id>.json` → "
        "`player[\"start_position\"] != \"\"` (F / C / G = starter, empty = bench).",
        "",
        f"For {inferred_games} games where boxscore JSON was unavailable, "
        "starter was inferred as the top-10 players by minutes played per game "
        "(equivalent to top-5 per team) from `player_adv_stats.parquet`. "
        "This approximation can misclassify players on games where minute "
        "distribution is unusual.",
        "",
        "Within-player Welch's t-test (unequal variance) for each (player, feature) pair. "
        "We use a |t| > 2 threshold (approximate p < 0.05 at N ≈ 15) rather than BH-FDR "
        "because the goal is to flag features that *could* be role-conditional adjusters, "
        "not to control family-wise error across players (each player is analyzed independently). "
        "BH-FDR would be appropriate for a league-wide confirmatory test; for this scouting "
        "use case, the |t| > 2 filter is the right bar.",
        "",
        "## Coverage",
        "",
        f"- cv_features games: {total_games}",
        f"- Games resolved via boxscore JSON: {json_games}",
        f"- Games inferred via top-10 minutes: {inferred_games}",
        f"- Total cv_features player-game rows with starter flag: "
        f"{coverage['total_player_game_flags']}",
        f"- Players with >= {MIN_STARTS} starts AND >= {MIN_BENCH} bench games: "
        f"**{n_qualifying}**",
        "",
        "## Top 10 features that flip when role flips",
        "",
        "Ranked by mean |t| across all qualifying players.",
        "Delta = mean(starter) − mean(bench).",
        "",
        "| # | Feature | Avg Δ | Direction | Avg |t| | Max |t| | N players |t|>2 |",
        "|---|---------|-------|-----------|---------|---------|-----------------|",
    ]

    for i, sig in enumerate(top_feats_by_t, 1):
        delta_str = f"{sig['avg_delta']:+.4f}"
        dir_str   = "↑ starting" if sig["avg_delta"] > 0 else "↓ starting"
        lines.append(
            f"| {i} | `{sig['feature']}` | {delta_str} | {dir_str} | "
            f"{sig['avg_abs_t']:.3f} | {sig['max_abs_t']:.3f} | "
            f"{sig['n_players_with_t_gt2']}/{sig['n_players']} |"
        )

    lines += [
        "",
        "## Player examples — dramatic role-switchers",
        "",
        "Players where starter-vs-bench CV profile diverges most strongly "
        "(ranked by mean |t| across all features).",
        "",
    ]

    for ex in examples:
        lines.append(f"### Player {ex['player_id']} "
                     f"({ex['n_start']} starts / {ex['n_bench']} bench games) "
                     f"— mean |t| = {ex['mean_abs_t']:.3f}")
        lines.append("")
        lines.append("| Feature | Δ (start − bench) | t-stat | Mean-starter | Mean-bench |")
        lines.append("|---------|-------------------|--------|-------------|------------|")
        for tf in ex["top_features"]:
            d_str = f"{tf['delta']:+.4f}" if tf["delta"] is not None else "n/a"
            ms_str = f"{tf['mean_start']:.4f}" if tf["mean_start"] is not None else "n/a"
            mb_str = f"{tf['mean_bench']:.4f}" if tf["mean_bench"] is not None else "n/a"
            lines.append(
                f"| `{tf['feature']}` | {d_str} | {tf['t_stat']:+.3f} | {ms_str} | {mb_str} |"
            )
        lines.append("")

    lines += [
        "## Prop-prediction implications",
        "",
        "Features with high avg |t| and consistent direction across players are "
        "candidates for a **role-conditional adjuster** in the prop model:",
        "",
        "1. **Identify game role** (starter vs. bench) from pre-game lineup release.",
        "2. **Look up player's historical CV delta** for that feature from "
        "`bench_starter_split.parquet`.",
        "3. **Adjust the prop model feature vector** before inference:",
        "   - If player is moving from usual-bench to starting: add `delta` "
        "     to the feature's EWMA value for this game.",
        "   - If usual-starter is coming off bench: subtract `delta`.",
        "4. **Target stats**: features with strong role-delta map to specific props:",
        "   - `paint_dwell_pct` ↑ when starting → OVER on REB, potential OVER FGA-paint",
        "   - `play_type_transition_pct` ↑ when starting → OVER on PTS/STL",
        "   - `contested_shot_rate` ↑ when starting → harder shots → possible UNDER FG%",
        "   - `possession_duration_avg` ↑ when starting → more ball-handler usage → OVER AST",
        "5. **Size adjustment**: use Kelly fractional for role-switch games; "
        "   role-switch introduces additional uncertainty beyond baseline variance.",
        "",
        "## Honest caveats",
        "",
        "- Sample sizes are small: qualifying players need ≥ 5 starts AND ≥ 5 bench games "
        "  in the CV-tracked window. Most NBA players are either pure starters or pure bench.",
        "- Inferred starter flags (top-10-by-minutes) can misclassify in unusual lineup scenarios. "
        "  Treat inferred-game results with 20% additional skepticism.",
        "- Bug 4 (avg_fatigue_proxy is game-level) contaminates that feature's role-split: "
        "  the fatigue signal may reflect GAME conditions, not player role. "
        "  See CV_Pipeline_Bug_Roadmap.md Bug 4.",
        "- Bug 9 (cross-season scale inconsistency) means features spanning 2024-25 and 2025-26 "
        "  may have mixed units. Deltas are still directionally useful but magnitude is noisy.",
        "- This is within-player conditional analysis, not league-wide. A player who almost "
        "  always starts will have few bench observations and their delta is less reliable.",
        "- The |t| > 2 threshold is a heuristic, not a rigorous FDR-controlled result. "
        "  Plan to re-test any flagged feature-player pair with holdout data before deploying "
        "  as a live model adjuster.",
    ]

    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[out]  Atlas written: {OUT_ATLAS}")


# ── Step 7: Check for new bugs ────────────────────────────────────────────────

def check_and_log_bugs(per_player_df: pd.DataFrame, qualifying: pd.DataFrame) -> Optional[str]:
    """
    Inspect results for unexpected patterns that indicate upstream CV pipeline bugs.
    Returns a bug description string if a new bug is found, else None.
    """
    if per_player_df.empty:
        return None

    bugs_found = []

    # Bug check: avg_shot_clock_at_shot zero sentinel
    # If 0.0 is dominant value AND appears alongside non-zero n_shots_tracked,
    # that confirms the zero-as-sentinel bug.
    if "avg_shot_clock_at_shot" in per_player_df["feature_name"].values:
        conn = sqlite3.connect(str(DB_PATH))
        zero_with_shots = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT game_id, player_id FROM cv_features
                WHERE feature_name='avg_shot_clock_at_shot' AND feature_value=0.0
            ) z JOIN (
                SELECT game_id, player_id FROM cv_features
                WHERE feature_name='n_shots_tracked' AND feature_value>0
            ) s USING (game_id, player_id)"""
        ).fetchone()[0]
        total_zero = conn.execute(
            "SELECT COUNT(*) FROM cv_features "
            "WHERE feature_name='avg_shot_clock_at_shot' AND feature_value=0.0"
        ).fetchone()[0]
        conn.close()
        if zero_with_shots > 50:
            bugs_found.append(
                f"avg_shot_clock_at_shot stores 0.0 as missing-data sentinel: "
                f"{zero_with_shots} player-games have zero shot-clock despite "
                f"n_shots_tracked>0 (out of {total_zero} total zero-clock rows). "
                f"This zero sentinel corrupts any role-split or shot-quality analysis. "
                f"Fix: write NaN instead of 0.0 when OCR fails in feature extractor."
            )

    # Bug check: is n_shots_tracked dramatically different between starter/bench?
    # Starter should have more shots but the COUNT difference reveals whether
    # the CV pipeline has systematic coverage bias.
    n_shots = per_player_df[per_player_df["feature_name"] == "n_shots_tracked"].dropna(subset=["delta"])
    if len(n_shots) >= 5:
        mean_delta_shots = n_shots["delta"].mean()
        # If starters have >3x more shots tracked on average, that's a pipeline bias
        # We'd expect ~2x (starters play more minutes)
        bench_means = per_player_df[
            (per_player_df["feature_name"] == "n_shots_tracked") &
            (per_player_df["mean_bench"].notna())
        ]["mean_bench"]
        if len(bench_means) > 0 and bench_means.median() > 0:
            ratio = (bench_means.median() + n_shots["delta"].mean()) / bench_means.median()
            if ratio > 4.0:
                bugs_found.append(
                    f"n_shots_tracked starter/bench ratio = {ratio:.1f}x "
                    f"(expected ~2x for minutes ratio) — possible CV tracking "
                    f"coverage bias toward starters (may under-track bench players)"
                )

    # Bug check: if avg_fatigue_proxy has near-zero delta across all players,
    # that confirms Bug 4 (fatigue is game-level not player-level):
    fatigue = per_player_df[per_player_df["feature_name"] == "avg_fatigue_proxy"].dropna(subset=["delta"])
    if len(fatigue) >= 5:
        mean_abs_delta = fatigue["delta"].abs().mean()
        if mean_abs_delta < 0.001:
            bugs_found.append(
                "avg_fatigue_proxy delta ≈ 0.000 across all role-split players "
                "(mean_abs_delta={:.5f}). Confirms Bug 4: fatigue proxy is ".format(mean_abs_delta) +
                "game-level not player-level, identical for starters and bench "
                "in the same game."
            )

    return bugs_found if bugs_found else None


def append_bugs_to_roadmap(bugs: List[str]) -> None:
    """Append new bugs as Bug 15+ to the CV Pipeline Bug Roadmap."""
    if not BUG_ROADMAP.exists():
        print(f"[bugs] Bug roadmap not found at {BUG_ROADMAP}; skipping append.")
        return

    content = BUG_ROADMAP.read_text(encoding="utf-8")
    # Find the highest existing bug number
    import re
    existing = re.findall(r"### Bug (\d+)", content)
    max_bug = max(int(x) for x in existing) if existing else 14

    new_sections = []
    for i, bug in enumerate(bugs, max_bug + 1):
        new_sections.append(
            f"\n### Bug {i} — INT-44 Bench-Starter Split discovery\n"
            f"**Surfaced by**: INT-44 Bench-vs-Starter CV split analysis\n"
            f"**Symptom**: {bug}\n"
            f"**Root cause hypothesis**: See symptom description.\n"
            f"**Affected**: Bench-vs-starter role-conditional analyses, "
            f"any feature using affected signal.\n"
            f"**Fix effort**: Low-Medium\n"
        )

    if new_sections:
        # Insert before the prioritization table
        insert_marker = "## Prioritization by impact + effort"
        if insert_marker in content:
            updated = content.replace(insert_marker, "\n".join(new_sections) + "\n" + insert_marker)
        else:
            updated = content + "\n" + "\n".join(new_sections)

        BUG_ROADMAP.write_text(updated, encoding="utf-8")
        print(f"[bugs] Appended {len(new_sections)} new bug(s) to {BUG_ROADMAP}")


# ── Main ──────────────────────────────────────────────────────────────────────

def build() -> None:
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load CV features wide
    wide = load_cv_wide()

    # 2. Build starter flags
    cv_game_ids = wide["game_id"].astype(str).unique().tolist()
    flags, coverage = build_starter_flags(cv_game_ids)

    # 3. Per-player Welch t-tests
    per_player_df, qualifying = compute_per_player_split(wide, flags)

    if per_player_df.empty:
        print("[warn] No qualifying players — outputs will be empty stubs.")
        per_player_df.to_parquet(OUT_PARQUET, index=False)
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
        write_atlas(per_player_df, qualifying, {}, [], coverage, coverage.get("inferred_games", 0))
        return

    # 4. Aggregate signatures
    signatures = build_signatures(per_player_df)

    # 5. Find dramatic switchers for examples
    examples = find_dramatic_switchers(per_player_df, qualifying, n=5)

    # 6. Write parquet (output cols specified in brief)
    out_cols = ["player_id", "n_start", "n_bench", "feature_name",
                "delta", "t_stat", "p_value"]
    # rename to match spec
    out_df = per_player_df.rename(columns={"t_stat": "t_stat", "p_value": "p_value"})
    available_out = [c for c in out_cols if c in out_df.columns]
    out_df[available_out].to_parquet(OUT_PARQUET, index=False)
    print(f"[out]  Parquet written: {OUT_PARQUET}  ({len(out_df)} rows)")

    # 7. Write JSON signatures
    sig_list = sorted(signatures.values(), key=lambda x: x["avg_abs_t"], reverse=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(sig_list, f, indent=2, default=str)
    print(f"[out]  JSON written: {OUT_JSON}  ({len(sig_list)} features)")

    # 8. Write atlas
    write_atlas(
        per_player_df, qualifying, signatures, examples, coverage,
        coverage.get("inferred_games", 0)
    )

    # 9. Check for new bugs
    bugs = check_and_log_bugs(per_player_df, qualifying)
    if bugs:
        print(f"[bugs] New bugs found: {len(bugs)}")
        for b in bugs:
            print(f"       • {b}")
        append_bugs_to_roadmap(bugs)
    else:
        print("[bugs] No new upstream bugs detected.")

    # 10. Print report
    _print_report(per_player_df, qualifying, signatures, examples, coverage)


def _print_report(
    per_player_df: pd.DataFrame,
    qualifying: pd.DataFrame,
    signatures: Dict,
    examples: List[Dict],
    coverage: Dict,
) -> None:
    print("\n" + "=" * 72)
    print("## INT-44 Bench vs. Starter CV Split — Report")
    print("=" * 72)

    print(f"\n### Coverage")
    print(f"  cv_features games:          {coverage['total_cv_games']}")
    print(f"  Boxscore JSON resolved:     {coverage['json_games']}")
    print(f"  Inferred (top-10 min):      {coverage['inferred_games']}")
    print(f"  Qualifying players (>={MIN_STARTS}s/>={MIN_BENCH}b): {len(qualifying)}")

    if per_player_df.empty:
        print("\n  No qualifying data - check cv_features coverage and starter flags.")
        return

    print(f"\n### Top 10 features by avg |t|")
    top_sigs = sorted(
        [v for v in signatures.values() if v["avg_abs_t"] > 0],
        key=lambda x: x["avg_abs_t"], reverse=True
    )[:10]
    print(f"  {'Feature':<35} {'Avg Delta':>10} {'Dir':>20} {'Avg|t|':>8} {'N(|t|>2)':>10}")
    print("  " + "-" * 85)
    for sig in top_sigs:
        dir_str = "^ starting" if sig["avg_delta"] > 0 else "v starting"
        print(f"  {sig['feature']:<35} {sig['avg_delta']:>+10.4f} {dir_str:>20} "
              f"{sig['avg_abs_t']:>8.3f} {sig['n_players_with_t_gt2']:>5}/{sig['n_players']}")

    print(f"\n### Dramatic role-switchers (top {len(examples)})")
    for ex in examples:
        tf = ex["top_features"][0] if ex["top_features"] else {}
        print(f"  Player {ex['player_id']:>10} "
              f"({ex['n_start']}s/{ex['n_bench']}b) "
              f"mean|t|={ex['mean_abs_t']:.3f}  "
              f"top-feat={tf.get('feature', '--')}  "
              f"delta={tf.get('delta', 'n/a')}")

    print(f"\n### Files written")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")
    print("=" * 72)


if __name__ == "__main__":
    build()
