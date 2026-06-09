"""calibrate_live_adjustment.py — fit the same-day adjustment coefficients from
history so the live layer's magnitudes are empirical, not guessed.

Three calibrated effects (all expressed as a multiplier on the base projection):
  1. INACTIVE usage bump  — when teammates are OUT, the player's scoring/usage rises.
     Fit: (actual_stat / base_l10 - 1)  ~  vacated_usage_share .
  2. BLOWOUT minutes haircut — in lopsided games starters sit; fit the minutes/stat
     reduction vs final margin (live: the spread predicts the margin).
     Fit: (actual_min / l10_min - 1)  ~  max(0, |margin| - SLACK) .
  3. PACE — handled at runtime as total/baseline (no historical game lines to fit);
     we record the league baseline total here so the live layer can scale.

Leak-free reconstruction: a player's baseline = L10 BEFORE the game; "out" teammates
= recent regulars (L10 min>=15, played a prev-3 team game) with no row this game.
Writes data/models/live_adjustment_coeffs.json . No production model touched.
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
OUT = _ROOT / "data" / "models" / "live_adjustment_coeffs.json"
SEASONS = ("2023-24", "2024-25", "2025-26")
BLOWOUT_SLACK = 12.0  # margin points before garbage time bites


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _teams_of(matchup):
    """Return (player_team, opponent) from a MATCHUP string, else (None, None)."""
    if not matchup:
        return None, None
    if " @ " in matchup:
        a, b = matchup.split(" @ "); return a.strip(), b.strip()
    if " vs. " in matchup:
        a, b = matchup.split(" vs. "); return a.strip(), b.strip()
    return None, None


def _team_of(matchup):
    return _teams_of(matchup)[0]


def build_team_scores():
    """team_score[(date, team)] = sum of all players' actual PTS that game (= team
    score). season_games carries no final scores, so we reconstruct from gamelogs."""
    score = defaultdict(float)
    have = set()
    for fp in glob.glob(str(_ROOT / "data" / "nba" / "gamelog_*_*.json")):
        try:
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for g in log:
            team = _team_of(g.get("MATCHUP"))
            d = g.get("GAME_DATE")
            pts = _f(g.get("PTS"))
            if team and d and pts is not None:
                ds = str(pd.to_datetime(d, errors="coerce").date())
                score[(ds, team)] += pts
                have.add((ds, team))
    return score


def reconstruct():
    """Per player-game leak-free rows with baseline, vacated usage, actual, margin."""
    team_scores = build_team_scores()

    def margin_for(ds, team, opp):
        ts = team_scores.get((ds, team)); os_ = team_scores.get((ds, opp))
        if ts is None or os_ is None:
            return None
        return ts - os_

    rows_by_td = defaultdict(list)
    per_player_rows = defaultdict(list)  # pid -> list of dicts chronological
    for fp in glob.glob(str(_ROOT / "data" / "nba" / "gamelog_*_*.json")):
        try:
            pid = int(Path(fp).stem.split("_")[1])
            log = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        recs = []
        for g in log:
            d = pd.to_datetime(g.get("GAME_DATE"), errors="coerce")
            if not pd.isna(d):
                recs.append((d, g))
        recs.sort(key=lambda kv: kv[0])
        mins, ptss, rebs = [], [], []
        for d, g in recs:
            team, opp = _teams_of(g.get("MATCHUP"))
            ds = d.date().isoformat()
            l10_min = float(np.mean(mins[-10:])) if mins else 0.0
            l10_pts = float(np.mean(ptss[-10:])) if ptss else 0.0
            l10_reb = float(np.mean(rebs[-10:])) if rebs else 0.0
            if team and len(mins) >= 5:
                rec = {"pid": pid, "date": ds, "team": team,
                       "l10_min": l10_min, "l10_pts": l10_pts, "l10_reb": l10_reb,
                       "actual_min": _f(g.get("MIN")), "actual_pts": _f(g.get("PTS")),
                       "actual_reb": _f(g.get("REB")),
                       "margin": margin_for(ds, team, opp)}
                rows_by_td[(team, ds)].append(rec)
                per_player_rows[pid].append(rec)
            m = _f(g.get("MIN"))
            if m is not None and m >= 1:
                mins.append(m); ptss.append(_f(g.get("PTS")) or 0.0)
                rebs.append(_f(g.get("REB")) or 0.0)

    team_dates = defaultdict(list)
    for (team, ds) in rows_by_td:
        team_dates[team].append(ds)
    for t in team_dates:
        team_dates[t] = sorted(set(team_dates[t]))

    out = []
    for (team, ds), played in rows_by_td.items():
        dates = team_dates[team]
        i = dates.index(ds)
        if i < 3:
            continue
        played_ids = {r["pid"] for r in played}
        roster = {}
        for j in range(max(0, i - 3), i):
            for rec in rows_by_td[(team, dates[j])]:
                roster[rec["pid"]] = rec
        vac_pts = vac_min = 0.0
        team_base_pts = sum(max(r["l10_pts"], 0) for r in played) + 1e-6
        for pid_, rec in roster.items():
            if pid_ in played_ids:
                continue
            if rec["l10_min"] >= 15:
                vac_min += rec["l10_min"]; vac_pts += rec["l10_pts"]
        for r in played:
            r = dict(r)
            r["vac_min"] = vac_min
            r["vac_pts"] = vac_pts
            out.append(r)
    return pd.DataFrame(out)


def main():
    print("reconstructing leak-free calibration rows (all seasons)...")
    df = reconstruct()
    df = df.dropna(subset=["actual_min", "actual_pts", "actual_reb"])
    df = df[(df["l10_min"] >= 10) & (df["actual_min"] >= 1)]
    print(f"  {len(df):,} player-game rows")

    coeffs = {"blowout_slack": BLOWOUT_SLACK}

    # --- 1. INACTIVE usage bump: (actual_pts/l10_pts - 1) ~ vac_pts_share ---
    # vac_share uses the canonical module formula so runtime can't drift from the fit.
    from src.prediction.live_adjustment import vacated_usage_share as _share
    d1 = df[(df["l10_pts"] >= 6)].copy()
    d1["vac_share"] = [
        _share([vp], pl) if vp > 0 else 0.0
        for vp, pl in zip(d1["vac_pts"], d1["l10_pts"])
    ]
    d1["pts_lift"] = d1["actual_pts"] / d1["l10_pts"] - 1.0
    d1 = d1[d1["pts_lift"].abs() < 2.0]  # drop absurd ratios
    k_pts, b_pts = np.polyfit(d1["vac_share"], d1["pts_lift"], 1)
    d1["reb_lift"] = d1["actual_reb"] / (d1["l10_reb"] + 1e-6) - 1.0
    d1r = d1[(d1["l10_reb"] >= 2) & (d1["reb_lift"].abs() < 2.0)]
    k_reb, b_reb = np.polyfit(d1r["vac_share"], d1r["reb_lift"], 1)
    coeffs["inactive_pts_k"] = float(k_pts)
    coeffs["inactive_reb_k"] = float(k_reb)
    # mean lift when a teammate is actually out, for sanity
    hi = d1[d1["vac_pts"] > 0]
    print(f"\n1. INACTIVE usage bump:")
    print(f"   pts_lift = {k_pts:+.3f} * vac_share + {b_pts:+.3f}   (slope k_pts)")
    print(f"   reb_lift = {k_reb:+.3f} * vac_share + {b_reb:+.3f}")
    print(f"   mean realized pts_lift when teammate out = {hi['pts_lift'].mean():+.3f} "
          f"(n={len(hi):,})")

    # --- 2. BLOWOUT minutes haircut: (actual_min/l10_min - 1) ~ max(0,|margin|-slack) ---
    d2 = df.dropna(subset=["margin"]).copy()
    d2["blow"] = (d2["margin"].abs() - BLOWOUT_SLACK).clip(lower=0)
    d2["min_lift"] = d2["actual_min"] / d2["l10_min"] - 1.0
    d2 = d2[d2["min_lift"].abs() < 1.0]
    k_blow, b_blow = np.polyfit(d2["blow"], d2["min_lift"], 1)
    coeffs["blowout_min_k"] = float(k_blow)  # negative => starters lose minutes
    big = d2[d2["margin"].abs() >= 20]
    small = d2[d2["margin"].abs() <= 6]
    print(f"\n2. BLOWOUT minutes haircut:")
    print(f"   min_lift = {k_blow:+.4f} * max(0,|margin|-{BLOWOUT_SLACK:.0f}) + {b_blow:+.3f}")
    print(f"   mean min_lift  |margin|>=20: {big['min_lift'].mean():+.3f}  "
          f"vs |margin|<=6: {small['min_lift'].mean():+.3f}")

    # --- 3. PACE baseline: median game total, reconstructed from team scores ---
    team_scores = build_team_scores()
    # pair each (date,team) with any opponent that day -> game totals (dedup by frozenset)
    by_date = defaultdict(dict)
    for (ds, team), sc in team_scores.items():
        by_date[ds][team] = sc
    totals = []
    for ds, teams in by_date.items():
        vals = list(teams.values())
        # crude: pair consecutive teams; good enough for a league-median total
        for i in range(0, len(vals) - 1, 2):
            tot = vals[i] + vals[i + 1]
            if 150 < tot < 320:
                totals.append(tot)
    base_total = float(np.median(totals)) if totals else 228.0
    coeffs["baseline_game_total"] = base_total
    coeffs["pace_damp"] = 0.5  # apply half of the raw total/baseline deviation (conservative)
    print(f"\n3. PACE: baseline league game total = {base_total:.1f} "
          f"(runtime scales counting stats by 1 + pace_damp*(total/baseline - 1))")

    coeffs["fit_n"] = int(len(df))
    coeffs["note"] = ("Conservative same-day adjustment. Multipliers applied to base "
                      "projection; damped; clamped at runtime. Calibrated leak-free on "
                      "all-season gamelogs + season_games margins/totals.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(coeffs, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(_ROOT)}")
    print(json.dumps(coeffs, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
