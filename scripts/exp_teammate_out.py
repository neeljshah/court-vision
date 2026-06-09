"""exp_teammate_out.py — THE causal test: does "a regular teammate is OUT tonight"
(minutes + usage vacated to this player) explain the PTS/REB OOF residual OOS?

Minutes-surprise drives the error; its predictable cause is same-night absences.
We reconstruct, leak-free, for each player-game:
  vacated_min = sum of L10 minutes of team regulars who did NOT play this game
  vacated_pts = same for L10 points (usage proxy)
  n_out       = count of such absent regulars
A "regular" = teammate whose as-of L10 min >= 15 and who played >=1 of the team's
previous 3 games. Everything is computed from prior games only.

Then test: does an XGB correction on these signals reduce OOF MAE on a future
hold-out? If yes, THIS is the signal to wire into PTS/REB. GPU XGB; no prod model.
"""
from __future__ import annotations

import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
SPLIT = "2026-02-15"
SEASON = "2025-26"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _team_of(matchup):
    if not matchup:
        return None
    if " @ " in matchup:
        return matchup.split(" @ ")[0].strip()
    if " vs. " in matchup:
        return matchup.split(" vs. ")[0].strip()
    return None


def build():
    """Return df of player-game rows with vacated_* signals + a (pid,date)->row map."""
    # Pass 1: per player, chronological, as-of L10 min/pts BEFORE each game.
    # rows_by_team_date[(team,date)] = list of dicts {pid, l10_min, l10_pts, played:1}
    rows_by_td = defaultdict(list)
    player_games = []  # (pid, date, team, l10_min, l10_pts)
    for fp in glob.glob(str(_ROOT / "data" / "nba" / f"gamelog_*_{SEASON}.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        # sort chronological
        recs = []
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            if pd.isna(d):
                continue
            recs.append((d, g))
        recs.sort(key=lambda kv: kv[0])
        mins, ptss = [], []
        for d, g in recs:
            team = _team_of(g.get("MATCHUP"))
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            ds = d.date().isoformat()
            if team:
                rows_by_td[(team, ds)].append(
                    {"pid": pid, "l10_min": l10_min, "l10_pts": l10_pts})
                player_games.append((pid, ds, team, l10_min, l10_pts))
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)

    # team -> sorted unique dates
    team_dates = defaultdict(list)
    for (team, ds) in rows_by_td:
        team_dates[team].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    # roster regulars per (team,date): players with row in any of previous 3 team-dates
    def recent_roster(team, ds):
        dates = team_dates[team]
        i = dates.index(ds)
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(team, dates[j])]:
                roster[rec["pid"]] = rec  # last seen l10 carries
        return roster

    out_rows = []
    for (team, ds), played in rows_by_td.items():
        if ds not in team_dates[team]:
            continue
        if team_dates[team].index(ds) < 3:
            continue  # need history
        played_ids = {r["pid"] for r in played}
        roster = recent_roster(team, ds)
        # absent regulars
        vac_min = vac_pts = 0.0
        n_out = 0
        for pid, rec in roster.items():
            if pid in played_ids:
                continue
            if rec["l10_min"] >= 15:
                vac_min += rec["l10_min"]; vac_pts += rec["l10_pts"]; n_out += 1
        for r in played:
            out_rows.append({
                "pid": r["pid"], "date": ds,
                "vac_min": vac_min, "vac_pts": vac_pts, "n_out": n_out,
                "own_l10_min": r["l10_min"],
            })
    return pd.DataFrame(out_rows)


def main():
    print("reconstructing rosters / vacated-minutes signal...")
    sig = build()
    print(f"  player-game rows with signal: {len(sig):,}")
    games_with_out = (sig["n_out"] > 0).mean() * 100
    print(f"  {games_with_out:.0f}% of player-games have >=1 regular teammate OUT "
          f"(mean vacated_min on those = "
          f"{sig.loc[sig['n_out']>0,'vac_min'].mean():.1f})")

    oof = pd.read_parquet(OOF)
    oof = oof[oof["game_date"].astype(str) >= "2025-10-01"].copy()
    oof["date"] = oof["game_date"].astype(str).str[:10]
    oof = oof.rename(columns={"player_id": "pid"})

    FEATS = ["vac_min", "vac_pts", "n_out", "own_l10_min"]
    for stat in ("pts", "reb"):
        d = oof[oof["stat"] == stat].merge(sig, on=["pid", "date"], how="inner")
        d["resid"] = d["actual"] - d["oof_pred"]
        tr = d[d["date"] < SPLIT]; te = d[d["date"] >= SPLIT]
        if len(te) < 200:
            print(f"[{stat}] too few test rows"); continue
        params = {"objective": "reg:absoluteerror", "max_depth": 4, "eta": 0.03,
                  "subsample": 0.8, "colsample_bytree": 0.8,
                  "device": "cuda", "tree_method": "hist"}
        try:
            bst = xgb.train(params, xgb.DMatrix(tr[FEATS], label=tr["resid"]),
                            num_boost_round=300)
        except Exception as exc:
            print(f"[cuda->cpu {exc}]"); params["device"] = "cpu"
            bst = xgb.train(params, xgb.DMatrix(tr[FEATS], label=tr["resid"]),
                            num_boost_round=300)
        corr = bst.predict(xgb.DMatrix(te[FEATS]))
        base = te["resid"].abs().mean()
        full = (te["resid"].values - corr).__abs__().mean()
        half = (te["resid"].values - 0.5 * corr).__abs__().mean()
        # restrict to the games where a teammate is actually out (where it should matter)
        mask = te["n_out"].values > 0
        base_o = np.abs(te["resid"].values[mask]).mean()
        full_o = np.abs(te["resid"].values[mask] - corr[mask]).mean()
        print(f"\n{stat.upper()} (train n={len(tr):,}, test n={len(te):,}):")
        print(f"  OOF MAE                         : {base:.4f}")
        print(f"  OOF + vacated correction        : {full:.4f}  ({(base-full)/base*100:+.2f}%)")
        print(f"  OOF + 0.5x vacated (damped)     : {half:.4f}  ({(base-half)/base*100:+.2f}%)")
        print(f"  --- on the {mask.sum():,} games with a teammate OUT ---")
        print(f"  OOF MAE                         : {base_o:.4f}")
        print(f"  OOF + correction                : {full_o:.4f}  ({(base_o-full_o)/base_o*100:+.2f}%)")
        imp = bst.get_score(importance_type="gain")
        print(f"  feature gain: {imp}")


if __name__ == "__main__":
    sys.exit(main())
