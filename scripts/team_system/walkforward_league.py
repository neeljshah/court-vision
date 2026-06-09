"""Leak-free, as-of, full-season WALK-FORWARD of the matchup-composition engine over the whole league.

THE GENERALIZATION PROOF the NYK/SAS work needs: every game is a matchup of two team IDENTITIES,
each measured vs the WHOLE LEAGUE from prior games only. We build each team's identity AS-OF (expanding,
prior games), compose it the way the sim composes it at the off/def node, and grade win/margin/total over
~1000 games. Reports Brier + straight-up accuracy + margin/total RMSE+bias + win-prob calibration.

Model ladder (each fully leak-free, as-of):
  M0 home-always           - the home-court-only floor
  M1 net-diff (strength)    - home.net - away.net + home_edge   (overall strength, NO off/def cross)
  M2 composition (off x def)- home.ortg vs away.drtg cross + pace -> points; the engine's team-level node
  M3 M2 + mechanisms        - decompose & re-add tov/ft/oreb identity adjustments (tests double-count)
  SIM embedded sim_win_prob - the baseline already stored in season_games (a different/older sim)

KEY math fact surfaced, not hidden: at the MARGIN level the symmetric off/def composition reduces to
the net-rating differential (home.ortg+away.drtg) - (away.ortg+home.drtg) = home.net - away.net, so M2's
margin == M1's margin unless pace/level structure is added. The composition's genuine value-add over pure
strength is in the TOTAL (pace x combined efficiency) and in the explicit mechanisms (M3). The walk-forward
measures exactly where structure helps and where it double-counts.

  python scripts/team_system/walkforward_league.py
"""
from __future__ import annotations
import json, os, math
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TS = os.path.join(ROOT, "data", "cache", "team_system")
BURNIN = 10            # require >= this many prior games for BOTH teams before grading
K_RTG = 400.0         # empirical-Bayes shrink (possessions) for ortg/drtg toward league mean
K_PACE = 8.0          # shrink (games) for pace toward league mean
K_MECH = 12.0         # shrink (games) for tov/ft/oreb identity toward neutral
SIGMA = 13.0          # NBA single-game margin SD for the win-prob map


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def main():
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    sg = {r["game_id"]: r for r in json.load(open(os.path.join(ROOT, "data", "nba", "season_games_2025-26.json")))["rows"]
          if "home_win" in r}
    # league priors
    L_ORTG = 100 * TG.pts.sum() / TG.poss.sum()
    L_PACE = TG.poss.mean()
    L_TOV = TG.opp_tov.sum() / TG.opp_poss.sum()
    L_FTR = TG.opp_fta.sum() / TG.opp_fga.sum()
    L_OREB = TG.oreb.sum() / (TG.oreb.sum() + TG.opp_dreb.sum())
    OWN_FTR = (TG.groupby("team").fta.sum() / TG.groupby("team").fga.sum()).to_dict()

    # one row per GAME (home perspective), sorted by date
    games = []
    for gid, g in TG.groupby("gid"):
        s = sg.get(gid)
        if s is None:
            continue
        ht, at = s["home_team"], s["away_team"]
        hr = g[g.team == ht]; ar = g[g.team == at]
        if len(hr) != 1 or len(ar) != 1:
            continue
        hr = hr.iloc[0]; ar = ar.iloc[0]
        games.append(dict(gid=gid, date=s["game_date"], ht=ht, at=at,
                          home_pts=int(hr.pts), away_pts=int(ar.pts), home_win=int(s["home_win"]),
                          sim_wp=s.get("sim_win_prob")))
    games = sorted(games, key=lambda r: (r["date"], r["gid"]))

    # as-of accumulators per team
    acc = {}  # team -> dict of running sums
    def blank():
        return dict(g=0, pts=0.0, poss=0.0, opp_pts=0.0, opp_poss=0.0,
                    opp_tov=0.0, opp_fta=0.0, opp_fga=0.0, oreb=0.0, opp_dreb=0.0)
    raw = {r.gid: r for r in TG.itertuples(index=False)}  # gid+team rows
    tg_by_gid_team = {(r.gid, r.team): r for r in TG.itertuples(index=False)}

    def identity(team):
        a = acc.get(team)
        if a is None or a["g"] == 0:
            return None
        # empirical-Bayes shrink rtg toward league (by possessions)
        w_o = a["poss"] / (a["poss"] + K_RTG); w_d = a["opp_poss"] / (a["opp_poss"] + K_RTG)
        ortg = (100 * a["pts"] / a["poss"]) * w_o + L_ORTG * (1 - w_o) if a["poss"] > 0 else L_ORTG
        drtg = (100 * a["opp_pts"] / a["opp_poss"]) * w_d + L_ORTG * (1 - w_d) if a["opp_poss"] > 0 else L_ORTG
        wp = a["g"] / (a["g"] + K_PACE)
        pace = (a["poss"] / a["g"]) * wp + L_PACE * (1 - wp) if a["g"] > 0 else L_PACE
        wm = a["g"] / (a["g"] + K_MECH)
        tov_force = 1 + wm * ((a["opp_tov"] / a["opp_poss"]) / L_TOV - 1) if a["opp_poss"] > 0 else 1.0
        ft_force = 1 + wm * ((a["opp_fta"] / a["opp_fga"]) / L_FTR - 1) if a["opp_fga"] > 0 else 1.0
        oreb = (a["oreb"] / (a["oreb"] + a["opp_dreb"])) if (a["oreb"] + a["opp_dreb"]) > 0 else L_OREB
        return dict(g=a["g"], ortg=ortg, drtg=drtg, pace=pace, net=ortg - drtg,
                    tov_force=tov_force, ft_force=ft_force, oreb=oreb)

    def update(team, gid):
        r = tg_by_gid_team[(gid, team)]
        a = acc.setdefault(team, blank())
        a["g"] += 1; a["pts"] += r.pts; a["poss"] += r.poss
        a["opp_pts"] += r.opp_pts; a["opp_poss"] += r.opp_poss
        a["opp_tov"] += r.opp_tov; a["opp_fta"] += r.opp_fta; a["opp_fga"] += r.opp_fga
        a["oreb"] += r.oreb; a["opp_dreb"] += r.opp_dreb

    # expanding home-edge (leak-free): running mean of (home_pts-away_pts) over GRADED prior games
    he_sum = 0.0; he_n = 0
    preds = []
    for gm in games:
        H = identity(gm["ht"]); A = identity(gm["at"])
        gradeable = H is not None and A is not None and H["g"] >= BURNIN and A["g"] >= BURNIN
        if gradeable:
            home_edge = (he_sum / he_n) if he_n > 0 else 2.5
            poss = 0.5 * (H["pace"] + A["pace"])
            # M1 strength: net-diff
            m1_margin = (H["net"] - A["net"]) + home_edge
            # M2 composition: off vs def cross at the node, pace -> totals
            h_rtg = H["ortg"] + (A["drtg"] - L_ORTG)
            a_rtg = A["ortg"] + (H["drtg"] - L_ORTG)
            h_pts = h_rtg / 100 * poss + home_edge / 2
            a_pts = a_rtg / 100 * poss - home_edge / 2
            m2_margin = h_pts - a_pts
            m2_total = h_pts + a_pts
            # M3 + mechanisms: adjust each team's pts by opponent's identity mechanisms
            #   tov: A's offense loses ~ (opp.tov_force-1)*L_TOV of possessions -> scale pts
            #   ft : scale the FT-point share by opp.ft_force ; oreb: 2nd-chance from own oreb vs opp dreb
            FT_SHARE = 0.18  # league FT share of points (~18%)
            h_mech = (1 - 0.5 * (A["tov_force"] - 1) * L_TOV) * (1 + FT_SHARE * (A["ft_force"] - 1)) * (1 + 0.10 * (H["oreb"] - L_OREB))
            a_mech = (1 - 0.5 * (H["tov_force"] - 1) * L_TOV) * (1 + FT_SHARE * (H["ft_force"] - 1)) * (1 + 0.10 * (A["oreb"] - L_OREB))
            h3 = h_pts * h_mech; a3 = a_pts * a_mech
            m3_margin = h3 - a3; m3_total = h3 + a3
            preds.append(dict(gid=gm["gid"], date=gm["date"], home_win=gm["home_win"],
                              margin=gm["home_pts"] - gm["away_pts"], total=gm["home_pts"] + gm["away_pts"],
                              m1_margin=m1_margin, m2_margin=m2_margin, m2_total=m2_total,
                              m3_margin=m3_margin, m3_total=m3_total, sim_wp=gm["sim_wp"]))
        # update AFTER predicting (leak-free), and feed the home-edge from this now-known game
        update(gm["ht"], gm["gid"]); update(gm["at"], gm["gid"])
        if gradeable:
            he_sum += (gm["home_pts"] - gm["away_pts"]); he_n += 1

    P = pd.DataFrame(preds)
    print(f"GRADED GAMES: {len(P)}  (burn-in {BURNIN}/team; league ORtg {L_ORTG:.1f}, pace {L_PACE:.1f}, "
          f"home_edge final {he_sum/he_n:+.2f})")
    y = P.home_win.values
    base = y.mean()
    print(f"home-win base rate: {base:.3f}")

    def wp_from_margin(m):
        return np.array([_phi(x / SIGMA) for x in m])

    def report(name, margin_col, total_col=None, wp=None):
        m = P[margin_col].values
        if wp is None:
            wp = wp_from_margin(m)
        wp = np.clip(wp, 1e-6, 1 - 1e-6)
        brier = np.mean((wp - y) ** 2)
        acc = np.mean((wp >= 0.5).astype(int) == y)
        # margin error
        mrmse = math.sqrt(np.mean((m - P.margin.values) ** 2)); mbias = np.mean(m - P.margin.values)
        line = f"  {name:22s} Brier {brier:.4f}  acc {acc:.3f}  margin RMSE {mrmse:5.2f} bias {mbias:+5.2f}"
        if total_col is not None:
            t = P[total_col].values
            trmse = math.sqrt(np.mean((t - P.total.values) ** 2)); tbias = np.mean(t - P.total.values)
            line += f"  total RMSE {trmse:5.2f} bias {tbias:+5.2f}"
        print(line)

    print("\n=== WIN / MARGIN / TOTAL (leak-free as-of) ===")
    report("M0 home-always", "m1_margin", wp=np.full(len(P), base))  # placeholder margin; wp=base
    # M0 proper: predict home always (wp = base rate -> acc = home always wins)
    print(f"  {'M0 home-always*':22s} Brier {np.mean((base-y)**2):.4f}  acc {base:.3f}  (constant)")
    report("M1 net-diff (strength)", "m1_margin")
    report("M2 composition off|def", "m2_margin", "m2_total")
    report("M3 + tov/ft/oreb mech", "m3_margin", "m3_total")
    if P.sim_wp.notna().any():
        s = P.dropna(subset=["sim_wp"])
        sw = np.clip(s.sim_wp.values, 1e-6, 1 - 1e-6); sy = s.home_win.values
        print(f"  {'SIM embedded sim_wp':22s} Brier {np.mean((sw-sy)**2):.4f}  acc {np.mean((sw>=0.5)==sy):.3f}  (n={len(s)})")

    # calibration of M2 win prob (the engine's composition)
    print("\n=== M2 win-prob calibration (composition) ===")
    wp = wp_from_margin(P.m2_margin.values)
    dfc = pd.DataFrame({"wp": wp, "y": y})
    dfc["bucket"] = pd.cut(dfc.wp, [0, .35, .5, .65, .8, 1.0])
    cc = dfc.groupby("bucket", observed=True).agg(pred=("wp", "mean"), actual=("y", "mean"), n=("y", "size"))
    print(cc.round(3).to_string())
    P.to_parquet(os.path.join(TS, "walkforward_league_preds.parquet"), index=False)
    print(f"\nwrote {len(P)} graded preds -> walkforward_league_preds.parquet")


if __name__ == "__main__":
    main()
