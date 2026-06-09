"""META-ENSEMBLE — fuse EVERY engine into ONE single-game prediction.

The signal -> model -> engine -> ONE hierarchy, realized:
  - thousands of SIGNALS (attrs/rates/effects/factors) feed
  - hundreds of MODELS (per-player, per-team, per-factor, per-facet) which compose into
  - several ENGINES (each a different methodology -> decorrelated views), fused here into
  - ONE calibrated prediction (with the engine disagreement = the honest model uncertainty).

Engines fused: the 5 analytic engines auto-discovered from engines/engine_*.py (player_impact, four_factors,
power_ratings, team_score, attribute_matchup) + the possession Monte Carlo (anchored marginals, the prop
engine) + the clock/trajectory engine + a clutch overlay (NYK clutch edge, competitive games only).

Fusion: each engine gives margin_home + margin_sd. Equal-weight is the honest default (no per-engine
reliability backtest exists); inverse-variance (1/margin_sd^2) is reported as a cross-check. The fused win
prob = Phi(fused_margin / pooled_game_sd). Engine spread (SD of the engine margins) = model uncertainty.
Clutch overlay applied last as a documented competitive-game tilt.

  python scripts/team_system/predict_ensemble.py --home NYK --away SAS
"""
from __future__ import annotations
import argparse, glob, importlib.util, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
import pandas as pd  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from sim.game_clock_sim import simulate_clock  # noqa: E402
from sim import clutch_adjust as ca  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


def _phi(z):
    from math import erf, sqrt
    return 0.5 * (1 + erf(z / sqrt(2)))


def _load_engines():
    mods = []
    for fp in sorted(glob.glob(os.path.join(HERE, "engines", "engine_*.py"))):
        name = os.path.splitext(os.path.basename(fp))[0]
        spec = importlib.util.spec_from_file_location(name, fp)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            if hasattr(m, "predict"):
                mods.append((name, m))
        except Exception as e:
            print(f"  !! {name} failed to load: {str(e)[:80]}")
    return mods


def _possession_engine(home, away, n=20000):
    res = simulate_game_fast(home, away, n_sims=n, seed=20260608, anchor=True, defense=True,
                             context={"neutral_site": False})
    m = res.home_total - res.away_total
    npl = sum(1 for p in res.players if res.players[p]["mean"]["pts"] >= 1)
    return {"engine": "possession_mc", "win_prob_home": float((m > 0).mean()), "margin_home": float(m.mean()),
            "total": float((res.home_total + res.away_total).mean()), "home_pts": float(res.home_total.mean()),
            "away_pts": float(res.away_total.mean()), "margin_sd": float(m.std()), "n_models": npl,
            "n_signals": npl * 25, "notes": "anchored player possession MC (SAS total inflated by anchor; see EDGE_GATE)",
            "_margin_samples": m}


def _clock_engine(home, away, n=4000):
    r = simulate_clock(home, away, n_sims=n, seed=20260608)
    m = r["finalh"] - r["finala"]
    return {"engine": "clock_trajectory", "win_prob_home": float(r["home_win"]), "margin_home": float(m.mean()),
            "total": float((r["finalh"] + r["finala"]).mean()), "home_pts": float(r["finalh"].mean()),
            "away_pts": float(r["finala"].mean()), "margin_sd": float(m.std()), "n_models": 10,
            "n_signals": 200, "notes": "clock-aware trajectory engine (quarter identity, Q4 decay, clutch)",
            "_margin_samples": m}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    home, away = TeamModel.from_cache(a.home), TeamModel.from_cache(a.away)
    ctx = {"neutral_site": False}

    preds = []
    for name, m in _load_engines():
        try:
            p = m.predict(a.home, a.away, ctx); p["engine"] = p.get("engine", name); preds.append(p)
        except Exception as e:
            print(f"  !! {name}.predict failed: {str(e)[:80]}")
    preds.append(_possession_engine(home, away))
    preds.append(_clock_engine(home, away))

    print(f"=== ENSEMBLE PREDICTION: {a.away} @ {a.home} ({len(preds)} engines) ===\n")
    print(f"{'engine':20s} {'NYKwin':>7s} {'margin':>7s} {'total':>6s} {'mSD':>5s} {'models':>6s} {'signals':>8s}")
    tot_models = tot_signals = 0
    for p in preds:
        tot_models += int(p.get("n_models", 0)); tot_signals += int(p.get("n_signals", 0))
        print(f"{p['engine']:20s} {p['win_prob_home']*100:6.1f}% {p['margin_home']:+7.1f} {p['total']:6.0f} "
              f"{p['margin_sd']:5.1f} {p.get('n_models',0):6d} {p.get('n_signals',0):8d}")

    margins = np.array([p["margin_home"] for p in preds])
    sds = np.array([p["margin_sd"] for p in preds])
    totals = np.array([p["total"] for p in preds])
    # --- gated reliability-weighting (V0; default-OFF => byte-identical equal-weight) ---
    eng_w = None
    if os.environ.get("CV_ENGINE_RELIABILITY_WEIGHTS") == "1":
        import json as _json
        _wp = os.path.join(ROOT, "data", "cache", "team_system", "engine_reliability_weights.json")
        if os.path.exists(_wp):
            _d = _json.load(open(_wp))
            if _d.get("beats_equal_weight"):           # only apply a learned win; null => stay equal-weight
                _map = dict(zip(_d["engines"], _d["weights"]))
                eng_w = np.array([_map.get(p["engine"], 0.0) for p in preds])
                if eng_w.sum() > 0:
                    eng_w = eng_w / eng_w.sum()
                else:
                    eng_w = None
    # equal-weight (honest default) + inverse-variance cross-check
    eq_margin = float((eng_w * margins).sum()) if eng_w is not None else float(margins.mean())
    w = 1.0 / np.maximum(sds, 1e-6) ** 2; w = w / w.sum()
    iv_margin = float((w * margins).sum())
    pooled_sd = float(np.sqrt((w * sds ** 2).sum()))      # ~ single-game outcome SD
    eq_total = float(totals.mean())
    engine_spread = float(margins.std())                   # model uncertainty = how much engines disagree

    eq_wp = _phi(eq_margin / pooled_sd); iv_wp = _phi(iv_margin / pooled_sd)
    print(f"\n--- FUSION ---")
    print(f"equal-weight margin {a.home} {eq_margin:+.2f}  -> win prob {a.home} {eq_wp*100:.1f}%")
    print(f"inverse-var  margin {a.home} {iv_margin:+.2f}  -> win prob {a.home} {iv_wp*100:.1f}%")
    print(f"fused total {eq_total:.1f}  |  pooled game SD {pooled_sd:.1f}  |  ENGINE DISAGREEMENT (margin SD) {engine_spread:.1f}")

    # clutch overlay (competitive games only) on the equal-weight margin distribution
    tg = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system", "team_game.parquet"))
    tilt = ca.clutch_tilt(a.home, a.away, tg)
    rng = np.random.default_rng(7)
    sim_margins = rng.normal(eq_margin, pooled_sd, 200000)
    adj = ca.adjust_margin(sim_margins.copy(), tilt)
    clutch_wp = float((adj > 0).mean())
    print(f"clutch overlay (tilt {a.home} {tilt:+.2f}, competitive games): win prob {a.home} {eq_wp*100:.1f}% -> {clutch_wp*100:.1f}%")

    print(f"\n--- ONE PREDICTION ---")
    proj_h = eq_total / 2 + eq_margin / 2; proj_a = eq_total / 2 - eq_margin / 2
    print(f"{a.home} {proj_h:.1f} - {proj_a:.1f} {a.away}  (margin {a.home} {eq_margin:+.1f}, total {eq_total:.0f})")
    print(f"WIN PROBABILITY {a.home} {clutch_wp*100:.0f}% / {a.away} {(1-clutch_wp)*100:.0f}%  "
          f"(talent-ensemble {eq_wp*100:.0f}%, +clutch overlay)")
    print(f"\nHIERARCHY: ~{tot_signals:,} signals -> {tot_models} models -> {len(preds)} engines -> 1 prediction")
    print(f"engine consensus: {(margins>0).sum()}/{len(preds)} lean {a.home}; disagreement {engine_spread:.1f} pts "
          f"(range {margins.min():+.1f} to {margins.max():+.1f})")

    # N_eff correction (gated, default-OFF, byte-identical when OFF) -- the SS4D correlation guard.
    # The 5 analytic engines mostly re-express the same net-rating signal (measured N_eff ~1.2), so the raw
    # k/{len} consensus + margin-SD disagreement OVERSTATE independence. Report the effective view count and a
    # widened honest model-uncertainty band. Reporting only -- the fused marginal/win-prob are UNCHANGED.
    if os.environ.get("CV_ENGINE_NEFF") == "1":
        import json as _json
        tsdir = os.path.join(ROOT, "data", "cache", "team_system")
        full = os.path.join(tsdir, "engine_decorrelation_full.json")    # measured full-7 N_eff (preferred)
        ana = os.path.join(tsdir, "engine_decorrelation.json")          # analytic-only (fallback)
        if os.path.exists(full):
            d = _json.load(open(full))
            n_eff_full = float(d.get("n_eff_full", float("nan")))
            widen = float(np.sqrt(len(preds) / max(n_eff_full, 1e-6)))
            eff_band = engine_spread * widen
            print(f"\n--- N_eff CORRECTION (engine decorrelation audit, MEASURED full-7) ---")
            print(f"the {len(preds)} engines = ~{n_eff_full:.1f} EFFECTIVE independent views "
                  f"(mean cross-corr {d.get('mean_offdiag_corr', float('nan')):.2f}). the 5 analytic engines are "
                  f"~1.2 views (one net-rating cluster, power_ratings~team_score r~0.99); possession_mc and clock "
                  f"are distinct (corr {d.get('possession_mc_corr_to_analytic', 0):+.2f}/"
                  f"{d.get('clock_corr_to_analytic', 0):+.2f} to that block) but correlate "
                  f"{d.get('possession_mc_clock_corr', 0):+.2f} with each other.")
            print(f"so the equal-weight fusion gives ~71% of its weight to ONE effective view; the raw margin-SD "
                  f"{engine_spread:.1f} OVERSTATES independence. N_eff-widened honest model uncertainty "
                  f"~{eff_band:.1f} pts ({widen:.2f}x). Read 'consensus {(margins>0).sum()}/{len(preds)}' as "
                  f"~{n_eff_full:.1f} effective views.")
        elif os.path.exists(ana):
            d = _json.load(open(ana))
            n_eff_analytic = float(d.get("n_eff", float("nan")))
            n_analytic = int(d.get("n_raw", 5))
            n_eff_full = n_eff_analytic + max(0, len(preds) - n_analytic)   # approximation if full not measured
            widen = float(np.sqrt(len(preds) / max(n_eff_full, 1e-6)))
            print(f"\n--- N_eff CORRECTION (analytic-only; run engine_decorrelation_full.py for the measured full-7) ---")
            print(f"the {n_analytic} analytic engines = ~{n_eff_analytic:.1f} effective views "
                  f"(mean corr {d.get('mean_offdiag_corr', float('nan')):.2f}); full ensemble approx ~{n_eff_full:.1f}, "
                  f"widen ~{widen:.2f}x (engine_decorrelation.json).")
        else:
            print("  (CV_ENGINE_NEFF=1 but engine_decorrelation*.json missing -- run engine_decorrelation_full.py)")

    print("HONEST: playoff game -> no proven betting edge (closing line beats the model in playoffs); projection only.")

    # fold into the War Room
    PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
    S, EN = "<!-- SIGNALS:ensemble START -->", "<!-- SIGNALS:ensemble END -->"
    if os.path.exists(PREVIEW):
        import re
        L = [S, "", "## Ensemble Prediction -- all engines -> ONE",
             f"*{a.away} @ {a.home}. {len(preds)} decorrelated engines fused (signal->model->engine->one). "
             f"Equal-weight is the honest default; clutch overlay applied last.*", "",
             "| engine | NYK win | margin | total | models |", "|---|--:|--:|--:|--:|"]
        for p in preds:
            L.append(f"| {p['engine']} | {p['win_prob_home']*100:.0f}% | {p['margin_home']:+.1f} | {p['total']:.0f} | {p.get('n_models',0)} |")
        L += ["", f"**FUSED: {a.home} {proj_h:.0f}-{proj_a:.0f} {a.away}, win prob {a.home} {clutch_wp*100:.0f}% "
              f"(talent {eq_wp*100:.0f}% + clutch).** Engine consensus {(margins>0).sum()}/{len(preds)} lean {a.home}, "
              f"disagreement {engine_spread:.1f} pts. Hierarchy ~{tot_signals:,} signals -> {tot_models} models -> "
              f"{len(preds)} engines -> 1. *Playoff projection, not a bet (no proven playoff edge).*", "", EN, ""]
        block = "\n".join(L)
        txt = open(PREVIEW, encoding="utf-8").read()
        txt = re.sub(re.escape(S) + r".*?" + re.escape(EN), block, txt, flags=re.S) if (S in txt and EN in txt) \
            else txt.rstrip() + "\n\n" + block + "\n"
        open(PREVIEW, "w", encoding="utf-8").write(txt)
        print("folded ## Ensemble Prediction into the War Room.")


if __name__ == "__main__":
    main()
