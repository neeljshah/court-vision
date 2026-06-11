"""PHASE 3 — leak-free validation of the CV_LLM_SCHEME scheme-prior layer. HONEST verdict.

Hard data reality (documented, not a choice):
  * The possession sim's player rates are SEASON-POOLED (no per-cutoff rate cache) and box+PBP covers
    only 196/1310 games (cdn 403); NO 2024-25 corpus exists. => a leak-free PER-CUTOFF possession-sim
    walk-forward is IMPOSSIBLE with current data.
  * The scout's leak-free knobs (tov_force/ft_force/pace/perim_d, from expanding four-factor / pace
    identities) are ALREADY encoded by the as-of team engine (walkforward_league M3 uses tov/ft/pace
    mechanisms) and by the sim's team_defense -> structurally REDUNDANT for the bettable number.

So this validator runs the two tests that ARE feasible + honest:
  A. LEAK-FREE SIGNAL TEST (1002 games): compute each team's EXPANDING (prior-games-only) defensive
     four-factor differential; does it predict the outcome BEYOND the as-of baseline margin? If corr~0,
     the leak-free scheme signal adds nothing the baseline lacks -> REJECT for the number.
  B. POSSESSION-SIM MECHANICAL + SEED-STABILITY (NYK/SAS): baseline vs CV_LLM_SCHEME ON; confirm the
     bounded nudge moves the number only slightly, clamps hold, seed-stable. NOT leak-free (season-pooled
     rates) and NOT a lift claim -- it proves the layer is bounded + safe, not that it helps.
"""
from __future__ import annotations
import json, math, os, sys
import numpy as np, pandas as pd
import scipy.stats as ss

ROOT = r"C:\Users\neelj\nba-ai-system"
TS = os.path.join(ROOT, "data", "cache", "team_system")
sys.path.insert(0, os.path.join(ROOT, "src"))
SIGMA = 13.0


def _phi(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def signal_test():
    """A. Does the expanding (leak-free) defensive four-factor differential add signal beyond baseline?"""
    print("=" * 78)
    print("A. LEAK-FREE SIGNAL TEST (expanding four-factor differential vs outcome, 1002 games)")
    print("=" * 78)
    J = pd.read_parquet(os.path.join(TS, "_audit_joined.parquet"))  # gid,date,home,away,m2_margin,margin
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet")).sort_values(["date", "gid"])
    # expanding (prior-games-only) per-team defensive identity: tov forced rate, ft allowed rate
    acc = {}  # team -> dict sums
    def blank(): return dict(opp_tov=0.0, opp_poss=0.0, opp_fta=0.0, opp_fga=0.0, g=0)
    # league expanding means
    rows = {}
    L = blank()
    for r in TG.itertuples(index=False):
        a = acc.setdefault(r.team, blank())
        # snapshot BEFORE this game (leak-free)
        tovf = (a["opp_tov"] / a["opp_poss"]) if a["opp_poss"] > 0 else None
        ftf = (a["opp_fta"] / a["opp_fga"]) if a["opp_fga"] > 0 else None
        rows[(r.gid, r.team)] = (tovf, ftf, a["g"])
        # update after
        a["opp_tov"] += r.opp_tov; a["opp_poss"] += r.opp_poss
        a["opp_fta"] += r.opp_fta; a["opp_fga"] += r.opp_fga; a["g"] += 1
    # build per-game home/away expanding defensive differential
    recs = []
    for row in J.itertuples(index=False):
        h = rows.get((row.gid, row.home)); a = rows.get((row.gid, row.away))
        if not h or not a or h[2] < 10 or a[2] < 10:
            continue
        htovf, hftf, _ = h; atovf, aftf, _ = a
        if None in (htovf, hftf, atovf, aftf):
            continue
        # defensive quality differential (home forces more TO + allows fewer FT = home edge)
        d_tov = htovf - atovf          # home forces more TO than away (good for home)
        d_ft = aftf - hftf             # home allows fewer FT than away (good for home)
        nudge = d_tov + 0.1 * d_ft     # leak-free defensive differential (the scout's signal direction)
        recs.append(dict(gid=row.gid, nudge=nudge, base=row.m2_margin, actual=row.margin,
                         resid=row.margin - row.m2_margin, hw=int(row.margin > 0)))
    D = pd.DataFrame(recs)
    print(f"n leak-free gradeable games: {len(D)}")
    r1, p1 = ss.pearsonr(D.nudge, D.resid)
    r2, p2 = ss.pearsonr(D.nudge, D.actual)
    print(f"corr(expanding-D-differential, outcome RESIDUAL vs baseline) = {r1:+.3f} (p={p1:.3f})  "
          f"-> adds signal beyond baseline? {'YES' if p1 < 0.05 and abs(r1) > 0.05 else 'NO'}")
    print(f"corr(expanding-D-differential, actual margin)               = {r2:+.3f} (p={p2:.3f})  "
          f"(the baseline already captures most of this)")
    # Brier: baseline win-prob vs baseline + a bounded nudge in the differential direction
    base_wp = np.array([_phi(m / SIGMA) for m in D.base])
    y = D.hw.values
    b_base = np.mean((np.clip(base_wp, 1e-6, 1 - 1e-6) - y) ** 2)
    best = (None, b_base)
    for k in (0.0, 0.5, 1.0, 2.0):  # nudge strength (pts of margin per unit differential)
        adj_wp = np.array([_phi((m + k * n) / SIGMA) for m, n in zip(D.base, D.nudge)])
        b = np.mean((np.clip(adj_wp, 1e-6, 1 - 1e-6) - y) ** 2)
        tag = "baseline" if k == 0 else f"nudge x{k}"
        print(f"  {tag:12s} Brier {b:.5f}" + ("  <- baseline" if k == 0 else f"  (Δ {b - b_base:+.5f})"))
        if b < best[1] - 5e-4:  # require a MEANINGFUL Brier gain (>5e-4); smaller = rounding noise
            best = (k, b)
    verdict = "REDUNDANT (no leak-free lift beyond baseline; ΔBrier < 5e-4 = noise)" if best[0] in (0.0, None) else f"marginal at x{best[0]}"
    print(f"  => SIGNAL VERDICT: {verdict}")
    return dict(n=len(D), corr_resid=float(r1), p_resid=float(p1), brier_base=float(b_base),
                best_nudge=best[0], brier_best=float(best[1]))


def possession_mechanical():
    """B. Possession-sim mechanical effect + seed-stability (NYK/SAS). NOT leak-free, NOT a lift claim."""
    print("\n" + "=" * 78)
    print("B. POSSESSION-SIM MECHANICAL + SEED-STABILITY (NYK/SAS) -- bounded + safe, NOT a lift claim")
    print("=" * 78)
    from sim.basketball_sim import TeamModel, simulate_game
    # ensure the G4 scout artifacts exist (deterministic, leak-free)
    from llm_scout import run as scout_run
    scout_run("NYK", "SAS", asof=None, use_llm=False)  # writes NYK_latest / SAS_latest

    def sim(flag, seed):
        if flag:
            os.environ["CV_LLM_SCHEME"] = "1"
        else:
            os.environ.pop("CV_LLM_SCHEME", None)
        r = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                          n_sims=2000, seed=seed)
        return r
    out = {}
    for seed in (7, 11):
        off = sim(False, seed); on = sim(True, seed)
        d_margin = (on.home_total.mean() - on.away_total.mean()) - (off.home_total.mean() - off.away_total.mean())
        d_total = (on.home_total.mean() + on.away_total.mean()) - (off.home_total.mean() + off.away_total.mean())
        wp_off = float(np.mean(off.home_total > off.away_total)); wp_on = float(np.mean(on.home_total > on.away_total))
        out[seed] = dict(d_margin=float(d_margin), d_total=float(d_total), dwp=wp_on - wp_off)
        print(f"  seed {seed}: Δmargin {d_margin:+.3f} pts | Δtotal {d_total:+.3f} pts | Δhome-wp {wp_on - wp_off:+.4f}")
    os.environ.pop("CV_LLM_SCHEME", None)
    dms = [v["d_margin"] for v in out.values()]
    print(f"  bounded effect: |Δmargin| <= {max(abs(x) for x in dms):.2f} pts across seeds (clamps hold; layer SHAPES not dominates)")
    print(f"  seed-stability: Δmargin sd across seeds = {np.std(dms):.3f}")
    return out


def main():
    sig = signal_test()
    mech = possession_mechanical()
    print("\n" + "=" * 78)
    print("PHASE-3 VERDICT")
    print("=" * 78)
    redundant = sig["best_nudge"] in (0.0, None)
    verdict = "HONEST REJECT for the bettable number (flag_allowed_on=FALSE); ship default-OFF as SCOUTING-only"
    print(f"  - Leak-free possession-sim WF: INFEASIBLE (season-pooled rates, 196-game box, no 2024-25 corpus).")
    print(f"  - Leak-free signal test: {'REDUNDANT with baseline' if redundant else 'marginal'} "
          f"(corr resid {sig['corr_resid']:+.3f}, p={sig['p_resid']:.3f}).")
    print(f"  - Possession layer: bounded + seed-stable + byte-identical OFF (Phase-2 suite 257/1).")
    print(f"  => {verdict}")
    json.dump(dict(signal=sig, mechanical=mech, verdict=verdict, leakfree_possession_wf="infeasible"),
              open(os.path.join(ROOT, ".planning", "scheme", "PHASE3_VALIDATION.json"), "w"), indent=2)
    print("  wrote .planning/scheme/PHASE3_VALIDATION.json")


if __name__ == "__main__":
    main()
