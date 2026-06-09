"""
Leave-one-out validation: does an OFFENSIVE matchup multiplier (NYK-vs-SAS)
reduce predicted-margin error beyond generic season net ratings?

For each held-out NYK-vs-SAS game (4 total), predict NYK margin two ways:
  BASELINE  : generic season net ratings only (each team's ortg/drtg computed
              from all their games EXCLUDING the 4 H2H games => "vs others"),
              scaled to the held-out game's actual pace.
  MATCHUP   : same, but each team's OFFENSE is scaled by its matchup multiplier
              (ortg_vs_opp / ortg_vs_others) computed ONLY from the OTHER 3 H2H
              games, then shrunk: shrunk = 1 + w*(raw-1), w = n/(n+K), n=3.

Sweep K in {2,4,6,10,20}, pick the K minimizing LOO MAE of the matchup model.
Report margin bias for both. ASCII-only output.

Honesty: only 4 H2H games => leave-one-out trains the matchup mult on n=3 each
time. This is very low statistical power; treat 'wire' cautiously.

DOUBLE-COUNT NOTE: the offensive matchup multiplier here is (ortg vs SAS)/(ortg
vs others), which divides out each team's own offensive quality AND nets out the
generic opponent-defense level (since 'vs others' is the average opponent). It is
therefore the RESIDUAL matchup signal beyond generic team quality and generic
opponent defense -- the part the possession sim does NOT already encode. (The sim
already applies opponent generic defense twice; this residual is orthogonal to
that by construction.)
"""
import pandas as pd

TG = r"C:\Users\neelj\nba-ai-system\data\cache\team_system\team_game.parquet"
LEAGUE_PACE = None  # computed below for context

def per100(pts, poss):
    return 100.0 * pts / poss


def season_off_def_vs_others(df, team, exclude_gids):
    """Generic ortg/drtg from team's games EXCLUDING the H2H gids (i.e. vs all
    OTHER opponents). Possession-weighted per-100, which is the proper aggregate.
    Returns (ortg, drtg)."""
    g = df[(df.team == team) & (~df.gid.isin(exclude_gids))]
    ortg = per100(g.pts.sum(), g.poss.sum())
    drtg = per100(g.opp_pts.sum(), g.opp_poss.sum())
    return ortg, drtg


def off_matchup_mult(df, team, opp, train_gids, K, n=3):
    """raw = ortg(team vs opp over train_gids) / ortg(team vs all others).
    Shrunk toward 1 with w = n/(n+K)."""
    h = df[(df.team == team) & (df.gid.isin(train_gids))]
    ortg_vs_opp = per100(h.pts.sum(), h.poss.sum())
    g = df[(df.team == team) & (~df.gid.isin(set(df[(df.team == team) & (df.opp == opp)].gid)))]
    ortg_vs_others = per100(g.pts.sum(), g.poss.sum())
    raw = ortg_vs_opp / ortg_vs_others
    w = n / (n + K)
    shrunk = 1.0 + w * (raw - 1.0)
    return shrunk, raw, ortg_vs_opp, ortg_vs_others


def main():
    df = pd.read_parquet(TG)
    league_pace = df.poss.mean()

    nyk_h = df[(df.team == "NYK") & (df.opp == "SAS")].sort_values("date").reset_index(drop=True)
    all_h2h_gids = set(nyk_h.gid)
    assert len(nyk_h) == 4, f"expected 4 H2H, got {len(nyk_h)}"

    results = []  # per held-out game

    for K in [2, 4, 6, 10, 20]:
        per_game = []
        for i, row in nyk_h.iterrows():
            test_gid = row.gid
            train_gids = all_h2h_gids - {test_gid}  # other 3 H2H games

            # Generic season net ratings from games EXCLUDING all 4 H2H games.
            nyk_ortg, nyk_drtg = season_off_def_vs_others(df, "NYK", all_h2h_gids)
            sas_ortg, sas_drtg = season_off_def_vs_others(df, "SAS", all_h2h_gids)

            pace = row.poss  # NYK poss in this game (both teams ~ same poss/game)
            opp_pace = row.opp_poss

            # Expected per-100 efficiencies (matchup of off vs opp def, averaged)
            nyk_off_eff_base = 0.5 * (nyk_ortg + sas_drtg)
            sas_off_eff_base = 0.5 * (sas_ortg + nyk_drtg)

            # BASELINE predicted margin (scale efficiency by each team's pace)
            base_nyk_pts = nyk_off_eff_base * pace / 100.0
            base_sas_pts = sas_off_eff_base * opp_pace / 100.0
            pred_margin_base = base_nyk_pts - base_sas_pts

            # MATCHUP: offensive multipliers from the OTHER 3 H2H games, shrunk
            nyk_mult, nyk_raw, _, _ = off_matchup_mult(df, "NYK", "SAS", train_gids, K)
            sas_mult, sas_raw, _, _ = off_matchup_mult(df, "SAS", "NYK", train_gids, K)

            nyk_off_eff_mu = 0.5 * (nyk_ortg * nyk_mult + sas_drtg)
            sas_off_eff_mu = 0.5 * (sas_ortg * sas_mult + nyk_drtg)
            mu_nyk_pts = nyk_off_eff_mu * pace / 100.0
            mu_sas_pts = sas_off_eff_mu * opp_pace / 100.0
            pred_margin_mu = mu_nyk_pts - mu_sas_pts

            actual_margin = row.pts - row.opp_pts

            per_game.append(dict(
                gid=test_gid, date=str(row.date), kind=row.kind,
                actual=actual_margin,
                base=pred_margin_base, mu=pred_margin_mu,
                nyk_mult=nyk_mult, sas_mult=sas_mult,
                nyk_raw=nyk_raw, sas_raw=sas_raw,
            ))
        results.append((K, per_game))

    # ------------ baseline metrics (K-independent) ------------
    base_games = results[0][1]
    base_abs = [abs(g["base"] - g["actual"]) for g in base_games]
    base_bias = sum(g["base"] - g["actual"] for g in base_games) / 4.0
    mae_base = sum(base_abs) / 4.0

    print("=" * 70)
    print("LEAVE-ONE-OUT NYK-vs-SAS MARGIN VALIDATION (n=4 H2H games)")
    print("=" * 70)
    print("league avg pace (poss/game) = %.1f" % league_pace)
    ng = season_off_def_vs_others(df, "NYK", set(nyk_h.gid))
    sg = season_off_def_vs_others(df, "SAS", set(nyk_h.gid))
    print("NYK vs-others ortg/drtg = %.1f / %.1f" % ng)
    print("SAS vs-others ortg/drtg = %.1f / %.1f" % sg)
    print()
    print("BASELINE (generic net ratings only):")
    print("  MAE = %.3f   margin bias = %+.3f" % (mae_base, base_bias))
    print()

    print("MATCHUP sweep over K (n=3 train, w=3/(3+K)):")
    best = None
    for K, per_game in results:
        mu_abs = [abs(g["mu"] - g["actual"]) for g in per_game]
        mu_bias = sum(g["mu"] - g["actual"] for g in per_game) / 4.0
        mae_mu = sum(mu_abs) / 4.0
        w = 3.0 / (3.0 + K)
        flag = ""
        if best is None or mae_mu < best[1]:
            best = (K, mae_mu, mu_bias, per_game)
        print("  K=%2d  w=%.3f  MAE=%.3f  bias=%+.3f" % (K, w, mae_mu, mu_bias))
    print()

    bestK, mae_mu, mu_bias, bg = best
    print("BEST K = %d  ->  matchup MAE = %.3f (baseline %.3f)  bias %+.3f" % (
        bestK, mae_mu, mae_base, mu_bias))
    print()
    print("Per-game (best K=%d): pred vs actual margin (NYK perspective)" % bestK)
    detail_lines = []
    for g in bg:
        line = ("%s %-7s actual %+4d | base %+6.1f (err %5.1f) | matchup %+6.1f (err %5.1f) "
                "[mult NYK %.3f SAS %.3f]") % (
            g["date"], g["kind"], int(g["actual"]),
            g["base"], abs(g["base"] - g["actual"]),
            g["mu"], abs(g["mu"] - g["actual"]),
            g["nyk_mult"], g["sas_mult"])
        print("  " + line)
        detail_lines.append(line)

    improves = mae_mu < mae_base
    rec = "wire" if (improves and (mae_base - mae_mu) > 0.5) else "reject"
    print()
    print("improves=%s  recommendation=%s" % (improves, rec))
    print("raw (unshrunk) matchup mults across LOO folds:")
    for g in bg:
        print("  %s NYK_raw=%.3f SAS_raw=%.3f" % (g["date"], g["nyk_raw"], g["sas_raw"]))

    # emit machine-readable summary
    print()
    print("SUMMARY_JSON_BEGIN")
    import json
    print(json.dumps(dict(
        mae_baseline=round(mae_base, 4),
        mae_matchup=round(mae_mu, 4),
        margin_bias_baseline=round(base_bias, 4),
        margin_bias_matchup=round(mu_bias, 4),
        best_K=int(bestK),
        improves=bool(improves),
        recommendation=rec,
        detail="\n".join(detail_lines),
    )))
    print("SUMMARY_JSON_END")


if __name__ == "__main__":
    main()
