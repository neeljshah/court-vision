"""
INT-29: Exponential-Decay-Weighted Current Form CV Profiles
===========================================================
Builds per-player current-form vectors using exponential decay (half-life = 5 games),
so recent games count most.  Contrasts with INT-1 (equal-weighted season means).

Outputs:
  data/intelligence/current_form_profiles.parquet
  data/intelligence/form_vs_baseline_deltas.json
  vault/Intelligence/Current_Form_Atlas.md

Usage:
    python scripts/build_current_form.py
    python scripts/build_current_form.py --half-life 3
"""
from __future__ import annotations

import io
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Force UTF-8 stdout on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent

IN_CV_PG      = ROOT / "data" / "player_cv_per_game.parquet"
IN_REST       = ROOT / "data" / "rest_travel.parquet"
IN_PF         = ROOT / "data" / "player_pf.parquet"
IN_INT18      = ROOT / "data" / "intelligence" / "rolling_trends.parquet"

OUT_PROFILES  = ROOT / "data" / "intelligence" / "current_form_profiles.parquet"
OUT_DELTAS    = ROOT / "data" / "intelligence" / "form_vs_baseline_deltas.json"
ATLAS_MD      = ROOT / "vault" / "Intelligence" / "Current_Form_Atlas.md"

OUT_PROFILES.parent.mkdir(parents=True, exist_ok=True)
ATLAS_MD.parent.mkdir(parents=True, exist_ok=True)

TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HALF_LIFE          = 5      # games  (i=0 -> w=1.0; i=5 -> w=0.5; i=10 -> w=0.25)
MIN_GAMES          = 5      # minimum games per player to include

# NOTE on threshold calibration:
# decay-weighted mean vs equal-weighted mean produces inherently smaller z-scores than
# INT-18's window method (recent window vs prior window).  With dataset-wide std
# normalisation, the natural z range in this dataset is [0, ~0.9].
# We use p85 of the empirical max-z distribution (~0.40) rather than INT-18's 1.5.
# This identifies the top ~15% of players as "in transition" -- consistent with INT-18.
TRANSITION_Z_THRESH = 0.40  # |z| > this on any feature = "in transition"

# Secondary signal: ratio of recent-3 games vs prior-all games
# Ratio > 1.5 or < 0.67 = strong directional signal
RECENT_N_FOR_RATIO  = 3     # compare last N games vs remaining as raw ratio

# Features: same reliable set as INT-18 (≥85% coverage, no dead columns)
FEATURES = [
    "cvb_paint_time_pct",
    "cvb_near_basket_pct",
    "cvb_avg_dist_to_basket",
    "cvb_fatigue_score",
    "cvb_avg_velocity",
    "cvb_avg_defender_dist",
    "cvb_avg_spacing",
    "cvb_off_ball_dist",
    "cvb_paint_pressure_own",
    "minutes_proxy",
]

FEATURE_LABELS = {
    "cvb_paint_time_pct":     "paint_dwell_pct",
    "cvb_near_basket_pct":    "near_basket_pct",
    "cvb_avg_dist_to_basket": "avg_dist_to_basket",
    "cvb_fatigue_score":      "fatigue_score",
    "cvb_avg_velocity":       "avg_velocity",
    "cvb_avg_defender_dist":  "defender_dist",
    "cvb_avg_spacing":        "team_spacing",
    "cvb_off_ball_dist":      "off_ball_dist",
    "cvb_paint_pressure_own": "paint_pressure_own",
    "minutes_proxy":          "minutes_proxy",
}

# Classify trend direction using these usage/volume features
USAGE_FEATURES = {
    "cvb_fatigue_score", "cvb_avg_velocity", "minutes_proxy",
    "cvb_near_basket_pct", "cvb_paint_time_pct",
}


# ---------------------------------------------------------------------------
# Step 0 — Load & prepare data
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    cv = pd.read_parquet(IN_CV_PG)

    # Build game_id -> game_date from rest_travel + player_pf
    rest = pd.read_parquet(IN_REST)
    pf   = pd.read_parquet(IN_PF)
    dates = (
        pd.concat([
            rest[["game_id", "game_date"]],
            pf[["game_id", "game_date"]],
        ])
        .drop_duplicates("game_id")
        .assign(game_id=lambda d: d["game_id"].astype(str),
                game_date=lambda d: pd.to_datetime(d["game_date"]))
    )

    cv["game_id"] = cv["game_id"].astype(str)
    df = cv.merge(dates, on="game_id", how="left")

    # Drop tracker placeholder rows (no resolved player name)
    df = df[~df["player_name"].astype(str).str.contains(r"#\?", na=False)].copy()

    # Require a game_date
    df = df[df["game_date"].notna()].copy()

    # Player key: prefer nba_player_id, fall back to player_name
    has_id = df["nba_player_id"].notna()
    df["_player_key"] = np.where(
        has_id,
        df["nba_player_id"].astype("object").where(has_id, None).astype(str),
        df["player_name"].astype(str),
    )

    return df


# ---------------------------------------------------------------------------
# Step 1 — Dataset-wide std for z-score normalisation
# ---------------------------------------------------------------------------

def compute_dataset_stds(df: pd.DataFrame) -> dict[str, float]:
    stds: dict[str, float] = {}
    for feat in FEATURES:
        if feat not in df.columns:
            stds[feat] = np.nan
            continue
        col = pd.to_numeric(df[feat], errors="coerce").dropna()
        s = float(col.std(ddof=1)) if len(col) > 1 else np.nan
        stds[feat] = s if s and s > 1e-9 else np.nan
    return stds


# ---------------------------------------------------------------------------
# Step 2 — Per-player exponential-decay weighted mean
# ---------------------------------------------------------------------------

def decay_weights(n: int, half_life: float = HALF_LIFE) -> np.ndarray:
    """
    Weight game i (0=most recent) with 0.5^(i / half_life).
    Returns array of shape (n,) in chronological order (newest first = index 0).
    """
    i = np.arange(n, dtype=float)
    return 0.5 ** (i / half_life)


def compute_player_profile(
    rows: pd.DataFrame,
    dataset_stds: dict[str, float],
) -> dict:
    """
    rows: all CV games for one player, sorted by date (newest first).
    Returns a flat dict with per-feature: current_form, season_baseline, delta, z.
    """
    n = len(rows)
    weights = decay_weights(n)

    profile: dict = {
        "n_cv_games": n,
        "latest_game_date": rows["game_date"].iloc[0].date().isoformat(),
        "earliest_game_date": rows["game_date"].iloc[-1].date().isoformat(),
    }

    for feat in FEATURES:
        label = FEATURE_LABELS[feat]
        if feat not in rows.columns:
            profile.update({
                f"{label}_current_form": np.nan,
                f"{label}_season_baseline": np.nan,
                f"{label}_delta": np.nan,
                f"{label}_z": np.nan,
            })
            continue

        vals = pd.to_numeric(rows[feat], errors="coerce").values
        mask = ~np.isnan(vals)
        if mask.sum() < 2:
            profile.update({
                f"{label}_current_form": float(vals[mask][0]) if mask.sum() == 1 else np.nan,
                f"{label}_season_baseline": float(vals[mask][0]) if mask.sum() == 1 else np.nan,
                f"{label}_delta": 0.0,
                f"{label}_z": 0.0,
            })
            continue

        w = weights[mask]
        v = vals[mask]

        w_mean  = float(np.sum(v * w) / np.sum(w))
        eq_mean = float(np.mean(v))
        delta   = w_mean - eq_mean

        std = dataset_stds.get(feat)
        z   = float(delta / std) if (std and not np.isnan(std) and std > 1e-9) else 0.0

        # Recent ratio: mean of last RECENT_N_FOR_RATIO games vs prior mean
        # Uses original (pre-mask) index order: rows are sorted newest-first
        recent_idx = np.where(mask)[0][:RECENT_N_FOR_RATIO]   # newest N valid games
        prior_idx  = np.where(mask)[0][RECENT_N_FOR_RATIO:]   # older valid games
        if len(recent_idx) > 0 and len(prior_idx) > 0:
            recent_mean = float(np.mean(v[:len(recent_idx)]))
            prior_mean  = float(np.mean(v[len(recent_idx):]))
            ratio = recent_mean / prior_mean if abs(prior_mean) > 1e-9 else 1.0
        else:
            recent_mean = w_mean
            prior_mean  = eq_mean
            ratio = 1.0

        profile.update({
            f"{label}_current_form": round(w_mean, 6),
            f"{label}_season_baseline": round(eq_mean, 6),
            f"{label}_delta": round(delta, 6),
            f"{label}_z": round(z, 4),
            f"{label}_recent_ratio": round(ratio, 4),
        })

    return profile


# ---------------------------------------------------------------------------
# Step 3 — Classify trend tag
# ---------------------------------------------------------------------------

def classify_trend(profile: dict, features: list[str]) -> tuple[str, float, str]:
    """
    Returns (trend_tag, max_abs_z, top_driver_label).
    Uses z-scores already in profile dict.
    """
    z_vals: dict[str, float] = {}
    for feat in features:
        label = FEATURE_LABELS[feat]
        z = profile.get(f"{label}_z", 0.0)
        if z is None or (isinstance(z, float) and np.isnan(z)):
            z = 0.0
        z_vals[label] = float(z)

    if not z_vals:
        return "STEADY", 0.0, "none"

    max_abs_z = max(abs(v) for v in z_vals.values())
    top_driver = max(z_vals, key=lambda k: abs(z_vals[k]))
    top_z      = z_vals[top_driver]

    if max_abs_z < TRANSITION_Z_THRESH:
        tag = "STEADY"
    else:
        # Determine direction from usage features
        usage_z_sum = sum(
            z_vals.get(FEATURE_LABELS[f], 0.0)
            for f in USAGE_FEATURES
            if FEATURE_LABELS[f] in z_vals
        )
        if usage_z_sum > 0.5:
            tag = "TRENDING_UP"
        elif usage_z_sum < -0.5:
            tag = "TRENDING_DOWN"
        else:
            tag = "STYLE_SHIFTING"

    return tag, round(max_abs_z, 4), top_driver


# ---------------------------------------------------------------------------
# Step 4 — Cross-check with INT-18 rolling_trends
# ---------------------------------------------------------------------------

INT18_HOT_TAGS  = {"HOT_BREAKOUT", "WARMING"}
INT18_COLD_TAGS = {"COLD_DECLINE", "COOLING"}


def load_int18_tags() -> dict[str, str]:
    """Returns player_name -> trend_tag dict from INT-18 rolling_trends.parquet."""
    if not IN_INT18.exists():
        return {}
    rt = pd.read_parquet(IN_INT18)
    return dict(zip(rt["player_name"], rt["trend_tag"]))


def compare_tags(int29_tag: str, int18_tag: str | None) -> str | None:
    """
    Returns a disagreement description if the two atlases diverge, else None.
    'HOT' in INT-29 = TRENDING_UP.  'HOT' in INT-18 = HOT_BREAKOUT / WARMING.
    """
    if int18_tag is None:
        return None

    int29_hot  = int29_tag == "TRENDING_UP"
    int29_cold = int29_tag == "TRENDING_DOWN"
    int18_hot  = int18_tag in INT18_HOT_TAGS
    int18_cold = int18_tag in INT18_COLD_TAGS

    if int29_hot and int18_cold:
        return f"INT-29=HOT vs INT-18={int18_tag} — decay sees recent surge, calendar window sees decline"
    if int29_cold and int18_hot:
        return f"INT-29=COLD vs INT-18={int18_tag} — decay sees recent drop, calendar window still shows hot"
    if int29_tag in ("TRENDING_UP", "TRENDING_DOWN") and int18_tag == "STEADY":
        return f"INT-29={int29_tag} vs INT-18=STEADY — decay caught a shift, 30-day window averaged it out"
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(half_life: float = HALF_LIFE) -> None:
    print(f"[INT-29] Loading CV per-game data...")
    df = load_data()
    print(f"  Rows loaded: {len(df):,} | Named players: {df['_player_key'].nunique()}")

    dataset_stds = compute_dataset_stds(df)
    int18_tags   = load_int18_tags()

    # Filter to players with >= MIN_GAMES
    counts = df.groupby("_player_key").size()
    qualified_keys = counts[counts >= MIN_GAMES].index.tolist()
    print(f"  Players with >= {MIN_GAMES} CV games: {len(qualified_keys)}")

    df_qual = df[df["_player_key"].isin(qualified_keys)].copy()

    # Build profiles
    records = []
    for pkey, grp in df_qual.groupby("_player_key"):
        grp_sorted = grp.sort_values("game_date", ascending=False).reset_index(drop=True)
        player_name = grp_sorted["player_name"].iloc[0]

        # Resolve nba_player_id
        nba_ids = grp_sorted["nba_player_id"].dropna()
        nba_player_id = int(nba_ids.iloc[0]) if len(nba_ids) > 0 else None

        profile = compute_player_profile(grp_sorted, dataset_stds)
        tag, max_z, top_driver = classify_trend(profile, FEATURES)

        # INT-18 cross-check
        int18_tag = int18_tags.get(player_name)
        disagreement = compare_tags(tag, int18_tag)

        record = {
            "player_id": nba_player_id,
            "player_name": player_name,
            "_player_key": pkey,
            "trend_tag": tag,
            "max_abs_z": max_z,
            "top_driver": top_driver,
            "int18_tag": int18_tag,
            "int18_disagreement": disagreement,
            **profile,
        }
        records.append(record)

    profiles_df = pd.DataFrame(records)
    profiles_df = profiles_df.sort_values("max_abs_z", ascending=False).reset_index(drop=True)

    # Save parquet
    profiles_df.to_parquet(OUT_PROFILES, index=False)
    print(f"[INT-29] Saved {len(profiles_df)} player profiles -> {OUT_PROFILES}")

    # ---------------------------------------------------------------------------
    # Build form_vs_baseline_deltas.json (compact summary)
    # ---------------------------------------------------------------------------
    deltas_out: dict = {
        "generated": TODAY,
        "half_life_games": half_life,
        "n_players_profiled": len(profiles_df),
        "n_in_transition": int((profiles_df["trend_tag"] != "STEADY").sum()),
        "players": [],
    }

    for _, row in profiles_df.iterrows():
        player_entry: dict = {
            "player_name": row["player_name"],
            "player_id": int(row["player_id"]) if row["player_id"] and not np.isnan(float(row["player_id"] if row["player_id"] else 0)) else None,
            "n_cv_games": int(row["n_cv_games"]),
            "latest_game_date": row["latest_game_date"],
            "trend_tag": row["trend_tag"],
            "max_abs_z": float(row["max_abs_z"]),
            "top_driver": row["top_driver"],
            "int18_tag": row.get("int18_tag"),
            "int18_disagreement": row.get("int18_disagreement"),
            "features": {},
        }
        for feat in FEATURES:
            label = FEATURE_LABELS[feat]
            player_entry["features"][label] = {
                "current_form": _safe_float(row.get(f"{label}_current_form")),
                "season_baseline": _safe_float(row.get(f"{label}_season_baseline")),
                "delta": _safe_float(row.get(f"{label}_delta")),
                "z": _safe_float(row.get(f"{label}_z")),
            }
        deltas_out["players"].append(player_entry)

    with open(OUT_DELTAS, "w", encoding="utf-8") as f:
        json.dump(deltas_out, f, indent=2, ensure_ascii=False)
    print(f"[INT-29] Saved deltas -> {OUT_DELTAS}")

    # ---------------------------------------------------------------------------
    # Build Atlas markdown
    # ---------------------------------------------------------------------------
    _write_atlas(profiles_df, deltas_out)
    print(f"[INT-29] Atlas written -> {ATLAS_MD}")

    # ---------------------------------------------------------------------------
    # Console report
    # ---------------------------------------------------------------------------
    _print_report(profiles_df)


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else round(f, 6)
    except (TypeError, ValueError):
        return None


def _write_atlas(df: pd.DataFrame, deltas: dict) -> None:
    n_total      = deltas["n_players_profiled"]
    n_transition = deltas["n_in_transition"]
    n_up   = int((df["trend_tag"] == "TRENDING_UP").sum())
    n_down = int((df["trend_tag"] == "TRENDING_DOWN").sum())
    n_shift = int((df["trend_tag"] == "STYLE_SHIFTING").sum())
    n_steady = int((df["trend_tag"] == "STEADY").sum())

    up_rows   = df[df["trend_tag"] == "TRENDING_UP"].head(10)
    down_rows = df[df["trend_tag"] == "TRENDING_DOWN"].head(10)
    disagree  = df[df["int18_disagreement"].notna()].head(5)

    lines = [
        "# Current Form Atlas (Exponential-Decay Weighted CV Profiles)",
        "",
        "## Methodology",
        f"Half-life = {HALF_LIFE} games (tunable via --half-life).  ",
        "Most recent game weight = 1.0; 5 games ago weight = 0.5; 10 games ago weight = 0.25.  ",
        f"Season baseline = equal-weighted mean across all games (same as INT-1).  ",
        f"Delta = current_form - season_baseline.  ",
        f"Z = delta / dataset_population_std (cross-player comparability).  ",
        f"'In transition' = max |z| > {TRANSITION_Z_THRESH} on any feature (calibrated to this dataset's z range [0, ~0.9]).",
        "",
        "## Coverage",
        f"- Players with >= {MIN_GAMES} CV games: **{n_total}**",
        f"- 'In transition' (max |z| > {TRANSITION_Z_THRESH}): **{n_transition}**",
        f"- TRENDING_UP: {n_up} | TRENDING_DOWN: {n_down} | STYLE_SHIFTING: {n_shift} | STEADY: {n_steady}",
        "",
        "## Top 10 Trending Up (current form > season baseline)",
        "| player | top feature | delta | z | n_games | latest_game |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in up_rows.iterrows():
        label = r["top_driver"]
        feat_name = next((f for f in FEATURES if FEATURE_LABELS[f] == label), None)
        delta = _safe_float(r.get(f"{label}_delta")) or 0.0
        z     = _safe_float(r.get(f"{label}_z")) or 0.0
        lines.append(
            f"| {r['player_name']} | {label} | {delta:+.4f} | {z:+.2f}z "
            f"| {int(r['n_cv_games'])} | {r['latest_game_date']} |"
        )

    lines += [
        "",
        "## Top 10 Trending Down (current form < season baseline)",
        "| player | top feature | delta | z | n_games | latest_game |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in down_rows.iterrows():
        label = r["top_driver"]
        delta = _safe_float(r.get(f"{label}_delta")) or 0.0
        z     = _safe_float(r.get(f"{label}_z")) or 0.0
        lines.append(
            f"| {r['player_name']} | {label} | {delta:+.4f} | {z:+.2f}z "
            f"| {int(r['n_cv_games'])} | {r['latest_game_date']} |"
        )

    lines += [
        "",
        "## Top 5 Disagreements with INT-18 Rolling 30-Day",
    ]
    if len(disagree) == 0:
        lines.append("*No significant disagreements between INT-29 and INT-18.*")
    else:
        lines.append("| player | INT-29 tag | INT-18 tag | explanation |")
        lines.append("|---|---|---|---|")
        for _, r in disagree.iterrows():
            lines.append(
                f"| {r['player_name']} | {r['trend_tag']} | {r.get('int18_tag','N/A')} "
                f"| {r.get('int18_disagreement','')} |"
            )

    lines += [
        "",
        "## How to Use",
        "- **Pre-bet:** replace INT-1 season_baseline with `current_form` value when adjusting player props",
        "- **Cross-check:** combine with INT-18 trend tag for confirmation (both agree = stronger signal)",
        "- **In-transition players:** highest alpha — book lines still priced on season mean",
        "- **TRENDING_UP + INT-18 HOT:** lean OVER on usage/scoring props",
        "- **TRENDING_DOWN + INT-18 COLD:** lean UNDER or fade",
        "- **STYLE_SHIFTING:** role change, not volume change — look at specific feature direction",
        "",
        "## Honest Caveats",
        f"- Half-life {HALF_LIFE} is heuristic — {HALF_LIFE-2} games would weight recency harder, "
        f"{HALF_LIFE+2} games would be smoother",
        "- Players with mostly old CV games (no recent coverage) have decay weights ~ equal weights -> STEADY",
        "- Small game counts (5-7) make decay weights coarse — treat STEADY from those as 'unknown'",
        "- ISSUE-022: `defender_dist` has a sentinel=200ft bug — treat those z-scores as directional only",
        "- All CV data is 2024-25 and 2025-26 seasons only",
        "",
        "---",
        f"*Generated {TODAY} by INT-29: `scripts/build_current_form.py`*",
        "*Linked: [[Current_Form_Atlas]] | [[Rolling_Trends_Atlas]] | [[Player_Atlas]] | [[Betting_Signal_Ranking]]*",
    ]

    ATLAS_MD.write_text("\n".join(lines), encoding="utf-8")


def _print_report(df: pd.DataFrame) -> None:
    n_total = len(df)
    n_trans = int((df["trend_tag"] != "STEADY").sum())
    n_up    = int((df["trend_tag"] == "TRENDING_UP").sum())
    n_down  = int((df["trend_tag"] == "TRENDING_DOWN").sum())
    n_shift = int((df["trend_tag"] == "STYLE_SHIFTING").sum())

    print()
    print("=" * 70)
    print("  INT-29 Current Form Profiles — Final Report")
    print("=" * 70)
    print()
    print("### Coverage")
    print(f"  Players profiled:     {n_total}")
    print(f"  'In transition':      {n_trans}")
    print(f"  TRENDING_UP:          {n_up}")
    print(f"  TRENDING_DOWN:        {n_down}")
    print(f"  STYLE_SHIFTING:       {n_shift}")
    print(f"  STEADY:               {n_total - n_trans}")
    print()

    print("### Top 5 Trending Up")
    up = df[df["trend_tag"] == "TRENDING_UP"].head(5)
    if len(up) == 0:
        print("  (none)")
    else:
        print(f"  {'Player':<30} {'Feature':<20} {'Delta':>10}  {'z':>7}")
        print(f"  {'-'*30} {'-'*20} {'-'*10}  {'-'*7}")
        for _, r in up.iterrows():
            label = r["top_driver"]
            d = _safe_float(r.get(f"{label}_delta")) or 0.0
            z = _safe_float(r.get(f"{label}_z")) or 0.0
            print(f"  {r['player_name']:<30} {label:<20} {d:+10.4f}  {z:+7.2f}z")
    print()

    print("### Top 5 Trending Down")
    dn = df[df["trend_tag"] == "TRENDING_DOWN"].head(5)
    if len(dn) == 0:
        print("  (none)")
    else:
        print(f"  {'Player':<30} {'Feature':<20} {'Delta':>10}  {'z':>7}")
        print(f"  {'-'*30} {'-'*20} {'-'*10}  {'-'*7}")
        for _, r in dn.iterrows():
            label = r["top_driver"]
            d = _safe_float(r.get(f"{label}_delta")) or 0.0
            z = _safe_float(r.get(f"{label}_z")) or 0.0
            print(f"  {r['player_name']:<30} {label:<20} {d:+10.4f}  {z:+7.2f}z")
    print()

    print("### Disagreements with INT-18")
    dis = df[df["int18_disagreement"].notna()]
    if len(dis) == 0:
        print("  (no disagreements - INT-29 and INT-18 are consistent)")
    else:
        for _, r in dis.head(5).iterrows():
            print(f"  {r['player_name']}: {r['int18_disagreement']}")
    print()

    print("### Files")
    print(f"  scripts/build_current_form.py")
    print(f"  data/intelligence/current_form_profiles.parquet")
    print(f"  data/intelligence/form_vs_baseline_deltas.json")
    print(f"  vault/Intelligence/Current_Form_Atlas.md")
    print()

    print("### How to Use")
    print("  - Pre-bet: use current_form values instead of INT-1 season_mean")
    print("  - Cross-check with INT-18 for confirmation")
    print("  - Strongest signal: both INT-18 and INT-29 agree (HOT in 18 AND TRENDING_UP in 29)")
    print()

    print("### Honest Caveats")
    print(f"  - Half-life={HALF_LIFE} is heuristic (tunable: --half-life N)")
    print("  - Players with old-only CV data: decay ~ equal -> STEADY (no recent data, not truly flat)")
    print("  - Small n (5-7 games): coarse decay weights, treat z<0.5 as directional only")
    print(f"  - Threshold {TRANSITION_Z_THRESH} is calibrated to this dataset's z range [0, ~0.9]")
    print("  - INT-18 uses calendar windows; INT-29 uses game-count decay -- compare both")
    print("=" * 70)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="INT-29: Exponential-decay current form CV profiles")
    parser.add_argument("--half-life", type=float, default=HALF_LIFE,
                        help=f"Half-life in games (default: {HALF_LIFE})")
    args = parser.parse_args()
    main(half_life=args.half_life)
