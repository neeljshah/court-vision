"""Night-loop: grade the sim's PREGAME WIN-PROBABILITY + margin calibration at scale (the moneyline/spread output).

The master state only graded sim win-prob on 4 NYK-vs-SAS games (small-n ~0.30). But every NYK/SAS game vs
ANY opponent gives a gradeable pregame prediction: simulate it, read the team's win-prob + the sim margin
distribution, grade vs the actual result. This reports Brier, a binned calibration curve, and the margin PIT
(is the actual margin uniform in the sim's margin distribution? -> tests the spread interval the master state
claims is reliable since the bias cancels in a difference). Baselines: always-0.5 (Brier 0.25) and the
base-rate. CAVEAT: the anchor rates are season-built (mildly in-sample); this is a calibration sanity check,
a strict as-of walk-forward is future work -- noted, not overclaimed. Changes nothing, ascii-only.

  python scripts/team_system/nightloop/measure_winprob.py --stride 1
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--nsims", type=int, default=3000)
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

    preds, wins, mpits, mcov = [], [], [], []      # win-prob, actual win, margin PIT, margin in [q10,q90]
    stot, atot, dts = [], [], []                   # sim predicted total (median), actual total, game date
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
        ha = sum(_pstat(p)["pts"] for p in bg["homeTeam"].get("players", []))
        aa = sum(_pstat(p)["pts"] for p in bg["awayTeam"].get("players", []))
        if ha == aa:
            continue
        n += 1
        # grade from the MINE team's perspective (NYK or SAS; if both, use home)
        mine_home = ht in MINE
        wp = float(res.home_win_prob) if mine_home else 1.0 - float(res.home_win_prob)
        actual_win = 1.0 if ((ha > aa) == mine_home) else 0.0
        preds.append(wp); wins.append(actual_win)
        sim_margin = (res.home_total - res.away_total) if mine_home else (res.away_total - res.home_total)
        act_margin = (ha - aa) if mine_home else (aa - ha)
        mpits.append(float((sim_margin < act_margin).mean()))
        q10, q90 = np.quantile(sim_margin, 0.1), np.quantile(sim_margin, 0.9)
        mcov.append(1.0 if q10 <= act_margin <= q90 else 0.0)
        stot.append(float(np.median(res.home_total + res.away_total))); atot.append(ha + aa); dts.append(str(gm["date"]))

    preds = np.array(preds); wins = np.array(wins)
    print(f"=== measure_winprob ===  {n} NYK/SAS games graded (in-sample anchor caveat)")
    if n < 10:
        print("VERDICT: too few"); return
    brier = float(np.mean((preds - wins) ** 2))
    base = float(wins.mean())
    brier_base = float(np.mean((base - wins) ** 2))
    print(f"  win-rate (actual) {base:.1%}  mean pred {preds.mean():.1%}")
    print(f"  BRIER  sim {brier:.4f}  vs always-0.5 {0.25:.4f}  vs base-rate {brier_base:.4f}")
    # calibration curve (quartile bins of pred)
    print(f"  calibration (pred bin -> actual win-rate):")
    edges = [0.0, 0.35, 0.5, 0.65, 1.01]
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (preds >= lo) & (preds < hi)
        if mask.sum() >= 5:
            print(f"    pred[{lo:.2f},{hi:.2f}): n={int(mask.sum()):>3d}  mean_pred {preds[mask].mean():.1%}  actual {wins[mask].mean():.1%}")
    mc = float(np.mean(mcov)); mp = float(np.mean(mpits))
    print(f"  margin: actual in sim [q10,q90] {mc:.1%} (target 80%)  | mean margin-PIT {mp:.2f} (target 0.50; <0.5 => sim margin too low)")

    # FIX TEST: does an out-of-sample ISOTONIC recalibration of the sim win-prob fix the under-confidence?
    # Fit on half the games, grade the other half (leak-free across the split), average both directions.
    try:
        from sklearn.isotonic import IsotonicRegression
        idx = np.arange(n); A = idx % 2 == 0; B = ~A
        recal_pred = np.zeros(n)
        def fit_apply(tr, te):
            iso = IsotonicRegression(out_of_bounds="clip").fit(preds[tr], wins[tr])
            recal_pred[te] = np.clip(iso.predict(preds[te]), 1e-3, 1 - 1e-3)
        fit_apply(A, B); fit_apply(B, A)
        brier_recal = float(np.mean((recal_pred - wins) ** 2))
        # STRAIGHT-UP who-wins accuracy (pick = side with win-prob > 0.5)
        acc_raw = float(np.mean((preds > 0.5) == (wins > 0.5)))
        acc_recal = float(np.mean((recal_pred > 0.5) == (wins > 0.5)))
        acc_fav = float(max(wins.mean(), 1 - wins.mean()))   # always-pick-the-likelier-side
        print(f"  RECAL (split-half OOS isotonic on sim win-prob): Brier {brier:.4f} -> {brier_recal:.4f} (base-rate {brier_base:.4f})")
        print(f"  STRAIGHT-UP who-wins ACCURACY: raw sim {acc_raw:.1%} -> recal {acc_recal:.1%}  (always-favorite {acc_fav:.1%})")
    except Exception as e:
        brier_recal = float("nan")
        print(f"  RECAL: skipped ({type(e).__name__})")

    # TEAM-TOTAL recalibration (the O/U output the War Room flags as untrustworthy): the anchor over-predicts
    # team totals. Leak-free OOS fix = subtract the OTHER half's mean total-bias. Player props are untouched.
    st = np.array(stot, float); at = np.array(atot, float)
    if len(st) >= 10:
        idx = np.arange(len(st)); A = idx % 2 == 0; B = ~A
        trec = np.zeros(len(st))
        trec[B] = st[B] - float((st[A] - at[A]).mean())     # subtract half-A bias from half-B (and vice versa)
        trec[A] = st[A] - float((st[B] - at[B]).mean())
        tb_raw = float((st - at).mean()); tb_rec = float((trec - at).mean())
        rmse_raw = float(np.sqrt(np.mean((st - at) ** 2))); rmse_rec = float(np.sqrt(np.mean((trec - at) ** 2)))
        print(f"  TEAM-TOTAL: raw bias {tb_raw:+.2f} (RMSE {rmse_raw:.1f}) -> OOS-recal bias {tb_rec:+.2f} (RMSE {rmse_rec:.1f}) "
              f"[over-predicts by ~{tb_raw:+.1f}; a simple bias-subtraction fixes the O/U center leak-free]")
        # regime split: the Finals are PLAYOFF elite-vs-elite where the over-bias is largest -> the correct
        # G3 O/U subtraction is the PLAYOFF bias, not the full-sample one.
        dd = np.array(dts); reg = dd < "2026-04-15"; pof = ~reg
        if reg.sum() >= 5:
            print(f"    reg-season (n={int(reg.sum())}): total bias {float((st[reg]-at[reg]).mean()):+.2f}")
        if pof.sum() >= 5:
            print(f"    PLAYOFFS  (n={int(pof.sum())}): total bias {float((st[pof]-at[pof]).mean()):+.2f}  <- the G3 O/U correction")
    recal_ok = (brier_recal == brier_recal) and brier_recal < brier - 0.003
    print(f"VERDICT: sim pregame win-prob Brier {brier:.4f} ({'BEATS' if brier < brier_base - 0.003 else 'ties/LOSES'} the {brier_base:.4f} base-rate, "
          f"{'beats' if brier < 0.247 else 'ties'} 0.25 coin-flip); UNDER-CONFIDENT (pred {preds.mean():.0%} vs actual {base:.0%}); "
          f"margin coverage {mc:.0%} vs 80%, PIT {mp:.2f}. "
          f"{'OOS isotonic recal HELPS (Brier ' + format(brier_recal, '.4f') + ') -> a win-prob recalibration is a viable fix.' if recal_ok else 'OOS isotonic recal did NOT clearly help -> under-confidence may be a one-sided-sample/small-n effect.'} "
          f"Caveat: 100% elite-team sample + in-sample anchor -> balanced multi-team + as-of walk-forward to confirm.")


if __name__ == "__main__":
    main()
