"""BET OPTIMIZER — turn the validated edge into OPTIMAL STAKES + backtested bankroll growth.

Accuracy != edge, and edge != optimal-bankroll. This is the money layer: given the model's prop predictions
vs real lines+odds, it (1) converts pred->P(over/under) with a per-stat residual sigma, (2) Kelly-sizes each
bet, (3) backtests bankroll growth over time at several Kelly fractions, and (4) compares betting EVERYTHING
to a SHARP POLICY restricted to the validated-edge contexts (reg-season; the edge archetypes WING_CREATOR/
THREE_D_WING pts + LEAD_GUARD ast; stable minutes). Reports terminal growth, ROI, hit%, max drawdown, and the
Kelly fraction that maximizes log-growth — the literal "optimize making money" objective, honestly bounded.

Discipline: REGULAR-SEASON only (the edge gate shows playoffs are NEGATIVE — see EDGE_GATE doc); fractional
Kelly (full Kelly over-bets a noisy edge); single-snapshot odds so this is the model-vs-line edge, NOT CLV.

  python scripts/team_system/bet_optimizer.py
"""
from __future__ import annotations
import glob, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
ROLES = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system",
                                     "player_roles.parquet")).set_index("pid")["archetype"].to_dict()
EDGE_ARCH = {"pts": {"WING_CREATOR", "THREE_D_WING", "PRIMARY_BIG", "LEAD_GUARD"},
             "ast": {"LEAD_GUARD", "FLOOR_GENERAL", "SCORING_GUARD"}}   # from the archetype edge screen


def _dec(american):
    a = np.asarray(american, float)
    return np.where(a > 0, 1 + a / 100.0, 1 + 100.0 / np.abs(a))


def load(stat):
    fs = [f for f in glob.glob(os.path.join(PIT, "crosstime_oof_*_oddsapi.parquet")) if stat in f and "regular" in f]
    D = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    D = D.dropna(subset=["line", "over_odds", "under_odds", "actual", "pred"]).copy()
    D["stat"] = stat; D["arch"] = D.pid.map(ROLES)
    return D.sort_values("date").reset_index(drop=True)


def kelly_bets(D, sigma):
    """Per row: model P(side), decimal odds, Kelly fraction f* for the +EV side."""
    p_over = 1.0 - 0.5 * (1 + np.vectorize(lambda z: __import__("math").erf(z))((D.line - D.pred) / (sigma * np.sqrt(2))))
    do, du = _dec(D.over_odds), _dec(D.under_odds)
    # EV of each side; pick the +EV side
    ev_o = p_over * do - 1.0
    ev_u = (1 - p_over) * du - 1.0
    over = ev_o >= ev_u
    p = np.where(over, p_over, 1 - p_over)
    d = np.where(over, do, du)
    fstar = np.clip((p * d - 1) / (d - 1), 0, 1)            # Kelly fraction (0 if no edge)
    # realized outcome at the real odds
    win = np.where(over, D.actual.values > D.line.values, D.actual.values < D.line.values)
    push = D.actual.values == D.line.values
    ret_unit = np.where(push, 0.0, np.where(win, d - 1, -1.0))   # net return per 1u staked
    return pd.DataFrame(dict(date=D.date.values, p=p, d=d, fstar=fstar, ret_unit=ret_unit,
                             ev=np.where(over, ev_o, ev_u), arch=D.arch.values, stat=D.stat.values))


def backtest(bets, kelly_frac, min_ev=0.0, cap=0.1):
    """Grow a bankroll bet-by-bet at fractional Kelly; return growth, ROI, hit%, max drawdown."""
    b = bets[bets.fstar > 0]
    b = b[b.ev >= min_ev]
    if not len(b):
        return dict(n=0, growth=1.0, roi=0.0, hit=0.0, maxdd=0.0)
    bank = 1.0; peak = 1.0; maxdd = 0.0; staked = 0.0; pnl = 0.0
    for f, r in zip(b.fstar.values, b.ret_unit.values):
        stake = min(kelly_frac * f, cap) * bank
        bank += stake * r; staked += stake; pnl += stake * r
        peak = max(peak, bank); maxdd = max(maxdd, (peak - bank) / peak)
    live = b.ret_unit != 0
    return dict(n=int(len(b)), growth=bank, roi=(pnl / staked * 100 if staked else 0.0),
                hit=float((b.ret_unit[live] > 0).mean() * 100 if live.any() else 0), maxdd=maxdd * 100)


def main():
    allbets = {}
    sigmas = {}
    for stat in ("pts", "ast"):
        D = load(stat)
        sigma = float((D.actual - D.pred).std())            # per-stat residual sigma -> P(over)
        sigmas[stat] = sigma
        allbets[stat] = kelly_bets(D, sigma)
        print(f"{stat.upper()}: n={len(D)} residual sigma={sigma:.2f}")
    bets = pd.concat(allbets.values(), ignore_index=True).sort_values("date").reset_index(drop=True)

    print("\n=== KELLY STAKING — bankroll growth on the model-vs-line edge (reg-season, all value bets) ===")
    print(f"{'policy':28s} {'n':>4s} {'ROI%':>7s} {'hit%':>5s} {'growth x':>9s} {'maxDD%':>7s}")
    for fr in (1.0, 0.5, 0.25, 0.1):
        r = backtest(bets, fr, min_ev=0.0)
        print(f"{'all bets, '+str(fr)+'-Kelly':28s} {r['n']:4d} {r['roi']:+7.2f} {r['hit']:5.1f} {r['growth']:9.2f} {r['maxdd']:7.1f}")
    # min-EV gate (only bet a real edge)
    for mev in (0.03, 0.05, 0.08):
        r = backtest(bets, 0.25, min_ev=mev)
        print(f"{'EV>='+str(mev)+', 0.25-Kelly':28s} {r['n']:4d} {r['roi']:+7.2f} {r['hit']:5.1f} {r['growth']:9.2f} {r['maxdd']:7.1f}")

    # SHARP POLICY: restrict to the validated edge archetypes per stat + a real EV gate
    sharp = bets[[a in EDGE_ARCH.get(s, set()) for a, s in zip(bets.arch, bets.stat)]]
    print("\n=== SHARP POLICY — only the edge archetypes (WING_CREATOR/THREE_D_WING/LEAD_GUARD etc.) ===")
    for fr in (0.5, 0.25, 0.1):
        r = backtest(sharp, fr, min_ev=0.03)
        print(f"{'edge-arch EV>=.03, '+str(fr)+'-K':28s} {r['n']:4d} {r['roi']:+7.2f} {r['hit']:5.1f} {r['growth']:9.2f} {r['maxdd']:7.1f}")

    # optimal Kelly fraction by terminal growth (sharp policy)
    grid = [(fr, backtest(sharp, fr, min_ev=0.03)["growth"]) for fr in np.arange(0.05, 1.01, 0.05)]
    best = max(grid, key=lambda x: x[1])
    print(f"\noptimal Kelly fraction (sharp policy, by terminal growth): {best[0]:.2f}  -> {best[1]:.2f}x bankroll")
    print("HONEST: reg-season model-vs-line edge (NOT CLV, NOT playoffs); single-snapshot odds; small n -> "
          "fractional Kelly + the EV gate are the discipline. Playoffs (the Finals) = no edge, do not bet the model.")


if __name__ == "__main__":
    main()
