"""build_calibration_frame_v2.py — enriched per-game calibration frame.

v1 (calibration_study.py) gave [pred, l10_min, rest, b2b, home, opp_pace, opp_def,
month, days]. The biggest bias is MINUTES surprise, whose predictable cause is
teammate availability. v2 adds the covariates that target it, leak-free:
  minutes shape : l3_min, l5_min, std_min, prev_min, min_trend (l3-l10)
  availability  : vac_min, vac_pts, n_out  (regular teammates OUT this game)
  role/rate     : l5_pts_pm, l5_reb_pm     (per-minute scoring/rebounding)

Writes data/cache/calibration_frame_v2.parquet. Reconstruction identical in spirit
to scripts/calibrate_live_adjustment.py (rosters from prior-3 team games, L10 before).
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
OUT = _ROOT / "data" / "cache" / "calibration_frame_v2.parquet"
SEASONS = ("2023-24", "2024-25", "2025-26")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _teams(m):
    if not m:
        return None, None, None
    if " @ " in m:
        a, b = m.split(" @ "); return a.strip(), b.strip(), 0
    if " vs. " in m:
        a, b = m.split(" vs. "); return a.strip(), b.strip(), 1
    return None, None, None


def team_state_index():
    idx = {}
    for s in SEASONS:
        p = _ROOT / "data" / "nba" / f"season_games_{s}.json"
        if not p.exists():
            continue
        for r in json.load(open(p, encoding="utf-8")).get("rows", []):
            d = r.get("game_date")
            for side in ("home", "away"):
                t = r.get(f"{side}_team")
                if t and d is not None and r.get(f"{side}_pace") is not None:
                    idx[(d, t)] = {"pace": float(r[f"{side}_pace"]),
                                   "def": float(r.get(f"{side}_def_rtg") or 112.0)}
    return idx


def main():
    print("reconstructing enriched covariates (all seasons)...")
    # pass: per (team,date) the players present + their as-of L10 min/pts
    rows_by_td = defaultdict(list)
    pg = defaultdict(dict)  # (pid,date) -> covariate dict (own)
    for fp in glob.glob(str(_ROOT / "data" / "nba" / "gamelog_*_*.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = sorted(((pd.to_datetime(g.get("GAME_DATE"), errors="coerce"), g)
                       for g in log), key=lambda kv: kv[0])
        mins, ptss, rebs = [], [], []
        prev_d = None; season_start = None
        for d, g in recs:
            if pd.isna(d):
                continue
            t, o, is_home = _teams(g.get("MATCHUP"))
            ds = d.date().isoformat()
            if season_start is None or (prev_d and (d - prev_d).days > 60):
                season_start = d
            rest = (d - prev_d).days if prev_d else 3
            if t and len(mins) >= 5:
                am = np.array(mins); ap = np.array(ptss); ar = np.array(rebs)
                l3 = float(am[-3:].mean()); l5 = float(am[-5:].mean())
                l10 = float(am[-10:].mean())
                rec = {
                    "pid": pid, "date": ds, "team": t, "opp": o,
                    "is_home": is_home, "rest_days": min(rest, 10),
                    "is_b2b": 1 if rest <= 1 else 0,
                    "l3_min": l3, "l5_min": l5, "l10_min": l10,
                    "std_min": float(am[-10:].std()), "prev_min": mins[-1],
                    "min_trend": l3 - l10,
                    "l5_pts_pm": float(ap[-5:].mean()) / max(l5, 1e-6),
                    "l5_reb_pm": float(ar[-5:].mean()) / max(l5, 1e-6),
                    "l10_pts": float(ap[-10:].mean()),
                    "month": d.month,
                    "days_into_season": (d - season_start).days if season_start else 0,
                }
                rows_by_td[(t, ds)].append(
                    {"pid": pid, "l10_min": l10, "l10_pts": rec["l10_pts"]})
                pg[(pid, ds)] = rec
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)
                rebs.append(_f(g.get("REB")) or 0.0)
            prev_d = d

    # vacated-minutes per (team,date)
    team_dates = defaultdict(list)
    for (t, ds) in rows_by_td:
        team_dates[t].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))
    vac_by_td = {}
    for (t, ds), played in rows_by_td.items():
        i = team_dates[t].index(ds)
        if i < 3:
            continue
        played_ids = {r["pid"] for r in played}
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(t, team_dates[t][j])]:
                roster[rec["pid"]] = rec
        vm = vp = 0.0; nout = 0
        for pid_, rec in roster.items():
            if pid_ not in played_ids and rec["l10_min"] >= 15:
                vm += rec["l10_min"]; vp += rec["l10_pts"]; nout += 1
        vac_by_td[(t, ds)] = (vm, vp, nout)

    tstate = team_state_index()
    oof = pd.read_parquet(OOF)
    oof["date"] = oof["game_date"].astype(str).str[:10]
    out = []
    for r in oof.itertuples(index=False):
        c = pg.get((int(r.player_id), r.date))
        if c is None:
            continue
        vm, vp, nout = vac_by_td.get((c["team"], r.date), (0.0, 0.0, 0))
        ost = tstate.get((r.date, c["opp"])) if c["opp"] else None
        out.append({
            "player_id": int(r.player_id), "date": r.date, "stat": r.stat,
            "season": r.season, "pred": float(r.oof_pred), "actual": float(r.actual),
            "l3_min": c["l3_min"], "l5_min": c["l5_min"], "l10_min": c["l10_min"],
            "std_min": c["std_min"], "prev_min": c["prev_min"], "min_trend": c["min_trend"],
            "rest_days": c["rest_days"], "is_b2b": c["is_b2b"], "is_home": c["is_home"],
            "opp_pace": ost["pace"] if ost else np.nan,
            "opp_def": ost["def"] if ost else np.nan,
            "vac_min": vm, "vac_pts": vp, "n_out": nout,
            "l5_pts_pm": c["l5_pts_pm"], "l5_reb_pm": c["l5_reb_pm"],
            "month": c["month"], "days_into_season": c["days_into_season"],
        })
    df = pd.DataFrame(out)
    df.to_parquet(OUT, index=False)
    print(f"  v2 frame: {len(df):,} rows, {df.shape[1]} cols -> {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
