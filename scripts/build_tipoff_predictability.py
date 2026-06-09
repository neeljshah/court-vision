#!/usr/bin/env python3
"""build_tipoff_predictability.py -- INT-43: Tip-off Frame Predictability Atlas.

Quantifies how much of a player-game's eventual CV-feature profile can be
predicted from just the first 100-300 frames (tip-off + opening possessions).

If first-100-frames CV signatures correlate r>0.5 with full-game signatures,
the system has a within-game-update signal (predict 2nd-half OVER/UNDER from
1st-quarter CV). If correlation is weak, it confirms behavior emerges over the
game arc.

Windows:
  w100  : first 100 sampled frames  (~20 seconds at 5 samples/sec)
  w300  : first 300 sampled frames  (~60 seconds)
  w1Q   : first 25% of each game's frame range (quarter estimate)
  full  : entire game

Correlation analysis is at the (game_id, player_slot) level.
Each window feature value is correlated with the full-game value across all
player-game observations.

Outputs:
  data/intelligence/tipoff_predictability.parquet
      cols: feature_name, window, n, r_pearson, r2, p_value
  data/intelligence/tipoff_predictability_signals.json
      features that pass r >= 0.5 at the 100-frame window
  vault/Intelligence/Tipoff_Predictability_Atlas.md

Usage:
    python scripts/build_tipoff_predictability.py
    python scripts/build_tipoff_predictability.py --min-games 5 --verbose
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT         = Path(r"C:\Users\neelj\nba-ai-system")
TRACKING_DIR = ROOT / "data" / "tracking"
INTEL_DIR    = ROOT / "data" / "intelligence"
VAULT_DIR    = ROOT / "vault" / "Intelligence"

OUT_PARQUET  = INTEL_DIR / "tipoff_predictability.parquet"
OUT_SIGNALS  = INTEL_DIR / "tipoff_predictability_signals.json"
OUT_ATLAS    = VAULT_DIR / "Tipoff_Predictability_Atlas.md"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MIN_TOTAL_ROWS       = 3_000    # skip tiny clip files
MIN_FRAMES_FOR_CORR  = 20       # min per-player rows in a window to count that obs
MIN_N_FOR_CORR       = 15       # min player-game pairs to compute a correlation
R_THRESHOLD          = 0.50     # threshold to declare a feature "predictable"

# Sampled-frame windows (ordinal rank within game, not absolute frame number)
# We sort unique frames ascending and take ranks 0-99, 0-299, 0-Q1end, all
WINDOW_100_FRAMES  = 100   # ordinal frame rank ceiling
WINDOW_300_FRAMES  = 300
FIRST_QUARTER_FRAC = 0.25  # first 25% of game frame range = approx Q1

# CV features to compute per window -- mirrors the columns available in
# tracking_data.csv and the features stored in cv_features table
CV_FEATURE_MAP = {
    # raw col                -> output feature name
    "velocity":              "avg_velocity",
    "acceleration":          "avg_acceleration",
    "ball_possession":       "ball_possession_rate",
    "distance_to_ball":      "avg_dist_to_ball",
    "dist_to_basket_ft":     "avg_dist_to_basket",
    "paint_touches":         "paint_touch_rate",
    "drive_flag":            "drive_rate",
    "off_ball_distance":     "avg_off_ball_dist",
    "team_spacing":          "avg_team_spacing",
    "vel_toward_basket":     "avg_vel_toward_basket",
    "dribble_count":         "avg_dribble_count",
    "jump_detected":         "jump_rate",
    "contest_arm_angle":     "avg_contest_arm_angle",
    "shot_clock_est":        "avg_shot_clock",
    "fast_break_flag":       "fast_break_rate",
}

RATE_FEATURES = {"ball_possession", "paint_touches", "drive_flag",
                 "jump_detected", "fast_break_flag"}

FEAT_NAMES = list(CV_FEATURE_MAP.values())
WINDOWS    = ["w100", "w300", "w1Q", "full"]


# ---------------------------------------------------------------------------
# Per-frame feature extraction
# ---------------------------------------------------------------------------

def _compute_player_window_features(g: pd.DataFrame) -> dict[str, float]:
    """Compute mean CV features for a player's slice of frames."""
    out: dict[str, float] = {"n_frames": len(g)}
    for col, feat_name in CV_FEATURE_MAP.items():
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
            # defender_distance sentinel filter (ISSUE-022)
            if col in ("distance_to_ball", "dist_to_basket_ft"):
                valid = valid[valid < 200]
            out[feat_name] = float(valid.mean()) if len(valid) > 0 else np.nan
    return out


# ---------------------------------------------------------------------------
# Per-game processing
# ---------------------------------------------------------------------------

def _process_one_game(game_id: str, verbose: bool = False,
                      min_frames_for_corr: int = MIN_FRAMES_FOR_CORR) -> list[dict]:
    """Load tracking_data.csv, compute per-player features for each window.

    Returns list of dicts with keys:
        game_id, player_id, window, n_frames, <feature_name>...
    """
    gdir    = TRACKING_DIR / game_id
    td_path = gdir / "tracking_data.csv"

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
            print(f"  [{game_id}] too small ({len(df)} rows), skip")
        return []

    # Coerce frame column to numeric
    df = df.copy()
    df["_frame_num"] = pd.to_numeric(df["frame"], errors="coerce")
    df = df.dropna(subset=["_frame_num"])
    if len(df) == 0:
        return []

    # Build ordinal frame rank per player_id -- sort unique frames per game
    # so "frame rank 0" = earliest observed frame, regardless of absolute value
    game_frames = sorted(df["_frame_num"].unique())
    frame_rank  = {f: i for i, f in enumerate(game_frames)}
    df["_frame_rank"] = df["_frame_num"].map(frame_rank)

    f_range = int(df["_frame_num"].max()) - int(df["_frame_num"].min())
    f_min   = int(df["_frame_num"].min())

    # Q1 threshold: first 25% of absolute frame range (mirrors quarter_momentum fallback)
    q1_frame_cutoff = f_min + int(f_range * FIRST_QUARTER_FRAC)

    rows = []
    for player_id, pgrp in df.groupby("player_id"):
        # Define window slices
        window_slices: dict[str, pd.DataFrame] = {
            "w100":  pgrp[pgrp["_frame_rank"] < WINDOW_100_FRAMES],
            "w300":  pgrp[pgrp["_frame_rank"] < WINDOW_300_FRAMES],
            "w1Q":   pgrp[pgrp["_frame_num"]  <= q1_frame_cutoff],
            "full":  pgrp,
        }

        for window_name, slice_df in window_slices.items():
            if len(slice_df) < min_frames_for_corr:
                continue
            feats = _compute_player_window_features(slice_df)
            rows.append({
                "game_id":   game_id,
                "player_id": player_id,
                "window":    window_name,
                **feats,
            })

    return rows


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------

def _compute_correlations(all_rows: list[dict], min_n: int = MIN_N_FOR_CORR) -> pd.DataFrame:
    """Compute per-feature correlation r(window_value, full_game_value)
    across all player-game observations.

    Returns DataFrame with cols:
        feature_name, window, n, r_pearson, r2, p_value
    """
    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Pivot to wide: one row per (game_id, player_id)
    # cols: <feature>_w100, <feature>_w300, <feature>_w1Q, <feature>_full
    full_df = df[df["window"] == "full"].copy()
    full_df = full_df.drop(columns=["window", "n_frames"])

    corr_rows = []

    for window in ["w100", "w300", "w1Q"]:
        win_df = df[df["window"] == window].copy()
        win_df = win_df.drop(columns=["window", "n_frames"])

        # Join full-game values onto window values
        merged = win_df.merge(
            full_df,
            on=["game_id", "player_id"],
            suffixes=(f"_{window}", "_full"),
        )

        if len(merged) < min_n:
            if len(merged) > 0:
                # Still record with NA
                for feat in FEAT_NAMES:
                    corr_rows.append({
                        "feature_name": feat,
                        "window":       window,
                        "n":            len(merged),
                        "r_pearson":    np.nan,
                        "r2":           np.nan,
                        "p_value":      np.nan,
                    })
            continue

        for feat in FEAT_NAMES:
            col_win  = f"{feat}_{window}"
            col_full = f"{feat}_full"

            if col_win not in merged.columns or col_full not in merged.columns:
                continue

            x = pd.to_numeric(merged[col_win],  errors="coerce")
            y = pd.to_numeric(merged[col_full], errors="coerce")

            valid_mask = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
            x = x[valid_mask].values
            y = y[valid_mask].values

            n = len(x)
            if n < min_n:
                corr_rows.append({
                    "feature_name": feat,
                    "window":       window,
                    "n":            n,
                    "r_pearson":    np.nan,
                    "r2":           np.nan,
                    "p_value":      np.nan,
                })
                continue

            # Pearson correlation
            try:
                r, p = stats.pearsonr(x, y)
            except Exception:
                r, p = np.nan, np.nan

            corr_rows.append({
                "feature_name": feat,
                "window":       window,
                "n":            n,
                "r_pearson":    round(float(r), 4) if np.isfinite(r) else np.nan,
                "r2":           round(float(r ** 2), 4) if np.isfinite(r) else np.nan,
                "p_value":      round(float(p), 6) if np.isfinite(p) else np.nan,
            })

    return pd.DataFrame(corr_rows)


# ---------------------------------------------------------------------------
# Signals JSON
# ---------------------------------------------------------------------------

def _build_signals_json(corr_df: pd.DataFrame) -> dict:
    """Extract features that pass r >= R_THRESHOLD at the 100-frame window."""
    if corr_df.empty:
        return {"threshold_r": R_THRESHOLD, "window": "w100", "signals": [], "generated": ""}

    w100 = corr_df[corr_df["window"] == "w100"].copy()
    w100 = w100.dropna(subset=["r_pearson"])
    w100 = w100.sort_values("r_pearson", ascending=False)

    pass_threshold = w100[w100["r_pearson"] >= R_THRESHOLD]

    signals = []
    for _, row in pass_threshold.iterrows():
        signals.append({
            "feature":   row["feature_name"],
            "r_pearson": row["r_pearson"],
            "r2":        row["r2"],
            "p_value":   row["p_value"],
            "n":         int(row["n"]),
        })

    # Also include summary for all three windows
    window_summary: dict[str, list] = {}
    for window in ["w100", "w300", "w1Q"]:
        wdf = corr_df[corr_df["window"] == window].dropna(subset=["r_pearson"])
        n_pass = int((wdf["r_pearson"] >= R_THRESHOLD).sum())
        best_r = float(wdf["r_pearson"].max()) if len(wdf) > 0 else 0.0
        worst_r = float(wdf["r_pearson"].min()) if len(wdf) > 0 else 0.0
        window_summary[window] = {
            "n_features_pass_r05": n_pass,
            "best_r":              round(best_r, 4),
            "worst_r":             round(worst_r, 4),
        }

    return {
        "threshold_r":    R_THRESHOLD,
        "window_100_signals": signals,
        "window_summary": window_summary,
        "generated":      pd.Timestamp.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# Diagnostic helpers (bug surfacing)
# ---------------------------------------------------------------------------

def _detect_scale_jump_bug(all_rows: list[dict]) -> Optional[str]:
    """Check if avg_dist_to_basket or avg_team_spacing shows bimodal scale
    distribution across games (i.e., some games in pixels, others in feet).
    This is a known class of bug (Bug 11) extended to new features.
    """
    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    full_df = df[df["window"] == "full"]

    suspect_features = ["avg_dist_to_basket", "avg_team_spacing", "avg_off_ball_dist",
                        "avg_dist_to_ball"]
    findings = []

    for feat in suspect_features:
        if feat not in full_df.columns:
            continue
        vals = pd.to_numeric(full_df[feat], errors="coerce").dropna()
        if len(vals) < 20:
            continue
        # Bimodal detection: check if there's a large gap in the distribution
        # Pixels are typically 50-500; feet are typically 1-50
        low_scale  = vals[vals < 50].count()
        high_scale = vals[vals >= 50].count()
        total      = low_scale + high_scale
        if total < 10:
            continue
        low_pct  = low_scale / total
        high_pct = high_scale / total
        # Bimodal if both clusters are non-trivial (5-95% split)
        if 0.05 < low_pct < 0.95:
            median_low  = float(vals[vals <  50].median()) if low_scale  > 0 else np.nan
            median_high = float(vals[vals >= 50].median()) if high_scale > 0 else np.nan
            ratio = (median_high / median_low) if (median_low and median_low > 0) else np.nan
            if ratio and ratio > 3:
                findings.append(
                    f"{feat}: {low_scale}/{total} games in feet-scale (<50), "
                    f"{high_scale}/{total} in pixel-scale (>=50), "
                    f"median_low={median_low:.1f} median_high={median_high:.1f} "
                    f"ratio={ratio:.1f}x"
                )

    return "\n".join(findings) if findings else None


def _detect_window_scale_drift(corr_df: pd.DataFrame) -> Optional[str]:
    """Check if any feature's w100 mean is dramatically different from full-game mean.
    This would indicate a systematic artifact in early frames (e.g., warmup detection,
    tip-off confusion, or homography not yet converged).
    """
    return None  # placeholder -- full implementation deferred to per-game comparison


# ---------------------------------------------------------------------------
# Atlas writer
# ---------------------------------------------------------------------------

def _write_atlas(
    corr_df: pd.DataFrame,
    signals: dict,
    n_games: int,
    n_skipped: int,
    n_total_obs: int,
    bug_finding: Optional[str],
) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)

    def fmt(v) -> str:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "n/a"
        return f"{v:.4f}"

    def fmt_pval(v) -> str:
        if v is None or (isinstance(v, float) and not np.isfinite(v)):
            return "n/a"
        if v < 0.001:
            return "<0.001"
        return f"{v:.3f}"

    # --- Summary stats ---
    w100_df = corr_df[corr_df["window"] == "w100"].dropna(subset=["r_pearson"])
    w300_df = corr_df[corr_df["window"] == "w300"].dropna(subset=["r_pearson"])
    w1q_df  = corr_df[corr_df["window"] == "w1Q"].dropna(subset=["r_pearson"])

    n_w100_pass = int((w100_df["r_pearson"] >= R_THRESHOLD).sum())
    n_w300_pass = int((w300_df["r_pearson"] >= R_THRESHOLD).sum())
    n_w1q_pass  = int((w1q_df["r_pearson"]  >= R_THRESHOLD).sum())
    n_feats     = len(FEAT_NAMES)

    # Top 5 best at w100
    top5 = w100_df.sort_values("r_pearson", ascending=False).head(5)
    # Worst 5 at w100 (lowest r)
    worst5 = w100_df.sort_values("r_pearson", ascending=True).head(5)

    def feature_table(fdf: pd.DataFrame) -> str:
        rows = ["| Feature | r (w100) | r (w300) | r (1Q) | r2 (w100) | p (w100) |",
                "|---------|----------|----------|--------|-----------|---------|"]
        for _, row in fdf.iterrows():
            fname = row["feature_name"]
            r100  = fmt(row["r_pearson"])
            r2_   = fmt(row["r2"])
            pv    = fmt_pval(row["p_value"])
            # Look up w300 and w1Q values
            r300_row = corr_df[(corr_df["feature_name"] == fname) & (corr_df["window"] == "w300")]
            r1q_row  = corr_df[(corr_df["feature_name"] == fname) & (corr_df["window"] == "w1Q")]
            r300 = fmt(r300_row["r_pearson"].values[0]) if len(r300_row) > 0 else "n/a"
            r1q  = fmt(r1q_row["r_pearson"].values[0])  if len(r1q_row)  > 0 else "n/a"
            rows.append(f"| {fname} | {r100} | {r300} | {r1q} | {r2_} | {pv} |")
        return "\n".join(rows)

    # Full feature table for all windows
    all_feats_table_rows = ["| Feature | r (w100) | r (w300) | r (1Q) | n (w100) | p (w100) |",
                            "|---------|----------|----------|--------|----------|---------|"]
    for feat in sorted(FEAT_NAMES):
        r100_row = corr_df[(corr_df["feature_name"] == feat) & (corr_df["window"] == "w100")]
        r300_row = corr_df[(corr_df["feature_name"] == feat) & (corr_df["window"] == "w300")]
        r1q_row  = corr_df[(corr_df["feature_name"] == feat) & (corr_df["window"] == "w1Q")]
        r100 = fmt(r100_row["r_pearson"].values[0]) if len(r100_row) > 0 else "n/a"
        r300 = fmt(r300_row["r_pearson"].values[0]) if len(r300_row) > 0 else "n/a"
        r1q  = fmt(r1q_row["r_pearson"].values[0])  if len(r1q_row)  > 0 else "n/a"
        n_   = str(int(r100_row["n"].values[0]))     if len(r100_row) > 0 else "n/a"
        pv   = fmt_pval(r100_row["p_value"].values[0]) if len(r100_row) > 0 else "n/a"
        all_feats_table_rows.append(f"| {feat} | {r100} | {r300} | {r1q} | {n_} | {pv} |")

    # Live-betting implication
    live_signals = signals.get("window_100_signals", [])
    live_signal_names = [s["feature"] for s in live_signals]

    if live_signal_names:
        live_bet_lines = [
            f"The following {len(live_signal_names)} features carry r>=0.50 predictive signal "
            f"from the opening 100 frames and can anchor live within-game updates:\n"
        ]
        for s in live_signals:
            live_bet_lines.append(
                f"- **{s['feature']}** (r={s['r_pearson']:.3f}, r²={s['r2']:.3f}, "
                f"n={s['n']}) -- first-100-frame value explains "
                f"{s['r2']*100:.0f}% of full-game variance"
            )
    else:
        live_bet_lines = [
            "No features cleared r>=0.50 at the 100-frame window. "
            "This suggests behavior is highly game-arc dependent."
        ]

    # Bug finding block
    bug_block = ""
    if bug_finding:
        bug_block = (
            f"\n## Anomaly / Bug Finding\n\n"
            f"The tipoff-window analysis surfaced a potential CV pipeline scale artifact:\n\n"
            f"```\n{bug_finding}\n```\n\n"
            f"See Bug 15 in CV_Pipeline_Bug_Roadmap.md for details.\n"
        )

    lines = [
        f"# INT-43 Tip-off Frame Predictability Atlas",
        f"",
        f"_Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}_",
        f"",
        f"**Question**: How much of a player-game's full CV-feature profile can be predicted from "
        f"just the first 100-300 frames (tip-off + opening possessions)?",
        f"",
        f"**If r>0.5**: first-100-frame signatures can anchor live within-game model updates "
        f"(predict 2nd-half OVER/UNDER from 1st-quarter CV).",
        f"**If r<0.5**: behavior emerges over the game arc -- early frames are poor predictors.",
        f"",
        f"## Coverage",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Games processed | {n_games} |",
        f"| Games skipped (too small / missing) | {n_skipped} |",
        f"| Total player-game-window observations | {n_total_obs} |",
        f"| Features analyzed | {n_feats} |",
        f"| Window: first 100 sampled frames | ~20 s of gameplay at 5 samples/sec |",
        f"| Window: first 300 sampled frames | ~60 s |",
        f"| Window: first-quarter estimate | first 25% of game frame range |",
        f"",
        f"## Headline: Feature Predictability from Tip-Off",
        f"",
        f"| Window | Features with r>=0.5 | Out of {n_feats} total |",
        f"|--------|--------------------|-----------------------|",
        f"| First 100 frames (~20s) | {n_w100_pass} | {n_w100_pass}/{n_feats} = {n_w100_pass/n_feats*100:.0f}% |",
        f"| First 300 frames (~60s) | {n_w300_pass} | {n_w300_pass}/{n_feats} = {n_w300_pass/n_feats*100:.0f}% |",
        f"| First quarter (25% of game) | {n_w1q_pass} | {n_w1q_pass}/{n_feats} = {n_w1q_pass/n_feats*100:.0f}% |",
        f"",
        f"## Best 5 Features at 100-Frame Window (Highest Early Predictability)",
        f"",
        feature_table(top5),
        f"",
        f"## Worst 5 Features at 100-Frame Window (Weakest Early Signal)",
        f"",
        feature_table(worst5),
        f"",
        f"## All Features -- Full Predictability Matrix",
        f"",
        "\n".join(all_feats_table_rows),
        f"",
        f"## Implications for Live Betting",
        f"",
        "\n".join(live_bet_lines),
        f"",
        f"### Interpretation Guide",
        f"",
        f"- **r >= 0.7 (strong)**: First-100-frame values alone explain >=49% of full-game variance. "
        f"Use as a direct live update signal -- e.g., if `avg_velocity` is in this tier, "
        f"a slow first minute predicts a slow full game.",
        f"- **r 0.5-0.7 (moderate)**: Useful directional signal but needs game-context filters "
        f"(pace, lineup, fatigue). Combine with INT-41 quarter momentum and INT-23 clutch profiles.",
        f"- **r < 0.5 (weak/emergent)**: Feature behavior unfolds over the game. Do NOT use "
        f"early-window values alone to adjust props. Wait for first-quarter data (w1Q).",
        f"",
        f"### Recommended In-Game Update Workflow",
        f"",
        f"1. After ~60 frames (first tip-off possession): compute w100 features for the "
        f"two primary ball-handlers.",
        f"2. Compare against player's season-average from cv_features.",
        f"3. For features with r>=0.5: flag significant deviation (z>1.5) as an early-game signal.",
        f"4. After first quarter (w1Q): re-score all features. High-r features at w1Q = "
        f"high-confidence H2 OVER/UNDER bias.",
        f"5. Cross-reference against INT-41 (quarter momentum) and INT-23 (clutch profiles) "
        f"before applying Kelly sizing.",
        f"",
        bug_block,
        f"## Honest Caveats",
        f"",
        f"- `scoreboard_period` is NULL across all processed games -- quarter assignment uses "
        f"frame-range percentile (25% cutoff). True first-quarter boundaries may differ slightly.",
        f"- Player identity is SLOT-level (1-10), not NBA player_id. Cross-game aggregation "
        f"not performed. All correlations are within-game (slot's first-100 vs slot's full game).",
        f"- Games with fewer than {MIN_TOTAL_ROWS} rows (clip excerpts) are excluded.",
        f"- ISSUE-022 defender_distance=200 sentinel is filtered (>200ft excluded) to reduce "
        f"corruption in distance-based features, but partial corruption may remain.",
        f"- Very short tip-off windows (w100 = 100 sampled frames) may have fewer than "
        f"{MIN_FRAMES_FOR_CORR} rows for bench players -- those observations are dropped.",
        f"- Bug 9 (cross-season scale inconsistency) may inflate or deflate correlations for "
        f"distance/spacing features across 2024-25 vs 2025-26 games.",
        f"",
        f"## Cross-Reference",
        f"",
        f"| INT | Signal | Relationship |",
        f"|-----|--------|-------------|",
        f"| INT-41 | Quarter Momentum | Uses same frame-quartile logic; Q1 = w1Q overlap |",
        f"| INT-23 | Clutch CV Split | Tip-off signal + clutch profile = full-game arc model |",
        f"| INT-8 | In-Game Momentum | H1 vs H2 split -- 1Q predictability addresses H1 only |",
        f"| INT-22 | Rest/Fatigue | Low tip-off velocity on back-to-back = compound fade signal |",
        f"",
        f"---",
        f"_Source: `scripts/build_tipoff_predictability.py` | INT-43_",
    ]

    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Wrote atlas: {OUT_ATLAS}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="INT-43: Tip-off frame predictability -- CV feature correlation analysis"
    )
    parser.add_argument(
        "--min-frames", type=int, default=MIN_FRAMES_FOR_CORR,
        help=f"Min frames per player-window obs [default: {MIN_FRAMES_FOR_CORR}]"
    )
    parser.add_argument(
        "--min-games", type=int, default=MIN_N_FOR_CORR,
        help=f"Min player-game pairs to compute correlation [default: {MIN_N_FOR_CORR}]"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    min_frames = args.min_frames
    min_n      = args.min_games

    print("INT-43 Tip-off Frame Predictability")
    print("=" * 50)

    if not TRACKING_DIR.exists():
        print(f"ERROR: tracking dir not found: {TRACKING_DIR}", file=sys.stderr)
        sys.exit(1)

    game_ids = sorted([
        d for d in os.listdir(TRACKING_DIR)
        if os.path.isdir(TRACKING_DIR / d)
    ])
    print(f"Found {len(game_ids)} game directories")

    all_rows: list[dict] = []
    n_processed = 0
    n_skipped   = 0

    for i, gid in enumerate(game_ids):
        td_path = TRACKING_DIR / gid / "tracking_data.csv"
        if not td_path.exists():
            n_skipped += 1
            continue

        rows = _process_one_game(gid, verbose=args.verbose,
                                 min_frames_for_corr=min_frames)
        if rows:
            all_rows.extend(rows)
            n_processed += 1
        else:
            n_skipped += 1

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(game_ids)}] processed={n_processed} obs={len(all_rows)}")

    print(f"Processed {n_processed} games, skipped {n_skipped}")
    print(f"Total player-game-window observations: {len(all_rows)}")

    if not all_rows:
        print("No data collected -- aborting", file=sys.stderr)
        sys.exit(1)

    # Bug detection pass
    print("Running scale-jump bug detection...")
    bug_finding = _detect_scale_jump_bug(all_rows)
    if bug_finding:
        print(f"  SCALE BUG DETECTED:\n{bug_finding}")
    else:
        print("  No scale-jump bugs detected")

    # Correlation analysis
    print("Computing per-feature correlations...")
    corr_df = _compute_correlations(all_rows, min_n=min_n)
    print(f"  Correlation rows: {len(corr_df)}")

    if corr_df.empty:
        print("ERROR: No correlations computed", file=sys.stderr)
        sys.exit(1)

    # Summary
    for window in ["w100", "w300", "w1Q"]:
        wdf = corr_df[(corr_df["window"] == window) & corr_df["r_pearson"].notna()]
        n_pass = int((wdf["r_pearson"] >= R_THRESHOLD).sum())
        best_r = wdf["r_pearson"].max()
        median_r = wdf["r_pearson"].median()
        print(f"  {window}: {n_pass}/{len(wdf)} features r>=0.5 | best_r={best_r:.3f} | median_r={median_r:.3f}")

    # Build signals JSON
    print("Building signals JSON...")
    signals = _build_signals_json(corr_df)

    # Print top signals
    top_sigs = signals.get("window_100_signals", [])
    if top_sigs:
        print(f"  Features passing r>={R_THRESHOLD} at 100-frame window: {len(top_sigs)}")
        for s in top_sigs[:5]:
            print(f"    {s['feature']}: r={s['r_pearson']:.3f} r2={s['r2']:.3f} n={s['n']}")
    else:
        print(f"  No features pass r>={R_THRESHOLD} at 100-frame window")

    # Worst feature
    w100_df = corr_df[(corr_df["window"] == "w100") & corr_df["r_pearson"].notna()]
    if len(w100_df) > 0:
        worst = w100_df.sort_values("r_pearson").iloc[0]
        print(f"  Worst feature (w100): {worst['feature_name']} r={worst['r_pearson']:.3f}")
        best  = w100_df.sort_values("r_pearson", ascending=False).iloc[0]
        print(f"  Best  feature (w100): {best['feature_name']}  r={best['r_pearson']:.3f}")

    # Write outputs
    print("Writing outputs...")
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    corr_df.to_parquet(OUT_PARQUET, index=False)
    print(f"  Wrote parquet: {OUT_PARQUET} ({len(corr_df)} rows)")

    with open(OUT_SIGNALS, "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2)
    print(f"  Wrote signals: {OUT_SIGNALS}")

    _write_atlas(
        corr_df=corr_df,
        signals=signals,
        n_games=n_processed,
        n_skipped=n_skipped,
        n_total_obs=len(all_rows),
        bug_finding=bug_finding,
    )

    # Final console summary
    print()
    print("=" * 50)
    print("INT-43 FINAL REPORT")
    print("=" * 50)

    w100_df = corr_df[(corr_df["window"] == "w100") & corr_df["r_pearson"].notna()]
    w1q_df  = corr_df[(corr_df["window"] == "w1Q")  & corr_df["r_pearson"].notna()]

    n_total_feats = len(FEAT_NAMES)
    n_100_pass = int((w100_df["r_pearson"] >= R_THRESHOLD).sum())
    n_1q_pass  = int((w1q_df["r_pearson"]  >= R_THRESHOLD).sum())

    print(f"Coverage: {n_processed} games processed")
    print(f"Features predictable (r>=0.5) from first 100 frames: {n_100_pass}/{n_total_feats}")
    print(f"Features predictable (r>=0.5) from first quarter:    {n_1q_pass}/{n_total_feats}")

    if len(w100_df) > 0:
        print()
        print("Top 5 Most Predictable Features (100-frame window):")
        for _, row in w100_df.sort_values("r_pearson", ascending=False).head(5).iterrows():
            print(f"  {row['feature_name']:<28} r={row['r_pearson']:.3f}  r2={row['r2']:.3f}")

        print()
        print("Top 5 Least Predictable Features (100-frame window):")
        for _, row in w100_df.sort_values("r_pearson", ascending=True).head(5).iterrows():
            print(f"  {row['feature_name']:<28} r={row['r_pearson']:.3f}  r2={row['r2']:.3f}")

    if bug_finding:
        print()
        print("BUG DETECTED: Scale jump artifact in distance/spacing features")
        print(f"  {bug_finding[:200]}...")

    print()
    print("Files written:")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_SIGNALS}")
    print(f"  {OUT_ATLAS}")

    print()
    print("How to use:")
    print("  Live bet: after ~60 frames, extract w100 features for primary ball-handler")
    print("  Signal features (r>=0.5 at w100) allow immediate prop adjustment")
    print("  Non-signal features: wait for Q1 window (w1Q) for reliable early signal")
    print("  Stack with INT-41 quarter momentum and INT-23 clutch profiles for full-game arc")


if __name__ == "__main__":
    main()
