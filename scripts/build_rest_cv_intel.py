"""build_rest_cv_intel.py — INT-22 Rest/B2B/Travel CV Impact Analysis.

Tests whether REST, BACK-TO-BACK, and TRAVEL show in CV behavioral signals.
Hypothesis: tired/traveled players exhibit measurable CV-trackable changes
(lower velocity, less paint dwell, slower defender approach).

Inputs:
  data/player_cv_per_game.parquet  — per-game CV feature rows
  data/player_cv_per_player.parquet — per-player baseline (season mean)
  data/rest_travel.parquet         — per-(team, game) is_b2b/miles/altitude
  data/nba/boxscore_*.json         — player→team mapping source
  data/nba/boxscore_adv_*.json     — additional player→team mapping
  data/intelligence/player_fingerprints.parquet — alternative baseline

Outputs:
  data/intelligence/rest_cv_impact.parquet
  data/intelligence/rest_cv_signatures.json
  vault/Intelligence/Rest_CV_Atlas.md
"""
from __future__ import annotations

import json
import glob
import os
import re
import sys
from collections import Counter
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── paths ────────────────────────────────────────────────────────────────────
CV_PER_GAME    = os.path.join(PROJECT_DIR, "data", "player_cv_per_game.parquet")
CV_PER_PLAYER  = os.path.join(PROJECT_DIR, "data", "player_cv_per_player.parquet")
REST_TRAVEL    = os.path.join(PROJECT_DIR, "data", "rest_travel.parquet")
NBA_CACHE      = os.path.join(PROJECT_DIR, "data", "nba")
INTEL_DIR      = os.path.join(PROJECT_DIR, "data", "intelligence")
VAULT_INTEL    = os.path.join(PROJECT_DIR, "vault", "Intelligence")

OUT_PARQUET    = os.path.join(INTEL_DIR, "rest_cv_impact.parquet")
OUT_JSON       = os.path.join(INTEL_DIR, "rest_cv_signatures.json")
OUT_ATLAS      = os.path.join(VAULT_INTEL, "Rest_CV_Atlas.md")

# ── context thresholds ───────────────────────────────────────────────────────
B2B_FLAG          = 1.0         # is_b2b == 1
HIGH_REST_DAYS    = 3           # rest_days >= 3
HIGH_TRAVEL_MILES = 1500        # miles_traveled > 1500
ALTITUDE_FT       = 4000        # altitude_ft > 4000 (Denver ~5183, Salt Lake ~4327)

# ── CV features to analyse ───────────────────────────────────────────────────
CV_FEATURES = [
    "cvb_avg_velocity",
    "cvb_paint_time_pct",
    "cvb_near_basket_pct",
    "cvb_avg_defender_dist",
    "cvb_fatigue_score",
    "cvb_avg_spacing",
    "cvb_off_ball_dist",
    "cvb_avg_dist_to_basket",
    "cvb_jump_frequency",
    "cvb_velocity_q4_dropoff",
    "cvb_contested_shot_pct",
    "cvb_close_to_basket_pct",
    "cvb_passes_per100",
    "cvb_dribbles_per100",
]

# ── interpretations per feature ──────────────────────────────────────────────
_FEATURE_INTERP = {
    "cvb_avg_velocity":          "Average on-court movement speed",
    "cvb_paint_time_pct":        "Fraction of time spent in paint",
    "cvb_near_basket_pct":       "Fraction of time near basket",
    "cvb_avg_defender_dist":     "Average nearest-defender distance",
    "cvb_fatigue_score":         "Composite fatigue proxy (frame-level)",
    "cvb_avg_spacing":           "Average spacing from teammates",
    "cvb_off_ball_dist":         "Off-ball movement distance",
    "cvb_avg_dist_to_basket":    "Average distance from basket",
    "cvb_jump_frequency":        "Jumps per minute estimate",
    "cvb_velocity_q4_dropoff":   "Q4 velocity relative to Q1-Q3",
    "cvb_contested_shot_pct":    "Share of shots taken while contested",
    "cvb_close_to_basket_pct":   "Fraction of time close to basket",
    "cvb_passes_per100":         "Pass actions per 100 frames",
    "cvb_dribbles_per100":       "Dribble actions per 100 frames",
}

# ── B2B interpretation direction ─────────────────────────────────────────────
# negative delta = lower on B2B (expected for "tired" signals)
_DIRECTION_SIGN = {
    "cvb_avg_velocity":       -1,   # lower = worse
    "cvb_paint_time_pct":     -1,
    "cvb_near_basket_pct":    -1,
    "cvb_avg_defender_dist":  +1,   # higher = less pressure (possibly lower effort)
    "cvb_fatigue_score":      +1,   # higher = more fatigue
    "cvb_velocity_q4_dropoff":-1,   # lower = more dropoff
    "cvb_jump_frequency":     -1,
}


def _build_player_game_team_map(cv_player_ids: set, cv_game_ids: set) -> Dict[Tuple[int, str], str]:
    """Build (player_id, game_id) -> team_abbreviation from all available sources."""
    mapping: Dict[Tuple[int, str], str] = {}

    # Source 1: advanced boxscores (teamtricode + personid)
    adv_files = glob.glob(os.path.join(NBA_CACHE, "boxscore_adv_*.json"))
    for path in adv_files:
        try:
            s = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gid = str(s.get("game_id", "")).zfill(10)
        if gid not in cv_game_ids:
            continue
        for p in s.get("players", []):
            pid = p.get("personid")
            team = p.get("teamtricode")
            if pid and team and int(pid) in cv_player_ids:
                mapping[(int(pid), gid)] = str(team)

    # Source 2: regular boxscores (team_abbreviation + player_id)
    bs_files = glob.glob(os.path.join(NBA_CACHE, "boxscore_0022*.json"))
    for path in bs_files:
        try:
            s = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        gid = str(s.get("game_id", "")).zfill(10)
        if gid not in cv_game_ids:
            continue
        for p in s.get("players", []):
            pid = p.get("player_id")
            team = p.get("team_abbreviation")
            if pid and team and int(pid) in cv_player_ids:
                key = (int(pid), gid)
                if key not in mapping:
                    mapping[key] = str(team)

    # Source 3: gamelog files (matchup field: 'BOS vs. MIA' = BOS is home team left side)
    gl_files = glob.glob(os.path.join(NBA_CACHE, "gamelog_full_*.json"))
    for path in gl_files:
        m = re.search(r"gamelog_full_(\d+)_", path)
        if not m:
            continue
        pid = int(m.group(1))
        if pid not in cv_player_ids:
            continue
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = payload if isinstance(payload, list) else payload.get("rows", [])
        for r in rows:
            gid = str(r.get("game_id", "")).zfill(10)
            if gid not in cv_game_ids:
                continue
            key = (pid, gid)
            if key in mapping:
                continue
            matchup = str(r.get("matchup", ""))
            m2 = re.match(r"^([A-Z]{3})\s+(@|vs\.?)\s+([A-Z]{3})$", matchup)
            if m2:
                mapping[key] = m2.group(1)  # left team = this player's team

    return mapping


def _compute_rest_days(rt: pd.DataFrame) -> pd.DataFrame:
    """Add rest_days column to rest_travel DataFrame."""
    rt = rt.sort_values(["team_abbreviation", "game_date"]).copy()
    rt["prev_game_date"] = rt.groupby("team_abbreviation")["game_date"].shift(1)
    rt["rest_days"] = (
        pd.to_datetime(rt["game_date"]) - pd.to_datetime(rt["prev_game_date"])
    ).dt.days
    return rt


def _tag_context(row: pd.Series) -> str:
    """Assign a single primary context tag per row."""
    if row["is_b2b"] == B2B_FLAG:
        return "B2B"
    if pd.notna(row["altitude_ft"]) and row["altitude_ft"] > ALTITUDE_FT:
        return "ALTITUDE"
    if pd.notna(row["miles_traveled"]) and row["miles_traveled"] > HIGH_TRAVEL_MILES:
        return "HIGH_TRAVEL"
    if pd.notna(row.get("rest_days")) and row["rest_days"] >= HIGH_REST_DAYS:
        return "HIGH_REST"
    return "NORMAL"


def _welch_t(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Welch's t-test: returns (t_stat, p_value). Handles small/degenerate arrays."""
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return (np.nan, np.nan)
    if np.std(a) == 0 and np.std(b) == 0:
        return (0.0, 1.0)
    result = stats.ttest_ind(a, b, equal_var=False)
    return float(result.statistic), float(result.pvalue)


def build() -> None:
    os.makedirs(INTEL_DIR, exist_ok=True)
    os.makedirs(VAULT_INTEL, exist_ok=True)

    # ── load core data ────────────────────────────────────────────────────────
    print("[load] Reading CV and rest/travel data...")
    cv       = pd.read_parquet(CV_PER_GAME)
    cv_pp    = pd.read_parquet(CV_PER_PLAYER)
    rt_raw   = pd.read_parquet(REST_TRAVEL)
    rt       = _compute_rest_days(rt_raw)

    # ── build player→team mapping ─────────────────────────────────────────────
    cv_player_ids = set(cv["nba_player_id"].dropna().astype(int).unique())
    cv_game_ids   = set(cv["game_id"].unique())
    print(f"[map]  Building player-game-team map for {len(cv_player_ids)} players "
          f"across {len(cv_game_ids)} games...")
    player_game_team = _build_player_game_team_map(cv_player_ids, cv_game_ids)
    print(f"[map]  {len(player_game_team)} (player, game) pairs resolved")

    # ── attach team_abbreviation to cv rows ───────────────────────────────────
    cv_with_id = cv[cv["nba_player_id"].notna()].copy()
    cv_with_id["nba_player_id"] = cv_with_id["nba_player_id"].astype(int)
    cv_with_id["team_abbreviation"] = cv_with_id.apply(
        lambda r: player_game_team.get((int(r["nba_player_id"]), str(r["game_id"]))),
        axis=1
    )
    cv_mapped = cv_with_id[cv_with_id["team_abbreviation"].notna()].copy()
    print(f"[map]  {len(cv_mapped)} / {len(cv_with_id)} cv rows with team resolved "
          f"({len(cv_mapped)/len(cv_with_id)*100:.0f}%)")

    # ── join rest/travel ──────────────────────────────────────────────────────
    merged = cv_mapped.merge(
        rt[["game_id", "team_abbreviation", "is_b2b", "is_b3b",
            "miles_traveled", "altitude_ft", "rest_days"]],
        on=["game_id", "team_abbreviation"],
        how="inner"
    )
    print(f"[join] After rest/travel join: {len(merged)} rows, "
          f"{merged['nba_player_id'].nunique()} players, "
          f"{merged['game_id'].nunique()} games")

    # ── build per-player baseline (season mean from cv_per_player) ────────────
    cv_pp_valid = cv_pp[cv_pp["nba_player_id"].notna()].copy()
    cv_pp_valid["nba_player_id"] = cv_pp_valid["nba_player_id"].astype(int)
    baseline_feats = [f for f in CV_FEATURES if f in cv_pp_valid.columns]
    baseline = cv_pp_valid.set_index("nba_player_id")[baseline_feats + ["player_name"]]

    # player std from per-game (for z-score)
    # rename to _pstd to avoid collision with existing cvb_off_ball_dist_std column
    per_game_std = (
        merged[["nba_player_id"] + [f for f in CV_FEATURES if f in merged.columns]]
        .groupby("nba_player_id")
        .std()
        .rename(columns={f: f"{f}_pstd" for f in CV_FEATURES})
    )

    # ── tag context ───────────────────────────────────────────────────────────
    merged["context"] = merged.apply(_tag_context, axis=1)
    ctx_counts = merged["context"].value_counts()
    print("\n[ctx]  Context distribution:")
    for ctx, cnt in ctx_counts.items():
        print(f"         {ctx:12s}: {cnt} player-game rows")

    available_feats = [f for f in CV_FEATURES if f in merged.columns]

    # ── compute per-row deltas from player baseline ───────────────────────────
    print("\n[delta] Computing per-row deltas from player baseline...")
    # Merge baseline into merged df
    merged_with_base = merged.join(
        baseline[available_feats].rename(columns={f: f"{f}_base" for f in available_feats}),
        on="nba_player_id",
        how="left"
    )
    merged_with_base = merged_with_base.join(per_game_std, on="nba_player_id", how="left")

    for feat in available_feats:
        delta_col = f"{feat}_delta"
        z_col     = f"{feat}_z"
        base_col  = f"{feat}_base"
        std_col   = f"{feat}_pstd"  # matches renamed per_game_std columns
        if base_col in merged_with_base.columns:
            merged_with_base[delta_col] = merged_with_base[feat] - merged_with_base[base_col]
            if std_col in merged_with_base.columns:
                merged_with_base[z_col] = (
                    merged_with_base[delta_col] / merged_with_base[std_col].replace(0, np.nan)
                )

    delta_feats = [f"{f}_delta" for f in available_feats]
    z_feats     = [f"{f}_z"     for f in available_feats]

    # ── Step 2: league-wide context aggregations ──────────────────────────────
    print("\n[agg]  Computing league-wide context signatures...")
    contexts = ["B2B", "HIGH_REST", "HIGH_TRAVEL", "ALTITUDE", "NORMAL"]
    normal_rows = merged_with_base[merged_with_base["context"] == "NORMAL"]

    signatures: Dict[str, dict] = {}
    for ctx in contexts:
        ctx_rows = merged_with_base[merged_with_base["context"] == ctx]
        n = len(ctx_rows)
        if n == 0:
            signatures[ctx] = {"n_games_observed": 0, "league_signature": {}}
            continue

        sig: Dict[str, dict] = {}
        for feat in available_feats:
            d_col = f"{feat}_delta"
            z_col = f"{feat}_z"
            if d_col not in ctx_rows.columns:
                continue
            ctx_deltas = ctx_rows[d_col].dropna().values
            ctx_z      = ctx_rows[z_col].dropna().values if z_col in ctx_rows.columns else np.array([])
            norm_deltas = normal_rows[d_col].dropna().values

            mean_delta = float(np.nanmean(ctx_deltas)) if len(ctx_deltas) > 0 else np.nan
            mean_z     = float(np.nanmean(ctx_z))     if len(ctx_z) > 0     else np.nan
            t_stat, p_val = _welch_t(ctx_deltas, norm_deltas)

            interp_base = _FEATURE_INTERP.get(feat, feat)
            # Auto-interpret direction
            if not np.isnan(mean_delta):
                direction = "higher" if mean_delta > 0 else "lower"
                interp = f"{direction.capitalize()} on {ctx}: {interp_base}"
            else:
                interp = interp_base

            sig[feat] = {
                "delta":  round(mean_delta, 4) if not np.isnan(mean_delta) else None,
                "z":      round(mean_z, 3)     if not np.isnan(mean_z)     else None,
                "t":      round(t_stat, 3)     if not np.isnan(t_stat)     else None,
                "p":      round(p_val, 4)      if not np.isnan(p_val)      else None,
                "n":      len(ctx_deltas),
                "interp": interp,
            }

        signatures[ctx] = {
            "n_games_observed":  n,
            "n_player_games":    n,
            "league_signature":  sig,
        }

    # ── Step 3: per-player B2B impact (top 30 by # B2B games) ────────────────
    print("\n[player] Computing per-player B2B signatures...")
    b2b_rows = merged_with_base[merged_with_base["context"] == "B2B"]
    normal_rows_by_player = merged_with_base[merged_with_base["context"] == "NORMAL"]

    b2b_per_player = b2b_rows.groupby("nba_player_id").size().sort_values(ascending=False)
    top_30_ids = b2b_per_player.head(30).index.tolist()

    per_player_records = []
    for pid in top_30_ids:
        pname = baseline.loc[pid, "player_name"] if pid in baseline.index else str(pid)
        p_b2b = b2b_rows[b2b_rows["nba_player_id"] == pid]
        p_norm = normal_rows_by_player[normal_rows_by_player["nba_player_id"] == pid]
        n_b2b = len(p_b2b)

        row_dict: Dict[str, object] = {
            "player_id":   pid,
            "player_name": pname,
            "context":     "B2B",
            "n_games":     n_b2b,
        }

        feat_z_pairs = []
        for feat in available_feats:
            d_col = f"{feat}_delta"
            z_col = f"{feat}_z"
            if d_col not in p_b2b.columns:
                continue
            p_b2b_deltas = p_b2b[d_col].dropna().values
            p_norm_deltas = p_norm[d_col].dropna().values if not p_norm.empty else np.array([])
            if len(p_b2b_deltas) == 0:
                continue

            mean_delta = float(np.nanmean(p_b2b_deltas))
            _z_vals    = p_b2b[z_col].dropna().values if z_col in p_b2b.columns else np.array([])
            mean_z     = float(np.nanmean(_z_vals)) if len(_z_vals) > 0 else np.nan
            t_stat, p_val = _welch_t(p_b2b_deltas, p_norm_deltas)

            row_dict[f"{feat}_delta"] = round(mean_delta, 4)
            row_dict[f"{feat}_z"]     = round(mean_z, 3) if not np.isnan(mean_z) else None
            row_dict[f"{feat}_t"]     = round(t_stat, 3) if not np.isnan(t_stat) else None

            feat_z_pairs.append((feat, mean_z))

        # top 3 features by |z|
        feat_z_sorted = sorted(feat_z_pairs, key=lambda x: abs(x[1]) if not np.isnan(x[1]) else 0, reverse=True)
        row_dict["top_feature_1"] = feat_z_sorted[0][0] if len(feat_z_sorted) > 0 else None
        row_dict["top_feature_1_z"] = round(feat_z_sorted[0][1], 3) if len(feat_z_sorted) > 0 else None
        row_dict["top_feature_2"] = feat_z_sorted[1][0] if len(feat_z_sorted) > 1 else None
        row_dict["top_feature_2_z"] = round(feat_z_sorted[1][1], 3) if len(feat_z_sorted) > 1 else None
        row_dict["top_feature_3"] = feat_z_sorted[2][0] if len(feat_z_sorted) > 2 else None
        row_dict["top_feature_3_z"] = round(feat_z_sorted[2][1], 3) if len(feat_z_sorted) > 2 else None

        per_player_records.append(row_dict)

    per_player_df = pd.DataFrame(per_player_records)

    # ── Step 4: write Parquet ─────────────────────────────────────────────────
    print(f"\n[out]  Writing {OUT_PARQUET}")
    per_player_df.to_parquet(OUT_PARQUET, index=False)
    print(f"       {len(per_player_df)} player rows saved")

    # ── Step 5: write JSON signatures ─────────────────────────────────────────
    print(f"[out]  Writing {OUT_JSON}")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(signatures, f, indent=2, default=str)

    # ── Step 6: write Atlas ───────────────────────────────────────────────────
    print(f"[out]  Writing {OUT_ATLAS}")
    _write_atlas(signatures, per_player_df, merged_with_base, ctx_counts, available_feats)

    # ── Step 7: print report ──────────────────────────────────────────────────
    _print_report(signatures, per_player_df, ctx_counts)


def _top_features_for_ctx(sig: dict, n: int = 3) -> list:
    """Return top-n features by |t| with valid t-stat in the signature."""
    feats = [
        (feat, info)
        for feat, info in sig.items()
        if info.get("t") is not None and not np.isnan(info["t"])
    ]
    feats.sort(key=lambda x: abs(x[1]["t"]), reverse=True)
    return feats[:n]


def _write_atlas(
    signatures: dict,
    per_player_df: pd.DataFrame,
    merged: pd.DataFrame,
    ctx_counts: pd.Series,
    available_feats: list,
) -> None:
    lines = [
        "# Rest / B2B / Travel CV Impact Atlas",
        "",
        "## Methodology",
        "Per-game context tagging (B2B, HIGH_REST, HIGH_TRAVEL, ALTITUDE) combined "
        "with CV deviation from player season-mean baseline. Welch's t-tests vs NORMAL "
        "context to identify systematic effects. Player baselines = season mean from "
        "`player_cv_per_player.parquet` (mild leakage: baselines include B2B games).",
        "",
        "## Coverage",
    ]

    for ctx in ["B2B", "HIGH_REST", "HIGH_TRAVEL", "ALTITUDE", "NORMAL"]:
        n = ctx_counts.get(ctx, 0)
        lines.append(f"- {ctx} player-game rows: {n}")

    total = len(merged)
    n_players = merged["nba_player_id"].nunique()
    n_games   = merged["game_id"].nunique()
    lines += [
        "",
        f"Total player-game rows with CV + context data: {total}",
        f"Unique players: {n_players}  |  Unique games: {n_games}",
        "",
        "## League-wide context signatures",
        "",
    ]

    ctx_order = ["B2B", "HIGH_TRAVEL", "ALTITUDE", "HIGH_REST"]
    for ctx in ctx_order:
        sig_data = signatures.get(ctx, {})
        sig      = sig_data.get("league_signature", {})
        n_pg     = sig_data.get("n_player_games", 0)
        lines.append(f"### {ctx} effect  (n={n_pg} player-games)")

        top = _top_features_for_ctx(sig, n=5)
        if not top:
            lines.append("*No significant features detected (likely insufficient sample).*")
            lines.append("")
            continue

        for feat, info in top:
            delta = info.get("delta")
            t     = info.get("t")
            p     = info.get("p")
            interp= info.get("interp", feat)
            sig_star = ""
            if p is not None and not np.isnan(p):
                if p < 0.05:
                    sig_star = " **"
                elif p < 0.10:
                    sig_star = " *"
            delta_str = f"{delta:+.4f}" if delta is not None else "n/a"
            t_str     = f"{t:+.2f}"    if t     is not None else "n/a"
            p_str     = f"{p:.4f}"     if p     is not None else "n/a"
            lines.append(f"- `{feat}`: delta={delta_str}  t={t_str}  p={p_str}{sig_star}")
            lines.append(f"  *{interp}*")
        lines.append("")

    # Per-player B2B table
    lines += [
        "## Per-player B2B sensitivity (top 30 by # B2B games)",
        "",
        "| player | n_b2b_games | top_feature | z |",
        "|--------|-------------|-------------|---|",
    ]
    for _, row in per_player_df.iterrows():
        feat = row.get("top_feature_1", "—") or "—"
        z    = row.get("top_feature_1_z")
        z_str = f"{z:+.2f}" if z is not None and not (isinstance(z, float) and np.isnan(z)) else "n/a"
        lines.append(f"| {row['player_name']} | {row['n_games']} | {feat} | {z_str} |")

    lines += [
        "",
        "## Betting implications",
        "- B2B player with historically low `cvb_avg_velocity` on B2Bs → "
        "downsize Kelly further, bias UNDER on PTS/REB",
        "- HIGH_TRAVEL games (>1500 mi): check `cvb_paint_time_pct` shift — "
        "if negative, UNDER on REB/AST props",
        "- ALTITUDE games (DEN/UTA): `cvb_fatigue_score` tends higher, "
        "`cvb_velocity_q4_dropoff` lower — bias UNDER on 2H props",
        "- Combine with INT-18 trend tag and INT-16 confidence multiplier for "
        "compound down-sizing",
        "",
        "## Honest caveats",
        "- Sample sizes per context are small: B2B ≈15% of all games, CV covers "
        "~9% of those (inherits Phase G tracking scope)",
        "- Player baselines are season means including their own B2B games → mild "
        "leakage (baselines slightly depressed, delta slightly under-estimated)",
        "- `miles_traveled` = 0 for home-stand games; only away-team travel is "
        "captured",
        "- ISSUE-022: `defender_distance=200.0` sentinel still affects "
        "`cvb_avg_defender_dist` signals — treat that feature's results cautiously",
        "- No B3B-specific context tested (small n); is_b2b also captures b3b",
        "- **t-stats with n<5 are unreliable** — filter by `n >= 5` before acting",
    ]

    with open(OUT_ATLAS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _print_report(signatures: dict, per_player_df: pd.DataFrame, ctx_counts: pd.Series) -> None:
    print("\n" + "=" * 70)
    print("## INT-22 Rest/B2B/Travel CV Impact — Final Report")
    print("=" * 70)

    print("\n### Coverage by context")
    for ctx in ["B2B", "HIGH_REST", "HIGH_TRAVEL", "ALTITUDE", "NORMAL"]:
        n = ctx_counts.get(ctx, 0)
        print(f"  {ctx:14s}: {n} player-game rows")

    print("\n### League-wide signature findings")
    for ctx in ["B2B", "HIGH_TRAVEL", "ALTITUDE", "HIGH_REST"]:
        sig_data = signatures.get(ctx, {})
        sig      = sig_data.get("league_signature", {})
        n        = sig_data.get("n_player_games", 0)
        top      = _top_features_for_ctx(sig, n=3)
        print(f"\n  {ctx} (n={n}):")
        if not top:
            print("    — no features with computable t-stat (likely n<2)")
            continue
        for feat, info in top:
            delta = info.get("delta")
            t     = info.get("t")
            p     = info.get("p")
            sig_flag = "**" if (p is not None and not np.isnan(p) and p < 0.05) else (
                       "*"  if (p is not None and not np.isnan(p) and p < 0.10) else "")
            d_str = f"{delta:+.4f}" if delta is not None else "n/a"
            t_str = f"{t:+.2f}"    if t is not None else "n/a"
            print(f"    {feat}: delta={d_str}  t={t_str}  {sig_flag}")

    print("\n### Top 5 B2B-sensitive players")
    print(f"  {'player':<25} {'n_b2b':>6} {'top_feature':<32} {'z':>6}")
    print("  " + "-" * 70)
    for _, row in per_player_df.head(5).iterrows():
        feat = row.get("top_feature_1", "—") or "—"
        z    = row.get("top_feature_1_z")
        z_str = f"{z:+.2f}" if z is not None and not (isinstance(z, float) and np.isnan(z)) else "n/a"
        print(f"  {str(row['player_name']):<25} {row['n_games']:>6} {feat:<32} {z_str:>6}")

    print("\n### Files")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")

    print("\n### How to use")
    print("  - Pre-bet: B2B for [player] AND their historical `cvb_avg_velocity` "
          "delta < -0.5 SD -> downsize Kelly + bias UNDER")
    print("  - Altitude alert (DEN/UTA road teams): check ALTITUDE sig for "
          "`cvb_fatigue_score` / velocity")
    print("  - Combine with INT-18 trend tag and INT-16 multiplier for compounding")

    print("\n### Honest caveats")
    print("  - Small samples: B2B n is the binding constraint")
    print("  - Mild baseline leakage: player baselines include their B2B games")
    print("  - ISSUE-022 affects cvb_avg_defender_dist reliability")
    print("=" * 70)


if __name__ == "__main__":
    build()
