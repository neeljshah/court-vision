"""Persistent profile factory — synthesize validated parquets into accumulating
per-player / per-team JSON profiles with provenance + confidence + as-of.

This is the TEMPLATE assembler (BUILD_LOG iteration 0). It MERGES into existing
profiles rather than clobbering: a section is updated only when the new build's
confidence >= existing OR its as_of is newer. Every numeric field traces to a real
parquet row — no fabricated values.

Usage:
  python scripts/build_persistent_profiles.py [--build-date YYYY-MM-DD] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
PROF = CACHE / "profiles"
PLAYERS_DIR = PROF / "players"
TEAMS_DIR = PROF / "teams"
SCHEMA_VERSION = "1.0"

CONF_ORDER = {"low": 0, "med": 1, "high": 2}


def conf_from_n(n: int, cap: Optional[str] = None) -> str:
    c = "high" if n >= 20 else "med" if n >= 5 else "low"
    if cap and CONF_ORDER[c] > CONF_ORDER[cap]:
        return cap
    return c


def _prefer_fresh(*paths: Path) -> Optional[pd.DataFrame]:
    """Return the first existing parquet (pass fresh-season path first)."""
    for p in paths:
        df = safe_read(p)
        if df is not None and not df.empty:
            return df
    return None


def _concat_seasons(*paths: Path) -> Optional[pd.DataFrame]:
    """Read + vertically concat available parquets (for base+fresh season merges)."""
    frames = [df for df in (safe_read(p) for p in paths) if df is not None]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def safe_read(path: Path) -> Optional[pd.DataFrame]:
    try:
        if path.exists():
            return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN read {path.name}: {exc}")
    return None


def clean(v: Any) -> Any:
    """JSON-safe scalar: NaN/inf -> None, numpy -> python."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return str(v)[:10]
    if pd.isna(v) if not isinstance(v, (list, dict)) else False:
        return None
    return v


def rd(series_val) -> Optional[float]:
    return clean(series_val)


# ---------------------------------------------------------------------------
# Source loaders -> dict keyed by player_id (int)
# ---------------------------------------------------------------------------

def load_sources() -> dict[str, Any]:
    s: dict[str, Any] = {}
    s["bio"] = safe_read(CACHE / "player_profile_features.parquet")
    s["quarter"] = safe_read(DATA / "player_quarter_stats.parquet")
    # tracking/hustle/playtypes: concat base(2024-25) + fresh(2025-26); section builders
    # pick latest season per player -> freshness where available, fallback coverage otherwise.
    s["tracking"] = _concat_seasons(DATA / "player_tracking.parquet",
                                    DATA / "player_tracking_2025-26.parquet")
    s["hustle"] = _concat_seasons(CACHE / "hustle_features.parquet",
                                  CACHE / "hustle_features_2025-26.parquet")
    s["foul"] = safe_read(CACHE / "foul_features.parquet")
    s["playtypes"] = _concat_seasons(DATA / "playtypes.parquet",
                                     DATA / "playtypes_2025-26.parquet")
    # matchup layer: prefer 2025-26 (single season) when present, else 2024-25.
    # NOT concat — these sections aggregate all rows per player; concat would mix seasons.
    s["defmatch"] = _prefer_fresh(DATA / "defender_matchups_2025-26.parquet",
                                  DATA / "defender_matchups_2024-25.parquet")
    s["cv"] = safe_read(DATA / "player_cv_per_player.parquet")
    s["team_adv"] = safe_read(DATA / "team_advanced_stats.parquet")
    s["team_reb"] = safe_read(DATA / "team_reb_context.parquet")
    # Iteration-1 enrichment sources (built by parallel agents; None until they land)
    s["clutch"] = safe_read(CACHE / "clutch_profiles_2025-26.parquet")
    s["propcal"] = safe_read(CACHE / "prop_calibration_history.parquet")
    s["intervalcal"] = safe_read(CACHE / "blk_player_dispersion.parquet")
    s["covfaced"] = _prefer_fresh(CACHE / "coverage_faced_matrix_2025-26.parquet",
                                  CACHE / "coverage_faced_matrix.parquet")
    s["team_scheme"] = safe_read(ROOT / "data" / "intelligence" / "defensive_schemes.parquet")
    s["onoff"] = safe_read(CACHE / "on_off_features.parquet")
    return s


def sec_on_off(pid: int, s: dict):
    """Player on/off impact — net-rating swing when on court (lineup value signal)."""
    o = s.get("onoff")
    if o is None or "player_id" not in o.columns:
        return None
    g = o[o["player_id"] == pid]
    if g.empty:
        return None
    if "season" in g.columns:
        g = g.sort_values("season").tail(1)
    r = g.iloc[0]
    d = {k: clean(r.get(k)) for k in
         ("on_court_plus_minus", "off_court_plus_minus", "on_off_diff", "minutes_on",
          "on_off_net_rating_diff", "on_off_orating_diff", "on_off_drating_diff",
          "on_off_pace_diff", "on_off_impact_z") if k in o.columns and not pd.isna(r.get(k))}
    d["season"] = clean(r.get("season"))
    mins = r.get("minutes_on") or 0
    n = int(mins / 30) if mins and not pd.isna(mins) else 0  # ~games-equiv from minutes
    prov = {"source": "on_off_features.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": clean(r.get("season"))}
    return d, prov


def sec_coverage_faced(pid: int, s: dict, names: dict[int, str]):
    """Who-guards-THEM: top defenders by matchup minutes + how the player shot vs each."""
    c = s.get("covfaced")
    if c is None or "off_player_id" not in c.columns:
        return None
    g = c[c["off_player_id"] == pid]
    if g.empty:
        return None
    mincol = "matchup_minutes_total" if "matchup_minutes_total" in c.columns else None
    if mincol:
        g = g.sort_values(mincol, ascending=False)
    top = []
    for _, r in g.head(8).iterrows():
        did = r.get("def_player_id")
        top.append({
            "def_player_id": clean(did),
            "def_player_name": clean(r.get("def_player_name")) or names.get(int(did) if pd.notna(did) else -1, None),
            "matchup_minutes": rd(r.get(mincol)) if mincol else None,
            "partial_possessions": rd(r.get("partial_possessions")),
            "off_fg_pct": rd(r.get("off_fg_pct")),
            "off_fg3_pct": rd(r.get("off_fg3_pct")),
            "off_points": rd(r.get("off_points")),
            "n_games": clean(r.get("n_games_matched")),
        })
    total_min = rd(g[mincol].sum()) if mincol else None
    n_def = int(g["def_player_id"].nunique()) if "def_player_id" in g.columns else len(g)
    d = {"n_defenders": n_def, "total_matchup_minutes": total_min, "top_defenders": top}
    season = clean(g["season"].iloc[0]) if "season" in g.columns else None
    prov = {"source": "coverage_faced_matrix.parquet", "n": n_def,
            "confidence": conf_from_n(n_def), "as_of": season}
    return d, prov


def sec_interval_calibration(pid: int, s: dict):
    """Per-player block-count overdispersion -> proper interval width for blk props."""
    c = s.get("intervalcal")
    if c is None or "player_id" not in c.columns:
        return None
    g = c[c["player_id"] == pid]
    if g.empty:
        return None
    r = g.iloc[0]
    d = {"blk": {k: clean(r.get(k)) for k in c.columns
                 if k not in ("player_id", "stat") and not pd.isna(r.get(k))}}
    n = int(r.get("n") or 0)
    prov = {"source": "blk_player_dispersion.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": "walk-forward-in-data"}
    return d, prov


def sec_clutch(pid: int, s: dict):
    c = s.get("clutch")
    if c is None or "player_id" not in c.columns:
        return None
    g = c[c["player_id"] == pid]
    if g.empty:
        return None
    r = g.iloc[0]
    d = {k: clean(r.get(k)) for k in c.columns
         if k not in ("player_id", "player_name") and not pd.isna(r.get(k))}
    gp = r.get("clutch_gp") if "clutch_gp" in c.columns else None
    n = int(gp) if gp is not None and not pd.isna(gp) else 0
    prov = {"source": "clutch_profiles_2025-26.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": "2025-26"}
    return d, prov


def sec_prop_calibration(pid: int, s: dict):
    p = s.get("propcal")
    if p is None or "player_id" not in p.columns:
        return None
    g = p[p["player_id"] == pid]
    if g.empty:
        return None
    by_stat = {}
    total_n = 0
    for _, r in g.iterrows():
        st = r.get("stat")
        if st is None or pd.isna(st):
            continue
        rec = {k: clean(r.get(k)) for k in g.columns
               if k not in ("player_id", "stat") and not pd.isna(r.get(k))}
        by_stat[str(st)] = rec
        total_n += int(r.get("n") or 0)
    if not by_stat:
        return None
    prov = {"source": "prop_calibration_history.parquet", "n": total_n,
            "confidence": conf_from_n(total_n), "as_of": "walk-forward-in-data"}
    return by_stat, prov


def build_name_map(s: dict) -> dict[int, str]:
    names: dict[int, str] = {}
    bio = s["bio"]
    if bio is not None:
        for _, r in bio.iterrows():
            names[int(r["player_id"])] = r.get("player_name") or ""
    cv = s["cv"]
    if cv is not None and "nba_player_id" in cv.columns:
        for _, r in cv.iterrows():
            pid = r.get("nba_player_id")
            if pd.notna(pid):
                names.setdefault(int(pid), r.get("player_name") or "")
    return names


# ---------------------------------------------------------------------------
# Per-player section builders. Each returns (section_dict, prov_dict) or None.
# ---------------------------------------------------------------------------

def sec_bio(pid: int, s: dict):
    bio = s["bio"]
    if bio is None:
        return None
    row = bio[bio["player_id"] == pid]
    if row.empty:
        return None
    r = row.iloc[0]
    keep = ["height_in", "weight_lb", "position", "draft_year", "draft_number",
            "undrafted_flag", "season_exp", "years_in_league_as_of",
            "age_precise_days_as_of", "college", "country", "rookie_flag_as_of"]
    d = {k: clean(r.get(k)) for k in keep if k in bio.columns}
    if d.get("age_precise_days_as_of"):
        d["age_years"] = round(d["age_precise_days_as_of"] / 365.25, 1)
    prov = {"source": "player_profile_features.parquet", "n": 1,
            "confidence": "high", "as_of": clean(r.get("profile_as_of"))}
    return d, prov


def _pergame(qdf: pd.DataFrame) -> pd.DataFrame:
    """Sum quarter rows -> per (game_id, player_id) box totals."""
    cols = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf", "min"]
    agg = qdf.groupby(["game_id", "player_id"])[cols].sum().reset_index()
    return agg


def sec_scoring_and_dist(pid: int, pergame: pd.DataFrame):
    g = pergame[pergame["player_id"] == pid]
    n = len(g)
    if n == 0:
        return None, None
    stats = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    scoring = {"n_games": int(n), "min_per_game": rd(g["min"].mean())}
    dist = {"n_games": int(n)}
    for st in stats:
        vals = g[st].astype(float)
        mean = float(vals.mean())
        var = float(vals.var(ddof=0))
        scoring[f"{st}_pg"] = round(mean, 3)
        # NegBinom dispersion = var/mean (>1 overdispersed). guard mean~0.
        disp = round(var / mean, 3) if mean > 0.05 else None
        dist[st] = {"mean": round(mean, 3), "var": round(var, 3), "dispersion": disp}
    conf = conf_from_n(n)
    prov_s = {"source": "player_quarter_stats.parquet(per-game sum)", "n": int(n),
              "confidence": conf, "as_of": "2025-26-in-data"}
    return ({"scoring": scoring}, prov_s), ({"dist": dist}, dict(prov_s))


def sec_quarter_shape(pid: int, qdf: pd.DataFrame):
    g = qdf[qdf["player_id"] == pid]
    if g.empty:
        return None
    by_p = g.groupby("period")["pts"].mean()
    ng = g["game_id"].nunique()
    shape = {f"q{int(p)}_pts": round(float(v), 3) for p, v in by_p.items() if p <= 4}
    ot = by_p[by_p.index > 4].mean() if (by_p.index > 4).any() else None
    if ot is not None and not math.isnan(ot):
        shape["ot_pts"] = round(float(ot), 3)
    # Q4 fade: q4 vs avg(q1..q3)
    early = [shape.get(f"q{i}_pts") for i in (1, 2, 3) if shape.get(f"q{i}_pts") is not None]
    if early and shape.get("q4_pts") is not None:
        base = sum(early) / len(early)
        shape["q4_vs_early_ratio"] = round(shape["q4_pts"] / base, 3) if base > 0.05 else None
    prov = {"source": "player_quarter_stats.parquet", "n": int(ng),
            "confidence": conf_from_n(int(ng)), "as_of": "2025-26-in-data"}
    return shape, prov


def sec_shot_diet(pid: int, s: dict):
    tr = s["tracking"]
    if tr is None:
        return None
    row = tr[tr["player_id"] == pid]
    if row.empty:
        return None
    # latest season
    if "season" in row.columns:
        row = row.sort_values("season").tail(1)
    r = row.iloc[0]
    d = {
        "drive_count": rd(r.get("trk_drv_count")),
        "drive_fg_pct": rd(r.get("trk_drv_fg_pct")),
        "drive_pts": rd(r.get("trk_drv_pts")),
        "catch_shoot_fga": rd(r.get("trk_cs_fga")),
        "catch_shoot_fg_pct": rd(r.get("trk_cs_fg_pct")),
        "catch_shoot_efg_pct": rd(r.get("trk_cs_efg_pct")),
        "catch_shoot_pts": rd(r.get("trk_cs_pts")),
        "season": clean(r.get("season")),
    }
    prov = {"source": "player_tracking.parquet", "n": 1, "confidence": "high",
            "as_of": clean(r.get("season"))}
    return d, prov


def sec_playmaking(pid: int, s: dict):
    tr = s["tracking"]
    if tr is None:
        return None
    row = tr[tr["player_id"] == pid]
    if row.empty:
        return None
    if "season" in row.columns:
        row = row.sort_values("season").tail(1)
    r = row.iloc[0]
    d = {
        "passes_made": rd(r.get("trk_pas_passes_made")),
        "passes_received": rd(r.get("trk_pas_passes_received")),
        "potential_ast": rd(r.get("trk_pas_potential_ast")),
        "ast_pts_created": rd(r.get("trk_pas_ast_points_created")),
        "secondary_ast": rd(r.get("trk_pas_secondary_ast")),
        "ft_ast": rd(r.get("trk_pas_ft_ast")),
        "season": clean(r.get("season")),
    }
    prov = {"source": "player_tracking.parquet", "n": 1, "confidence": "high",
            "as_of": clean(r.get("season"))}
    return d, prov


def sec_hustle(pid: int, s: dict):
    h = s["hustle"]
    if h is None:
        return None
    row = h[h["player_id"] == pid]
    if row.empty:
        return None
    if "season" in row.columns:
        row = row.sort_values("season").tail(1)
    r = row.iloc[0]
    gp = r.get("hustle_games_played") or 0
    d = {
        "games_played": clean(gp),
        "deflections": rd(r.get("hustle_deflections")),
        "contested_shots": rd(r.get("hustle_contested_shots")),
        "screen_assists": rd(r.get("hustle_screen_assists")),
        "box_outs": rd(r.get("hustle_box_outs")),
        "loose_balls": rd(r.get("hustle_loose_balls")),
        "charges_drawn": rd(r.get("hustle_charges_drawn")),
        "season": clean(r.get("season")),
    }
    n = int(gp) if gp and not pd.isna(gp) else 0
    prov = {"source": "hustle_features.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": clean(r.get("season"))}
    return d, prov


def sec_foul(pid: int, s: dict):
    f = s["foul"]
    if f is None:
        return None
    g = f[f["player_id"] == pid]
    if g.empty:
        return None
    if "game_date" in g.columns:
        g = g.sort_values("game_date")
    last = g.iloc[-1]
    d = {
        "pf_per_36_l5": rd(last.get("pf_per_36_l5")),
        "pf_per_36_l10": rd(last.get("pf_per_36_l10")),
        "foul_trouble_rate_l10": rd(last.get("foul_trouble_rate_l10")),
        "n_games": int(g["game_id"].nunique()) if "game_id" in g.columns else len(g),
    }
    n = d["n_games"]
    prov = {"source": "foul_features.parquet", "n": n, "confidence": conf_from_n(n),
            "as_of": clean(last.get("game_date"))}
    return d, prov


def sec_playtypes(pid: int, s: dict):
    p = s["playtypes"]
    if p is None:
        return None
    g = p[p["player_id"] == pid]
    if g.empty:
        return None
    if "season" in g.columns:
        latest = g["season"].max()
        g = g[g["season"] == latest]
    rows = [{"play_type": clean(r["play_type"]), "freq_pct": rd(r["freq_pct"]),
             "ppp": rd(r["ppp"])} for _, r in g.iterrows()]
    rows.sort(key=lambda x: (x["freq_pct"] or 0), reverse=True)
    prov = {"source": "playtypes.parquet", "n": len(rows), "confidence": "high",
            "as_of": clean(g["season"].iloc[0]) if "season" in g.columns else None}
    return rows, prov


def sec_defense_allowed(pid: int, s: dict):
    d = s["defmatch"]
    if d is None:
        return None
    g = d[d["def_player_id"] == pid]
    if g.empty:
        return None
    fga = g["fg_attempted_allowed"].sum()
    fg3a = g["fg3_attempted_allowed"].sum()
    out = {
        "matchup_minutes_total": rd(g["matchup_minutes_total"].sum()),
        "partial_possessions": rd(g["partial_possessions"].sum()),
        "points_allowed": rd(g["points_allowed"].sum()),
        "fg_made_allowed": clean(int(g["fg_made_allowed"].sum())),
        "fg_attempted_allowed": clean(int(fga)),
        "fg_pct_allowed": rd(g["fg_made_allowed"].sum() / fga) if fga > 0 else None,
        "fg3_attempted_allowed": clean(int(fg3a)),
        "fg3_pct_allowed": rd(g["fg3_made_allowed"].sum() / fg3a) if fg3a > 0 else None,
        "blocks_matchup": clean(int(g["blocks_matchup"].sum())),
        "switches_on": clean(int(g["switches_on"].sum())),
        "n_games": int(g["game_id"].nunique()),
    }
    n = out["n_games"]
    prov = {"source": "defender_matchups_2024-25.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": "2024-25"}
    return out, prov


def sec_cv(pid: int, s: dict):
    cv = s["cv"]
    if cv is None or "nba_player_id" not in cv.columns:
        return None
    g = cv[cv["nba_player_id"] == pid]
    if g.empty:
        return None
    r = g.iloc[0]
    keep = ["n_games", "n_frames", "minutes_proxy", "cvb_avg_defender_dist",
            "cvb_avg_spacing", "cvb_avg_velocity", "cvb_paint_time_pct",
            "cvb_contest_arm_mean", "cvb_contested_shot_pct", "cvb_pose_coverage_pct",
            "cvb_velocity_q4_dropoff", "cvb_fatigue_score"]
    d = {k: clean(r.get(k)) for k in keep if k in cv.columns}
    ng = int(r.get("n_games") or 0)
    # CV capped at med until identity fixed
    prov = {"source": "player_cv_per_player.parquet", "n": ng,
            "confidence": conf_from_n(ng, cap="med"), "as_of": "cv-in-data",
            "note": "broadcast-CV bonus; identity-blocked, capped med"}
    return d, prov


# ---------------------------------------------------------------------------
# Merge + write
# ---------------------------------------------------------------------------

def merge_section(existing: dict, key: str, payload, build_date: str):
    """payload = (section_data, prov) or None. Merge under accumulate semantics."""
    if payload is None:
        return
    data, prov = payload
    old_prov = existing.get("_provenance", {}).get(key)
    if old_prov is not None:
        new_c = CONF_ORDER[prov["confidence"]]
        old_c = CONF_ORDER[old_prov["confidence"]]
        new_as = str(prov.get("as_of") or "")
        old_as = str(old_prov.get("as_of") or "")
        # keep existing if it's strictly higher confidence AND not older
        if old_c > new_c and old_as >= new_as:
            return
    existing.setdefault("sections", {})[key] = data
    existing.setdefault("_provenance", {})[key] = prov


def load_existing(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def newest_as_of(prov: dict) -> Optional[str]:
    dates = []
    for v in prov.values():
        a = str(v.get("as_of") or "")
        if a and a[0].isdigit():
            dates.append(a[:10])
    return max(dates) if dates else None


def build_players(s: dict, names: dict[int, str], build_date: str, limit: Optional[int]):
    pergame = _pergame(s["quarter"]) if s["quarter"] is not None else pd.DataFrame()
    # universe = union of all player_ids appearing in any source
    pids: set[int] = set(names)
    for key, idcol in [("quarter", "player_id"), ("tracking", "player_id"),
                       ("hustle", "player_id"), ("foul", "player_id"),
                       ("playtypes", "player_id"), ("clutch", "player_id"),
                       ("propcal", "player_id")]:
        df = s[key]
        if df is not None and idcol in df.columns:
            pids.update(int(x) for x in df[idcol].dropna().unique())
    pids = sorted(pids)
    if limit:
        pids = pids[:limit]
    written = 0
    for pid in pids:
        path = PLAYERS_DIR / f"{pid}.json"
        prof = load_existing(path)
        prof.update({"player_id": pid, "player_name": names.get(pid, ""),
                     "schema_version": SCHEMA_VERSION, "last_built": build_date})
        prof.setdefault("sections", {})
        prof.setdefault("_provenance", {})

        sc = sec_scoring_and_dist(pid, pergame) if not pergame.empty else None
        scoring_payload = sc[0] if sc else None
        dist_payload = sc[1] if sc else None

        merge_section(prof, "bio", sec_bio(pid, s), build_date)
        merge_section(prof, "scoring_usage", scoring_payload, build_date)
        merge_section(prof, "count_distributions", dist_payload, build_date)
        merge_section(prof, "quarter_shape",
                      sec_quarter_shape(pid, s["quarter"]) if s["quarter"] is not None else None,
                      build_date)
        merge_section(prof, "shot_diet", sec_shot_diet(pid, s), build_date)
        merge_section(prof, "playmaking", sec_playmaking(pid, s), build_date)
        merge_section(prof, "hustle", sec_hustle(pid, s), build_date)
        merge_section(prof, "foul_propensity", sec_foul(pid, s), build_date)
        merge_section(prof, "playtypes", sec_playtypes(pid, s), build_date)
        merge_section(prof, "defense_allowed", sec_defense_allowed(pid, s), build_date)
        merge_section(prof, "clutch", sec_clutch(pid, s), build_date)
        merge_section(prof, "prop_calibration", sec_prop_calibration(pid, s), build_date)
        merge_section(prof, "interval_calibration", sec_interval_calibration(pid, s), build_date)
        merge_section(prof, "coverage_faced", sec_coverage_faced(pid, s, names), build_date)
        merge_section(prof, "on_off_impact", sec_on_off(pid, s), build_date)
        merge_section(prof, "cv_bonus", sec_cv(pid, s), build_date)

        if not prof["sections"]:
            continue  # nothing real for this id
        ao = newest_as_of(prof["_provenance"])
        if ao:
            prof["as_of_game_date"] = ao
        path.write_text(json.dumps(prof, indent=2, default=str), encoding="utf-8")
        written += 1
    return written, len(pids)


def build_teams(s: dict, build_date: str):
    adv = s["team_adv"]
    if adv is None:
        return 0
    reb = s["team_reb"]
    written = 0
    for tri, g in adv.groupby("team_tricode"):
        path = TEAMS_DIR / f"{tri}.json"
        prof = load_existing(path)
        prof.update({"team_tricode": tri, "schema_version": SCHEMA_VERSION,
                     "last_built": build_date})
        prof.setdefault("sections", {})
        prof.setdefault("_provenance", {})
        n = int(g["game_id"].nunique())
        ratings = {
            "n_games": n,
            "off_rtg": rd(g["off_rtg"].mean()),
            "def_rtg": rd(g["def_rtg"].mean()),
            "pace": rd(g["pace"].mean()),
            "efg_pct": rd(g["efg_pct"].mean()),
            "ts_pct": rd(g["ts_pct"].mean()),
            "ast_pct": rd(g["ast_pct"].mean()),
            "tov_ratio": rd(g["tov_ratio"].mean()),
            "oreb_pct": rd(g["oreb_pct"].mean()),
            "dreb_pct": rd(g["dreb_pct"].mean()),
        }
        last_date = str(g["game_date"].max())[:10] if "game_date" in g.columns else None
        merge_section(prof, "ratings", (ratings, {
            "source": "team_advanced_stats.parquet", "n": n,
            "confidence": conf_from_n(n), "as_of": last_date}), build_date)
        if reb is not None and "team_tricode" in reb.columns:
            rg = reb[reb["team_tricode"] == tri]
            if not rg.empty:
                rr = {c: rd(rg[c].mean()) for c in rg.columns
                      if c not in ("team_tricode", "game_id", "game_date")
                      and pd.api.types.is_numeric_dtype(rg[c])}
                merge_section(prof, "rebounding", (rr, {
                    "source": "team_reb_context.parquet", "n": int(len(rg)),
                    "confidence": conf_from_n(int(len(rg))), "as_of": last_date}), build_date)
        # defensive scheme tendencies
        sch = s.get("team_scheme")
        if sch is not None and "team" in sch.columns:
            sg = sch[sch["team"] == tri]
            if not sg.empty:
                sr = sg.iloc[0]
                sd = {k: clean(sr.get(k)) for k in sch.columns
                      if k != "team" and not pd.isna(sr.get(k))}
                sconf = str(sr.get("confidence") or conf_from_n(int(sr.get("n_opposing_player_games") or 0)))
                merge_section(prof, "defense_scheme", (sd, {
                    "source": "intelligence/defensive_schemes.parquet",
                    "n": int(sr.get("n_opposing_player_games") or 0),
                    "confidence": sconf if sconf in CONF_ORDER else "med",
                    "as_of": last_date}), build_date)
        ao = newest_as_of(prof["_provenance"])
        if ao:
            prof["as_of_game_date"] = ao
        path.write_text(json.dumps(prof, indent=2, default=str), encoding="utf-8")
        written += 1
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build-date", default=date.today().isoformat())
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    TEAMS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading sources... build_date={args.build_date}")
    s = load_sources()
    for k, v in s.items():
        print(f"  {k:10s}: {'MISSING' if v is None else f'{len(v)} rows'}")
    names = build_name_map(s)
    print(f"name_map: {len(names)} players")

    pw, ptotal = build_players(s, names, args.build_date, args.limit)
    print(f"\nPLAYER profiles written: {pw} / {ptotal} candidate ids")
    tw = build_teams(s, args.build_date)
    print(f"TEAM profiles written: {tw}")
    _coverage_report()


def _coverage_report():
    """Scan written player profiles and report per-section coverage + confidence mix."""
    from collections import Counter
    sec_counts: Counter = Counter()
    conf_counts: dict[str, Counter] = {}
    total = 0
    for fp in PLAYERS_DIR.glob("*.json"):
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        total += 1
        for sec in d.get("sections", {}):
            sec_counts[sec] += 1
        for sec, pv in d.get("_provenance", {}).items():
            conf_counts.setdefault(sec, Counter())[pv.get("confidence", "?")] += 1
    print(f"\n=== SECTION COVERAGE ({total} player profiles) ===")
    for sec, c in sec_counts.most_common():
        mix = conf_counts.get(sec, Counter())
        mixs = " ".join(f"{k}={v}" for k, v in sorted(mix.items()))
        print(f"  {sec:20s} {c:5d} ({100*c/total:4.1f}%)  [{mixs}]")


if __name__ == "__main__":
    main()
