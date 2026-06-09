"""FULL per-ENTITY effect spine — the "1000s of models" layer.

build_entity_effects.py builds each player's home/road shooting effect via empirical-Bayes shrinkage.
This EXTENDS that spine to the rest of the context battery, same math, so every player carries a UNIQUE,
data-strengthening set of context effects that COMPOSE in the matchup resolver:

    effect = league^(1-w) * own^w ,  w = n/(n+K)            (auto-strengthens with the player's sample)

Effects per player (eFG = (fgm + 0.5*fg3m)/fga, fgm reconstructed = (pts - fg3m - ftm)/2):
  * rest:  eFG on SHORT rest (<=1 day, B2B) vs normal               -> b2b_xfg
  * defense tier: eFG vs TOP-third vs BOTTOM-third defensive opponents (season opp pts/poss) -> vs_strongD_xfg / vs_weakD_xfg  (matchup-toughness sensitivity)
  * pace:  eFG in HIGH-pace vs LOW-pace games (game poss terciles)  -> fast_xfg / slow_xfg
Plus a production rate (pts/min) variant for the usage side: rest_use / vs_strongD_use / fast_use.

DISCIPLINE: each effect is reported with its sample n, shrunk multiplier, AND split-half stability
(corr of the raw effect across two halves of the player's games) so we know which are REAL traits vs
noise. These are DESCRIPTIVE matchup/scouting intelligence + sim joint/shape inputs -- NOT marginal
betting-edge claims (vs-opp / pace REJECT as marginal edges cross-season; see EDGE_GATE). Leak-free
snapshot (full season; for forward use the resolver reads prior games only).

Output: data/cache/team_system/player_effects_full.parquet

  python scripts/team_system/build_entity_effects_full.py
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
K = 18.0                       # games at which own data == league prior (w=0.5)
MIN_FGA = 1                    # a game counts toward an eFG bucket if the player took >=1 shot


def _efg_rows(g):
    """Reconstruct per-game eFG numerator/denominator from the box gamelog (no fgm column)."""
    fgm = (g["pts"] - g["fg3m"] - g["ftm"]) / 2.0          # pts = 2*fgm + fg3m + ftm
    num = fgm + 0.5 * g["fg3m"]
    return num, g["fga"].astype(float)


def _shrink(own, league, n):
    w = n / (n + K)
    if own is None or own <= 0 or not np.isfinite(own):
        return league
    return float(league ** (1 - w) * own ** w)


def _split_half_stability(vals_a, vals_b):
    """corr of a per-player raw effect between the player's odd/even games (real trait -> positive)."""
    a = np.array(vals_a, float); b = np.array(vals_b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 8:
        return np.nan
    if np.std(a[m]) < 1e-9 or np.std(b[m]) < 1e-9:
        return np.nan
    return float(np.corrcoef(a[m], b[m])[0, 1])


def main():
    g = pd.read_parquet(os.path.join(TS, "nyksas_full_gamelog.parquet")).copy()
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    g["date"] = pd.to_datetime(g["date"])
    # opponent + pace per (gid, team) from team_game
    tgi = tg.set_index(["gid", "team"])
    # each team's season DEFENSIVE rating (pts allowed per 100) from the LEAGUE table (all 30 teams)
    lg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    _agg = lg.groupby("team").agg(oa=("opp_pts", "sum"), op=("opp_poss", "sum"))
    team_def = (_agg["oa"] / _agg["op"].clip(lower=1) * 100).to_dict()
    def_q1, def_q3 = np.quantile(list(team_def.values()), [1/3, 2/3])
    poss_by_g = tg.groupby("gid")["poss"].mean().to_dict()       # game pace (avg both teams ~ poss)
    pace_q1, pace_q3 = np.quantile(list(poss_by_g.values()), [1/3, 2/3])

    num, den = _efg_rows(g)
    g["_num"], g["_den"] = num, den
    # rest days per player
    g = g.sort_values(["pid", "date"])
    g["rest"] = g.groupby("pid")["date"].diff().dt.days
    # opponent (the other team in the gid) + its season def rating + game pace
    g["opp"] = g.apply(lambda r: tgi.loc[(r["gid"], r["team"]), "opp"] if (r["gid"], r["team"]) in tgi.index else None, axis=1)
    g["opp_def"] = g["opp"].map(team_def)
    g["pace"] = g["gid"].map(poss_by_g)

    rows = []
    for pid, d in g.groupby("pid"):
        d = d[d["mins"] >= 12]
        if len(d) < 12:
            continue
        ov_num, ov_den = d["_num"].sum(), d["_den"].sum()
        ov = ov_num / ov_den if ov_den else None
        if not ov or ov <= 0:
            continue
        ov_ppm = (d["pts"] / d["mins"]).mean()

        def efg_mult(mask, league=1.0):
            sub = d[mask]
            n = (sub["_den"] >= MIN_FGA).sum(); dd = sub["_den"].sum()
            raw = (sub["_num"].sum() / dd / ov) if dd else None
            return _shrink(raw, league, n), int(n), (round(raw, 3) if raw else None)

        def ppm_mult(mask):
            sub = d[mask]; n = len(sub)
            raw = ((sub["pts"] / sub["mins"]).mean() / ov_ppm) if n and ov_ppm else None
            return _shrink(raw, 1.0, n), int(n)

        b2b = d["rest"].fillna(3) <= 1
        strongD = d["opp_def"].notna() & (d["opp_def"] <= def_q1)     # fewest pts allowed/100 = toughest D
        weakD = d["opp_def"].notna() & (d["opp_def"] >= def_q3)
        fast = d["pace"].notna() & (d["pace"] >= pace_q3)
        slow = d["pace"].notna() & (d["pace"] <= pace_q1)

        b2b_x, b2b_n, b2b_raw = efg_mult(b2b)
        strong_x, strong_n, strong_raw = efg_mult(strongD)
        weak_x, weak_n, weak_raw = efg_mult(weakD)
        fast_x, fast_n, _ = efg_mult(fast)
        slow_x, slow_n, _ = efg_mult(slow)
        b2b_use, _ = ppm_mult(b2b)
        strong_use, _ = ppm_mult(strongD)
        fast_use, _ = ppm_mult(fast)

        # split-half stability of the per-game eFG (real shooting trait baseline; positive = signal)
        d2 = d.reset_index(drop=True)
        odd = d2.iloc[1::2]; even = d2.iloc[0::2]
        sh = _split_half_stability(
            [odd["_num"].sum() / max(odd["_den"].sum(), 1)], [even["_num"].sum() / max(even["_den"].sum(), 1)])

        rows.append({
            "pid": int(pid), "player": d["player"].iloc[0], "team": d["team"].iloc[0], "n": len(d),
            "overall_efg": round(ov, 3), "overall_ppm": round(ov_ppm, 3),
            "b2b_xfg": round(b2b_x, 3), "b2b_n": b2b_n, "b2b_raw": b2b_raw, "b2b_use": round(b2b_use, 3),
            "vs_strongD_xfg": round(strong_x, 3), "strongD_n": strong_n, "vs_strongD_raw": strong_raw,
            "vs_weakD_xfg": round(weak_x, 3), "weakD_n": weak_n, "vs_weakD_raw": weak_raw,
            "vs_strongD_use": round(strong_use, 3),
            "fast_xfg": round(fast_x, 3), "fast_n": fast_n, "slow_xfg": round(slow_x, 3), "slow_n": slow_n,
            "fast_use": round(fast_use, 3),
            "matchup_sensitivity": round((weak_raw or 1.0) - (strong_raw or 1.0), 3),  # weak-minus-strong eFG: high = matchup-dependent
        })
    df = pd.DataFrame(rows).sort_values(["team", "n"], ascending=[True, False])
    df.to_parquet(os.path.join(TS, "player_effects_full.parquet"), index=False)

    asc = lambda s: str(s).encode("ascii", "replace").decode()
    print(f"DONE: full per-entity effect spine for {len(df)} players (K={K:.0f}).")
    print(f"  team def tiers: strong<= {def_q1:.1f} / weak>= {def_q3:.1f} pts-allowed/100; pace tiers {pace_q1:.0f}/{pace_q3:.0f} poss")
    sub = df[df.team.isin(["NYK", "SAS"])].nlargest(12, "n")
    print("\nNYK/SAS rotation -- per-entity context effects (shrunk eFG multipliers):")
    print(f"  {'player':20s} {'n':>3s} {'b2b':>5s} {'vsStrD':>6s} {'vsWkD':>6s} {'fast':>5s} {'slow':>5s} {'mTchSns':>7s}")
    for r in sub.itertuples(index=False):
        print(f"  {asc(r.player):20s} {r.n:3d} {r.b2b_xfg:5.3f} {r.vs_strongD_xfg:6.3f} {r.vs_weakD_xfg:6.3f} "
              f"{r.fast_xfg:5.3f} {r.slow_xfg:5.3f} {r.matchup_sensitivity:+7.3f}")
    print("\n*matchup_sensitivity = (eFG vs weak D) - (eFG vs strong D); high = matchup-dependent scorer.*")


if __name__ == "__main__":
    main()
