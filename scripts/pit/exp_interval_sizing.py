"""EXPERIMENT: consistency/role intelligence as a per-bet SIGMA (interval width)
=> Kelly stake => does ROI / per-unit-risk beat FLAT sizing?

PRIOR SUPPORT (memory): "consistency-CV is an orthogonal INTERVAL signal" — a
player's consistency/variance prior predicts |residual| (rel-err corr ~+0.41,
3.4x across quartiles) but NOT the point estimate. The recommended use is CI
width + Kelly SIZING, not the point model. This script WIRES IT IN and measures
ROI / Kelly log-growth via better sizing.

THIS IS A SIZING EXPERIMENT, NOT A POINT TILT. The bet DIRECTION (over/under) and
the point `pred` are never changed. Only the STAKE per bet changes:
  stake ~ edge / sigma_perbet   (or full-Kelly with per-bet sigma)
where sigma_perbet comes from the player's as-of consistency-CV. We bet bigger on
predictable players, smaller on volatile ones, and (Kelly) effectively skip bets
whose true interval makes the model edge illusory.

LEAK-FREE consistency signal (full coverage, no thin-CV-coverage dependence):
For each (player_id, stat) the as-of coefficient of variation of that player's
OWN realized values, computed from PRIOR games only (the same actual history the
calframe already contains, walked forward). This is exactly the per_player_confidence
CV concept but with as-of discipline and full corpus coverage.

METHOD (strict, mirrors PREDICTION_HARNESS_GUIDE):
  1. corr(consistency_CV, |actual-pred|) must be POSITIVE and survive OUT-OF-SAMPLE
     (fit nothing; just measure on the held-out LATE half). This is the
     does-the-sigma-signal-predict-|residual| gate.
  2. Build per-bet sigma = base_sigma(stat) * f(player_cv_z). Validate it improves
     interval calibration (coverage closer to nominal / pinball) vs flat per-stat sigma.
  3. Size each bet several ways and compare TOTAL ROI and Kelly log-growth-per-unit-risk
     on the HELD-OUT late half:
        - flat 1u (baseline)
        - edge/sigma_flat   (per-stat flat sigma from interval_sigma_recommendation.json)
        - edge/sigma_perbet (consistency-scaled sigma)        <-- the hypothesis
        - Kelly(sigma_flat) and Kelly(sigma_perbet)
  4. >=2 INDEPENDENT corpora (Family A + Family B or C). drop |odds|<100, coherence,
     reg-season only.

Run: conda run -n basketball_ai python scripts/pit/exp_interval_sizing.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from math import erf, sqrt

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = ig.ROOT
SIGMA_REC = os.path.join(ROOT, "data", "cache", "profiles", "_reference",
                         "interval_sigma_recommendation.json")

STATS = ["ast", "reb", "pts", "fg3m"]
MIN_PRIOR = 8           # need >= this many prior games to trust a player's CV
N_CV_FLOOR = 0.05       # floor on CV so a perfectly-flat player isn't infinite-stake


# --------------------------------------------------------------------------- #
# 1. base per-stat sigma (the prior per-stat fix we must beat / compare against)
# --------------------------------------------------------------------------- #
def base_sigmas():
    rec = json.load(open(SIGMA_REC, encoding="utf-8"))["stats"]
    # recommended_sigma is the calibrated 1-game count sigma per stat
    return {s: float(rec[s]["recommended_sigma"]) for s in rec}


# --------------------------------------------------------------------------- #
# 2. leak-free as-of per-(player,stat) consistency CV from the actual history.
#    Walk the calframe forward: for each game, CV = std/mean of PRIOR games.
#    Returns dict[(pid,date,stat)] -> {"cv":, "n_prior":, "mean":, "std":}
# --------------------------------------------------------------------------- #
def build_asof_cv():
    import pandas as pd
    cal = ig._cal()  # already has normalized "d"
    cal = cal[["player_id", "d", "stat", "actual"]].dropna(subset=["actual"])
    cal = cal.sort_values(["player_id", "stat", "d"])
    out = {}
    for (pid, stat), grp in cal.groupby(["player_id", "stat"], sort=False):
        vals = grp["actual"].to_numpy(dtype=float)
        dates = grp["d"].to_numpy()
        # cumulative prior mean/std (strictly prior => shift by 1)
        csum = np.cumsum(vals)
        csum2 = np.cumsum(vals * vals)
        for i in range(len(vals)):
            n = i  # number of strictly-prior games
            if n >= 1:
                m = csum[i - 1] / n
                var = max(csum2[i - 1] / n - m * m, 0.0)
                sd = sqrt(var)
                cv = sd / max(abs(m), 1e-6)
            else:
                m = sd = cv = np.nan
            out[(int(pid), pd.Timestamp(dates[i]).normalize(), stat)] = {
                "cv": cv, "n_prior": n, "mean": m, "std": sd}
    return out


def attach_cv(bets, asof_cv):
    matched = 0
    for b in bets:
        rec = asof_cv.get((b["pid"], b["gdate"], b["stat"]))
        if rec is not None and rec["n_prior"] >= MIN_PRIOR and np.isfinite(rec["cv"]):
            b["_cv"] = rec["cv"]
            b["_cv_std"] = rec["std"]
            b["_cv_n"] = rec["n_prior"]
            matched += 1
        else:
            b["_cv"] = np.nan
            b["_cv_std"] = np.nan
            b["_cv_n"] = rec["n_prior"] if rec else 0
    print(f"    consistency-CV attached (n_prior>={MIN_PRIOR}): {matched}/{len(bets)} "
          f"({100*matched/max(len(bets),1):.0f}%)")
    return bets


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _phi(z):
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def temporal_halves(bets):
    ds = sorted({b["gdate"] for b in bets})
    mid = ds[len(ds) // 2]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    return early, late


def stat_cv_stats(bets, stat):
    """median + log-std of the consistency CV for this stat (for z-scoring)."""
    cvs = np.array([b["_cv"] for b in bets
                    if b["stat"] == stat and np.isfinite(b.get("_cv", np.nan))])
    if len(cvs) < 20:
        return None
    lcv = np.log(np.clip(cvs, N_CV_FLOOR, None))
    return {"med_log": float(np.median(lcv)), "std_log": float(np.std(lcv) + 1e-9),
            "med_cv": float(np.median(cvs))}


# --------------------------------------------------------------------------- #
# 3. per-bet sigma = base_sigma(stat) * exp(z-scaled deviation of player's CV).
#    A more-volatile-than-typical player gets a WIDER interval; a metronome a
#    narrower one. Empirically: sigma_perbet uses the player's own count-std when
#    available (cv_std = as-of std of the stat) which IS the natural width; we
#    blend toward the per-stat base for stability.
# --------------------------------------------------------------------------- #
def per_bet_sigma(b, base_sig, cvstats, blend=0.5):
    """sigma for this bet. Returns (sigma_flat, sigma_perbet)."""
    s_flat = base_sig
    cv = b.get("_cv", np.nan)
    cstd = b.get("_cv_std", np.nan)
    if not (np.isfinite(cv) and cvstats is not None and np.isfinite(cstd)):
        return s_flat, s_flat
    # player's own realized count-std is a direct interval width; blend with base
    s_player = blend * cstd + (1 - blend) * s_flat
    return s_flat, max(s_player, 0.25 * s_flat)


# --------------------------------------------------------------------------- #
# 4. sizing -> ROI and Kelly log-growth
# --------------------------------------------------------------------------- #
def _dec_odds(odds):
    return (100.0 / abs(odds) + 1.0) if odds < 0 else (odds / 100.0 + 1.0)


def model_prob(b, sigma):
    """P(over) under Normal(pred, sigma); bet side = pred>line already in settle."""
    z = (b["pred"] - b["line"]) / max(sigma, 1e-6)
    p_over = _phi(z)
    bet_over = b["pred"] > b["line"]
    return p_over if bet_over else (1.0 - p_over)


def grade_sized(bets, sizer, sigma_fn=None, edge_min=0.0, kelly_cap=0.25):
    """Generic sizer. sizer in {flat, edge_over_sigma, kelly}. Returns dict with
    weighted ROI (pnl/total_stake) and Kelly sum-log-growth."""
    total_stake = 0.0
    pnl = 0.0
    logg = 0.0   # sum of log(1 + stake_frac*(b-1)) winning / log(1-stake_frac) losing  (Kelly growth proxy)
    n = nz = 0
    for b in bets:
        pred = b.get("pred")
        if pred is None or not np.isfinite(pred):
            continue
        if abs(pred - b["line"]) < edge_min:
            continue
        res = ig.settle(b, pred)
        if res is None:
            continue
        _, won, payout_per100 = res  # payout_per100: +decimal_profit*100 win, -100 loss
        n += 1

        if sizer == "flat":
            stake = 1.0
        else:
            sig = sigma_fn(b)
            if sig is None or not np.isfinite(sig):
                continue
            edge_pts = abs(pred - b["line"])
            if sizer == "edge_over_sigma":
                stake = edge_pts / sig
            elif sizer == "kelly":
                p = model_prob(b, sig)
                odds = b["over_odds"] if pred > b["line"] else b["under_odds"]
                dec = _dec_odds(odds)
                bdec = dec - 1.0
                f = (p * dec - 1.0) / bdec if bdec > 1e-9 else 0.0
                f = max(0.0, min(f, kelly_cap))
                stake = f
            else:
                stake = 1.0
        if stake <= 0:
            continue
        nz += 1
        total_stake += stake
        # pnl scales linearly with stake (payout_per100 already per 1u=100)
        pnl += stake * payout_per100 / 100.0
        # kelly growth (only meaningful for fractional kelly stakes)
        dec = _dec_odds(b["over_odds"] if pred > b["line"] else b["under_odds"])
        if won:
            logg += np.log(1.0 + stake * (dec - 1.0))
        else:
            logg += np.log(max(1.0 - stake, 1e-6))
    roi = (pnl / total_stake * 100.0) if total_stake > 0 else 0.0
    return {"n": n, "n_bet": nz, "roi_pct": roi, "pnl": pnl,
            "total_stake": total_stake, "logg": logg,
            "logg_per_bet": (logg / nz if nz else 0.0)}


# --------------------------------------------------------------------------- #
# residual-magnitude validation (the load-bearing gate)
# --------------------------------------------------------------------------- #
def resid_mag_corr(bets, stat, key="_cv"):
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None, len(sub)
    sig = np.array([b[key] for b in sub])
    absr = np.array([abs(b["actual"] - b["pred"]) for b in sub])
    if np.std(sig) < 1e-9:
        return None, len(sub)
    r = np.corrcoef(sig, absr)[0, 1]
    return r, len(sub)


def quartile_resid(bets, stat, key="_cv"):
    """mean |resid| in low vs high CV quartile (the 3.4x claim)."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 40:
        return None
    sig = np.array([b[key] for b in sub])
    absr = np.array([abs(b["actual"] - b["pred"]) for b in sub])
    q1, q3 = np.percentile(sig, [25, 75])
    lo = absr[sig <= q1].mean()
    hi = absr[sig >= q3].mean()
    return {"lo_resid": lo, "hi_resid": hi, "ratio": (hi / lo if lo > 1e-9 else np.nan),
            "n_lo": int((sig <= q1).sum()), "n_hi": int((sig >= q3).sum())}


# --------------------------------------------------------------------------- #
# interval calibration: does per-bet sigma cover better than flat?
# --------------------------------------------------------------------------- #
def coverage_check(bets, stat, base_sig, cvstats, z=1.645):
    """fraction of |actual-pred| <= z*sigma for flat vs per-bet sigma (nominal=0.90)."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get("_cv", np.nan))]
    if len(sub) < 30:
        return None
    cov_flat = cov_pb = 0
    for b in sub:
        sf, sp = per_bet_sigma(b, base_sig, cvstats)
        err = abs(b["actual"] - b["pred"])
        cov_flat += err <= z * sf
        cov_pb += err <= z * sp
    n = len(sub)
    return {"n": n, "cov_flat": cov_flat / n, "cov_perbet": cov_pb / n}


# --------------------------------------------------------------------------- #
# main per-corpus run
# --------------------------------------------------------------------------- #
def run_corpus(corpus, asof_cv, base, edge_min_map=None):
    edge_min_map = edge_min_map or {}
    print(f"\n{'='*74}\n CORPUS: {corpus}\n{'='*74}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'})  joined n={len(bets)}")
    if not coh["coherent"]:
        print(" !! corrupt corpus, skipping")
        return None
    attach_cv(bets, asof_cv)
    early, late = temporal_halves(bets)
    print(f" split: early n={len(early)}  late(HELD-OUT) n={len(late)}")

    result = {"corpus": corpus, "stats": {}}

    # ---- per-stat: (a) does CV predict |resid| OOS, (b) coverage, (c) sizing ----
    for stat in STATS:
        nstat = len([b for b in late if b["stat"] == stat])
        if nstat < 40:
            continue
        cvstats = stat_cv_stats(early, stat) or stat_cv_stats(bets, stat)
        base_sig = base.get(stat, 1.0)
        print(f"\n  --- {stat.upper()}  (late n={nstat}) ---")

        # (a) residual-magnitude correlation OOS (LATE half = held out)
        r_late, n_late = resid_mag_corr(late, stat, "_cv")
        r_early, _ = resid_mag_corr(early, stat, "_cv")
        q = quartile_resid(late, stat, "_cv")
        qstr = (f"  |resid| lo={q['lo_resid']:.2f} hi={q['hi_resid']:.2f} ratio={q['ratio']:.2f}x"
                if q else "")
        print(f"   corr(CV,|resid|): early={r_early if r_early is None else round(r_early,3)} "
              f"late={r_late if r_late is None else round(r_late,3)}{qstr}")

        # (b) interval coverage flat vs per-bet (nominal 0.90 at z=1.645)
        cov = coverage_check(late, stat, base_sig, cvstats)
        if cov:
            print(f"   coverage@90 flat={cov['cov_flat']:.3f}  per-bet={cov['cov_perbet']:.3f}  (nominal 0.90)")

        # (c) sizing comparison on HELD-OUT late half
        em = edge_min_map.get(stat, 0.0)
        late_s = [b for b in late if b["stat"] == stat]

        def sig_flat(b, bs=base_sig):
            return bs

        def sig_pb(b, bs=base_sig, cs=cvstats):
            return per_bet_sigma(b, bs, cs)[1]

        flat = grade_sized(late_s, "flat", edge_min=em)
        eos_flat = grade_sized(late_s, "edge_over_sigma", sigma_fn=sig_flat, edge_min=em)
        eos_pb = grade_sized(late_s, "edge_over_sigma", sigma_fn=sig_pb, edge_min=em)
        k_flat = grade_sized(late_s, "kelly", sigma_fn=sig_flat, edge_min=em)
        k_pb = grade_sized(late_s, "kelly", sigma_fn=sig_pb, edge_min=em)

        print(f"   SIZING ROI (held-out, edge_min={em}):")
        print(f"     flat 1u           roi={flat['roi_pct']:+6.2f}%  (n={flat['n_bet']})")
        print(f"     edge/sigma_flat   roi={eos_flat['roi_pct']:+6.2f}%  (n={eos_flat['n_bet']} stake={eos_flat['total_stake']:.0f})")
        print(f"     edge/sigma_PERBET roi={eos_pb['roi_pct']:+6.2f}%  (n={eos_pb['n_bet']} stake={eos_pb['total_stake']:.0f})")
        print(f"     Kelly sigma_flat  roi={k_flat['roi_pct']:+6.2f}%  logg/bet={k_flat['logg_per_bet']:+.4f} (n={k_flat['n_bet']})")
        print(f"     Kelly sigma_PERBT roi={k_pb['roi_pct']:+6.2f}%  logg/bet={k_pb['logg_per_bet']:+.4f} (n={k_pb['n_bet']})")

        result["stats"][stat] = {
            "n_late": nstat, "r_late": r_late, "r_early": r_early,
            "quartile": q, "coverage": cov,
            "flat": flat, "eos_flat": eos_flat, "eos_pb": eos_pb,
            "k_flat": k_flat, "k_pb": k_pb}

    # ---- bettable book (AST+REB) aggregate sizing ----
    bettable = [b for b in late if b["stat"] in ("ast", "reb")]
    if bettable:
        # per-stat sigma fns
        def sig_flat_all(b):
            return base.get(b["stat"], 1.0)

        cvmap = {s: (stat_cv_stats(early, s) or stat_cv_stats(bets, s)) for s in ("ast", "reb")}

        def sig_pb_all(b):
            return per_bet_sigma(b, base.get(b["stat"], 1.0), cvmap.get(b["stat"]))[1]

        flat = grade_sized(bettable, "flat")
        eos_pb = grade_sized(bettable, "edge_over_sigma", sigma_fn=sig_pb_all)
        eos_fl = grade_sized(bettable, "edge_over_sigma", sigma_fn=sig_flat_all)
        k_pb = grade_sized(bettable, "kelly", sigma_fn=sig_pb_all)
        k_fl = grade_sized(bettable, "kelly", sigma_fn=sig_flat_all)
        print(f"\n  === BETTABLE BOOK (AST+REB) held-out aggregate ===")
        print(f"     flat 1u           roi={flat['roi_pct']:+6.2f}%  (n={flat['n_bet']})")
        print(f"     edge/sigma_flat   roi={eos_fl['roi_pct']:+6.2f}%  (n={eos_fl['n_bet']})")
        print(f"     edge/sigma_PERBET roi={eos_pb['roi_pct']:+6.2f}%  (n={eos_pb['n_bet']})")
        print(f"     Kelly sigma_flat  roi={k_fl['roi_pct']:+6.2f}%  logg/bet={k_fl['logg_per_bet']:+.4f}")
        print(f"     Kelly sigma_PERBT roi={k_pb['roi_pct']:+6.2f}%  logg/bet={k_pb['logg_per_bet']:+.4f}")
        result["bettable"] = {"flat": flat, "eos_pb": eos_pb, "eos_fl": eos_fl,
                              "k_pb": k_pb, "k_fl": k_fl}
    return result


def main():
    print("Building leak-free as-of per-(player,stat) consistency CV from calframe actuals ...")
    asof_cv = build_asof_cv()
    print(f"  built {len(asof_cv):,} as-of CV records")
    base = base_sigmas()
    print("base per-stat sigma (recommended):", {k: round(v, 2) for k, v in base.items()})

    # AST gets the gated edge_min where the real edge lives; others 0
    edge_min_map = {"ast": 0.75}

    results = []
    # Family A (the big sample)
    r = run_corpus("extended_oos_canonical.csv", asof_cv, base, edge_min_map)
    if r:
        results.append(r)
    # Family B (independent same-season, odds-api, thin)
    r = run_corpus("regular_season_2025_26_oddsapi.csv", asof_cv, base, edge_min_map)
    if r:
        results.append(r)
    # Family C (independent cross-season)
    r = run_corpus("regular_season_2024_25_oddsapi.csv", asof_cv, base, edge_min_map)
    if r:
        results.append(r)

    # ---- verdict summary ----
    print(f"\n{'#'*74}\n VERDICT SUMMARY\n{'#'*74}")
    print("Gate 1 — does consistency-CV predict |residual| OOS (late half, corr>0)?")
    for r in results:
        fam = r["corpus"]
        for stat, s in r["stats"].items():
            rl = s["r_late"]
            print(f"  [{fam[:28]:28s}] {stat:4s} corr_late="
                  f"{rl if rl is None else round(rl, 3)}")
    print("\nGate 2 — does consistency-sized ROI beat flat on the bettable book?")
    for r in results:
        if "bettable" in r:
            bb = r["bettable"]
            print(f"  [{r['corpus'][:28]:28s}] flat={bb['flat']['roi_pct']:+.2f}%  "
                  f"eos_perbet={bb['eos_pb']['roi_pct']:+.2f}%  "
                  f"kelly_perbet={bb['k_pb']['roi_pct']:+.2f}% "
                  f"(logg/bet flat={bb['k_fl']['logg_per_bet']:+.4f} pb={bb['k_pb']['logg_per_bet']:+.4f})")


if __name__ == "__main__":
    main()
