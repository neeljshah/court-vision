"""Role / archetype spine — the shared layer ratings + the sim reason over.

Assigns every rotation player a basketball ROLE (archetype) from his rates + physical
attributes + tracking signals, plus a set of continuous role PROPENSITIES (creation,
playmaking, spacing, rim pressure, rebounding, rim protection, perimeter D). Both the
role-aware 2K ratings (`build_player_ratings.py`) and the possession sim
(`basketball_sim.py` routing) consume this.

Why it matters: a flat average of skills tanks specialists (a 26-ppg lead guard who can't
rebound). The role says WHICH skills define a player so OVERALL and possession routing weight
them correctly.

Output: data/cache/team_system/player_roles.parquet
  python scripts/team_system/build_player_roles.py
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
SIG = os.path.join(ROOT, "data", "cache", "signals")


def _pct(pool: np.ndarray, v) -> float:
    """Percentile (0-1) of v within pool (NaN-safe). 0.5 if undefined."""
    pool = pool[~np.isnan(pool)]
    if len(pool) == 0 or v is None or (isinstance(v, float) and np.isnan(v)):
        return 0.5
    return float((pool < v).mean())


def _load_signal(name: str, key: str) -> pd.DataFrame:
    fp = os.path.join(SIG, name + ".parquet")
    if not os.path.exists(fp):
        return pd.DataFrame()
    d = pd.read_parquet(fp)
    if "season" in d.columns:
        d = d.sort_values("season").groupby(key).tail(1)
    return d.set_index(key)


def posgroup(h: float) -> str:
    if h < 77:
        return "GUARD"
    if h < 81:
        return "WING"
    return "BIG"


def main():
    pr = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    at = pd.read_parquet(os.path.join(TS, "player_attributes.parquet")).set_index("pid")
    sp = _load_signal("scoring_profile", "player_id")     # self-creation, play-type
    pm = _load_signal("playmaking", "player_id")          # ast%, drives
    dm = _load_signal("defense_matchup", "def_player_id")  # opp-adjusted stops

    pr = pr.copy()
    pr["ppm"] = pr.pts_pg / pr.mpg.clip(lower=1)
    denom = 2 * pr.use_per_min * (pr.shot_share + pr.ft_share)
    pr["ts"] = np.where(denom > 0, pr.ppm / denom, np.nan)
    pr["reb_pm"] = pr.oreb_per_min + pr.dreb_per_min
    pr["rim_share"] = pr.z_rim + pr.z_paint

    ref = pr[pr.mpg >= 10]
    POOL = {c: ref[c].to_numpy(float) for c in
            ["use_per_min", "ast_per_min", "fg3_rate", "rim_share", "reb_pm",
             "blk_per_min", "stl_per_min", "ppm", "ts"]}
    # position-relative rebounding pools
    refh = ref.merge(at[["height_in"]], left_on="pid", right_index=True, how="left")
    refh["pg"] = refh.height_in.fillna(78).map(posgroup)
    REB_POOL = {g: refh[refh.pg == g].reb_pm.to_numpy(float) for g in ("GUARD", "WING", "BIG")}

    rows = []
    for r in pr.itertuples(index=False):
        pid = int(r.pid)
        a = at.loc[pid] if pid in at.index else None
        h = float(a.height_in) if a is not None and pd.notna(a.height_in) else 78.0
        pg = posgroup(h)
        s = sp.loc[pid] if len(sp) and pid in sp.index else None
        p = pm.loc[pid] if len(pm) and pid in pm.index else None
        d = dm.loc[pid] if len(dm) and pid in dm.index else None

        # --- continuous propensities (0-1) ---
        self_create = float(s.sc_unassisted_share_2pm) if s is not None and pd.notna(
            getattr(s, "sc_unassisted_share_2pm", np.nan)) else 0.5
        creation = _pct(POOL["use_per_min"], r.use_per_min) * (0.55 + 0.45 * np.clip(self_create / 0.5, 0.3, 1.6))
        creation = float(np.clip(creation, 0, 1))
        ast_pct = float(p.ast_pct_bbref) if p is not None and pd.notna(
            getattr(p, "ast_pct_bbref", np.nan)) else np.nan
        playmaking = _pct(POOL["ast_per_min"], r.ast_per_min)
        if not np.isnan(ast_pct):
            playmaking = 0.6 * playmaking + 0.4 * np.clip(ast_pct / 40.0, 0, 1)
        spacing = _pct(POOL["fg3_rate"], r.fg3_rate) * float(np.clip((r.fg3_pct or 0.30) / 0.34, 0.25, 1.4))
        spacing = float(np.clip(spacing, 0, 1))
        rim_pressure = _pct(POOL["rim_share"], r.rim_share)
        rebounding = _pct(REB_POOL[pg], r.reb_pm)            # position-relative
        rim_protect = 0.6 * _pct(POOL["blk_per_min"], r.blk_per_min) + 0.4 * np.clip((h - 78) / 8, 0, 1)
        stops = float(d.stops_pctile) / 99.0 if d is not None and pd.notna(
            getattr(d, "stops_pctile", np.nan)) else np.nan
        perimeter_d = _pct(POOL["stl_per_min"], r.stl_per_min)
        if not np.isnan(stops):
            perimeter_d = 0.5 * perimeter_d + 0.5 * stops

        usep = _pct(POOL["use_per_min"], r.use_per_min)
        scorer = _pct(POOL["ppm"], r.ppm)

        # --- archetype decision tree ---
        arch = _classify(pg, h, r, usep, scorer, creation, playmaking, spacing,
                         rim_pressure, rim_protect, rebounding, perimeter_d)
        rows.append({
            "pid": pid, "player": r.player, "team": r.team, "mpg": float(r.mpg),
            "height_in": h, "posgroup": pg, "archetype": arch,
            "creation": round(creation, 3), "playmaking": round(float(playmaking), 3),
            "spacing": round(spacing, 3), "rim_pressure": round(float(rim_pressure), 3),
            "rebounding": round(float(rebounding), 3), "rim_protect": round(float(rim_protect), 3),
            "perimeter_d": round(float(perimeter_d), 3), "self_create": round(self_create, 3),
            "usage_pct": round(usep, 3), "scorer_pct": round(scorer, 3),
        })
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(TS, "player_roles.parquet"), index=False)

    asc = lambda x: str(x).encode("ascii", "replace").decode()
    print(f"DONE: roles for {len(df)} players -> player_roles.parquet")
    print(df.archetype.value_counts().to_string())
    print("\nNYK/SAS roster archetypes:")
    sub = df[df.team.isin(["NYK", "SAS"]) & (df.mpg >= 10)].sort_values(["team", "usage_pct"], ascending=[True, False])
    for r in sub.itertuples(index=False):
        print(f"  {asc(r.player):22s} {r.team} {r.posgroup:5s} {r.archetype:18s} "
              f"crea{r.creation:.2f} play{r.playmaking:.2f} spc{r.spacing:.2f} "
              f"rimP{r.rim_pressure:.2f} reb{r.rebounding:.2f} rimD{r.rim_protect:.2f} perD{r.perimeter_d:.2f}")


def _classify(pg, h, r, usep, scorer, creation, playmaking, spacing,
              rim_pressure, rim_protect, rebounding, perimeter_d) -> str:
    """Rule-based archetype from position group + propensities."""
    hi_use = usep >= 0.78          # top-quartile usage
    mid_use = usep >= 0.55
    hi_play = playmaking >= 0.62
    hi_space = spacing >= 0.55
    if pg == "BIG":
        if rim_protect >= 0.80 and usep < 0.55 and scorer < 0.70:
            return "ANCHOR_BIG"             # rim-protect/rebound specialist (Robinson, Kornet)
        if hi_use and rim_protect >= 0.75:
            return "TWO_WAY_BIG"            # unicorn: primary + rim protector (Wemby)
        if mid_use and hi_space:
            return "STRETCH_BIG"            # spacing + scoring big (KAT-ish)
        if mid_use:
            return "PRIMARY_BIG"            # post/usage hub
        return "ROLE_BIG"                   # connector / low-usage big
    if pg == "GUARD":
        if mid_use and hi_play:
            return "LEAD_GUARD"            # primary initiator (Brunson, Fox, Castle, Harper)
        if hi_use:
            return "SCORING_GUARD"         # ball-dominant scorer
        if hi_play:
            return "FLOOR_GENERAL"         # pass-first PG
        if r.mpg < 22 and usep >= 0.55:
            return "BENCH_SCORER"          # microwave (Clarkson)
        if hi_space:
            return "OFF_GUARD"             # 3&D / spot-up guard (McBride, Shamet)
        return "CONNECTOR_GUARD"
    # WING
    if h < 80 and mid_use and hi_play and scorer >= 0.5:
        return "LEAD_GUARD"                # ball-dominant scoring initiator (Luka, Castle, Harper)
    if h < 81 and hi_play and rebounding >= 0.55 and scorer < 0.5:
        return "CONNECTOR_WING"            # playmaking/defensive point-forward (Draymond-type)
    if r.mpg < 22 and hi_use:
        return "BENCH_SCORER"              # microwave off the bench (Clarkson)
    if usep >= 0.62:
        return "WING_CREATOR"              # scoring/creating wing (Keldon)
    if hi_space or (perimeter_d >= 0.68 and spacing >= 0.38):
        return "THREE_D_WING"              # 3&D: shoots OR strong perimeter D (Bridges, OG, Vassell)
    if rebounding >= 0.55 or playmaking >= 0.55:
        return "CONNECTOR_WING"            # glue (Hart, Sochan)
    return "ROLE_WING"


if __name__ == "__main__":
    main()
