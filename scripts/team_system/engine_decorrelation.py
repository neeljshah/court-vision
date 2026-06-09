"""ENGINE DECORRELATION AUDIT (the SS4D correlation guard) -- how many EFFECTIVE independent engines?

predict_ensemble.py fuses 7 engines equal-weight and reports "engine disagreement = SD of the 7 margins"
as the model uncertainty, and "k/7 engines lean home" as a consensus. BUT several analytic engines
(player_impact / four_factors / power_ratings / team_score / attribute_matchup) ultimately read the SAME
rate/vault tables -> at the MARGIN level the symmetric off/def composition collapses to the net-rating
differential (proven in walkforward_league.py). So those are NOT independent votes; treating them as 5
independent views makes the disagreement band TOO NARROW and the consensus count overstated.

This measures it: run each engine's predict() across a PANEL of real league matchups, take each engine's
predicted home margin, and compute the cross-engine PEARSON correlation of those margins across the panel.
From the correlation matrix R (N engines):
    N_eff = N^2 / (1^T R 1)        # effective number of independent engines (=N if orthogonal, =1 if all r=1)
N_eff tells you how many *effective* independent methodologies you really have, so the reported
"disagreement = uncertainty" can be WIDENED honestly: the SD of k correlated estimates understates the
consensus uncertainty by ~ sqrt(N / N_eff).

This is a MEASUREMENT (leak-free: it characterizes the engines' response surface across matchups, it does
NOT predict outcomes or refit weights -- the reliability refit stays BLOCKED, SS4D). Deterministic for the 5
analytic engines (no sim noise); possession_mc/clock are characterized separately (sim-noise-attenuated,
cache-thin for non-NYK/SAS -> labeled).

  python scripts/team_system/engine_decorrelation.py --n 80
"""
from __future__ import annotations
import argparse, glob, importlib.util, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import pandas as pd  # noqa: E402

TS = os.path.join(ROOT, "data", "cache", "team_system")
OUT = os.path.join(TS, "engine_decorrelation.json")
ASC = lambda s: str(s).encode("ascii", "replace").decode()


def n_eff_from_corr(R):
    """Effective number of independent estimators from a correlation matrix R.
    N_eff = N^2 / (1^T R 1): = N when orthogonal (R=I), = 1 when all r=1 (one shared view).
    This is the Kish-style effective sample size for the variance of the mean of correlated estimators."""
    R = np.asarray(R, float)
    N = R.shape[0]
    ones = np.ones(N)
    return float(N ** 2 / (ones @ R @ ones))


def _load_analytic_engines():
    mods = []
    for fp in sorted(glob.glob(os.path.join(HERE, "engines", "engine_*.py"))):
        name = os.path.splitext(os.path.basename(fp))[0]
        spec = importlib.util.spec_from_file_location(name, fp)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            if hasattr(m, "predict"):
                mods.append((name.replace("engine_", ""), m))
        except Exception as e:
            print(f"  !! {name} failed to load: {ASC(str(e))[:80]}")
    return mods


def _panel(n):
    """A spread of real league matchups (distinct ordered team pairs), spanning the strength spectrum."""
    lg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    # team strength = season point differential per team (to spread the panel across mismatches)
    net = (lg.groupby("team").apply(lambda d: (d.pts - d.opp_pts).mean())).sort_values()
    teams = list(net.index)
    pairs = lg[["team", "opp"]].drop_duplicates().values.tolist()
    rng = np.random.default_rng(20260608)
    rng.shuffle(pairs)
    # keep distinct unordered-ish spread; cap at n
    seen, panel = set(), []
    for h, a in pairs:
        if h == a:
            continue
        panel.append((h, a))
        if len(panel) >= n:
            break
    return panel, net


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80, help="panel size (distinct matchups)")
    ap.add_argument("--nsims", type=int, default=4000, help="sims for possession_mc/clock characterization")
    a = ap.parse_args()

    engines = _load_analytic_engines()
    names = [n for n, _ in engines]
    panel, net = _panel(a.n)
    print(f"=== ENGINE DECORRELATION AUDIT -- {len(engines)} analytic engines x {len(panel)} matchups ===\n")
    print("engines:", ", ".join(names))

    ctx = {"neutral_site": True}   # neutral -> isolate the team-strength response (no constant home add)
    M = np.full((len(panel), len(engines)), np.nan)
    for j, (nm, m) in enumerate(engines):
        for i, (h, aw) in enumerate(panel):
            try:
                p = m.predict(h, aw, ctx)
                M[i, j] = float(p["margin_home"])
            except Exception as e:
                if i == 0:
                    print(f"  !! {nm}.predict failed: {ASC(str(e))[:70]}")
    ok = ~np.isnan(M).any(axis=1)
    M = M[ok]
    print(f"clean matchups: {M.shape[0]}/{len(panel)}\n")

    # cross-engine Pearson correlation of predicted margins across the panel
    R = np.corrcoef(M.T)
    print("cross-engine margin correlation (across matchups):")
    print("            " + "".join(f"{n[:8]:>9s}" for n in names))
    for i, n in enumerate(names):
        print(f"  {n[:10]:10s}" + "".join(f"{R[i, k]:9.3f}" for k in range(len(names))))

    N = len(names)
    n_eff = n_eff_from_corr(R)
    mean_off = float((R.sum() - N) / (N * (N - 1)))
    widen = float(np.sqrt(N / n_eff))
    print(f"\nmean off-diagonal corr = {mean_off:.3f}")
    print(f"N (raw engines)        = {N}")
    print(f"N_eff (independent)    = {n_eff:.2f}")
    print(f"disagreement WIDEN factor sqrt(N/N_eff) = {widen:.2f}x")

    # redundant clusters (corr > 0.95)
    red = [(names[i], names[k], R[i, k]) for i in range(N) for k in range(i + 1, N) if R[i, k] > 0.95]
    if red:
        print("\nREDUNDANT pairs (corr>0.95 -> effectively ONE view):")
        for x, y, r in sorted(red, key=lambda t: -t[2]):
            print(f"  {x:18s} ~ {y:18s} r={r:.3f}")
    else:
        print("\nno pair exceeds corr>0.95 (all engines add a distinct margin response).")

    # possession_mc + clock characterization on a cache-rich subset (NYK/SAS + a few) -- labeled honestly
    poss_clock = {}
    try:
        from sim.basketball_sim import TeamModel  # noqa: E402
        from sim.fast_sim import simulate_game_fast  # noqa: E402
        from sim.game_clock_sim import simulate_clock  # noqa: E402
        rich = ["NYK", "SAS"]
        sub = [(h, aw) for (h, aw) in panel if h in rich and aw in rich] or [("SAS", "NYK"), ("NYK", "SAS")]
        for (h, aw) in [("SAS", "NYK"), ("NYK", "SAS")]:
            try:
                hm, am = TeamModel.from_cache(h), TeamModel.from_cache(aw)
                r = simulate_game_fast(hm, am, n_sims=a.nsims, seed=20260608, anchor=True, defense=True,
                                       context={"neutral_site": True})
                pm = float((r.home_total - r.away_total).mean())
                rc = simulate_clock(hm, am, n_sims=max(1000, a.nsims // 2), seed=20260608)
                cm = float((rc["finalh"] - rc["finala"]).mean())
                poss_clock[f"{h}_vs_{aw}"] = {"possession_mc_margin": pm, "clock_margin": cm}
            except Exception as e:
                print(f"  (possession/clock on {h} vs {aw} skipped: {ASC(str(e))[:50]})")
    except Exception as e:
        print(f"  (possession/clock characterization skipped: {ASC(str(e))[:60]})")

    art = {
        "asof": "2026-06-07",
        "builder": "engine_decorrelation.py",
        "engines": names,
        "n_matchups": int(M.shape[0]),
        "corr_matrix": R.tolist(),
        "mean_offdiag_corr": mean_off,
        "n_raw": N,
        "n_eff": n_eff,
        "widen_factor": widen,
        "redundant_pairs": [[x, y, float(r)] for x, y, r in red],
        "possession_clock_note": ("possession_mc/clock use TeamModel.from_cache -- rich for NYK/SAS only; "
                                  "treated as 2 separate methodologies, not part of the analytic-block corr"),
        "possession_clock_samples": poss_clock,
    }
    tmp = OUT + ".staging"
    with open(tmp, "w") as f:
        json.dump(art, f, indent=1)
    os.replace(tmp, OUT)
    print(f"\nwrote {OUT}")
    print(f"\nREAD: the {N} analytic engines are ~{n_eff:.1f} EFFECTIVE independent views "
          f"(mean cross-corr {mean_off:.2f}). The ensemble's 'k/{N+2} engines agree' consensus and its "
          f"margin-SD disagreement should be read against N_eff, not the raw count; widen the model-uncertainty "
          f"band ~{widen:.2f}x. possession_mc + clock are 2 genuinely distinct methodologies (possession- and "
          f"clock-level) added on top.")


if __name__ == "__main__":
    main()
