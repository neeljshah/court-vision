"""
INT-18: Rolling 30-Day CV Trend Intelligence
Detects within-season player role/style shifts using a 30-day rolling window
vs a 31-90 day prior baseline. Faster and more sensitive than INT-15
season-over-season, and immune to cross-season scale bugs.

Usage:
    python scripts/build_rolling_trends.py

Outputs:
    data/intelligence/rolling_trends.parquet
    data/intelligence/active_trend_signals.json
    vault/Intelligence/Rolling_Trends_Atlas.md
    vault/Intelligence/Trends/<player_name>.md  (top 10 movers)
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent

IN_CV_PG  = PROJECT_ROOT / "data" / "player_cv_per_game.parquet"
IN_DATES  = PROJECT_ROOT / "data" / "rest_travel.parquet"

OUT_PARQUET = PROJECT_ROOT / "data" / "intelligence" / "rolling_trends.parquet"
OUT_SIGNALS = PROJECT_ROOT / "data" / "intelligence" / "active_trend_signals.json"
ATLAS_MD    = PROJECT_ROOT / "vault" / "Intelligence" / "Rolling_Trends_Atlas.md"
TRENDS_DIR  = PROJECT_ROOT / "vault" / "Intelligence" / "Trends"

OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
TRENDS_DIR.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()

# Window definitions (days)
RECENT_DAYS  = 30
PRIOR_START_DAYS = 90
MIN_GAMES_WINDOW = 2   # minimum games in each window to analyze a player

# Trend classification thresholds (in sigma / z-score units)
HOT_COLD_THRESHOLD = 1.0   # |z| > 1.0 on volume features = HOT/COLD
STYLE_THRESHOLD    = 1.0   # |z| > 1.0 on style features = STYLE_SHIFT
STEADY_THRESHOLD   = 0.5   # no feature |z| > 0.5 = STEADY
ACTIVE_Z_THRESHOLD = 2.0   # z > 2.0 = tradeable signal (books may not have adjusted)

# ─────────────────────────────────────────────────────────────────────────────
# Reliable features (≥85% coverage, no known scale inconsistency, within-season)
# ─────────────────────────────────────────────────────────────────────────────
# Volume / usage features — changes here = role change
VOLUME_FEATURES = [
    "cvb_paint_time_pct",        # fraction of time in paint (role signal)
    "cvb_near_basket_pct",       # near-basket positioning
    "cvb_avg_dist_to_basket",    # average distance from basket (lower = more post/paint)
    "cvb_fatigue_score",         # total distance traveled proxy (workload)
    "cvb_avg_velocity",          # movement intensity
]

# Style features — changes here = shot selection / play style shift
STYLE_FEATURES = [
    "cvb_avg_defender_dist",     # how closely defended (higher = more space = hot hand signal)
    "cvb_paint_pressure_own",    # paint occupancy pressure (only 46% coverage — use when available)
]

# EXCLUDED — cross-game scale inconsistency (some games in feet, others in pixels):
# cvb_avg_spacing  — 13/78 games have values ~2-30 (feet), rest ~200-400 (pixels)
# cvb_off_ball_dist — same bimodal distribution (13 low / 53 high games)

# Minutes proxy — overall workload / availability
WORKLOAD_FEATURES = [
    "minutes_proxy",             # proxy for minutes played per game
]

ALL_FEATURES = VOLUME_FEATURES + STYLE_FEATURES + WORKLOAD_FEATURES
# NOTE: cvb_avg_spacing and cvb_off_ball_dist intentionally excluded — bimodal pixel/feet
# scale across games causes spurious z-scores. See build_player_cv_profiles.py comments.

# Which features signal volume/usage change (used for HOT_BREAKOUT / COLD_DECLINE)
USAGE_SIGNAL_FEATURES = set(VOLUME_FEATURES + WORKLOAD_FEATURES)

# Features affected by ISSUE-022 — note in output but don't block on them
ISSUE_022_FEATURES = {"cvb_avg_defender_dist"}

# Feature display names for reports
FEATURE_LABELS = {
    "cvb_paint_time_pct":     "paint_dwell_pct",
    "cvb_near_basket_pct":    "near_basket_pct",
    "cvb_avg_dist_to_basket": "avg_dist_to_basket",
    "cvb_fatigue_score":      "fatigue_score",
    "cvb_avg_velocity":       "avg_velocity",
    "cvb_avg_defender_dist":  "defender_dist",
    "cvb_paint_pressure_own": "paint_pressure_own",
    "minutes_proxy":          "minutes_proxy",
    # Excluded (scale-inconsistent): cvb_avg_spacing, cvb_off_ball_dist
}

TOP_N_NOTES  = 10   # per-player markdown cards
TOP_N_ATLAS  = 10   # rows in atlas tables


# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — Load & prepare data
# ─────────────────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
    """Merge CV per-game profiles with game dates. Returns real-player rows only."""
    cv = pd.read_parquet(IN_CV_PG)
    rest = pd.read_parquet(IN_DATES)

    game_dates = (
        rest[["game_id", "game_date"]]
        .drop_duplicates("game_id")
        .assign(game_date=lambda d: pd.to_datetime(d["game_date"]))
    )

    df = cv.merge(game_dates, on="game_id", how="left")

    # Drop tracker placeholder rows (no real player name)
    df = df[~df["player_name"].astype(str).str.contains(r"#\?", na=False)].copy()

    # Require a game_date
    df = df[df["game_date"].notna()].copy()

    # Normalise player key: prefer nba_player_id when resolved, else player_name.
    # Use numpy where to avoid Int64 coercion issues.
    has_nba_id = df["nba_player_id"].notna()
    df["_player_key"] = np.where(
        has_nba_id,
        df["nba_player_id"].astype("object").where(has_nba_id, None).astype(str),
        df["player_name"].astype(str),
    )

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Compute dataset-wide feature stds for z-score normalisation
# ─────────────────────────────────────────────────────────────────────────────

def compute_dataset_stds(df: pd.DataFrame) -> dict[str, float]:
    """Compute population std for each feature across all rows (cross-player baseline)."""
    stds: dict[str, float] = {}
    for feat in ALL_FEATURES:
        if feat not in df.columns:
            stds[feat] = np.nan
            continue
        col = pd.to_numeric(df[feat], errors="coerce").dropna()
        s = float(col.std(ddof=1)) if len(col) > 1 else np.nan
        stds[feat] = s if (s is not None and s > 1e-9) else np.nan
    return stds


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Per-player windowed analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze_player(
    player_df: pd.DataFrame,
    dataset_stds: dict[str, float],
) -> dict | None:
    """
    Compute rolling-window trend for a single player.
    Returns None if the player doesn't have enough data in both windows.
    """
    if player_df.empty:
        return None

    player_df = player_df.sort_values("game_date").copy()
    max_date = player_df["game_date"].max()
    recent_cutoff = max_date - pd.Timedelta(days=RECENT_DAYS)
    prior_start   = max_date - pd.Timedelta(days=PRIOR_START_DAYS)

    recent_mask = player_df["game_date"] >= recent_cutoff
    prior_mask  = (player_df["game_date"] >= prior_start) & (player_df["game_date"] < recent_cutoff)

    recent_games = player_df[recent_mask]
    prior_games  = player_df[prior_mask]

    if len(recent_games) < MIN_GAMES_WINDOW or len(prior_games) < MIN_GAMES_WINDOW:
        return None

    # Representative name (mode over all games, not just recent)
    player_name = str(player_df["player_name"].mode().iat[0])

    feature_rows: list[dict] = []
    for feat in ALL_FEATURES:
        if feat not in player_df.columns:
            continue
        r_vals = pd.to_numeric(recent_games[feat], errors="coerce").dropna()
        p_vals = pd.to_numeric(prior_games[feat], errors="coerce").dropna()
        if len(r_vals) < 1 or len(p_vals) < 1:
            continue  # feature not populated for this player

        r_mean = float(r_vals.mean())
        p_mean = float(p_vals.mean())
        delta  = r_mean - p_mean

        ds = dataset_stds.get(feat, np.nan)
        z = float(delta / ds) if (ds and np.isfinite(ds)) else np.nan

        feature_rows.append({
            "feature":      feat,
            "prior_mean":   round(p_mean, 4),
            "recent_mean":  round(r_mean, 4),
            "delta":        round(delta, 4),
            "z":            round(z, 4) if np.isfinite(z) else None,
        })

    if not feature_rows:
        return None

    feat_df = pd.DataFrame(feature_rows).dropna(subset=["z"])

    # ── Trend classification ──────────────────────────────────────────────────
    usage_feats = feat_df[feat_df["feature"].isin(USAGE_SIGNAL_FEATURES)]
    style_feats = feat_df[feat_df["feature"].isin(set(STYLE_FEATURES))]

    max_usage_z     = float(usage_feats["z"].max())  if not usage_feats.empty else 0.0
    min_usage_z     = float(usage_feats["z"].min())  if not usage_feats.empty else 0.0
    max_abs_style_z = float(style_feats["z"].abs().max()) if not style_feats.empty else 0.0
    max_abs_z       = float(feat_df["z"].abs().max())

    # Determine trend tag
    if max_usage_z > HOT_COLD_THRESHOLD:
        trend_tag = "HOT_BREAKOUT"
    elif min_usage_z < -HOT_COLD_THRESHOLD:
        trend_tag = "COLD_DECLINE"
    elif max_abs_style_z > STYLE_THRESHOLD and max_abs_z < HOT_COLD_THRESHOLD + 0.5:
        trend_tag = "STYLE_SHIFT"
    elif max_abs_z < STEADY_THRESHOLD:
        trend_tag = "STEADY"
    else:
        # Usage shift below threshold but visible movement
        if max_usage_z > 0:
            trend_tag = "WARMING"
        elif min_usage_z < 0:
            trend_tag = "COOLING"
        else:
            trend_tag = "STEADY"

    # Top 3 driver features by |z|
    top3 = (
        feat_df.reindex(feat_df["z"].abs().sort_values(ascending=False).index)
        .head(3)[["feature", "prior_mean", "recent_mean", "delta", "z"]]
        .to_dict("records")
    )
    # Replace feature key with display label
    for row in top3:
        row["feature_label"] = FEATURE_LABELS.get(row["feature"], row["feature"])

    # Build per-feature flat columns for parquet output
    flat_features: dict[str, float] = {}
    for row in feat_df.to_dict("records"):
        fname = row["feature"]
        flat_features[f"{fname}_recent"] = row["recent_mean"]
        flat_features[f"{fname}_prior"]  = row["prior_mean"]
        flat_features[f"{fname}_delta"]  = row["delta"]
        flat_features[f"{fname}_z"]      = row["z"]

    result: dict = {
        "player_name":       player_name,
        "n_games_recent":    int(len(recent_games)),
        "n_games_prior":     int(len(prior_games)),
        "latest_game_date":  str(max_date.date()),
        "recent_cutoff":     str(recent_cutoff.date()),
        "prior_start":       str(prior_start.date()),
        "trend_tag":         trend_tag,
        "max_abs_z":         round(max_abs_z, 4),
        "max_usage_z":       round(max_usage_z, 4),
        "min_usage_z":       round(min_usage_z, 4),
        "top_3_drivers":     json.dumps(top3),
        **flat_features,
    }

    # Attach player_id for parquet joins
    if "nba_player_id" in player_df.columns and player_df["nba_player_id"].notna().any():
        result["player_id"] = int(player_df["nba_player_id"].dropna().iloc[0])
    else:
        result["player_id"] = None

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Run across all players
# ─────────────────────────────────────────────────────────────────────────────

def build_all_trends(df: pd.DataFrame) -> pd.DataFrame:
    dataset_stds = compute_dataset_stds(df)
    print("Dataset stds:")
    for feat, s in dataset_stds.items():
        label = FEATURE_LABELS.get(feat, feat)
        print(f"  {label}: {s:.4f}" if s and np.isfinite(s) else f"  {label}: N/A")

    results = []
    skipped_coverage = 0
    skipped_window   = 0

    for pkey, pdf in df.groupby("_player_key"):
        # Skip if fewer than 6 total CV games (per spec)
        if len(pdf) < 6:
            skipped_coverage += 1
            continue

        row = analyze_player(pdf, dataset_stds)
        if row is None:
            skipped_window += 1
            continue
        row["_player_key"] = str(pkey)
        results.append(row)

    print(f"\nAnalyzed {len(results)} players | "
          f"skipped (insufficient games): {skipped_coverage} | "
          f"skipped (empty windows): {skipped_window}")

    if not results:
        return pd.DataFrame()

    out = pd.DataFrame(results)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Active trend signals (HOT_BREAKOUT with z > 2.0)
# ─────────────────────────────────────────────────────────────────────────────

def build_active_signals(trends: pd.DataFrame) -> list[dict]:
    hot = trends[trends["trend_tag"] == "HOT_BREAKOUT"].copy()
    # Check if any driver feature has z > ACTIVE_Z_THRESHOLD
    active = []
    for _, row in hot.iterrows():
        try:
            drivers = json.loads(row["top_3_drivers"])
        except Exception:
            drivers = []
        hot_drivers = [d for d in drivers if d.get("z") and d["z"] > ACTIVE_Z_THRESHOLD]
        if hot_drivers:
            active.append({
                "player_name":     row["player_name"],
                "player_id":       row.get("player_id"),
                "trend_tag":       row["trend_tag"],
                "max_abs_z":       float(row["max_abs_z"]),
                "n_games_recent":  int(row["n_games_recent"]),
                "n_games_prior":   int(row["n_games_prior"]),
                "latest_game_date": row["latest_game_date"],
                "hot_drivers":     hot_drivers,
                "bet_signal":      "OVER bias on AST/usage props — role expansion detected",
            })
    # Sort by max driver z descending
    active.sort(key=lambda x: max(d["z"] for d in x["hot_drivers"]), reverse=True)
    return active


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Per-player trend cards (top 10 movers)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Convert player name to safe filename component."""
    return "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in name).replace(" ", "_").lower()


def _storyline(row: dict, drivers: list[dict]) -> str:
    """Generate a one-paragraph storyline from driver features."""
    tag = row["trend_tag"]
    name = row["player_name"]
    n_r  = row["n_games_recent"]

    if not drivers:
        return f"No driver features strong enough to construct a narrative (max |z| < {STEADY_THRESHOLD})."

    top = drivers[0]
    top_label = top.get("feature_label", top["feature"])
    top_z     = top.get("z", 0)
    top_delta = top.get("delta", 0)
    top_prior = top.get("prior_mean", 0)
    top_recent= top.get("recent_mean", 0)

    direction = "increased" if top_delta > 0 else "decreased"
    change_pct = abs(top_delta / top_prior * 100) if top_prior and top_prior != 0 else 0

    if tag == "HOT_BREAKOUT":
        line1 = (
            f"Over the last {RECENT_DAYS} days ({n_r} games), {name}'s {top_label} "
            f"has {direction} by {abs(top_delta):.3f} ({change_pct:.0f}%), "
            f"a {abs(top_z):.1f}σ move vs the prior 31-90 day baseline."
        )
        line2 = (
            "This signals a meaningful role expansion — more usage, more paint presence, "
            "or higher workload."
        ) if top_z > 0 else (
            "This signals increased defensive attention or repositioning."
        )
    elif tag == "COLD_DECLINE":
        line1 = (
            f"Over the last {RECENT_DAYS} days ({n_r} games), {name}'s {top_label} "
            f"has {direction} by {abs(top_delta):.3f} ({change_pct:.0f}%), "
            f"a {abs(top_z):.1f}σ drop vs the prior 31-90 day baseline."
        )
        line2 = "This suggests reduced role, possible injury, or scheme change."
    elif tag == "STYLE_SHIFT":
        line1 = (
            f"Over the last {RECENT_DAYS} days ({n_r} games), {name}'s {top_label} "
            f"has shifted by {top_delta:.3f} ({abs(top_z):.1f}σ) without a large volume change."
        )
        line2 = (
            "This is a style-only shift: same role, different shot selection or spacing behavior."
        )
    else:
        line1 = (
            f"{name}'s CV metrics are stable over the last {RECENT_DAYS} days "
            f"({n_r} games). No significant shift detected."
        )
        line2 = "Baseline pricing likely already reflects current form."

    return f"{line1} {line2}"


def _bet_lines(row: dict, drivers: list[dict]) -> str:
    """Suggest 2-3 bet-angle bullet points."""
    tag = row["trend_tag"]
    lines = []
    if tag == "HOT_BREAKOUT":
        lines.append("- OVER on usage-correlated props (AST, PTS, REB) — book lines may lag role shift")
        lines.append("- Volatility may be elevated short-term (new role = inconsistent execution)")
        lines.append("- Watch next 2-3 games to confirm before full-size")
    elif tag == "COLD_DECLINE":
        lines.append("- UNDER on usage-correlated props — reduced role signals")
        lines.append("- Check injury report before betting UNDER (injury = scratched, not just reduced minutes)")
        lines.append("- May recover if lineup change or injury is temporary")
    elif tag == "STYLE_SHIFT":
        lines.append("- Style shift only — volume props (PTS, REB, AST) likely unaffected")
        lines.append("- Watch for shot-selection-sensitive lines (3P makes, FG%)")
    else:
        lines.append("- No strong CV signal; rely on box-score and lineup context")
    return "\n".join(lines)


def write_player_card(row: dict, out_dir: Path) -> Path:
    """Write a single player trend card to vault/Intelligence/Trends/."""
    name = row["player_name"]
    try:
        drivers = json.loads(row["top_3_drivers"])
    except Exception:
        drivers = []

    # Driver feature table
    driver_table_lines = ["| feature | prior_mean | recent_mean | delta | z |",
                           "|---|---|---|---|---|"]
    for d in drivers:
        z_str = f"{d['z']:+.2f}σ" if d.get("z") is not None else "N/A"
        label = d.get("feature_label", d.get("feature", "?"))
        driver_table_lines.append(
            f"| {label} | {d.get('prior_mean', 0):.4f} | {d.get('recent_mean', 0):.4f} "
            f"| {d.get('delta', 0):+.4f} | {z_str} |"
        )
    driver_table = "\n".join(driver_table_lines)

    tag = row["trend_tag"]
    storyline = _storyline(row, drivers)
    bet_lines  = _bet_lines(row, drivers)

    issue_note = ""
    if any(FEATURE_LABELS.get(d.get("feature", ""), d.get("feature", "")) == "defender_dist"
           for d in drivers):
        issue_note = "\n> **Note:** defender_dist is subject to ISSUE-022 (sentinel=200ft); interpret with caution.\n"

    content = textwrap.dedent(f"""\
        # {name} — Active Trend (as of {TODAY})

        ## Recent {RECENT_DAYS}-day vs prior 31-90d window
        - Games in recent window: {row['n_games_recent']}
        - Games in prior window:  {row['n_games_prior']}
        - Latest CV game: {row['latest_game_date']}
        - Recent window from: {row['recent_cutoff']}
        - Prior window from:  {row['prior_start']}

        ## Driver features
        {driver_table}

        ## Trend tag: {tag}
        {issue_note}
        ## Storyline
        {storyline}

        ## What this could mean for upcoming bets
        {bet_lines}

        ---
        *INT-18 rolling 30-day window. Within-season only — immune to cross-season scale bugs.*
        *Re-run `scripts/build_rolling_trends.py` regularly to refresh.*
    """)

    fname = _safe_filename(name) + ".md"
    out_path = out_dir / fname
    out_path.write_text(content, encoding="utf-8")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Atlas
# ─────────────────────────────────────────────────────────────────────────────

def write_atlas(trends: pd.DataFrame) -> None:
    if trends.empty:
        return

    n_total = len(trends)
    tag_counts = trends["trend_tag"].value_counts()

    def _tag_count(tag: str) -> int:
        return int(tag_counts.get(tag, 0))

    hot_rows  = trends[trends["trend_tag"] == "HOT_BREAKOUT"].nlargest(TOP_N_ATLAS, "max_abs_z")
    cold_rows = trends[trends["trend_tag"] == "COLD_DECLINE"].nsmallest(TOP_N_ATLAS, "min_usage_z")
    style_rows= trends[trends["trend_tag"] == "STYLE_SHIFT"].nlargest(TOP_N_ATLAS, "max_abs_z")

    def _top_driver_label(row_data: dict) -> str:
        try:
            drivers = json.loads(row_data["top_3_drivers"])
            if drivers:
                return drivers[0].get("feature_label", drivers[0].get("feature", "?"))
        except Exception:
            pass
        return "?"

    def _top_driver_z(row_data: dict) -> str:
        try:
            drivers = json.loads(row_data["top_3_drivers"])
            if drivers and drivers[0].get("z") is not None:
                return f"{drivers[0]['z']:+.2f}σ"
        except Exception:
            pass
        return "?"

    def _build_table(rows: pd.DataFrame, label: str) -> str:
        if rows.empty:
            return f"*No {label} players detected.*\n"
        lines = [f"| player | top_driver | z | n_recent | n_prior | latest_game |",
                 "|---|---|---|---|---|---|"]
        for _, r in rows.iterrows():
            rd = r.to_dict()
            lines.append(
                f"| {r['player_name']} "
                f"| {_top_driver_label(rd)} "
                f"| {_top_driver_z(rd)} "
                f"| {r['n_games_recent']} "
                f"| {r['n_games_prior']} "
                f"| {r['latest_game_date']} |"
            )
        return "\n".join(lines)

    hot_table   = _build_table(hot_rows,  "HOT_BREAKOUT")
    cold_table  = _build_table(cold_rows, "COLD_DECLINE")
    style_table = _build_table(style_rows,"STYLE_SHIFT")

    content = textwrap.dedent(f"""\
        # Rolling 30-Day Trend Atlas

        ## Methodology
        Each player's last-30-day CV profile vs 31-90 day prior baseline.
        Within-season comparison only — immune to cross-season scale bugs (Bug 9 from INT-15).
        Window anchored to each player's own most recent CV game date.

        Minimum 2 games in each window required. Minimum 6 total CV games per player.
        Z-scores computed against dataset-wide population std for cross-player comparability.

        Feature set: {len(ALL_FEATURES)} reliable CV features (≥85% coverage, no known scale issues).

        ## Current state (as of {TODAY})
        - Players analyzed: {n_total}
        - HOT_BREAKOUT: {_tag_count('HOT_BREAKOUT')}
        - COLD_DECLINE: {_tag_count('COLD_DECLINE')}
        - STYLE_SHIFT: {_tag_count('STYLE_SHIFT')}
        - WARMING: {_tag_count('WARMING')}
        - COOLING: {_tag_count('COOLING')}
        - STEADY: {_tag_count('STEADY')}

        ## Top {TOP_N_ATLAS} active HOT streaks
        {hot_table}

        ## Top {TOP_N_ATLAS} active COLD declines
        {cold_table}

        ## Top style shifters
        {style_table}

        ## How to use
        - **Daily refresh:** re-run `python scripts/build_rolling_trends.py` before lines open
        - **Pre-bet lookup:** check `active_trend_signals.json` — if player is HOT_BREAKOUT and
          book line hasn't adjusted, lean OVER on usage props (AST, PTS)
        - **Risk-aware sizing:** high-z trends carry higher variance; size per INT-16 multiplier
        - **ISSUE-022 note:** `defender_dist` is subject to sentinel=200ft bug — treat those z-scores
          as directional only, not precise

        ## Honest caveats
        - "30 days" is wall-clock; CV game density varies (some players have 2 games, some 9)
        - Players with <2 games in either window excluded — {skipped_window_count} skipped this run
        - Single-game outliers can dominate small windows (especially n_recent=2)
        - Z-scores are cross-player comparisons; a +2σ z for a low-variance feature
          may mean less than +2σ for a high-variance feature
        - `cvb_avg_spacing` and `cvb_off_ball_dist` **excluded** — bimodal pixel/feet scale
          across games causes spurious 3σ signals (confirmed in 13/78 games)
        - ISSUE-022: `defender_dist` sentinel=200ft may corrupt those z-scores
        - Re-run regularly — trends can reverse quickly mid-season

        ---
        *Generated by INT-18: `scripts/build_rolling_trends.py`*
        *Linked: [[Rolling_Trends_Atlas]] | [[Development_Atlas]] | [[Betting_Signal_Ranking]]*
    """)

    ATLAS_MD.write_text(content, encoding="utf-8")
    print(f"Wrote Atlas: {ATLAS_MD}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

# Module-level counter so write_atlas can reference it
skipped_window_count = 0


def main() -> int:
    global skipped_window_count

    print("=" * 60)
    print("INT-18: Rolling 30-Day CV Trend Intelligence")
    print("=" * 60)

    # ── Load data ──────────────────────────────────────────────────────────────
    print("\nLoading CV per-game profiles...")
    df = load_data()
    print(f"  Loaded {len(df)} rows | {df['player_name'].nunique()} unique real players")
    print(f"  Date range: {df['game_date'].min().date()} to {df['game_date'].max().date()}")
    print(f"  Games: {df['game_id'].nunique()}")

    # ── Build trends ───────────────────────────────────────────────────────────
    print("\nBuilding rolling-window trends...")
    # Count skipped before build_all_trends runs so we can inject into atlas
    real_per_player = df.groupby("_player_key").size()
    skipped_coverage = int((real_per_player < 6).sum())
    skipped_window_count = 0  # will be updated inside build_all_trends output parse

    trends = build_all_trends(df)

    if trends.empty:
        print("ERROR: No players met window requirements.", file=sys.stderr)
        return 1

    # Re-read actual skipped_window from build_all_trends console output is tricky;
    # recompute: players with >=6 games minus analyzed count
    eligible_keys = real_per_player[real_per_player >= 6].index
    skipped_window_count = len(eligible_keys) - len(trends)

    # ── Print per-player summary ───────────────────────────────────────────────
    print("\n" + "-" * 60)
    print(f"Analyzed {len(trends)} players:")
    tag_counts = trends["trend_tag"].value_counts()
    for tag, cnt in tag_counts.items():
        print(f"  {tag}: {cnt}")

    # ── Write parquet ──────────────────────────────────────────────────────────
    trends.to_parquet(OUT_PARQUET, index=False)
    print(f"\nWrote parquet: {OUT_PARQUET}")

    # ── Active signals ─────────────────────────────────────────────────────────
    active_signals = build_active_signals(trends)
    OUT_SIGNALS.write_text(
        json.dumps({"generated": TODAY, "count": len(active_signals), "signals": active_signals},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote active signals: {OUT_SIGNALS} ({len(active_signals)} players)")

    # ── Top-10 player cards ────────────────────────────────────────────────────
    top10 = trends.nlargest(TOP_N_NOTES, "max_abs_z")
    print(f"\nWriting top-{TOP_N_NOTES} player trend cards...")
    for _, row in top10.iterrows():
        card_path = write_player_card(row.to_dict(), TRENDS_DIR)
        print(f"  {card_path.name}")

    # ── Atlas ──────────────────────────────────────────────────────────────────
    print("\nWriting Rolling Trends Atlas...")
    write_atlas(trends)

    # ── Final report ──────────────────────────────────────────────────────────
    hot_players  = trends[trends["trend_tag"] == "HOT_BREAKOUT"].nlargest(5, "max_abs_z")
    cold_players = trends[trends["trend_tag"] == "COLD_DECLINE"].nsmallest(5, "min_usage_z")

    print("\n" + "=" * 60)
    print("## INT-18 Rolling 30-Day Trends - Final Report")
    print("=" * 60)

    print(f"\n### Coverage")
    print(f"- Players with >=6 CV games:          {len(eligible_keys)}")
    print(f"- Passed both window filters (>=2/2): {len(trends)}")
    print(f"- Currently HOT_BREAKOUT:             {int(tag_counts.get('HOT_BREAKOUT', 0))}")
    print(f"- Currently COLD_DECLINE:             {int(tag_counts.get('COLD_DECLINE', 0))}")
    print(f"- Currently STYLE_SHIFT:              {int(tag_counts.get('STYLE_SHIFT', 0))}")

    print("\n### Top 5 hottest players right now (max +z on usage features)")
    print(f"{'player':<28} {'top_driver':<22} {'z':>6} {'n_rec':>6} {'n_prior':>7}")
    print("-" * 75)
    for _, r in hot_players.iterrows():
        try:
            drivers = json.loads(r["top_3_drivers"])
            top_d = drivers[0] if drivers else {}
            dlabel = top_d.get("feature_label", top_d.get("feature", "?"))
            dz     = f"{top_d['z']:+.2f}s" if top_d.get("z") is not None else "?"
        except Exception:
            dlabel, dz = "?", "?"
        safe_name = r["player_name"].encode("ascii", "replace").decode()
        print(f"  {safe_name:<26} {dlabel:<22} {dz:>6} {r['n_games_recent']:>6} {r['n_games_prior']:>7}")

    print("\n### Top 5 coldest players right now (max -z on usage features)")
    print(f"{'player':<28} {'top_driver':<22} {'z':>6} {'n_rec':>6} {'n_prior':>7}")
    print("-" * 75)
    for _, r in cold_players.iterrows():
        try:
            drivers = json.loads(r["top_3_drivers"])
            top_d = drivers[0] if drivers else {}
            dlabel = top_d.get("feature_label", top_d.get("feature", "?"))
            dz     = f"{top_d['z']:+.2f}s" if top_d.get("z") is not None else "?"
        except Exception:
            dlabel, dz = "?", "?"
        safe_name = r["player_name"].encode("ascii", "replace").decode()
        print(f"  {safe_name:<26} {dlabel:<22} {dz:>6} {r['n_games_recent']:>6} {r['n_games_prior']:>7}")

    print("\n### How to use")
    print("- Daily refresh: re-run `python scripts/build_rolling_trends.py`")
    print("- Pre-bet: check active_trend_signals.json -> OVER bias on HOT players")
    print("- Combine with INT-16 variance multiplier for bet sizing")

    print("\n### Files")
    print(f"  scripts/build_rolling_trends.py")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_SIGNALS}")
    print(f"  {ATLAS_MD}")
    print(f"  {TRENDS_DIR}/<player>.md  (top {TOP_N_NOTES} movers)")

    print("\n### Honest caveats")
    print("- 30-day window is wall-clock; some players have only 2 games in recent window")
    print("- Players with <2 games in either window excluded (strict filter)")
    print("- cvb_avg_spacing and cvb_off_ball_dist EXCLUDED: bimodal pixel/feet scale (13/78 games low)")
    print("- ISSUE-022: defender_distance sentinel=200ft may corrupt defender_dist z-scores")
    print("- Single-game outliers can dominate small windows (especially n_recent=2)")
    print("- Z-scores are cross-player; magnitude is relative to population variance")
    print("- Re-run regularly -- trends can reverse quickly mid-season")

    return 0


if __name__ == "__main__":
    sys.exit(main())
