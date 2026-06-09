"""Night-loop: SIZE the star upper-tail right-skew fix (measurement-only, does NOT touch the engine).

The possession MC's per-player pts shock (_apply_dispersion) is a mean-1 lognormal sigma~0.20, damped
further by the team-total hold -> the resulting per-star pts distribution is too SYMMETRIC about a correct
mean. measure_signal upper_tail found the signature: actual pts > sim q90 17.0% (target 10%) and < sim q10
only 3.7% (target 10%) on 270 starter-games -> reality is RIGHT-SKEWED (mode below mean, long upper tail).

This harness collects (actual, sim-samples) per star ONCE (the GPU sim, ~2 min), then sweeps a
mean-preserving right-skew WARP strength s applied post-hoc to each player's sim samples, recomputes that
player's q10/q90, and re-tallies the tail exceedance rates. It reports the s that lands BOTH tails nearest
10%, plus the variance inflation that s implies. SELF-VALIDATES: at s=0 the warp is the identity, so it MUST
reproduce the baseline 17%/3.7% (a faithfulness check printed up top); and the warp re-pins each mean exactly
(marginals unchanged) just like the engine. The sized s is a CANDIDATE for human review -- the engine fix is
to add this skew to the lognormal shock in _apply_dispersion while keeping the team-total hold + mean re-pin.
ascii-only prints.

  python scripts/team_system/nightloop/measure_skew.py
  python scripts/team_system/nightloop/measure_skew.py --stride 2 --nsims 6000
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))
from build_player_rates import _pstat  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

TS = os.path.join(ROOT, "data", "cache", "team_system")
BOX = os.path.join(TS, "box")
MINE = {"NYK", "SAS"}


def right_skew_warp(x, s):
    """Mean-PRESERVING right-skew warp of sample array x by strength s>=0 (s=0 -> identity).

    Convex warp of the standardized deviations: w = (exp(s*z/sd)-1)/s, which stretches positive deviations
    and compresses negative ones (a longer upper tail, a shorter lower tail = right skew) while s->0 gives
    the identity. The mean is re-pinned exactly afterward (and again after the >=0 clip) so the marginal
    never moves -- identical contract to the engine's _apply_dispersion (mean re-pinned LAST)."""
    x = np.asarray(x, dtype=float)
    m = float(x.mean())
    z = x - m
    sd = float(z.std()) + 1e-9
    u = z / sd
    if s <= 1e-9:
        w = u
    else:
        w = (np.exp(np.clip(s * u, -20.0, 20.0)) - 1.0) / s
    z2 = w * sd
    x2 = z2 - float(z2.mean()) + m       # re-pin mean exactly
    x2 = np.maximum(x2, 0.0)             # pts cannot be negative
    mu = float(x2.mean())
    if mu > 1e-9:
        x2 = x2 * (m / mu)              # re-pin mean again after the clip
    return x2


def asym_disp(x, up, down):
    """Mean-PRESERVING ASYMMETRIC dispersion: stretch above-mean deviations by (1+up), compress below-mean
    by (1-down). up>0 lengthens the upper tail (raises q90); down>0 compresses the lower tail (raises q10).
    Mean re-pinned exactly afterward (and after the >=0 clip) -- same contract as the engine."""
    x = np.asarray(x, dtype=float)
    m = float(x.mean())
    z = x - m
    z2 = np.where(z > 0, z * (1.0 + up), z * (1.0 - down))
    x2 = z2 - float(z2.mean()) + m
    x2 = np.maximum(x2, 0.0)
    mu = float(x2.mean())
    if mu > 1e-9:
        x2 = x2 * (m / mu)
    return x2


def tails(pairs, s):
    """Given [(actual, sim_samples)], warp each sim sample set by s, return (>q90 rate, <q10 rate, sd-ratio)."""
    above, below, sdr = [], [], []
    for actual, sm in pairs:
        w = right_skew_warp(sm, s) if s > 1e-9 else sm
        q10, q90 = np.quantile(w, 0.1), np.quantile(w, 0.9)
        above.append(1.0 if actual > q90 else 0.0)
        below.append(1.0 if actual < q10 else 0.0)
        sdr.append(w.std() / (np.asarray(sm, float).std() + 1e-9))
    return float(np.mean(above)), float(np.mean(below)), float(np.mean(sdr))


def tails_asym(pairs, up, down):
    """Asymmetric-dispersion version of tails(): returns (>q90 rate, <q10 rate, sd-ratio)."""
    above, below, sdr = [], [], []
    for actual, sm in pairs:
        w = asym_disp(sm, up, down) if (up > 1e-9 or down > 1e-9) else np.asarray(sm, float)
        q10, q90 = np.quantile(w, 0.1), np.quantile(w, 0.9)
        above.append(1.0 if actual > q90 else 0.0)
        below.append(1.0 if actual < q10 else 0.0)
        sdr.append(w.std() / (np.asarray(sm, float).std() + 1e-9))
    return float(np.mean(above)), float(np.mean(below)), float(np.mean(sdr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--nsims", type=int, default=4000)
    ap.add_argument("--minmin", type=float, default=28.0)
    a = ap.parse_args()

    rates = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    trates = json.load(open(os.path.join(TS, "team_rates.json")))
    games = sorted(json.load(open(os.path.join(TS, "nyk_sas_games.json"))), key=lambda g: g["date"])[::a.stride]
    models = {}

    def m(t):
        if t not in models:
            try:
                models[t] = TeamModel.from_cache(t, rates_df=rates, team_rates=trates)
            except Exception:
                models[t] = None
        return models[t]

    allpairs, n = [], 0
    for gm in games:
        bf = os.path.join(BOX, f"{gm['gid']}.json")
        if not os.path.exists(bf):
            continue
        bg = json.load(open(bf))["game"]
        ht, at = bg["homeTeam"]["teamTricode"], bg["awayTeam"]["teamTricode"]
        if ht not in MINE and at not in MINE:
            continue
        hm, am = m(ht), m(at)
        if not hm or not am:
            continue
        try:
            res = simulate_game_fast(hm, am, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                                     context={"neutral_site": False})
        except Exception:
            continue
        n += 1
        for tri, side in ((ht, bg["homeTeam"]), (at, bg["awayTeam"])):
            if tri not in MINE:
                continue
            for p in side.get("players", []):
                st = _pstat(p)
                pid = int(p["personId"])
                if st["min"] < 16.0 or pid not in res.players:           # collect broad; filter at measure-time
                    continue
                allpairs.append((float(st["pts"]), np.asarray(res.players[pid]["samples"]["pts"], dtype=float),
                                 float(st["min"]), str(gm["date"]), pid))

    def sub(mn):
        return [(p[0], p[1]) for p in allpairs if p[2] >= mn]

    pairs = sub(a.minmin)
    print(f"=== measure_skew ===  {n} games, starters min>={a.minmin:.0f}, n_pg={len(pairs)} (collected {len(allpairs)} min>=16)")
    if not pairs:
        print("VERDICT: no data"); return

    # ROOT-CAUSE TEST 1: does the tail asymmetry SCALE with the minutes threshold? The sim is pregame /
    # minutes-AVERAGED; conditioning on high ACTUAL minutes selects a player's heavy-minute (higher-output)
    # games, so a rising >q90 / falling <q10 as the threshold climbs = a MINUTES-CONDITIONING SELECTION
    # artifact (sim correctly doesn't know minutes in advance), NOT a fixable dispersion/mean defect.
    print(f"  minutes-threshold scan (asymmetry vs the actual-minutes cut):")
    print(f"  {'min>=':>6s} {'n_pg':>6s} {'>q90':>7s} {'<q10':>7s}")
    for t in [16, 20, 24, 28, 32, 36]:
        pr = sub(t)
        if len(pr) < 20:
            continue
        av = [1.0 if ac > np.quantile(sm, 0.9) else 0.0 for ac, sm in pr]
        bl = [1.0 if ac < np.quantile(sm, 0.1) else 0.0 for ac, sm in pr]
        print(f"  {t:>6d} {len(pr):>6d} {np.mean(av):>7.1%} {np.mean(bl):>7.1%}")

    # ROOT-CAUSE TEST 2: quantify the MEAN under-prediction directly + split reg-season vs playoff. If the
    # under-bias is concentrated in PLAYOFF games, the cause is plausibly playoff usage-concentration lifting
    # remaining stars above their recency/season anchor blend (a real but data-thin lever); if uniform, it is
    # a generic anchor/subsample property. (leak-free: mean_bias = sim anchor mean - actual, per player-game.)
    def bias_tails(rows):
        bs = [float(sm.mean()) - ac for ac, sm in rows]            # neg => sim UNDER-predicts the actual
        av = [1.0 if ac > np.quantile(sm, 0.9) else 0.0 for ac, sm in rows]
        bl = [1.0 if ac < np.quantile(sm, 0.1) else 0.0 for ac, sm in rows]
        return float(np.mean(bs)), float(np.mean(av)), float(np.mean(bl))
    PLAYOFF_CUT = "2026-04-15"
    p28 = [(p[0], p[1], p[3]) for p in allpairs if p[2] >= 28.0]
    reg = [(a2, s2) for a2, s2, d in p28 if d < PLAYOFF_CUT]
    pof = [(a2, s2) for a2, s2, d in p28 if d >= PLAYOFF_CUT]
    print(f"  mean-bias (sim_mean - actual; neg=sim UNDER-predicts) + tails, min>=28, split @ {PLAYOFF_CUT}:")
    for label, rows in [("ALL ", sub(28.0)), ("reg ", reg), ("play", pof)]:
        if len(rows) < 10:
            print(f"    {label}: n={len(rows)} (too few to read)"); continue
        mb, av, bl = bias_tails(rows)
        print(f"    {label}: n={len(rows):>3d}  mean_bias {mb:+.2f}  >q90 {av:.1%}  <q10 {bl:.1%}")

    # ROOT-CAUSE TEST 3 (capstone): ORACLE-MINUTES. Scale each player's sim distribution by
    # (actual_min / his mean sample min): give the sim oracle knowledge of realized minutes. If the under-
    # bias + over-rate then VANISH, the upper tail is fully the minutes-surprise ceiling (sim correct;
    # the artifact is evaluating a minutes-marginalized sim vs minutes-SELECTED actuals). Oracle is a
    # DIAGNOSTIC, not a predictor (realized minutes are same-day info).
    from collections import defaultdict
    mins = defaultdict(list)
    for p in allpairs:
        mins[p[4]].append(p[2])
    expmin = {k: float(np.mean(v)) for k, v in mins.items()}
    orac = []
    for pts, sm, mn, d, pid in allpairs:
        if mn < 28.0:
            continue
        sc = float(np.clip(mn / max(expmin[pid], 1e-6), 0.5, 2.0))
        orac.append((pts, np.asarray(sm, float) * sc))
    if len(orac) >= 20:
        mb, av, bl = bias_tails(orac)
        print(f"  ORACLE-minutes (scale sim by actual/expected min), min>=28: n={len(orac)} "
              f"mean_bias {mb:+.2f}  >q90 {av:.1%}  <q10 {bl:.1%}  (non-oracle was -2.25 / 17.0% / 3.7%)")

    # SELF-CHECK: s=0 must reproduce the upper_tail baseline (faithfulness of this harness)
    a0, b0, _ = tails(pairs, 0.0)
    print(f"  self-check s=0 (must match upper_tail ~17.0%/3.7%):  >q90 {a0:.1%}   <q10 {b0:.1%}")

    # ROOT-CAUSE DIAGNOSTIC: is the 17%/3.7% asymmetry a dispersion-SHAPE defect, or just the known ~-1.79
    # mean UNDER-bias (anchor target sits low on this playoff-heavy subsample) shifting the whole dist down?
    # Add a constant delta to every sample (pure mean shift, no shape change) and watch the tails. If a
    # delta near the ~1.8 under-bias lands BOTH tails ~10%, the 'upper-tail candidate' IS the mean-bias.
    print(f"  mean-shift diagnostic (delta pts added to every sample; tests if asymmetry = mean under-bias):")
    print(f"  {'delta':>6s} {'>q90':>7s} {'<q10':>7s}")
    for delta in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        av, bl = [], []
        for actual, sm in pairs:
            w = np.asarray(sm, float) + delta
            av.append(1.0 if actual > np.quantile(w, 0.9) else 0.0)
            bl.append(1.0 if actual < np.quantile(w, 0.1) else 0.0)
        print(f"  {delta:>6.2f} {np.mean(av):>7.1%} {np.mean(bl):>7.1%}")
    print(f"  {'skew_s':>7s} {'>q90':>7s} {'<q10':>7s} {'sd_ratio':>9s}  (target 10%/10%)")
    grid = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0]
    rows = []
    for s in grid:
        av, bl, sr = tails(pairs, s)
        rows.append((s, av, bl, sr))
        print(f"  {s:>7.2f} {av:>7.1%} {bl:>7.1%} {sr:>9.3f}")

    best = min(rows, key=lambda r: abs(r[1] - 0.10) + abs(r[2] - 0.10))
    s, av, bl, sr = best
    print(f"  pure-skew best: s={s:.2f} -> >q90 {av:.1%}/<q10 {bl:.1%} (sd x{sr:.2f})")

    # ASYMMETRIC dispersion: the diagnosis is q10 AND q90 both too low (mean correct) -> extend the upper
    # tail (up) AND compress the lower tail (down). Sweep the 2-D grid, find the combo nearest 10%/10%.
    print(f"\n  ASYMMETRIC up/down dispersion (up=extend upper tail, down=compress lower tail):")
    print(f"  {'up':>5s} {'down':>6s} {'>q90':>7s} {'<q10':>7s} {'sd_ratio':>9s}")
    arows = []
    for up in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
        for down in [0.0, 0.2, 0.4, 0.6, 0.8]:
            av2, bl2, sr2 = tails_asym(pairs, up, down)
            arows.append((up, down, av2, bl2, sr2))
    abest = min(arows, key=lambda r: abs(r[2] - 0.10) + abs(r[3] - 0.10))
    for up, down, av2, bl2, sr2 in arows:
        mark = "  <-best" if (up, down) == (abest[0], abest[1]) else ""
        if down in (0.0, 0.4, 0.8) or mark:        # print a readable subset + the winner
            print(f"  {up:>5.2f} {down:>6.2f} {av2:>7.1%} {bl2:>7.1%} {sr2:>9.3f}{mark}")
    up, down, av2, bl2, sr2 = abest
    aok = abs(av2 - 0.10) < 0.035 and abs(bl2 - 0.10) < 0.035
    verdict = (f"ASYMMETRIC up={up:.2f}/down={down:.2f} lands >q90 {av2:.1%}/<q10 {bl2:.1%} (sd x{sr2:.2f}) "
               f"vs pure-skew best >q90 {av:.1%}/<q10 {bl:.1%} (sd x{sr:.2f}). "
               f"{'CANDIDATE (human review): _apply_dispersion needs ASYMMETRIC shock (lengthen upper / compress lower) -- a single right-skew or symmetric sigma cannot calibrate both tails.' if aok else 'EVEN ASYMMETRIC cannot fully hit 10/10 here -> the <q10=3.7% lower-tail (sim floor too low for stars) is a deeper structural issue (minutes/possession downside), not a dispersion-shape knob.'}")
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
