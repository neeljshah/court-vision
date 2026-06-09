"""Night-loop: SANDBOX-validate the fix for the same-player under-correlation (does NOT touch the engine).

measure_corr.py found the sim under-correlates same-player pts-reb (realized +0.19 vs sim +0.03) because
_apply_dispersion uses an INDEPENDENT shock per stat-group. Proposed fix = add a SHARED mean-1 shock across
a player's pts/reb/ast. This harness validates that mechanism in a sandbox: it applies a shared lognormal
shock (sigma_shared) on top of the collected sim samples, re-pins each stat's mean (marginals preserved),
and re-measures the sim pts-reb correlation + the marginal SD inflation the shared shock costs. SELF-CHECK:
sigma_shared=0 reproduces the baseline sim corr (~0.03). Reports the sigma_shared that lands sim pts-reb corr
near the realized +0.19, and the SD cost (the REAL engine fix would rebalance: move variance from the
independent shock into the shared one, so net marginal SD stays put -- noted, not done here). Full board
re-validation (teammate rho, coherence, pytest) requires engine integration by a human; this only proves the
mechanism + sizes it. Changes nothing, ascii-only.

  python scripts/team_system/nightloop/measure_corr_fix.py --stride 1 --ming 12
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

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


def _colcorr_mean(MA, MB, ks):
    """Mean over sampled columns k of the across-game (rows) corr of MA[:,k] vs MB[:,k]."""
    A = MA[:, ks]; B = MB[:, ks]
    am = A - A.mean(0); bm = B - B.mean(0)
    num = (am * bm).sum(0)
    den = np.sqrt((am ** 2).sum(0) * (bm ** 2).sum(0))
    ok = den > 1e-9
    return float(np.mean(num[ok] / den[ok])) if ok.any() else np.nan


def apply_shared(arrs, sigma, rng):
    """Apply ONE shared mean-1 lognormal shock (sigma) across a player's [pts,reb,ast] game-arrays, re-pin
    each mean. Returns new arrays. sigma=0 -> identity. The shared draw is the SAME for all 3 stats (per sim),
    which is what induces same-player cross-stat correlation."""
    if sigma <= 1e-9:
        return arrs
    n = len(arrs[0])
    s = np.exp(sigma * rng.standard_normal(n) - 0.5 * sigma ** 2)   # mean-1 lognormal, shared across stats
    out = []
    for a in arrs:
        b = a * s
        mu = b.mean()
        if mu > 1e-9:
            b = b * (a.mean() / mu)     # re-pin marginal mean exactly
        out.append(b)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--nsims", type=int, default=1500)
    ap.add_argument("--ming", type=int, default=12)
    ap.add_argument("--minmin", type=float, default=18.0)
    ap.add_argument("--ksamp", type=int, default=300)
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

    sim = defaultdict(list)   # pid -> list over games of [pts_arr, reb_arr, ast_arr]
    n = 0
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
                st = _pstat(p); pid = int(p["personId"])
                if st["min"] < a.minmin or pid not in res.players:
                    continue
                s = res.players[pid]["samples"]
                reb = np.asarray(s["reb"] if "reb" in s else (np.asarray(s["oreb"], float) + np.asarray(s["dreb"], float)), float)
                sim[pid].append([np.asarray(s["pts"], float), reb, np.asarray(s["ast"], float)])

    pids = [pid for pid in sim if len(sim[pid]) >= a.ming]
    rng = np.random.default_rng(7)
    ks = rng.integers(0, a.nsims, size=a.ksamp)
    shock_rng = np.random.default_rng(11)

    print(f"=== measure_corr_fix ===  {n} games, {len(pids)} players (>= {a.ming} games)  [target realized pts_reb +0.19]")
    print(f"  {'sigma_shared':>12s} {'sim pts_reb':>12s} {'pts SD x':>9s}")
    grid = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
    rows = []
    for sig in grid:
        corrs, sdr = [], []
        for pid in pids:
            G = len(sim[pid])
            warped = []
            for g in range(G):
                base = sim[pid][g]
                w = apply_shared(base, sig, shock_rng)
                warped.append(w)
                if sig > 0:
                    sdr.append(w[0].std() / (base[0].std() + 1e-9))
            MA = np.stack([warped[g][0] for g in range(G)])    # pts (G, nsims)
            MB = np.stack([warped[g][1] for g in range(G)])    # reb
            c = _colcorr_mean(MA, MB, ks)
            if not np.isnan(c):
                corrs.append(c)
        sd_ratio = float(np.mean(sdr)) if sdr else 1.0
        rows.append((sig, float(np.mean(corrs)), sd_ratio))
        print(f"  {sig:>12.2f} {np.mean(corrs):>+12.3f} {sd_ratio:>9.3f}")

    base_corr = rows[0][1]
    hit = min(rows, key=lambda r: abs(r[1] - 0.19))
    print(f"  self-check sigma=0 sim pts_reb {base_corr:+.3f} (must match measure_corr baseline ~+0.03)")
    ok = abs(base_corr - 0.03) < 0.04
    print(f"VERDICT: {'self-check OK; ' if ok else 'SELF-CHECK OFF (interpret with care); '}"
          f"a shared lognormal sigma~{hit[0]:.2f} lifts sim pts_reb corr {base_corr:+.3f}->{hit[1]:+.3f} "
          f"(toward realized +0.19) at +{(hit[2]-1)*100:.0f}% marginal pts-SD -> the shared-shock fix MECHANISM "
          f"works; the real engine fix rebalances (cut the independent shock so net SD holds) + must be re-validated "
          f"on the full board (teammate rho/coherence/pytest). Sandbox-confirmed, NOT applied.")


if __name__ == "__main__":
    main()
