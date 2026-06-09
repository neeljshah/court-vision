"""Wave 1 builder: per-player SCORING PROFILE signal set.

Sources: shotloc_regular_season_*.parquet, player_breakdown_features.parquet,
player_tracking_features.parquet, synergy_ppp_features.parquet,
atlas_player_ft_profile.parquet, atlas_player_scoring_creation.parquet

Volume gates (applied in builder so parquet is clean):
  - Zone shot-share / zone FG%: NaN when shotloc_total_fga < 50
  - ft_pct / pct_pts_from_ft:   NaN when fta_pg < 1.0
leak_rule = season-agg. Output: data/cache/signals/scoring_profile.parquet
Usage:  python scripts/signals/build_scoring_profile.py
"""
from __future__ import annotations

import json
import os
import glob

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "data", "cache")
OUT_DIR = os.path.join(CACHE, "signals")
OUT = os.path.join(OUT_DIR, "scoring_profile.parquet")

# --- helpers ----------------------------------------------------------------

def _pct(num, den):
    """Safe percentage; returns NaN if denominator is 0 or NaN."""
    try:
        return float(num) / float(den) if (den and not np.isnan(den) and den != 0) else np.nan
    except Exception:
        return np.nan


# --- source loaders ---------------------------------------------------------

_SHOTLOC_MIN_FGA = 50   # season FGA floor for zone-share / zone-FG% signals
_FT_MIN_FTA_PG   = 1.0  # FTA/game floor for ft_pct / pct_pts_from_ft signals


def _load_shotloc() -> pd.DataFrame:
    """Load most recent shotloc snapshot; compute per-zone FGA, FGM, FG%.

    Volume gate (<_SHOTLOC_MIN_FGA season FGA): zone_shot_share, zone_fg_pct,
    corner3_vs_above3_ratio → NaN.  Raw counts always written.
    shotloc_total_fga kept as auditable coverage column.
    """
    pattern = os.path.join(CACHE, "cv_fix", "shotloc_regular_season_*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])  # most recent cumulative snapshot

    # Zone column pairs (FGM, FGA) from the actual schema
    zones = {
        "rim":        ("Restricted Area|FGM",          "Restricted Area|FGA"),
        "paint_nonra": ("In The Paint (Non-RA)|FGM",   "In The Paint (Non-RA)|FGA"),
        "midrange":   ("Mid-Range|FGM",                "Mid-Range|FGA"),
        "corner3":    ("Corner 3|FGM",                 "Corner 3|FGA"),
        "above3":     ("Above the Break 3|FGM",        "Above the Break 3|FGA"),
    }
    rows = []
    for _, r in df.iterrows():
        total_fga = sum(
            float(r.get(v[1], 0) or 0) for v in zones.values()
        )
        sufficient_vol = total_fga >= _SHOTLOC_MIN_FGA
        row = {"player_id": int(r["PLAYER_ID"]), "player_name": r["PLAYER_NAME"],
               "shotloc_total_fga": total_fga}   # audit column — never NaN'd
        for zone, (fgm_col, fga_col) in zones.items():
            fgm = float(r.get(fgm_col, 0) or 0)
            fga = float(r.get(fga_col, 0) or 0)
            row[f"shotloc_{zone}_fgm"] = fgm
            row[f"shotloc_{zone}_fga"] = fga
            row[f"shotloc_{zone}_fg_pct"] = (
                round(_pct(fgm, fga), 3) if sufficient_vol else np.nan
            )
            row[f"shotloc_{zone}_shot_share"] = (
                round(_pct(fga, total_fga), 3) if (sufficient_vol and total_fga) else np.nan
            )
        atb3_fga = float(r.get("Above the Break 3|FGA", 0) or 0)
        c3_fga   = float(r.get("Corner 3|FGA", 0) or 0)
        total3   = atb3_fga + c3_fga
        row["shotloc_corner3_vs_above3_ratio"] = (
            round(_pct(c3_fga, total3), 3) if (sufficient_vol and total3) else np.nan
        )
        rows.append(row)

    out = pd.DataFrame(rows)
    assert out.player_id.nunique() == len(out), "shotloc: dup player_ids detected"
    return out


def _load_breakdown() -> pd.DataFrame:
    """Load player_breakdown_features (2024-25): assisted/self-created + zone pts shares."""
    path = os.path.join(CACHE, "player_breakdown_features.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    # Keep the most recent season per player (already only 2024-25 in this file)
    keep = [
        "player_id",
        "scoring_pct_pts_3pt",
        "scoring_pct_pts_paint",
        "scoring_pct_pts_ft",
        "scoring_pct_pts_mid_range",
        "scoring_pct_pts_fast_break",
        "scoring_pct_ast_2pm",
        "scoring_pct_uast_2pm",
        "scoring_pct_ast_3pm",
        "scoring_pct_uast_3pm",
        "misc_pts_paint",
        "misc_pts_fast_break",
        "misc_pts_2nd_chance",
    ]
    out = df[keep].drop_duplicates("player_id").copy()
    # Two-pass rename → clean "bkdn_" prefix (avoid double-prefix from partial names)
    out = out.rename(columns={c: f"bkdn_{c[c.index('_')+1:]}" if c != "player_id" else c
                               for c in out.columns})
    out = out.rename(columns={c: f"bkdn_{c}" for c in out.columns if c != "player_id"})
    out.columns = [c.replace("bkdn_bkdn_", "bkdn_") for c in out.columns]
    assert out.player_id.nunique() == len(out), "breakdown: dup player_ids"
    return out


def _load_tracking() -> pd.DataFrame:
    """Load player_tracking_features: catch-and-shoot + drives (most recent season)."""
    path = os.path.join(CACHE, "player_tracking_features.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    season_order = sorted(df.season.unique(), reverse=True)
    best_season = season_order[0] if season_order else None
    df = df[df.season == best_season].copy()

    keep = [
        "player_id",
        "catch_shoot_fgm", "catch_shoot_fga", "catch_shoot_fg_pct",
        "catch_shoot_fg3m", "catch_shoot_fg3a", "catch_shoot_fg3_pct",
        "catch_shoot_efg_pct",
        "drives_per_g", "drive_fg_pct", "drive_pts_per_drive",
        "drive_ast_per_drive", "drive_pts_pct",
        "passes_made_per_g", "potential_ast", "ast_points_created",
        "secondary_ast",
    ]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].drop_duplicates("player_id").copy()
    rename = {c: f"trk_{c}" for c in out.columns if c != "player_id"}
    out = out.rename(columns=rename)
    assert out.player_id.nunique() == len(out), "tracking: dup player_ids"
    return out


def _load_synergy() -> pd.DataFrame:
    """Load synergy_ppp_features: most recent season PPP by play type."""
    path = os.path.join(CACHE, "synergy_ppp_features.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    season_order = sorted(df.season.unique(), reverse=True)
    best_season = season_order[0] if season_order else None
    df = df[df.season == best_season].copy()
    out = df.drop(columns=["season"]).drop_duplicates("player_id").copy()
    out = out.rename(columns={c: f"syn_{c}" for c in out.columns if c != "player_id"})
    out.columns = [c.replace("syn_syn_", "syn_") for c in out.columns]
    assert out.player_id.nunique() == len(out), "synergy: dup player_ids"
    return out


def _load_ft_profile() -> pd.DataFrame:
    """Load atlas_player_ft_profile: FTA/36, FT%, pct_pts_from_FT.

    Volume gate (<_FT_MIN_FTA_PG FTA/game): ft_pct, ft_pct_l10, ft_pct_cv,
    pct_pts_from_ft → NaN.  fta_pg / fta_per_36 always written (auditable).
    """
    path = os.path.join(CACHE, "atlas_player_ft_profile.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    rows = []
    for _, r in df.iterrows():
        pid = int(r["player_id"])
        stab = {} if pd.isna(r.get("stability")) else json.loads(r["stability"])
        att  = {} if pd.isna(r.get("attempts"))  else json.loads(r["attempts"])
        fta_pg = att.get("fta_pg")
        ok_ft = (fta_pg is not None
                 and not (isinstance(fta_pg, float) and np.isnan(fta_pg))
                 and fta_pg >= _FT_MIN_FTA_PG)
        rows.append({
            "player_id":       pid,
            "fta_pg":          fta_pg,            # volume — always written
            "fta_per_36":      att.get("fta_per_36"),
            "ft_pct":          stab.get("ft_pct")         if ok_ft else np.nan,
            "ft_pct_l10":      stab.get("ft_pct_l10")     if ok_ft else np.nan,
            "ft_pct_cv":       stab.get("ft_pct_cv")      if ok_ft else np.nan,
            "pct_pts_from_ft": att.get("pct_pts_from_ft") if ok_ft else np.nan,
        })
    out = pd.DataFrame(rows).drop_duplicates("player_id")
    assert out.player_id.nunique() == len(out), "ft_profile: dup player_ids"
    return out


def _load_scoring_creation() -> pd.DataFrame:
    """Load atlas_player_scoring_creation: transition, halfcourt, self-created splits."""
    path = os.path.join(CACHE, "atlas_player_scoring_creation.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    keep = [
        "player_id",
        "unassisted_share_2pm", "assisted_share_2pm",
        "unassisted_share_3pm", "assisted_share_3pm",
        "transition_pts_share", "halfcourt_pts_share",
        "pts_3pt_share", "pts_paint_share", "pts_ft_share", "pts_midrange_share",
        "drives_per_game", "drive_pts_share", "drive_ast_rate",
        "catch_shoot_efg", "catch_shoot_3pa_per_g",
        "transition_poss_per_game",
    ]
    keep = [c for c in keep if c in df.columns]
    out = df[keep].drop_duplicates("player_id").copy()
    rename = {c: f"sc_{c}" for c in out.columns if c != "player_id"}
    out = out.rename(columns=rename)
    assert out.player_id.nunique() == len(out), "scoring_creation: dup player_ids"
    return out


# --- merge ------------------------------------------------------------------

def build() -> pd.DataFrame:
    shotloc   = _load_shotloc()
    breakdown = _load_breakdown()
    tracking  = _load_tracking()
    synergy   = _load_synergy()
    ft        = _load_ft_profile()
    creation  = _load_scoring_creation()

    frames = [f for f in [shotloc, breakdown, tracking, synergy, ft, creation]
              if not f.empty]
    if not frames:
        raise RuntimeError("No source data loaded — check data/cache paths.")
    base = frames[0]
    for f in frames[1:]:
        base = base.merge(f, on="player_id", how="outer")
    assert len(base) <= 1000, f"Row count {len(base)} suspiciously large — join bug?"
    assert len(base) >= 400,  f"Row count {len(base)} suspiciously low — data issue?"
    base = base.sort_values("player_id").reset_index(drop=True)
    base["signal_domain"] = "scoring_profile"
    base["leak_rule"]     = "season-agg"
    base["as_of"]         = "2025-26"

    return base


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    out = build()
    out.to_parquet(OUT, index=False)
    n_rows    = len(out)
    n_players = out.player_id.nunique()
    n_cols    = len(out.columns)
    print(f"DONE: scoring_profile signals -> {OUT}")
    print(f"  rows={n_rows}  distinct players={n_players}  columns={n_cols}")
    print()
    print("=== 3 sample rows (key signals) ===")
    cols_show = [c for c in [
        "player_id", "player_name",
        "shotloc_rim_fg_pct", "shotloc_corner3_shot_share",
        "ft_pct", "fta_per_36", "pct_pts_from_ft",
        "sc_transition_pts_share", "sc_unassisted_share_2pm",
        "trk_catch_shoot_fg_pct", "trk_drives_per_g",
        "syn_pnr_bh_ppp", "syn_spotup_ppp",
    ] if c in out.columns]
    print(out[cols_show].head(3).to_string(index=False))
    print()

    def _prt(rows_df, label):
        print(f"=== Sanity: {label} ===")
        for r in rows_df.itertuples(index=False):
            vals = {f: getattr(r, f, None) for f in rows_df.columns if f != "player_name"}
            nm = str(getattr(r, "player_name", "")).encode("ascii", "replace").decode("ascii") or str(vals.get("player_id", ""))
            kv = "  ".join(f"{k}={v:.3f}" for k, v in vals.items()
                           if k != "player_id" and v == v and v is not None)
            print(f"  {nm:<26s}  {kv}")

    rim_cols = ["player_name", "player_id", "shotloc_rim_shot_share", "shotloc_rim_fg_pct"]
    _prt(out[[c for c in rim_cols if c in out.columns]]
         .dropna(subset=["shotloc_rim_shot_share"]).nlargest(8, "shotloc_rim_shot_share"),
         "top rim scorers (shot share)")
    print()
    cs_cols = ["player_name", "player_id", "trk_catch_shoot_fga", "trk_catch_shoot_fg_pct"]
    _prt(out[[c for c in cs_cols if c in out.columns]]
         .dropna(subset=["trk_catch_shoot_fga"]).nlargest(8, "trk_catch_shoot_fga"),
         "top catch-and-shoot volume (season FGA)")


if __name__ == "__main__":
    main()
