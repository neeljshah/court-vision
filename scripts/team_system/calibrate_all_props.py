"""PER-PROP CALIBRATION SCORECARD — is EVERY prop's distribution accurate vs real outcomes?

A prop is only bettable if its distribution matches reality (else any "edge" vs the line is a model bug, not
money). This runs the sim once and, for every rotation player x every market (singles + combos), compares the
sim distribution to that player's REAL game-to-game distribution (full_gamelog).

The SHAPE grade is what decides whether a prop is trustworthy to price. It is the CENTERED over-prob error
`shapeErr` = mean |P_sim(over) - P_real(over)| at the .5-lines around each player's median (the live book
lines), AFTER shifting the sim to the real mean. Centering removes the legitimate matchup/recency LEVEL bias
(pts/combos run ~1pt below season mean vs an elite-D playoff matchup; that is the model's edge call, judged on
the edge side, NOT a shape bug) and leaves pure distribution-shape miscalibration. Threshold logic: a 5pp
over-prob error ~= the vig, so <5pp = OK (shape error below the vig, trustworthy), 5-9pp = WATCH, >9pp = FIX.

bias / freqErr / cover% are kept INFORMATIONAL only. [q10,q90] cover% is DEGENERATE for low-count discrete
stats (a perfectly-calibrated Poisson scores 88-98% there) so it must NOT drive the grade -- doing so flagged
blk FIX while blk is the best-calibrated discrete prop (shapeErr 2.0%). freqErr is P(>=1) = the over-prob at
line 0.5, a line nobody bets (it flagged ast/tov WATCH though both are well-calibrated at real lines).

Run it after any engine change; fix the FIX/WATCH on shapeErr; re-run.

  python scripts/team_system/calibrate_all_props.py
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402

TS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cache", "team_system")
SINGLES = ["pts", "reb", "ast", "fg3m", "stl", "blk", "ftm", "tov"]


def _combo(s, key):
    return {"pra": s["pts"] + s["reb"] + s["ast"], "pr": s["pts"] + s["reb"], "pa": s["pts"] + s["ast"],
            "ra": s["reb"] + s["ast"], "stocks": s["stl"] + s["blk"]}.get(key)


def _shape_err(sim, real):
    """CENTERED over-prob error = pure distribution-shape miscalibration (the SHAPE grade).
    Shift sim to real's mean, then mean |P_sim(>line) - P_real(>line)| at the .5-lines bracketing real's
    median (the live book lines). Centering strips the legitimate matchup/recency LEVEL bias so this measures
    SHAPE only. This is meaningful for discrete low-count stats where [q10,q90] coverage is degenerate."""
    s = sim + (real.mean() - sim.mean())
    med = float(np.median(real))
    lines = [k + 0.5 for k in range(max(0, int(np.floor(med)) - 1), int(np.ceil(med)) + 3)]
    if not lines:
        return np.nan
    return float(np.mean([abs((s > L).mean() - (real > L).mean()) for L in lines]))


def main():
    G = pd.read_parquet(os.path.join(TS, "nyksas_full_gamelog.parquet"))
    res = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                             n_sims=15000, seed=3, anchor=True, defense=True, context={"neutral_site": False})
    markets = SINGLES + ["pra", "pr", "pa", "ra", "stocks"]
    agg = {m: {"bias": [], "freq_err": [], "cover": [], "shape_err": []} for m in markets}
    for pid, d in res.players.items():
        if d["mean"]["pts"] < 8:
            continue
        r = G[(G.pid == pid) & (G.mins >= 15)]
        if len(r) < 8:
            continue
        s = {k: np.asarray(v, float) for k, v in d["samples"].items()}
        for m in markets:
            sim = s[m] if m in s else _combo(s, m)
            if m in SINGLES:
                real = r[m].values.astype(float)
            else:
                real = (_combo({k: r[k].values.astype(float) for k in ["pts", "reb", "ast", "stl", "blk"]}, m))
            if real is None or len(real) < 8:
                continue
            agg[m]["bias"].append(sim.mean() - real.mean())
            agg[m]["freq_err"].append((sim >= 1).mean() - (real >= 1).mean())
            q10, q90 = np.quantile(sim, .1), np.quantile(sim, .9)
            agg[m]["cover"].append(((real >= q10) & (real <= q90)).mean())
            se = _shape_err(sim, real)
            if not np.isnan(se):
                agg[m]["shape_err"].append(se)
    print("=== PER-PROP CALIBRATION SCORECARD (sim vs real, rotation players) ===")
    print("SHAPE grades on shapeErr = centered over-prob MAE at the live book lines (pure distribution shape).")
    print("bias/freqErr/cover% are INFORMATIONAL: bias<0 on pts/combos = the matchup/recency edge call (not a")
    print("bug); cover% is degenerate for low counts (calibrated Poisson scores 88-98%) so it does NOT grade.\n")
    print(f"{'market':7s} {'bias':>6s} {'freqErr':>8s} {'cover%':>7s} {'shapeErr':>8s}  shape")
    for m in markets:
        a = agg[m]
        if not a["bias"]:
            continue
        b = np.mean(a["bias"]); fe = np.mean(np.abs(a["freq_err"])) * 100; cov = np.mean(a["cover"]) * 100
        se = np.mean(a["shape_err"]) * 100
        shape = "OK" if se < 5 else ("WATCH" if se < 9 else "FIX")
        print(f"{m:7s} {b:+6.2f} {fe:7.1f}% {cov:6.0f}% {se:7.1f}%  {shape}")
    print("\nSHAPE: shapeErr<5pp OK (below the vig), 5-9pp WATCH, >9pp FIX. Fix FIX/WATCH on shapeErr in the engine.")


if __name__ == "__main__":
    main()
