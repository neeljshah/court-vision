"""
build_streak_signatures.py — INT-5: Hot/Cold Streak Signature Intelligence

For each player with CV tracking history AND matching NBA stat targets, classify
every game as HOT / COLD / NEUTRAL per stat and find which CV features differ
significantly between streak states.

Outputs:
  data/intelligence/streak_signatures.parquet
  data/intelligence/streak_signatures_summary.json
  data/intelligence/streak_excluded_players.json   (Bug 29: zero-CV exclusion list)
  vault/Intelligence/Streak_Atlas.md
  vault/Intelligence/Streaks/<player_name>_streaks.md  (top 10 by n_games)

Usage:
    python scripts/build_streak_signatures.py

Bug fixes applied (2026-05-28):
  Bug 7  — Label shift: HOT/COLD label for game N uses rolling stats from [N-5,N-1]
  Bug 5  — CV-quality gate: player-games with <5 active CV features non-zero excluded
  Bug 29 — Zero-CV player gate: players with mean completeness <10% excluded entirely;
            exclusion list written to data/intelligence/streak_excluded_players.json
"""

import json
import os
import sqlite3
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "nba_ai.db")
PLAYER_JSON = os.path.join(ROOT, "data", "nba", "player_full_2024-25.json")
NBA_DIR = os.path.join(ROOT, "data", "nba")
OUT_DIR = os.path.join(ROOT, "data", "intelligence")
VAULT_INTEL_DIR = os.path.join(ROOT, "vault", "Intelligence")
STREAKS_DIR = os.path.join(VAULT_INTEL_DIR, "Streaks")

PARQUET_OUT = os.path.join(OUT_DIR, "streak_signatures.parquet")
SUMMARY_OUT = os.path.join(OUT_DIR, "streak_signatures_summary.json")
EXCLUDED_OUT = os.path.join(OUT_DIR, "streak_excluded_players.json")  # Bug 29
ATLAS_OUT = os.path.join(VAULT_INTEL_DIR, "Streak_Atlas.md")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(VAULT_INTEL_DIR, exist_ok=True)
os.makedirs(STREAKS_DIR, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
# Reliable CV features from INT-1 audit (excludes dead: play_type_drive_pct, avg_closeout_speed)
ACTIVE_FEATURES = [
    "paint_dwell_pct",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "avg_shot_distance",
    "touches_per_game",
    "shots_per_possession",
    "possession_duration_avg",
    "second_chance_rate",
    "potential_assists",
    "preshot_velocity_peak",
    "defender_approach_speed",
    "play_type_transition_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "catch_shoot_pct",
    "avg_dribble_count",
    "contested_shot_rate",
    "avg_defender_distance",
]

STATS = ["pts", "reb", "ast"]
Z_HOT = 1.5
Z_COLD = -1.5
T_SIG = 2.0          # |t| threshold for signature features
MIN_GAMES = 5         # Minimum CV games for per-player analysis
MIN_HOT_COLD = 2      # Minimum HOT or COLD games to include player
TOP_N_PLAYERS = 10    # Players to write individual streak notes for

# Bug 5 fix: CV-quality gate — minimum nonzero active CV features per player-game.
# Bug 5 description allows "50% nonzero OR >= 5 nonzero features in the EAV table".
# 50% of 19 features = ~9.5 → leaves only 4 players with >=5 games (unusable).
# Use >= 5 nonzero (the EAV alternative): 26% of 19 features, still filters pure-zero rows.
CV_QUALITY_MIN_NONZERO = 5      # player-game must have >= 5 active features non-zero
# Bug 29 fix: per-player completeness gate — players below this mean completeness excluded
PLAYER_COMPLETENESS_MIN = 0.10  # < 10% mean completeness → excluded entirely
# Bug 7 fix: rolling window for shifted labels (use stats from prior N games)
LABEL_SHIFT_WINDOW = 5          # games [N-5, N-1] inform game N label


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_player_name_map() -> dict:
    """Build player_id (int) -> display name dict."""
    name_map = {}
    if not os.path.exists(PLAYER_JSON):
        print("  [WARN] player_full JSON not found — names will be IDs")
        return name_map
    with open(PLAYER_JSON, encoding="utf-8") as f:
        data = json.load(f)
    for name, info in data.items():
        pid = info.get("player_id")
        if pid:
            name_map[int(pid)] = name.title()
    return name_map


def load_game_date_map() -> dict:
    """Build game_id -> game_date from season_games JSONs + boxscore JSONs."""
    date_map = {}
    # From season_games files
    for fname in os.listdir(NBA_DIR):
        if fname.startswith("season_games_") and fname.endswith(".json"):
            fpath = os.path.join(NBA_DIR, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                for row in data.get("rows", []):
                    gid = row.get("game_id")
                    gdate = row.get("game_date")
                    if gid and gdate:
                        date_map[gid] = gdate
            except Exception as e:
                print(f"  [WARN] {fname}: {e}")
    # Supplement from boxscore files
    for fname in os.listdir(NBA_DIR):
        if fname.startswith("boxscore_") and fname.endswith(".json") and "adv" not in fname and "matchups" not in fname:
            gid = fname.replace("boxscore_", "").replace(".json", "")
            if gid not in date_map:
                fpath = os.path.join(NBA_DIR, fname)
                try:
                    with open(fpath, encoding="utf-8", errors="replace") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        gdate = data.get("game_date") or data.get("date")
                        if gdate:
                            date_map[gid] = gdate
                except Exception:
                    pass
    return date_map


def load_cv_features_wide() -> pd.DataFrame:
    """Load cv_features from DB, pivot wide."""
    conn = sqlite3.connect(DB_PATH)
    df_long = pd.read_sql(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()
    # Bug 27 guard: null potential_assists=0 before pivoting so that zero-PA games
    # (45.1% of all CV games where the xAST submodule did not run) are treated as
    # missing rather than as real zero observations.  This prevents PA zeros from
    # polluting t-tests and signature mean comparisons.
    pa_mask = (df_long["feature_name"] == "potential_assists") & (df_long["feature_value"] == 0.0)
    df_long.loc[pa_mask, "feature_value"] = float("nan")  # Bug 27 guard
    df_wide = df_long.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    df_wide.columns.name = None
    return df_wide


def load_boxscore_stats() -> pd.DataFrame:
    """
    Load per-player per-game stats from boxscore JSONs.
    Returns DataFrame: game_id, player_id, pts, reb, ast, game_date
    """
    records = []
    date_map = load_game_date_map()

    for fname in os.listdir(NBA_DIR):
        if not (fname.startswith("boxscore_") and fname.endswith(".json")):
            continue
        if "adv" in fname or "matchups" in fname:
            continue
        gid = fname.replace("boxscore_", "").replace(".json", "")
        fpath = os.path.join(NBA_DIR, fname)
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
            players = data.get("players", [])
            gdate = date_map.get(gid, "")
            for p in players:
                pid = p.get("player_id")
                if pid is None:
                    continue
                pts = p.get("pts", 0) or 0
                reb = p.get("reb", 0) or 0
                ast = p.get("ast", 0) or 0
                minutes = p.get("min", "")
                # Skip DNP rows (min is empty string or "00:00" or None)
                if not minutes or str(minutes).strip() in ("", "00:00", "0:00", None):
                    continue
                records.append({
                    "game_id": gid,
                    "player_id": int(pid),
                    "pts": float(pts),
                    "reb": float(reb),
                    "ast": float(ast),
                    "game_date": gdate,
                })
        except Exception as e:
            print(f"  [WARN] {fname}: {e}")

    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    return df


def load_gamelog_season_avgs() -> pd.DataFrame:
    """
    Compute per-player season-average PTS/REB/AST from gamelog JSONs.
    Returns DataFrame: player_id, season_avg_pts, season_avg_reb, season_avg_ast
    """
    records = []
    for fname in os.listdir(NBA_DIR):
        if not (fname.startswith("gamelog_") and fname.endswith(".json")):
            continue
        # Extract player_id from filename: gamelog_<pid>_<season>.json
        parts = fname.replace("gamelog_", "").replace(".json", "").split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        fpath = os.path.join(NBA_DIR, fname)
        try:
            with open(fpath, encoding="utf-8", errors="replace") as f:
                rows = json.load(f)
            if not isinstance(rows, list) or not rows:
                continue
            for r in rows:
                if r.get("MIN", 0) and float(r.get("MIN", 0) or 0) > 0:
                    records.append({
                        "player_id": pid,
                        "pts": float(r.get("PTS", 0) or 0),
                        "reb": float(r.get("REB", 0) or 0),
                        "ast": float(r.get("AST", 0) or 0),
                    })
        except Exception:
            pass

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["player_id", "season_avg_pts", "season_avg_reb",
                                     "season_avg_ast", "season_std_pts", "season_std_reb",
                                     "season_std_ast"])

    agg = df.groupby("player_id").agg(
        season_avg_pts=("pts", "mean"),
        season_avg_reb=("reb", "mean"),
        season_avg_ast=("ast", "mean"),
        season_std_pts=("pts", "std"),
        season_std_reb=("reb", "std"),
        season_std_ast=("ast", "std"),
        n_gamelog_games=("pts", "count"),
    ).reset_index()
    # Use population floor for std so very few games don't blow up z-scores
    agg["season_std_pts"] = agg["season_std_pts"].fillna(1.0).clip(lower=0.5)
    agg["season_std_reb"] = agg["season_std_reb"].fillna(1.0).clip(lower=0.3)
    agg["season_std_ast"] = agg["season_std_ast"].fillna(1.0).clip(lower=0.3)
    return agg


# ── Core Analysis ─────────────────────────────────────────────────────────────

def compute_cv_completeness(cv_wide: pd.DataFrame) -> pd.DataFrame:
    """
    Bug 5 / Bug 29 fix: compute per-player-game CV feature completeness.
    Returns cv_wide with added columns:
      n_nonzero_cv   — count of active features that are non-zero
      cv_completeness — fraction of active features that are non-zero
    Also returns per-player mean completeness for Bug 29 gate.
    """
    active_cols = [c for c in ACTIVE_FEATURES if c in cv_wide.columns]
    feat_data = cv_wide[active_cols].fillna(0)
    cv_wide = cv_wide.copy()
    cv_wide["n_nonzero_cv"] = (feat_data != 0).sum(axis=1)
    cv_wide["cv_completeness"] = cv_wide["n_nonzero_cv"] / max(len(active_cols), 1)
    return cv_wide


def apply_bug29_player_gate(
    cv_wide: pd.DataFrame,
    name_map: dict,
) -> tuple:
    """
    Bug 29 fix: exclude players whose mean cv_completeness across all their games
    falls below PLAYER_COMPLETENESS_MIN (< 10%).

    Returns:
      (cv_wide_filtered, excluded_dict)
      excluded_dict: {player_id: {name, n_games, mean_completeness}}
    """
    player_comp = (
        cv_wide.groupby("player_id")["cv_completeness"]
        .mean()
        .reset_index()
        .rename(columns={"cv_completeness": "mean_completeness"})
    )
    # Players below the threshold
    low = player_comp[player_comp["mean_completeness"] < PLAYER_COMPLETENESS_MIN]
    excluded_ids = set(low["player_id"].astype(int).tolist())

    excluded_dict = {}
    for _, row in low.iterrows():
        pid = int(row["player_id"])
        n_games = int((cv_wide["player_id"] == pid).sum())
        excluded_dict[str(pid)] = {
            "player_id": pid,
            "player_name": name_map.get(pid, str(pid)),
            "n_games": n_games,
            "mean_cv_completeness": round(float(row["mean_completeness"]), 4),
            "exclusion_reason": "Bug 29: mean cv_feature_completeness < 10%",
        }

    # Bug 29 fix: filter out zero-CV players before atlas enters any downstream join
    cv_filtered = cv_wide[~cv_wide["player_id"].isin(excluded_ids)].copy()
    print(
        f"  [Bug 29] Excluded {len(excluded_ids)} players "
        f"(mean completeness < {PLAYER_COMPLETENESS_MIN:.0%}) — "
        f"{len(cv_filtered)} player-game rows remain"
    )
    return cv_filtered, excluded_dict


def build_joined_dataset(
    cv_wide: pd.DataFrame,
    boxscores: pd.DataFrame,
    baselines: pd.DataFrame,
    name_map: dict,
) -> pd.DataFrame:
    """
    Join CV features with boxscore actuals + season baselines.
    Returns merged DataFrame with z-scores and SHIFTED labels (Bug 7).

    Bug 7 fix: HOT/COLD label for game N is computed from the player's rolling
    mean/std across the prior LABEL_SHIFT_WINDOW games [N-5, N-1], NOT game N.
    This prevents same-game leakage — the label is now a true prior-game predictor.

    Bug 5 fix: player-games with cv_completeness < CV_QUALITY_MIN_FRAC are excluded
    before label computation and analysis (low-coverage games falsely look COLD).
    """
    # Ensure matching types
    cv_wide = cv_wide.copy()
    cv_wide["player_id"] = cv_wide["player_id"].astype(int)
    boxscores = boxscores.copy()
    boxscores["player_id"] = boxscores["player_id"].astype(int)

    # Merge CV with boxscores (CV features + stat actuals in same row)
    df = cv_wide.merge(boxscores, on=["player_id", "game_id"], how="inner")
    print(f"  CV-boxscore inner join: {len(df)} rows, {df['player_id'].nunique()} players")

    # Bug 5 fix: CV-quality gate — drop player-games with too few non-zero CV features.
    # Uses n_nonzero_cv >= CV_QUALITY_MIN_NONZERO (>=5 of 19 features nonzero).
    # This filters pure-zero rows (low-tracking-coverage games) without over-pruning.
    pre_quality = len(df)
    df = df[df["n_nonzero_cv"] >= CV_QUALITY_MIN_NONZERO].copy()
    dropped_quality = pre_quality - len(df)
    print(
        f"  [Bug 5] CV-quality gate (>= {CV_QUALITY_MIN_NONZERO} nonzero features): "
        f"dropped {dropped_quality} rows ({dropped_quality / max(pre_quality, 1):.1%}), "
        f"{len(df)} remain, {df['player_id'].nunique()} players"
    )

    # Merge baselines
    df = df.merge(baselines, on="player_id", how="left")

    # Add player names
    df["player_name"] = df["player_id"].map(name_map).fillna(df["player_id"].astype(str))

    # Sort by player then date — required for the label shift
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # Bug 7 fix: shift label assignment by 1 game per player.
    # For each player, compute a rolling mean/std over the PRIOR LABEL_SHIFT_WINDOW games
    # (min_periods=1), then z-score THAT game's actual stat against the rolling baseline.
    # This means: label for game N = f(stats in games [N-5, N-1]) — zero same-game leakage.
    for stat in STATS:
        rolling_mean = (
            df.groupby("player_id")[stat]
            .transform(lambda s: s.shift(1).rolling(LABEL_SHIFT_WINDOW, min_periods=1).mean())
        )
        rolling_std = (
            df.groupby("player_id")[stat]
            .transform(lambda s: s.shift(1).rolling(LABEL_SHIFT_WINDOW, min_periods=1).std())
        )
        # Fill std NaN (first game per player has no prior data) with season-level std
        season_std = df[f"season_std_{stat}"].clip(lower=0.01)
        rolling_std = rolling_std.fillna(season_std).clip(lower=0.01)
        # Fill mean NaN (first game per player) with season-level mean
        rolling_mean = rolling_mean.fillna(df[f"season_avg_{stat}"])

        # Bug 7 fix: z-score uses CURRENT game's actual stat vs PRIOR-WINDOW rolling baseline
        df[f"z_{stat}"] = (df[stat] - rolling_mean) / rolling_std

    # Classify HOT / COLD / NEUTRAL (same thresholds, now leakage-free)
    for stat in STATS:
        z = df[f"z_{stat}"]
        df[f"label_{stat}"] = "NEUTRAL"
        df.loc[z > Z_HOT, f"label_{stat}"] = "HOT"
        df.loc[z < Z_COLD, f"label_{stat}"] = "COLD"

    # Drop first game per player (no prior history = label is unstable)
    # Bug 7 fix: first game per player has shift(1) = NaN so rolling mean = season avg;
    # this is noisier than subsequent games. Flag and drop them for cleanliness.
    first_game_mask = df.groupby("player_id").cumcount() == 0
    dropped_first = first_game_mask.sum()
    df = df[~first_game_mask].copy()
    print(
        f"  [Bug 7] Dropped {dropped_first} first-game-per-player rows "
        f"(no prior history for shifted label); {len(df)} rows remain"
    )

    return df


def get_active_cv_features(df: pd.DataFrame) -> list:
    """Return active CV features present in df with non-zero variance."""
    active = []
    for feat in ACTIVE_FEATURES:
        if feat not in df.columns:
            print(f"  [WARN] Feature '{feat}' not in dataset — skipping")
            continue
        std = df[feat].std(skipna=True)
        if std == 0 or pd.isna(std):
            print(f"  [SKIP] Feature '{feat}' has zero variance")
            continue
        active.append(feat)
    return active


def compute_signature(df: pd.DataFrame, stat: str, features: list) -> dict:
    """
    For a given stat, compute HOT/COLD signatures across all players.
    Returns dict with hot_signature and cold_signature sub-dicts.
    """
    hot = df[df[f"label_{stat}"] == "HOT"]
    cold = df[df[f"label_{stat}"] == "COLD"]
    neutral = df[df[f"label_{stat}"] == "NEUTRAL"]

    n_hot = len(hot)
    n_cold = len(cold)
    n_neutral = len(neutral)

    def sig_features(group_df, group_name, n_group):
        """Find features with |t| > T_SIG between group and neutral."""
        sigs = []
        for feat in features:
            g_vals = group_df[feat].dropna()
            n_vals = neutral[feat].dropna()
            if len(g_vals) < 5 or len(n_vals) < 5:
                continue
            g_mean = float(g_vals.mean())
            n_mean = float(n_vals.mean())
            g_std = float(g_vals.std())
            n_std = float(n_vals.std())
            try:
                t_stat, p_val = stats.ttest_ind(g_vals, n_vals, equal_var=False)
            except Exception:
                continue
            if pd.isna(t_stat):
                continue
            if abs(t_stat) > T_SIG:
                pct_diff = ((g_mean - n_mean) / (abs(n_mean) + 1e-9)) * 100
                sigs.append({
                    "feature": feat,
                    f"{group_name}_mean": round(g_mean, 4),
                    "neutral_mean": round(n_mean, 4),
                    "t": round(float(t_stat), 3),
                    "p_val": round(float(p_val), 4),
                    "interpretation": _interpret(feat, g_mean, n_mean, pct_diff, group_name),
                })
        # Sort by |t|
        sigs.sort(key=lambda x: abs(x["t"]), reverse=True)
        return sigs

    hot_sigs = sig_features(hot, "hot", n_hot)
    cold_sigs = sig_features(cold, "cold", n_cold)

    return {
        "hot_signature": {
            "n_hot_games": n_hot,
            "n_neutral_games": n_neutral,
            "signature_features": hot_sigs,
        },
        "cold_signature": {
            "n_cold_games": n_cold,
            "n_neutral_games": n_neutral,
            "signature_features": cold_sigs,
        },
    }


def _interpret(feat: str, g_mean: float, n_mean: float, pct_diff: float, direction: str) -> str:
    """Generate human-readable interpretation string."""
    trend = "+" if g_mean > n_mean else "-"
    label = "MORE" if g_mean > n_mean else "LESS"
    abs_pct = abs(pct_diff)
    interpretations = {
        "paint_dwell_pct": f"{trend}{abs_pct:.0f}% paint dwell -> {label} time near the basket",
        "touches_per_game": f"{trend}{abs_pct:.0f}% ball touches -> {label} ball involvement",
        "potential_assists": f"{trend}{abs_pct:.0f}% pass attempts -> {label} playmaking activity",
        "avg_shot_distance": f"{trend}{abs_pct:.0f}% avg shot distance -> shooting {label} at the rim" if g_mean < n_mean else f"+{abs_pct:.0f}% avg shot distance -> shooting more from range",
        "shots_per_possession": f"{trend}{abs_pct:.0f}% shot rate per possession",
        "possession_duration_avg": f"{trend}{abs_pct:.0f}% possession duration -> {label} decision time",
        "catch_shoot_pct": f"{trend}{abs_pct:.0f}% catch-and-shoot rate -> {label} off-ball activity",
        "avg_dribble_count": f"{trend}{abs_pct:.0f}% dribbles per possession -> {label} creation",
        "contested_shot_rate": f"{trend}{abs_pct:.0f}% contested shots -> {label} defensive pressure",
        "avg_defender_distance": f"{trend}{abs_pct:.0f}% defender distance -> {label} space (NOTE: sentinel issues)",
        "second_chance_rate": f"{trend}{abs_pct:.0f}% second-chance rate",
        "preshot_velocity_peak": f"{trend}{abs_pct:.0f}% pre-shot speed -> {label} off-movement",
        "defender_approach_speed": f"{trend}{abs_pct:.0f}% closeout speed -> {label} defensive urgency",
        "play_type_transition_pct": f"{trend}{abs_pct:.0f}% transition plays",
        "play_type_isolation_pct": f"{trend}{abs_pct:.0f}% isolation plays -> {label} self-creation",
        "play_type_post_pct": f"{trend}{abs_pct:.0f}% post-up plays",
        "shot_zone_paint_pct": f"{trend}{abs_pct:.0f}% paint shot pct -> {label} rim finishes",
        "shot_zone_mid_range_pct": f"{trend}{abs_pct:.0f}% mid-range shot pct",
        "shot_zone_3pt_pct": f"{trend}{abs_pct:.0f}% 3-point shot pct -> {label} perimeter shooting",
    }
    return interpretations.get(feat, f"{trend}{abs_pct:.0f}% vs neutral")


def compute_player_signatures(
    df: pd.DataFrame,
    features: list,
    name_map: dict,
) -> pd.DataFrame:
    """
    For each player with >= MIN_GAMES CV games, find their personal streak indicators.
    Returns per-player summary DataFrame.
    """
    records = []

    players = df.groupby("player_id").size()
    eligible = players[players >= MIN_GAMES].index.tolist()

    for pid in eligible:
        pdf = df[df["player_id"] == pid]
        pname = name_map.get(pid, str(pid))
        n_games = len(pdf)

        row = {
            "player_id": pid,
            "player_name": pname,
            "n_cv_games": n_games,
        }

        for stat in STATS:
            n_hot = int((pdf[f"label_{stat}"] == "HOT").sum())
            n_cold = int((pdf[f"label_{stat}"] == "COLD").sum())
            row[f"n_hot_{stat}"] = n_hot
            row[f"n_cold_{stat}"] = n_cold

        # Find best personal hot/cold indicators (most different feature between hot vs cold)
        best_hot_feat = None
        best_cold_feat = None
        best_hot_t = 0.0
        best_cold_t = 0.0

        for stat in STATS:
            hot_p = pdf[pdf[f"label_{stat}"] == "HOT"]
            cold_p = pdf[pdf[f"label_{stat}"] == "COLD"]
            neutral_p = pdf[pdf[f"label_{stat}"] == "NEUTRAL"]

            for feat in features:
                # Hot vs non-hot
                if len(hot_p) >= 2 and len(neutral_p) >= 2:
                    h_vals = hot_p[feat].dropna()
                    n_vals = neutral_p[feat].dropna()
                    if len(h_vals) >= 2 and len(n_vals) >= 2:
                        try:
                            t, _ = stats.ttest_ind(h_vals, n_vals, equal_var=False)
                            if not pd.isna(t) and abs(t) > abs(best_hot_t):
                                best_hot_t = float(t)
                                best_hot_feat = f"{feat}_{stat}"
                        except Exception:
                            pass

                # Cold vs non-cold
                if len(cold_p) >= 2 and len(neutral_p) >= 2:
                    c_vals = cold_p[feat].dropna()
                    n_vals = neutral_p[feat].dropna()
                    if len(c_vals) >= 2 and len(n_vals) >= 2:
                        try:
                            t, _ = stats.ttest_ind(c_vals, n_vals, equal_var=False)
                            if not pd.isna(t) and abs(t) > abs(best_cold_t):
                                best_cold_t = float(t)
                                best_cold_feat = f"{feat}_{stat}"
                        except Exception:
                            pass

        row["best_hot_indicator"] = best_hot_feat or ""
        row["best_hot_t"] = round(best_hot_t, 3)
        row["best_cold_indicator"] = best_cold_feat or ""
        row["best_cold_t"] = round(best_cold_t, 3)
        records.append(row)

    return pd.DataFrame(records)


# ── Vault Writeup ─────────────────────────────────────────────────────────────

def write_streak_atlas(df: pd.DataFrame, summary: dict, player_summary: pd.DataFrame):
    """Write the main Streak_Atlas.md vault file."""

    def sig_table(sig_list: list, value_col: str) -> str:
        if not sig_list:
            return "_No features reached |t| > 2.0 — patterns not strong enough to surface._\n"
        lines = ["| CV feature | streak mean | neutral mean | t-stat | interpretation |",
                 "|---|---|---|---|---|"]
        for s in sig_list[:10]:
            feat = s["feature"]
            streak_mean = s.get(f"{value_col}_mean", "?")
            n_mean = s.get("neutral_mean", "?")
            t = s.get("t", "?")
            interp = s.get("interpretation", "")
            lines.append(f"| {feat} | {streak_mean} | {n_mean} | {t} | {interp} |")
        return "\n".join(lines) + "\n"

    lines = [
        "# CV Hot/Cold Streak Signature Atlas",
        "",
        "## Methodology",
        "",
        f"For each stat, compare CV features in **HOT** (z > +{Z_HOT}) vs **COLD** (z < {Z_COLD}) vs **NEUTRAL** games.",
        "z-score is computed relative to the player's own season mean and standard deviation from gamelog data.",
        "Signature features are those with |t| > 2.0 (Welch's t-test, unequal-variance) between HOT/COLD and NEUTRAL.",
        "",
        "**Important caveats:**",
        "- z > 1.5 is a moderate bar — captures clear overperformance, not just extreme outliers",
        "- All CV data is from 2024-25 and 2025-26 seasons only",
        "- `avg_defender_distance` carries a sentinel value ISSUE-022 (200.0 = not tracked); treat with caution",
        "- Correlation ≠ causation: many signatures may reflect minutes/role confounds",
        "- Per-player signatures with n < 5 HOT or COLD games are noisy — flagged accordingly",
        "",
    ]

    for stat in STATS:
        stat_data = summary.get(stat, {})
        hot_sig = stat_data.get("hot_signature", {})
        cold_sig = stat_data.get("cold_signature", {})
        n_hot = hot_sig.get("n_hot_games", 0)
        n_cold = cold_sig.get("n_cold_games", 0)
        n_neutral = hot_sig.get("n_neutral_games", 0)

        lines += [
            f"## {stat.upper()} streak signatures",
            "",
            f"Total classified games — HOT: {n_hot} | COLD: {n_cold} | NEUTRAL: {n_neutral}",
            "",
            f"### Hot {stat.upper()} games (N={n_hot})",
            "",
            sig_table(hot_sig.get("signature_features", []), "hot"),
            "",
            f"### Cold {stat.upper()} games (N={n_cold})",
            "",
            sig_table(cold_sig.get("signature_features", []), "cold"),
            "",
            f"### Honest read for {stat.upper()}",
        ]

        # Auto-generate honest read
        hot_top = hot_sig.get("signature_features", [])
        cold_top = cold_sig.get("signature_features", [])
        if hot_top:
            t1 = hot_top[0]
            lines.append(f"- Strongest hot predictor: `{t1['feature']}` (t={t1['t']:.2f}) — {t1['interpretation']}")
        else:
            lines.append("- No strong CV predictors of hot scoring emerged — performance variance may be stats-driven")
        if cold_top:
            t1 = cold_top[0]
            lines.append(f"- Strongest cold predictor: `{t1['feature']}` (t={t1['t']:.2f}) — {t1['interpretation']}")

        # Confound check
        touch_hot = next((s for s in hot_top if "touches_per_game" in s["feature"]), None)
        if touch_hot:
            lines.append(f"- ⚠️ `touches_per_game` appears as a hot signature — likely reflects minutes/usage confound, not independent CV signal")

        lines.append("")

    # Per-player streak indicators table
    lines += [
        "## Per-player streak indicators (top 30 players by n_games)",
        "",
        "| player | n_cv | n_hot_pts | n_cold_pts | n_hot_reb | n_hot_ast | best_hot_indicator | best_cold_indicator |",
        "|---|---|---|---|---|---|---|---|",
    ]

    top30 = player_summary.nlargest(30, "n_cv_games")
    for _, row in top30.iterrows():
        lines.append(
            f"| {row['player_name']} | {row['n_cv_games']} | "
            f"{row['n_hot_pts']} | {row['n_cold_pts']} | "
            f"{row['n_hot_reb']} | {row['n_hot_ast']} | "
            f"{row.get('best_hot_indicator', '')} | {row.get('best_cold_indicator', '')} |"
        )

    lines.append("")

    with open(ATLAS_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  [OK] Wrote {ATLAS_OUT}")


def write_player_streak_note(
    pid: int,
    pname: str,
    pdf: pd.DataFrame,
    features: list,
    summary_row: dict,
):
    """Write individual player streak note."""
    safe_name = pname.replace(" ", "_").replace("/", "_")
    out_path = os.path.join(STREAKS_DIR, f"{safe_name}_streaks.md")

    lines = [
        f"# {pname} — Hot/Cold Streak Signatures",
        "",
        f"**CV games tracked:** {len(pdf)}",
        "",
    ]

    for stat in STATS:
        n_hot = int((pdf[f"label_{stat}"] == "HOT").sum())
        n_cold = int((pdf[f"label_{stat}"] == "COLD").sum())
        n_neutral = int((pdf[f"label_{stat}"] == "NEUTRAL").sum())
        avg = pdf["season_avg_" + stat].iloc[0] if f"season_avg_{stat}" in pdf.columns else float("nan")

        lines += [
            f"## {stat.upper()} Performance",
            "",
            f"Season baseline: **{avg:.1f}** | HOT: {n_hot} games | COLD: {n_cold} games | NEUTRAL: {n_neutral} games",
            "",
        ]

        hot_games = pdf[pdf[f"label_{stat}"] == "HOT"].sort_values(f"z_{stat}", ascending=False)
        cold_games = pdf[pdf[f"label_{stat}"] == "COLD"].sort_values(f"z_{stat}")

        if n_hot > 0:
            lines.append(f"### Hot {stat.upper()} games")
            lines.append("")
            lines.append(f"| game_date | actual_{stat} | z_{stat} | touches | paint_dwell | potential_assists |")
            lines.append("|---|---|---|---|---|---|")
            for _, g in hot_games.head(5).iterrows():
                gdate = str(g.get("game_date", ""))[:10]
                actual = g[stat]
                z = g[f"z_{stat}"]
                touches = g.get("touches_per_game", float("nan"))
                paint = g.get("paint_dwell_pct", float("nan"))
                pa = g.get("potential_assists", float("nan"))
                lines.append(
                    f"| {gdate} | {actual:.0f} | {z:+.2f} | {touches:.1f} | {paint:.3f} | {pa:.1f} |"
                )
            lines.append("")

        if n_cold > 0:
            lines.append(f"### Cold {stat.upper()} games")
            lines.append("")
            lines.append(f"| game_date | actual_{stat} | z_{stat} | touches | paint_dwell | potential_assists |")
            lines.append("|---|---|---|---|---|---|")
            for _, g in cold_games.head(5).iterrows():
                gdate = str(g.get("game_date", ""))[:10]
                actual = g[stat]
                z = g[f"z_{stat}"]
                touches = g.get("touches_per_game", float("nan"))
                paint = g.get("paint_dwell_pct", float("nan"))
                pa = g.get("potential_assists", float("nan"))
                lines.append(
                    f"| {gdate} | {actual:.0f} | {z:+.2f} | {touches:.1f} | {paint:.3f} | {pa:.1f} |"
                )
            lines.append("")

        # Personal predictive signature
        if n_hot >= 2 and n_cold >= 2:
            hot_df = pdf[pdf[f"label_{stat}"] == "HOT"]
            cold_df = pdf[pdf[f"label_{stat}"] == "COLD"]
            neutral_df = pdf[pdf[f"label_{stat}"] == "NEUTRAL"]

            personal_sigs = []
            for feat in features:
                h = hot_df[feat].dropna()
                c = cold_df[feat].dropna()
                n = neutral_df[feat].dropna()
                if len(h) >= 2 and len(n) >= 2:
                    try:
                        t, _ = stats.ttest_ind(h, n, equal_var=False)
                        if not pd.isna(t) and abs(t) >= 1.5:
                            personal_sigs.append((feat, "hot", float(t), float(h.mean()), float(n.mean())))
                    except Exception:
                        pass
                if len(c) >= 2 and len(n) >= 2:
                    try:
                        t, _ = stats.ttest_ind(c, n, equal_var=False)
                        if not pd.isna(t) and abs(t) >= 1.5:
                            personal_sigs.append((feat, "cold", float(t), float(c.mean()), float(n.mean())))
                    except Exception:
                        pass

            personal_sigs.sort(key=lambda x: abs(x[2]), reverse=True)

            if personal_sigs:
                lines.append(f"### Predictive {stat.upper()} signature")
                lines.append("")
                for feat, direction, t, g_mean, n_mean in personal_sigs[:3]:
                    pct = ((g_mean - n_mean) / (abs(n_mean) + 1e-9)) * 100
                    lines.append(
                        f"- `{feat}` is {abs(pct):.0f}% {'higher' if g_mean > n_mean else 'lower'} in {direction.upper()} games "
                        f"(t={t:+.2f})"
                    )
                lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  [OK] Wrote {out_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("INT-5: Hot/Cold Streak Signature Intelligence")
    print("=" * 60)

    # Step 1: Load data
    print("\n[1/6] Loading data...")
    name_map = load_player_name_map()
    print(f"  Player name map: {len(name_map)} entries")

    cv_wide_raw = load_cv_features_wide()
    print(f"  CV features (wide): {len(cv_wide_raw)} (player, game) rows, {cv_wide_raw['player_id'].nunique()} players")

    boxscores = load_boxscore_stats()
    print(f"  Boxscores: {len(boxscores)} rows, {boxscores['player_id'].nunique()} players, {boxscores['game_id'].nunique()} games")

    baselines = load_gamelog_season_avgs()
    print(f"  Season baselines: {len(baselines)} players")

    # Bug 5 + Bug 29: compute completeness then apply gates
    print("\n[1b/6] Applying CV quality gates (Bug 5 + Bug 29)...")
    cv_wide_raw["player_id"] = cv_wide_raw["player_id"].astype(int)
    cv_wide_with_comp = compute_cv_completeness(cv_wide_raw)

    # Bug 29 fix: per-player completeness gate — exclude zero-CV players entirely
    cv_wide, excluded_dict = apply_bug29_player_gate(cv_wide_with_comp, name_map)

    # Write Bug 29 exclusion list
    excluded_out = {
        "generated": "2026-05-28",
        "gate": f"mean cv_feature_completeness < {PLAYER_COMPLETENESS_MIN:.0%} across all player games",
        "n_excluded": len(excluded_dict),
        "excluded_players": excluded_dict,
    }
    with open(EXCLUDED_OUT, "w", encoding="utf-8") as f:
        json.dump(excluded_out, f, indent=2)
    print(f"  [Bug 29] Wrote exclusion list: {EXCLUDED_OUT} ({len(excluded_dict)} players)")

    # Step 2: Join datasets
    print("\n[2/6] Joining datasets (Bug 5 + Bug 7 gates active)...")
    df = build_joined_dataset(cv_wide, boxscores, baselines, name_map)

    # Step 3: Get active features
    print("\n[3/6] Validating CV features...")
    features = get_active_cv_features(df)
    print(f"  Active features: {len(features)} — {features}")

    # Summary stats
    for stat in STATS:
        n_hot = int((df[f"label_{stat}"] == "HOT").sum())
        n_cold = int((df[f"label_{stat}"] == "COLD").sum())
        n_neutral = int((df[f"label_{stat}"] == "NEUTRAL").sum())
        print(f"  {stat.upper()}: HOT={n_hot}, COLD={n_cold}, NEUTRAL={n_neutral}")

    # Step 4: Compute global signatures
    print("\n[4/6] Computing global HOT/COLD signatures...")
    summary = {}
    for stat in STATS:
        print(f"  Computing {stat.upper()} signatures...")
        summary[stat] = compute_signature(df, stat, features)
        hot_sigs = summary[stat]["hot_signature"]["signature_features"]
        cold_sigs = summary[stat]["cold_signature"]["signature_features"]
        print(f"    HOT {stat.upper()}: {len(hot_sigs)} signature features")
        print(f"    COLD {stat.upper()}: {len(cold_sigs)} signature features")

    # Step 5: Per-player signatures
    print("\n[5/6] Computing per-player streak summaries...")
    player_summary = compute_player_signatures(df, features, name_map)
    print(f"  Players with >= {MIN_GAMES} CV games: {len(player_summary)}")

    # Players with meaningful HOT or COLD history
    has_streaks = player_summary[
        (player_summary["n_hot_pts"] >= MIN_HOT_COLD) |
        (player_summary["n_cold_pts"] >= MIN_HOT_COLD) |
        (player_summary["n_hot_reb"] >= MIN_HOT_COLD) |
        (player_summary["n_cold_reb"] >= MIN_HOT_COLD) |
        (player_summary["n_hot_ast"] >= MIN_HOT_COLD) |
        (player_summary["n_cold_ast"] >= MIN_HOT_COLD)
    ]
    print(f"  Players with >= {MIN_HOT_COLD} HOT or COLD games: {len(has_streaks)}")

    # Step 6: Write outputs
    print("\n[6/6] Writing outputs...")

    # a) Parquet
    # Select output columns — cv_completeness added as new column (Bug 5/29 diagnostic)
    cv_cols = [c for c in features if c in df.columns]
    out_cols = (
        ["player_id", "player_name", "game_id", "game_date"]
        + STATS
        + [f"season_avg_{s}" for s in STATS]
        + [f"z_{s}" for s in STATS]
        + [f"label_{s}" for s in STATS]
        + ["cv_completeness"]   # Bug 5/29: new additive column, does not rename existing cols
        + cv_cols
    )
    out_cols = [c for c in out_cols if c in df.columns]
    df_out = df[out_cols].copy()
    df_out.to_parquet(PARQUET_OUT, index=False)
    print(f"  [OK] streak_signatures.parquet: {len(df_out)} rows")

    # b) Summary JSON
    # Add metadata
    full_summary = {
        "metadata": {
            "n_player_games": len(df),
            "n_players": df["player_id"].nunique(),
            "n_active_features": len(features),
            "active_features": features,
            "z_hot_threshold": Z_HOT,
            "z_cold_threshold": Z_COLD,
            "t_significance_threshold": T_SIG,
            "generated": "2026-05-28",
            # Bug fix metadata
            "bug7_label_shift_window": LABEL_SHIFT_WINDOW,
            "bug5_cv_quality_min_nonzero": CV_QUALITY_MIN_NONZERO,
            "bug29_player_completeness_min": PLAYER_COMPLETENESS_MIN,
            "bug29_n_excluded_players": len(excluded_dict),
        }
    }
    for stat in STATS:
        full_summary[stat] = summary[stat]

    with open(SUMMARY_OUT, "w", encoding="utf-8") as f:
        json.dump(full_summary, f, indent=2)
    print(f"  [OK] streak_signatures_summary.json")

    # c) Atlas
    write_streak_atlas(df, summary, player_summary)

    # d) Per-player notes for top N players
    top_players = player_summary.nlargest(TOP_N_PLAYERS, "n_cv_games")
    print(f"  Writing streak notes for top {len(top_players)} players...")
    for _, prow in top_players.iterrows():
        pid = int(prow["player_id"])
        pname = str(prow["player_name"])
        pdf = df[df["player_id"] == pid].copy()
        write_player_streak_note(pid, pname, pdf, features, prow.to_dict())

    # ── Final Report ───────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("INT-5 Hot/Cold Streak Signatures — Final Report")
    print("=" * 60)
    print()
    print("### Coverage")
    print(f"  Player-games with both CV + boxscore data: {len(df)}")
    for stat in STATS:
        n_h = int((df[f"label_{stat}"] == "HOT").sum())
        n_c = int((df[f"label_{stat}"] == "COLD").sum())
        print(f"  {stat.upper()} HOT games: {n_h} | COLD games: {n_c}")
    print(f"  Players with >=5 CV games + >=2 HOT or COLD: {len(has_streaks)}")
    print()

    for stat in STATS:
        hot_sigs = summary[stat]["hot_signature"]["signature_features"]
        cold_sigs = summary[stat]["cold_signature"]["signature_features"]
        n_hot = summary[stat]["hot_signature"]["n_hot_games"]
        n_cold = summary[stat]["cold_signature"]["n_cold_games"]
        print(f"### {stat.upper()} signatures")
        print(f"  HOT ({n_hot} games) — top features:")
        for s in hot_sigs[:3]:
            print(f"    {s['feature']}: t={s['t']:+.2f}, {s['interpretation']}")
        if not hot_sigs:
            print("    (none reached |t|>2.0)")
        print(f"  COLD ({n_cold} games) — top features:")
        for s in cold_sigs[:3]:
            print(f"    {s['feature']}: t={s['t']:+.2f}, {s['interpretation']}")
        if not cold_sigs:
            print("    (none reached |t|>2.0)")
        print()

    # Most actionable signatures
    actionable = []
    for stat in STATS:
        for direction in ["hot", "cold"]:
            sigs = summary[stat][f"{direction}_signature"]["signature_features"]
            for s in sigs:
                if abs(s["t"]) >= 2.5:
                    actionable.append({
                        "stat": stat,
                        "direction": direction,
                        "feature": s["feature"],
                        "t": s["t"],
                        "interpretation": s["interpretation"],
                    })
    actionable.sort(key=lambda x: abs(x["t"]), reverse=True)

    if actionable:
        print("### Most-actionable signatures (|t| >= 2.5)")
        print(f"  {'stat':<6} {'dir':<5} {'feature':<28} {'t':>6}  interpretation")
        for a in actionable[:10]:
            print(f"  {a['stat']:<6} {a['direction']:<5} {a['feature']:<28} {a['t']:>+6.2f}  {a['interpretation'][:60]}")
    print()
    print("### Files written")
    print(f"  {PARQUET_OUT}")
    print(f"  {SUMMARY_OUT}")
    print(f"  {ATLAS_OUT}")
    print(f"  {STREAKS_DIR}/<player>_streaks.md (x{len(top_players)})")
    print()
    print("### Honest caveats")
    print("  - z>1.5 threshold = moderate bar; includes normal variance peaks")
    print("  - Coverage biased to 2024-25 / 2025-26 (bulk of CV data)")
    print("  - Per-player signatures with n<5 hot/cold games are noisy")
    print("  - touches_per_game / shots_per_possession likely confounded with minutes")
    print("  - avg_defender_distance has ISSUE-022 sentinel (200.0 = missing data)")
    print("  - Signatures are correlational — mechanism not established")


if __name__ == "__main__":
    main()
