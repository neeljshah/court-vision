"""Wave 1 builder: per-player shot-clock buckets and leverage/game-script scoring signals.

Sources (all official NBA data — no thin CV broadcast):
  data/cache/atlas_player_shot_clock_scoring.parquet  — late-clock shots/pg + late_clock_rate + ts%
  data/cache/atlas_player_clutch_scoring.parquet      — clutch pts/pg, shots/pg, plus-minus, pts/36
  data/cache/atlas_player_score_margin_splits.parquet — leading/tied/trailing pts/fg splits
  data/cache/clutch_profiles_2025-26.parquet          — official clutch agg: gp/min/pts/fg%/pm/p36
  data/cache/pbp_possession_features.parquet          — per-game late_clock_shots & clutch counts
  data/cache/quarter_features.parquet                 — Q1-Q4 pts shape, Q4-share, 2H-share

Leak rule: SEASON-AGGREGATE. All source atlases represent the full 2025-26 (or prior) season agg;
pbp features are shifted(1) at consumer time — here we only build aggs for scouting. Label:
  leak_rule = "season-agg"  (consumer A/C scouting; do NOT use as a point-model feature without
  a proper shift-by-game-date as-of wrapper).

Key signals emitted (one row per player_id):
  Shot-clock:
    late_clock_shots_pg     — late-clock (<7s) shot attempts per game (pbp-derived season avg)
    late_clock_rate         — late_clock_shots / total_poss proxy
    late_clock_ts_pct       — true shooting pct (overall, proxy for shot quality)
    late_clock_efg_pct      — eFG% overall (proxy)

  Clutch (last 5 min, within 5 pts):
    clutch_pts_pg           — clutch pts per clutch game (clutch_profiles 2025-26)
    clutch_fg_pct, clutch_fg3_pct, clutch_ft_pct
    clutch_pts_per36        — pace-normalised clutch scoring rate
    clutch_plus_minus       — net points per clutch game
    clutch_shots_pg         — clutch shot attempts per game (pbp-derived)
    clutch_pts_pg_pbp       — clutch pts per game (pbp-derived; cross-check)
    clutch_and1_pg          — and-1 completions per game

  Leverage splits (leading / tied / trailing by >= 5 pts):
    lead_pts_pg, lead_efg_pct, lead_fga_pg    — performance when team is ahead
    tied_pts_pg, tied_efg_pct, tied_fga_pg
    trail_pts_pg, trail_efg_pct, trail_fga_pg
    lead_vs_tied_pts_pm_delta  — pts/min delta vs tied state (positive = more pts/min when leading)
    trail_vs_tied_pts_pm_delta — pts/min delta vs tied state (positive = more pts/min when trailing)

  Quarter shape (from quarter_features):
    q1_pts_pg, q2_pts_pg, q3_pts_pg, q4_pts_pg
    q4_share_pts             — Q4 pts as fraction of total pts (Q4 clutch weight)
    second_half_min_share    — fraction of team-mins in 2H (playing time trend)

  python scripts/signals/build_shotclock_leverage.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "data", "cache", "signals")
OUT = os.path.join(OUT_DIR, "shotclock_leverage.parquet")

# Source paths
P_SC   = os.path.join(ROOT, "data", "cache", "atlas_player_shot_clock_scoring.parquet")
P_CL   = os.path.join(ROOT, "data", "cache", "atlas_player_clutch_scoring.parquet")
P_SMS  = os.path.join(ROOT, "data", "cache", "atlas_player_score_margin_splits.parquet")
P_CLUT = os.path.join(ROOT, "data", "cache", "clutch_profiles_2025-26.parquet")
P_PBP  = os.path.join(ROOT, "data", "cache", "pbp_possession_features.parquet")
P_QF   = os.path.join(ROOT, "data", "cache", "quarter_features.parquet")
P_PROF = os.path.join(ROOT, "data", "cache", "player_profile_features.parquet")

MIN_GAMES_PBP = 10      # min games for pbp late-clock agg
MIN_GAMES_CLUTCH = 5    # min clutch games for official clutch agg


def _safe_json(x) -> dict:
    """Parse JSON blob from atlas column safely."""
    if isinstance(x, str):
        try:
            return json.loads(x)
        except (json.JSONDecodeError, TypeError):
            return {}
    if isinstance(x, dict):
        return x
    return {}


# --------------------------------------------------------------------------
# 1. Shot-clock signals from atlas_player_shot_clock_scoring
# --------------------------------------------------------------------------
def _build_shot_clock(df_sc: pd.DataFrame) -> pd.DataFrame:
    """Extract late-clock metrics; early/mid defer due to pkey mismatch noted in atlas."""
    rows = []
    for _, row in df_sc.iterrows():
        late = _safe_json(row.get("late"))
        qual = _safe_json(row.get("shot_quality"))
        rows.append({
            "player_id": int(row.player_id),
            "late_clock_shots_pg":  late.get("shots_pg"),
            "late_clock_rate":      late.get("late_clock_rate"),
            "late_clock_ts_pct":    qual.get("ts_pct"),
            "late_clock_efg_pct":   qual.get("efg_pct"),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 2. Clutch signals from atlas_player_clutch_scoring
# --------------------------------------------------------------------------
def _build_clutch_atlas(df_cl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df_cl.iterrows():
        pbp  = _safe_json(row.get("pbp_clutch"))
        rows.append({
            "player_id":         int(row.player_id),
            "clutch_shots_pg":   pbp.get("clutch_shots_pg"),
            "clutch_pts_pg_pbp": pbp.get("clutch_pts_pg"),
            "clutch_and1_pg":    pbp.get("and1_pg"),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 3. Official clutch profile (2025-26) — flat columns
# --------------------------------------------------------------------------
def _build_clutch_official(df_clut: pd.DataFrame) -> pd.DataFrame:
    df = df_clut[df_clut.clutch_gp >= MIN_GAMES_CLUTCH].copy()
    return df[["player_id", "clutch_gp", "clutch_min",
               "clutch_pts", "clutch_fg_pct", "clutch_fg3_pct",
               "clutch_ft_pct", "clutch_plus_minus", "clutch_pts_per36"]].copy()


# --------------------------------------------------------------------------
# 4. Score-margin leverage splits from atlas
# --------------------------------------------------------------------------
def _build_margin_splits(df_sms: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df_sms.iterrows():
        lead  = _safe_json(row.get("leading"))
        tied  = _safe_json(row.get("tied"))
        trail = _safe_json(row.get("trailing"))
        lead_pts  = lead.get("pts_pg")
        tied_pts  = tied.get("pts_pg")
        trail_pts = trail.get("pts_pg")
        lead_min  = lead.get("min_pg")
        tied_min  = tied.get("min_pg")
        trail_min = trail.get("min_pg")
        # Per-minute rates remove exposure confound (tied states accumulate far more min
        # than blowout states, so raw pts_pg deltas skew negative in both directions).
        def _pm(pts, mins): return pts / mins if (pts and mins and mins > 0) else None
        lead_pm, tied_pm, trail_pm = _pm(lead_pts, lead_min), _pm(tied_pts, tied_min), _pm(trail_pts, trail_min)
        lead_vs_tied  = (lead_pm  - tied_pm) if (lead_pm  is not None and tied_pm is not None) else None
        trail_vs_tied = (trail_pm - tied_pm) if (trail_pm is not None and tied_pm is not None) else None
        rows.append({
            "player_id":           int(row.player_id),
            "lead_pts_pg":         lead_pts,
            "lead_efg_pct":        lead.get("efg_pct"),
            "lead_fga_pg":         lead.get("fga_pg"),
            "lead_min_pg":         lead_min,
            "lead_n_games":        lead.get("n_games"),
            "tied_pts_pg":         tied_pts,
            "tied_efg_pct":        tied.get("efg_pct"),
            "tied_fga_pg":         tied.get("fga_pg"),
            "tied_min_pg":         tied_min,
            "tied_n_games":        tied.get("n_games"),
            "trail_pts_pg":        trail_pts,
            "trail_efg_pct":       trail.get("efg_pct"),
            "trail_fga_pg":        trail.get("fga_pg"),
            "trail_min_pg":        trail_min,
            "trail_n_games":       trail.get("n_games"),
            "lead_vs_tied_pts_pm_delta":  lead_vs_tied,
            "trail_vs_tied_pts_pm_delta": trail_vs_tied,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 5. PBP late-clock season aggregate
# --------------------------------------------------------------------------
def _to_season(game_date: pd.Series) -> pd.Series:
    dt = pd.to_datetime(game_date)
    year = dt.dt.year
    month = dt.dt.month
    return year.where(month >= 10, year - 1).astype(str) + "-" + \
        (year + 1).where(month >= 10, year).astype(str).str[-2:]


def _build_pbp_late_clock(df_pbp: pd.DataFrame) -> pd.DataFrame:
    """Season aggregate of late-clock shots and clutch counts from per-game PBP.

    Picks the most recent season where >= MIN_GAMES_PBP seasons exist for enough players.
    PBP coverage is thin for 2024-25 and 2025-26 (only ~48 and ~9 games respectively);
    falls back to 2023-24 which has 1 230 games and 430+ eligible players.
    """
    df = df_pbp.copy()
    df["season"] = _to_season(df.game_date)
    # Find best season: most recent where at least 100 players have >= MIN_GAMES_PBP
    seasons_sorted = sorted(df.season.unique(), reverse=True)
    chosen_season = None
    for s in seasons_sorted:
        g = df[df.season == s].groupby("player_id")["game_id"].nunique()
        if (g >= MIN_GAMES_PBP).sum() >= 100:
            chosen_season = s
            break
    if chosen_season is None:
        # Nothing qualifies; return empty frame with correct columns
        return pd.DataFrame(columns=["player_id", "pbp_n_games", "pbp_season",
                                     "pbp_late_shots_pg", "pbp_clutch_shots_pg",
                                     "pbp_clutch_pts_pg", "pbp_and1_pg"])
    df_lat = df[df.season == chosen_season]
    agg = df_lat.groupby("player_id").agg(
        pbp_n_games=("game_id", "nunique"),
        pbp_late_shots_total=("pbp_late_clock_shots", "sum"),
        pbp_clutch_shots_total=("pbp_clutch_shots_attempted", "sum"),
        pbp_clutch_pts_total=("pbp_clutch_pts_scored", "sum"),
        pbp_and1_total=("pbp_and1_count", "sum"),
    ).reset_index()
    # Filter minimum games
    agg = agg[agg.pbp_n_games >= MIN_GAMES_PBP].copy()
    agg["pbp_late_shots_pg"]   = agg.pbp_late_shots_total   / agg.pbp_n_games
    agg["pbp_clutch_shots_pg"] = agg.pbp_clutch_shots_total / agg.pbp_n_games
    agg["pbp_clutch_pts_pg"]   = agg.pbp_clutch_pts_total   / agg.pbp_n_games
    agg["pbp_and1_pg"]         = agg.pbp_and1_total          / agg.pbp_n_games
    agg["pbp_season"]          = chosen_season
    return agg[["player_id", "pbp_n_games", "pbp_season",
                "pbp_late_shots_pg", "pbp_clutch_shots_pg",
                "pbp_clutch_pts_pg", "pbp_and1_pg"]]


# --------------------------------------------------------------------------
# 6. Quarter shape from quarter_features
# --------------------------------------------------------------------------
def _build_quarter_shape(df_qf: pd.DataFrame) -> pd.DataFrame:
    """Season aggregate of Q1-Q4 pts and Q4 weight. Use most recent season."""
    latest = df_qf.season.max()
    df_lat = df_qf[df_qf.season == latest].copy()
    # Convert pts cols to float (int32 in source)
    for c in ["q1_pts", "q2_pts", "q3_pts", "q4_pts"]:
        df_lat[c] = df_lat[c].astype(float)
    agg = df_lat.groupby("player_id").agg(
        qs_n_games=("game_id", "nunique"),
        q1_pts_pg=("q1_pts", "mean"),
        q2_pts_pg=("q2_pts", "mean"),
        q3_pts_pg=("q3_pts", "mean"),
        q4_pts_pg=("q4_pts", "mean"),
        q4_share_pts=("fourth_quarter_share_pts", "mean"),
        second_half_min_share=("second_half_share_min", "mean"),
    ).reset_index()
    # Q4 scoring tilt: positive = concentrates in Q4
    total_pg = (agg.q1_pts_pg + agg.q2_pts_pg + agg.q3_pts_pg + agg.q4_pts_pg)
    agg["q4_pts_tilt"] = (agg.q4_pts_pg / total_pg.replace(0, np.nan)).round(3)
    agg["qs_season"]   = latest
    return agg


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build() -> pd.DataFrame:
    # Load all sources
    df_sc   = pd.read_parquet(P_SC)
    df_cl   = pd.read_parquet(P_CL)
    df_sms  = pd.read_parquet(P_SMS)
    df_clut = pd.read_parquet(P_CLUT)
    df_pbp  = pd.read_parquet(P_PBP)
    df_qf   = pd.read_parquet(P_QF)
    df_prof = pd.read_parquet(P_PROF)[["player_id", "player_name"]]

    # Build each component
    sc   = _build_shot_clock(df_sc)
    cla  = _build_clutch_atlas(df_cl)
    cof  = _build_clutch_official(df_clut)
    sms  = _build_margin_splits(df_sms)
    pbp  = _build_pbp_late_clock(df_pbp)
    qsh  = _build_quarter_shape(df_qf)

    # Start from the union of all player_ids that appear in any source
    all_pids = pd.DataFrame({
        "player_id": list(set(
            sc.player_id.tolist() +
            cla.player_id.tolist() +
            sms.player_id.tolist()
        ))
    })

    # Left-merge all components
    out = all_pids.merge(df_prof,  on="player_id", how="left")
    out = out.merge(sc,   on="player_id", how="left")
    out = out.merge(cla,  on="player_id", how="left")
    out = out.merge(cof,  on="player_id", how="left")
    out = out.merge(sms,  on="player_id", how="left")
    out = out.merge(pbp,  on="player_id", how="left")
    out = out.merge(qsh,  on="player_id", how="left")

    # Sanity: row count should be close to #unique players, not a Cartesian blowup
    n_before = len(all_pids)
    assert len(out) == n_before, (
        f"Row count changed after merge: {n_before} -> {len(out)} "
        "(possible Cartesian join on player_id — check duplicate keys in source frames)"
    )

    # Round numeric columns
    float_cols = out.select_dtypes("float64").columns
    out[float_cols] = out[float_cols].round(4)

    # Metadata
    out["signal_domain"]  = "shotclock_leverage"
    out["leak_rule"]      = "season-agg"
    out["as_of"]          = "2026-06-06"

    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)

    n_players = out.player_id.nunique()
    print(f"DONE: shotclock_leverage signals -> {OUT}")
    print(f"  rows={len(out)}  distinct players={n_players}")
    print(f"  columns={len(out.columns)}: {list(out.columns)}")
    print()

    # Sample 3 rows
    print("--- 3 sample rows ---")
    sample_cols = [
        "player_id", "player_name",
        "late_clock_shots_pg", "late_clock_rate", "late_clock_ts_pct",
        "clutch_pts_pg", "clutch_plus_minus", "clutch_pts_per36",
        "lead_pts_pg", "tied_pts_pg", "trail_pts_pg",
        "trail_vs_tied_pts_pm_delta",
        "q4_pts_pg", "q4_pts_tilt",
    ]
    avail = [c for c in sample_cols if c in out.columns]
    print(out[avail].dropna(subset=["player_name"]).head(3).to_string(index=False))
    print()

    # Sanity ranking: top late-clock users (late_clock_shots_pg) vs top clutch scorers
    print("--- Sanity: Top 8 late-clock shot-takers (late_clock_shots_pg) ---")
    lc = out[out.late_clock_shots_pg.notna()].nlargest(8, "late_clock_shots_pg")
    for r in lc.itertuples(index=False):
        name  = getattr(r, "player_name", r.player_id)
        lc_pg = getattr(r, "late_clock_shots_pg", None)
        lcr   = getattr(r, "late_clock_rate", None)
        print(f"  {str(name):25s}  late_shots_pg={lc_pg:.2f}  late_clock_rate={lcr:.3f}" if lcr else
              f"  {str(name):25s}  late_shots_pg={lc_pg:.2f}")
    print()

    print("--- Sanity: Top 8 clutch scorers (clutch_pts_per36) ---")
    cl = out[out.clutch_pts_per36.notna()].nlargest(8, "clutch_pts_per36")
    for r in cl.itertuples(index=False):
        name = str(getattr(r, "player_name", r.player_id)).encode("ascii", errors="replace").decode()
        p36  = getattr(r, "clutch_pts_per36", None)
        pm   = getattr(r, "clutch_plus_minus", None)
        print(f"  {name:25s}  clutch_p36={p36:.1f}  clutch_pm={pm:.1f}" if (pm is not None) else
              f"  {name:25s}  clutch_p36={p36:.1f}")
    print()

    print("--- Sanity: Top 8 trailing elevators (trail_vs_tied_pts_pm_delta) ---")
    tr = out[out.trail_vs_tied_pts_pm_delta.notna()].nlargest(8, "trail_vs_tied_pts_pm_delta")
    for r in tr.itertuples(index=False):
        name   = getattr(r, "player_name", r.player_id)
        delta  = getattr(r, "trail_vs_tied_pts_pm_delta", None)
        trail  = getattr(r, "trail_pts_pg", None)
        tied   = getattr(r, "tied_pts_pg", None)
        print(f"  {str(name):25s}  trail_pm_delta={delta:.3f}  trail_pts={trail:.2f}  tied_pts={tied:.2f}")


if __name__ == "__main__":
    main()
