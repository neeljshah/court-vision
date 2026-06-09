"""validate_live_adjustment.py — does the same-day layer actually beat base OOS?

Applies the calibrated live adjustment to the production OOF predictions on
2025-26 hold-out games, reconstructing the same-day context leak-free:
  * inactives -> vacated_usage_share (regular teammates with no row that game)
  * blowout   -> final margin (reconstructed from team scores); the spread proxy

Reports MAE base vs adjusted, OVERALL and on the subset where the adjustment
actually fires (a teammate is out and/or the game was lopsided) — that subset is
where a live edge would show up. Honest: this uses RECONSTRUCTED inactives/margin
(what we could know historically); the live feed gives confirmed inactives + the
pre-game spread, which is cleaner. Touches no production model.
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
sys.path.insert(0, str(_ROOT))
from src.prediction.live_adjustment import (  # noqa: E402
    adjust_projection, vacated_usage_share, load_coeffs,
)

OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
SEASON = "2025-26"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _teams(matchup):
    if not matchup:
        return None, None
    if " @ " in matchup:
        a, b = matchup.split(" @ "); return a.strip(), b.strip()
    if " vs. " in matchup:
        a, b = matchup.split(" vs. "); return a.strip(), b.strip()
    return None, None


def build_context():
    """(pid,date) -> {vac_share, margin} reconstructed leak-free for 2025-26."""
    # team scores (all gamelogs, for margins)
    team_score = defaultdict(float)
    for fp in glob.glob(str(_ROOT / "data" / "nba" / f"gamelog_*_{SEASON}.json")):
        try:
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for g in log:
            t, _o = _teams(g.get("MATCHUP")); pts = _f(g.get("PTS"))
            d = g.get("GAME_DATE")
            if t and d and pts is not None:
                team_score[(str(pd.to_datetime(d).date()), t)] += pts

    rows_by_td = defaultdict(list)
    pid_date_opp = {}
    for fp in glob.glob(str(_ROOT / "data" / "nba" / f"gamelog_*_{SEASON}.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = sorted(((pd.to_datetime(g.get("GAME_DATE"), errors="coerce"), g)
                       for g in log), key=lambda kv: kv[0])
        mins, ptss = [], []
        for d, g in recs:
            if pd.isna(d):
                continue
            t, o = _teams(g.get("MATCHUP")); ds = d.date().isoformat()
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            if t and len(mins) >= 5:
                rows_by_td[(t, ds)].append(
                    {"pid": pid, "l10_min": l10_min, "l10_pts": l10_pts})
                pid_date_opp[(pid, ds)] = (t, o)
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)

    team_dates = defaultdict(list)
    for (t, ds) in rows_by_td:
        team_dates[t].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    ctx = {}
    for (t, ds), played in rows_by_td.items():
        i = team_dates[t].index(ds)
        if i < 3:
            continue
        played_ids = {r["pid"] for r in played}
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(t, team_dates[t][j])]:
                roster[rec["pid"]] = rec
        out_l10_pts = [rec["l10_pts"] for pid_, rec in roster.items()
                       if pid_ not in played_ids and rec["l10_min"] >= 15]
        for r in played:
            t2, o2 = pid_date_opp.get((r["pid"], ds), (t, None))
            margin = None
            if o2 is not None:
                ts = team_score.get((ds, t2)); os_ = team_score.get((ds, o2))
                if ts is not None and os_ is not None:
                    margin = ts - os_
            ctx[(r["pid"], ds)] = {
                "vac_share": vacated_usage_share(out_l10_pts, r["l10_pts"]),
                "margin": margin,
            }
    return ctx


def main():
    coeffs = load_coeffs()
    ctx = build_context()
    oof = pd.read_parquet(OOF)
    oof = oof[oof["game_date"].astype(str) >= "2025-10-01"].copy()
    oof["date"] = oof["game_date"].astype(str).str[:10]

    print(f"context rows: {len(ctx):,}\n")
    print(f"{'stat':<5}{'n':>7}{'MAE_base':>10}{'MAE_adj':>10}{'delta%':>9}"
          f"   |  fires n   MAE_base  MAE_adj  delta%")
    for stat in ("pts", "reb"):
        sub = oof[oof["stat"] == stat]
        rows = []
        for r in sub.itertuples(index=False):
            cx = ctx.get((int(r.player_id), str(r.game_date)[:10]))
            if cx is None:
                continue
            base = float(r.oof_pred)
            adj = adjust_projection(
                {stat: base}, vac_share=cx["vac_share"],
                game_spread=(abs(cx["margin"]) if cx["margin"] is not None else None),
                coeffs=coeffs)[stat]
            fires = (cx["vac_share"] > 0.05) or (
                cx["margin"] is not None and abs(cx["margin"]) > 14)
            rows.append((abs(base - r.actual), abs(adj - r.actual), fires))
        a = np.array([(x, y) for x, y, _ in rows])
        fmask = np.array([f for _, _, f in rows])
        mae_b, mae_a = a[:, 0].mean(), a[:, 1].mean()
        fb, fa = a[fmask, 0].mean(), a[fmask, 1].mean()
        print(f"{stat:<5}{len(a):>7,d}{mae_b:>10.4f}{mae_a:>10.4f}"
              f"{(mae_b-mae_a)/mae_b*100:>+8.2f}%   |  {fmask.sum():>6,d} "
              f"{fb:>9.4f}{fa:>9.4f}{(fb-fa)/fb*100:>+7.2f}%")
    print("\n'fires' = the subset where a teammate is out (share>0.05) and/or "
          "|margin|>14 — where same-day info matters. Live feed (confirmed "
          "inactives + pre-game spread) is cleaner than this reconstruction.")


if __name__ == "__main__":
    sys.exit(main())
