"""FULL 7-ENGINE decorrelation -- the rigorous N_eff (tests iter-1's '+2 independent' approximation).

iter-1 (engine_decorrelation.py) measured the 5 ANALYTIC engines exactly (deterministic, league-wide) ->
N_eff 1.19, and APPROXIMATED possession_mc + clock as 2 fully-independent views (-> full N_eff ~3.2). This
script measures possession_mc + clock margins ON THE SAME real-matchup panel (with the league-injection trick
from engine_vs_composition.py so the sim works for arbitrary teams), so the FULL 7x7 correlation + N_eff are
measured, not assumed. If possession_mc actually correlates with the net-rating block, the true N_eff is lower
and the honest Game-7 uncertainty band should widen MORE.

  python scripts/team_system/engine_decorrelation_full.py --n 30 --nsims 3000
"""
from __future__ import annotations
import argparse, glob, importlib.util, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import pandas as pd  # noqa: E402
import sim.basketball_sim as bs  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from sim.game_clock_sim import simulate_clock  # noqa: E402
from engine_decorrelation import n_eff_from_corr  # noqa: E402

TS = os.path.join(ROOT, "data", "cache", "team_system")
ASC = lambda s: str(s).encode("ascii", "replace").decode()


def _load_analytic():
    mods = []
    for fp in sorted(glob.glob(os.path.join(HERE, "engines", "engine_*.py"))):
        name = os.path.splitext(os.path.basename(fp))[0]
        spec = importlib.util.spec_from_file_location(name, fp)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        if hasattr(m, "predict"):
            mods.append((name.replace("engine_", ""), m))
    return mods


def _inject_league():
    """Clean 30-team defense + pace so possession_mc/clock run for arbitrary teams (engine_vs_composition trick)."""
    TG = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    ident = {}
    for t, g in TG.groupby("team"):
        ident[t] = dict(pace=g.poss.mean())
    dfl = pd.read_parquet(os.path.join(TS, "team_defense_league.parquet")).set_index("team")
    val = pd.read_parquet(os.path.join(TS, "team_defense.parquet")).set_index("team")
    bs._TEAM_DEF = {}
    for t in ident:
        src = val if t in val.index else dfl
        bs._TEAM_DEF[t] = dict(tov_force=float(src.loc[t, "tov_force"]), ft_force=float(src.loc[t, "ft_force"]),
                               oreb_strength=float(dfl.loc[t, "oreb_strength"]))
    tr = json.load(open(os.path.join(TS, "team_rates.json")))
    for t in ident:
        if t in tr:
            tr[t]["pace"] = ident[t]["pace"]
    rates_df = pd.read_parquet(os.path.join(TS, "player_rates.parquet"))
    return rates_df, tr, list(ident.keys())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--nsims", type=int, default=3000)
    a = ap.parse_args()

    engines = _load_analytic()
    rates_df, tr, teams = _inject_league()
    # panel of real matchups among teams the sim can build
    lg = pd.read_parquet(os.path.join(TS, "league_team_game.parquet"))
    pairs = [(h, aw) for h, aw in lg[["team", "opp"]].drop_duplicates().values.tolist() if h != aw]
    rng = np.random.default_rng(20260608)
    rng.shuffle(pairs)
    panel = pairs[: a.n]

    names = [n for n, _ in engines] + ["possession_mc", "clock"]
    ctx = {"neutral_site": True}
    M = []
    for (h, aw) in panel:
        row = []
        ok = True
        for nm, m in engines:
            try:
                row.append(float(m.predict(h, aw, ctx)["margin_home"]))
            except Exception:
                ok = False; break
        if not ok:
            continue
        try:
            hm = TeamModel.from_cache(h, rates_df=rates_df, team_rates=tr)
            am = TeamModel.from_cache(aw, rates_df=rates_df, team_rates=tr)
            res = simulate_game_fast(hm, am, n_sims=a.nsims, seed=2026, anchor=True, defense=True,
                                     context={"neutral_site": True})
            row.append(float((res.home_total - res.away_total).mean()))
            rc = simulate_clock(hm, am, n_sims=max(1500, a.nsims // 2), seed=2026)
            row.append(float((rc["finalh"] - rc["finala"]).mean()))
        except Exception as e:
            print(f"  (sim skip {h} vs {aw}: {ASC(str(e))[:50]})"); continue
        M.append(row)
    M = np.array(M)
    print(f"=== FULL 7-ENGINE DECORRELATION -- {M.shape[0]} matchups x {len(names)} engines ({a.nsims} sims) ===\n")
    R = np.corrcoef(M.T)
    print("            " + "".join(f"{n[:8]:>9s}" for n in names))
    for i, n in enumerate(names):
        print(f"  {n[:10]:10s}" + "".join(f"{R[i, k]:9.3f}" for k in range(len(names))))

    N = len(names)
    n_eff = n_eff_from_corr(R)
    mean_off = float((R.sum() - N) / (N * (N - 1)))
    widen = float(np.sqrt(N / n_eff))
    # possession_mc / clock corr with the analytic block (mean of their corr to the 5 analytic)
    na = len(engines)
    pm_corr = float(np.mean([R[na, k] for k in range(na)]))
    ck_corr = float(np.mean([R[na + 1, k] for k in range(na)]))
    pm_ck = float(R[na, na + 1])
    print(f"\nmean off-diagonal corr = {mean_off:.3f}")
    print(f"N (raw)   = {N}")
    print(f"N_eff     = {n_eff:.2f}   (iter-1 approximation was ~3.2)")
    print(f"WIDEN factor sqrt(N/N_eff) = {widen:.2f}x")
    print(f"possession_mc mean corr to analytic block = {pm_corr:+.3f}")
    print(f"clock         mean corr to analytic block = {ck_corr:+.3f}")
    print(f"possession_mc ~ clock corr                = {pm_ck:+.3f}")

    art = {"asof": "2026-06-07", "builder": "engine_decorrelation_full.py", "engines": names,
           "n_matchups": int(M.shape[0]), "nsims": a.nsims, "corr_matrix": R.tolist(),
           "mean_offdiag_corr": mean_off, "n_raw": N, "n_eff_full": n_eff, "widen_factor": widen,
           "possession_mc_corr_to_analytic": pm_corr, "clock_corr_to_analytic": ck_corr,
           "possession_mc_clock_corr": pm_ck}
    tmp = os.path.join(TS, "engine_decorrelation_full.json")
    json.dump(art, open(tmp + ".staging", "w"), indent=1)
    os.replace(tmp + ".staging", tmp)
    print(f"\nwrote {tmp}")
    print(f"\nREAD: measured full-7 N_eff = {n_eff:.1f} effective independent views. possession_mc adds a "
          f"{'DISTINCT' if pm_corr < 0.8 else 'partly-redundant'} view (corr {pm_corr:+.2f} to the analytic "
          f"block); clock adds a {'DISTINCT' if ck_corr < 0.8 else 'partly-redundant'} view (corr {ck_corr:+.2f}).")


if __name__ == "__main__":
    main()
