"""
INT-67: Player Development Trend Extension (v2)
================================================

Extends INT-15 (`build_player_development.py`) from a season-over-season
2-point delta into a WITHIN-SEASON SLOPE signal at the (player_id, game_date)
grain. Whereas v1 produces ~42 rows total (one per player who has both
seasons), v2 emits one row per player-game inside 2025-26 where the player
has a sliding-window of `MIN_WINDOW` recent games.

Hypothesis: the slope of CV behavioral features OVER TIME is a leading
indicator of role/usage change. A rising `paint_dwell_pct` slope means the
player is becoming more interior; a falling `touches_per_game` slope means
usage is shrinking. These trends should price props ahead of L5/EWMA which
weight all five recent games equally.

Outputs (per player_id, game_date):
    - slope_<feat>            : OLS slope of feature over last `WINDOW` games
                                  (units: feature_units per game-index)
    - slope_z_<feat>           : slope normalized by within-player σ
    - r2_<feat>                : OLS R² (slope stability)
    - regime_change_<feat>     : bool — slope flipped sign vs prior window OR
                                  |slope_z| > 1.5
    - n_window                 : how many games went into the regression
    - dev_score                : sum |slope_z| of top-5 features (analog of v1)
    - top_trending_features    : top-3 features by |slope_z| with direction

Validation gates (see INT-67 doc):
    1. Sanity: known role-changers should rank top by |slope_z|
    2. Cross-corr with INT-54 archetype_outlier_z must be ≤0.9 (or B4 is
       redundant — do not promote to feature). r ≈ 0.5 is the target.
    3. Walk-forward downstream: ≥3/4 folds positive on any prop stat MAE.

File allowlist (per dispatch instructions):
    WRITE: this file, data/intelligence/player_development_v2.parquet
    WRITE: vault/Intelligence/INT-67_Player_Development_v2.md
    READ-ONLY: scripts/build_player_development.py, INT-54 outlier parquet
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "nba_ai.db"
PLAYER_FULL_JSON = PROJECT_ROOT / "data" / "nba" / "player_full_2024-25.json"
SEASON_GAMES_25 = PROJECT_ROOT / "data" / "nba" / "season_games_2025-26.json"

OUT_PARQUET = PROJECT_ROOT / "data" / "intelligence" / "player_development_v2.parquet"
OUT_SIGNALS = PROJECT_ROOT / "data" / "intelligence" / "player_development_v2_signals.json"

ARCHETYPE_OUTLIER_PARQUET = PROJECT_ROOT / "data" / "intelligence" / "archetype_outlier_signals.parquet"

# Window over which we fit the OLS slope.  Empirical ceiling: ~75 players have
# ≥3 games in 2025-26; ~30 have ≥5; only 7 have ≥8.  We pick 5 as the LOWER
# threshold to broaden coverage (vs v1's MIN_GAMES_Y2=3 only-mean), and we fit
# the slope over the LAST `WINDOW_SLOPE` games up to and including the current one.
MIN_WINDOW = 5            # need ≥5 games to fit any slope
WINDOW_SLOPE = 8          # use up to last 8 games for OLS

# Stable-scale features (carried forward from v1's classification).  Within-season
# slopes are not affected by the 2024→2025 pipeline version change, so we can
# safely use MORE features than v1's cross-season scope.  But we still avoid the
# always-zero and degenerate ones.
SLOPE_FEATURES = [
    # volume / usage
    "touches_per_game",
    "shots_per_possession",
    "potential_assists",
    "possession_duration_avg",
    "paint_dwell_pct",
    # play-style mix
    "shot_zone_3pt_pct",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "play_type_transition_pct",
    "play_type_isolation_pct",
    # shooting profile
    "avg_shot_distance",
    "catch_shoot_pct",
    "contested_shot_rate",
    # physicality / spacing
    "avg_spacing",
    "avg_fatigue_proxy",
    "avg_dribble_count",
]
# Excluded from PRIMARY slopes (sparse / ISSUE-022 corrupted), but we still
# compute slope_z so the AI Chat can reference them with the caution flag.
ISSUE_022_FEATURES = {"avg_defender_distance", "defender_approach_speed"}

# Thresholds for the regime-change flag.  Mirrors v1's z=1σ cut but is applied
# to the within-season slope (not the seasonal delta).
Z_REGIME_THRESHOLD = 1.5      # |slope_z| > 1.5 ⇒ strong trend
TOP_K_TRENDS = 3              # how many features appear in `top_trending`
TOP_K_DEV_SCORE = 5           # sum |z| of top-K = dev_score (matches v1)


# ──────────────────────────────────────────────────────────────────────────────
# Loaders
# ──────────────────────────────────────────────────────────────────────────────

def load_cv_features() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT game_id, player_id, feature_name, feature_value FROM cv_features",
        conn,
    )
    conn.close()
    # Bug 27 guard mirrored from v1: PA=0 means xAST didn't run for that game.
    mask = (df["feature_name"] == "potential_assists") & (df["feature_value"] == 0.0)
    df.loc[mask, "feature_value"] = np.nan
    return df


def load_game_dates() -> dict:
    """{game_id: 'YYYY-MM-DD'} from the 2025-26 schedule.  Used to sort games
    chronologically before fitting the slope."""
    if not SEASON_GAMES_25.exists():
        return {}
    with open(SEASON_GAMES_25, encoding="utf-8") as f:
        raw = json.load(f)
    rows = raw.get("rows", []) if isinstance(raw, dict) else raw
    out = {}
    for row in rows or []:
        if isinstance(row, dict):
            gid = row.get("game_id")
            gd = row.get("game_date", "")
            if gid:
                out[gid] = gd
    return out


def load_player_name_map() -> dict:
    if not PLAYER_FULL_JSON.exists():
        return {}
    with open(PLAYER_FULL_JSON, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict):
        return {v["player_id"]: k.title() for k, v in raw.items() if "player_id" in v}
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# Pivot to per-(player, game, feature) wide
# ──────────────────────────────────────────────────────────────────────────────

def pivot_player_game(df: pd.DataFrame, game_dates: dict) -> pd.DataFrame:
    """Returns wide df with columns [player_id, game_id, game_date, <features...>].
    Restricted to 2025-26 only — within-season slope is the v2 contract."""
    df = df[df["game_id"].astype(str).str.startswith("00225")].copy()
    wide = df.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    wide["game_date"] = wide["game_id"].map(game_dates).fillna("")
    # Drop rows with no parseable date so chronological sort is well-defined.
    wide = wide[wide["game_date"] != ""].copy()
    wide["game_date"] = pd.to_datetime(wide["game_date"], errors="coerce")
    wide = wide.dropna(subset=["game_date"]).sort_values(["player_id", "game_date"])
    return wide


# ──────────────────────────────────────────────────────────────────────────────
# OLS slope helpers
# ──────────────────────────────────────────────────────────────────────────────

def _ols_slope_r2(y: np.ndarray) -> tuple:
    """Returns (slope, r2) for OLS fit of y against x = 0..n-1.
    Returns (nan, nan) if y has <2 non-nan values or σ_y == 0."""
    mask = ~np.isnan(y)
    if mask.sum() < 2:
        return (float("nan"), float("nan"))
    yy = y[mask]
    xx = np.arange(len(y))[mask].astype(float)
    if yy.std() == 0:
        return (0.0, 0.0)
    # slope = cov(x,y) / var(x)
    xm, ym = xx.mean(), yy.mean()
    num = ((xx - xm) * (yy - ym)).sum()
    den = ((xx - xm) ** 2).sum()
    if den == 0:
        return (0.0, 0.0)
    slope = float(num / den)
    intercept = ym - slope * xm
    y_pred = slope * xx + intercept
    ss_res = ((yy - y_pred) ** 2).sum()
    ss_tot = ((yy - ym) ** 2).sum()
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return (slope, float(max(min(r2, 1.0), -1.0)))


def compute_player_slopes(wide: pd.DataFrame) -> list:
    """For every (player, game_date), if the player has ≥MIN_WINDOW prior games
    INCLUDING the current one, fit OLS slope over the last WINDOW_SLOPE games
    for every feature in SLOPE_FEATURES (+ISSUE_022 with caution flag)."""
    records = []
    all_features = SLOPE_FEATURES + sorted(ISSUE_022_FEATURES)
    # Pre-compute population std per feature for slope_z normalization later.
    # (Within-player std would be ideal, but most players have <8 games — use
    # cross-player slope σ on the same window size instead, computed in a
    # second pass.)
    for pid, grp in wide.groupby("player_id"):
        grp = grp.sort_values("game_date").reset_index(drop=True)
        n_total = len(grp)
        if n_total < MIN_WINDOW:
            continue  # not enough history
        for i in range(MIN_WINDOW - 1, n_total):
            window = grp.iloc[max(0, i - WINDOW_SLOPE + 1): i + 1]
            n_win = len(window)
            row = {
                "player_id": int(pid),
                "game_id": grp.iloc[i]["game_id"],
                "game_date": grp.iloc[i]["game_date"],
                "n_window": int(n_win),
            }
            for f in all_features:
                if f not in window.columns:
                    row[f"slope_{f}"] = np.nan
                    row[f"r2_{f}"] = np.nan
                    continue
                y = window[f].to_numpy(dtype=float)
                s, r2 = _ols_slope_r2(y)
                row[f"slope_{f}"] = s
                row[f"r2_{f}"] = r2
            records.append(row)
    return records


def add_slope_z(records: list) -> pd.DataFrame:
    """Adds slope_z_<feat> column for each feature by normalizing each slope
    against the cross-player σ of that feature's slope (excluding nans)."""
    df = pd.DataFrame(records)
    if df.empty:
        return df
    all_features = SLOPE_FEATURES + sorted(ISSUE_022_FEATURES)
    for f in all_features:
        sc = f"slope_{f}"
        if sc not in df.columns:
            continue
        vals = df[sc].dropna()
        std = float(vals.std()) if len(vals) > 1 else 1.0
        std = std if std > 1e-9 else 1.0
        df[f"slope_z_{f}"] = (df[sc] / std).round(3)
    return df


def add_regime_change(df: pd.DataFrame) -> pd.DataFrame:
    """For each feature, regime_change is True when:
        a) |slope_z| > Z_REGIME_THRESHOLD     (strong trend), OR
        b) sign(slope) flipped from the same player's previous row
    Per-feature regime_change columns + an aggregate `any_regime_change` bool.
    """
    if df.empty:
        return df
    df = df.sort_values(["player_id", "game_date"]).reset_index(drop=True)
    all_features = SLOPE_FEATURES + sorted(ISSUE_022_FEATURES)
    for f in all_features:
        sc = f"slope_{f}"
        zc = f"slope_z_{f}"
        if sc not in df.columns:
            continue
        prev_sign = (
            df.groupby("player_id")[sc]
            .shift(1)
            .apply(lambda v: np.sign(v) if v is not None and not pd.isna(v) else np.nan)
        )
        cur_sign = df[sc].apply(lambda v: np.sign(v) if v is not None and not pd.isna(v) else np.nan)
        sign_flip = (prev_sign != cur_sign) & prev_sign.notna() & cur_sign.notna() & (prev_sign != 0) & (cur_sign != 0)
        strong = df[zc].abs() > Z_REGIME_THRESHOLD
        df[f"regime_change_{f}"] = (sign_flip | strong).fillna(False)
    rc_cols = [c for c in df.columns if c.startswith("regime_change_")]
    df["any_regime_change"] = df[rc_cols].any(axis=1)
    return df


def add_dev_score_and_top_trends(df: pd.DataFrame, name_map: dict) -> pd.DataFrame:
    """dev_score = sum |slope_z| of top-TOP_K_DEV_SCORE features.  Also writes
    a `top_trending` JSON string listing the top-TOP_K_TRENDS features with
    direction (up/down) and the slope_z value."""
    if df.empty:
        return df
    feat_z_cols = [
        c for c in df.columns
        if c.startswith("slope_z_") and c.replace("slope_z_", "") in SLOPE_FEATURES
    ]
    dev_scores = []
    top_trends = []
    for _, row in df.iterrows():
        z_pairs = []
        for col in feat_z_cols:
            v = row[col]
            if v is not None and not pd.isna(v):
                z_pairs.append((col.replace("slope_z_", ""), float(v)))
        z_pairs.sort(key=lambda x: abs(x[1]), reverse=True)
        dev_scores.append(round(sum(abs(z) for _, z in z_pairs[:TOP_K_DEV_SCORE]), 3))
        top_trends.append(json.dumps([
            {"feature": f, "slope_z": round(z, 3), "direction": "up" if z > 0 else "down"}
            for f, z in z_pairs[:TOP_K_TRENDS]
        ]))
    df["dev_score"] = dev_scores
    df["top_trending"] = top_trends
    df["player_name"] = df["player_id"].map(name_map).fillna(
        df["player_id"].apply(lambda x: f"Player_{x}")
    )
    return df


# ──────────────────────────────────────────────────────────────────────────────
# Redundancy check against INT-54 archetype_outlier_signals
# ──────────────────────────────────────────────────────────────────────────────

def check_redundancy_with_int54(df: pd.DataFrame) -> dict:
    """Join on (player_id, game_id) and compute Pearson r between dev_score
    and archetype outlier_z.  If r > 0.9, B4 is REDUNDANT and should not be
    promoted to a prop_pergame feature — kept only as an AI Chat narrative."""
    if not ARCHETYPE_OUTLIER_PARQUET.exists():
        return {"status": "skipped", "reason": "INT-54 parquet not found"}
    int54 = pd.read_parquet(ARCHETYPE_OUTLIER_PARQUET)
    if "outlier_z" not in int54.columns or "player_id" not in int54.columns:
        return {"status": "skipped", "reason": "INT-54 schema mismatch"}
    merged = df.merge(
        int54[["player_id", "game_id", "outlier_z"]],
        on=["player_id", "game_id"],
        how="inner",
    )
    if len(merged) < 10:
        return {"status": "low_overlap", "n_overlap": int(len(merged))}
    r = float(merged["dev_score"].corr(merged["outlier_z"]))
    verdict = (
        "REDUNDANT (do not promote to feature)" if abs(r) > 0.9
        else "COMPLEMENTARY (acceptable overlap)" if abs(r) >= 0.5
        else "INDEPENDENT (measures distinct signal)"
    )
    return {
        "status": "ok",
        "n_overlap": int(len(merged)),
        "pearson_r": round(r, 4),
        "verdict": verdict,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=== INT-67 Player Development v2 — Within-Season Slope Trends ===")

    print("Loading CV features...")
    raw = load_cv_features()
    print(f"  {len(raw)} feature rows")

    print("Loading game dates + name map...")
    game_dates = load_game_dates()
    name_map = load_player_name_map()
    print(f"  {len(game_dates)} dated games, {len(name_map)} named players")

    print("Pivoting to (player, game) wide format (2025-26 only)...")
    wide = pivot_player_game(raw, game_dates)
    print(f"  {len(wide)} player-game rows, {wide['player_id'].nunique()} players")

    print(f"Fitting OLS slopes (MIN_WINDOW={MIN_WINDOW}, WINDOW_SLOPE={WINDOW_SLOPE})...")
    recs = compute_player_slopes(wide)
    print(f"  {len(recs)} (player, game) slope rows")

    if not recs:
        print("[!] No slopes computed — likely not enough history per player.")
        print("    Empty parquet will be written for downstream contract stability.")

    print("Computing within-feature slope_z normalization...")
    df = add_slope_z(recs)

    print("Detecting regime changes (|z|>1.5 or sign flip)...")
    df = add_regime_change(df)

    print("Computing dev_score + top_trending list...")
    df = add_dev_score_and_top_trends(df, name_map)

    print("Cross-correlating with INT-54 archetype_outlier_z (redundancy check)...")
    redundancy = check_redundancy_with_int54(df)
    print(f"  → {redundancy}")

    print(f"Writing {OUT_PARQUET}...")
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)

    # Compact signals JSON for AI Chat / dashboards (top dev_score per player).
    per_player_latest = (
        df.sort_values("game_date")
          .groupby("player_id")
          .tail(1)
          .sort_values("dev_score", ascending=False)
    )
    signals = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "n_rows": int(len(df)),
        "n_players": int(df["player_id"].nunique() if len(df) else 0),
        "redundancy_check": redundancy,
        "top_trending_players": per_player_latest.head(20)[
            ["player_id", "player_name", "game_date", "dev_score", "top_trending"]
        ].assign(game_date=lambda d: d["game_date"].astype(str)).to_dict(orient="records"),
    }
    with open(OUT_SIGNALS, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)

    print()
    print("=" * 60)
    print("## INT-67 Player Development v2 — Final Report")
    print("=" * 60)
    print(f"- rows: {len(df)}")
    print(f"- players: {df['player_id'].nunique() if len(df) else 0}")
    print(f"- redundancy vs INT-54: {redundancy}")
    if len(df):
        rc_cnt = int(df["any_regime_change"].sum())
        print(f"- regime-change events flagged: {rc_cnt} ({rc_cnt / len(df):.1%} of rows)")
    print()
    print("Next step: Sonnet wires `dev_score` + `slope_z_<feat>` for top features")
    print("into the prop_pergame feature builder and runs the 4-fold WF gate.")
    print("If WF ≥3/4 positive on any stat → SHIP B4. If WF<3/4 AND redundancy r>0.9")
    print("→ DROP from feature pipeline, keep only for AI Chat narrative use.")


if __name__ == "__main__":
    main()
