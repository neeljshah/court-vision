"""EXPERIMENT (prediction-integration): does a player's STABLE outcome IMPACT
(on/off plus-minus swing + adjusted plus-minus + who-decides consensus z) carry
prop-residual signal the model didn't already absorb via usage/form features?

HYPOTHESIS (basketball): the reliability audit found on/off plus-minus is the one
STABLE outcome signal (split-half 0.74). A genuinely high-impact player may carry
production more consistently (smaller |residual| => SELECTION/SIZING signal) or have
a different prop residual (POINT TILT) than role-players the model treats similarly.

STRICT leak-free design:
  - PRIMARY impact = PRIOR-SEASON (2024-25) only:
      on_off_impact_z   (on_off_features.parquet, season 2024-25, z-scored on/off swing)
      rapm_per100_z     (player_plusminus.json rapm_2024_25 ridge-RAPM, z-scored)
    => these never see 2025-26 game outcomes -> leak-free for 2025-26 reg-season bets.
  - SECONDARY (leak-FLAGGED, sensitivity only): 2025-26 adj_impact + consensus_z are
    SAME-SEASON season-aggregates (a Jan bet's aggregate includes Feb-Apr games) -> mild
    lookahead; reported separately, never used to claim ship.

TESTS:
  (0) ORTHOGONALITY pre-screen: corr(impact, actual-pred) per stat (PTS/AST/REB).
      |corr| >~ 0.05 to proceed; else fast-reject (model already has it; impact is
      collinear with usage).
  (a) POINT tilt: pred_adj = pred + beta*impact_z, fit beta on EARLY half, grade LATE.
  (b) SELECTION/predictability: does high-impact tercile have SMALLER |residual|
      (more predictable)? + ROI-by-impact-tercile (bet only high-impact players).

GRADE on >=2 INDEPENDENT corpora: Family A (extended_oos) AND Family C
(regular_season_2024_25_oddsapi, cross-season) [+ Family B oddsapi-25-26 if n allows].
drop |odds|<100 (grader does), coherence guard, reg-season only.

Run: conda run -n basketball_ai python scripts/pit/exp_onoff_feature.py
Read-only except stdout; writes nothing.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

ROOT = r"C:\Users\neelj\nba-ai-system"
STATS = ["ast", "reb", "pts"]  # the bettable stats per VS_VEGAS; fg3m optional


# ---------------------------------------------------------------------------
# 1. Build the leak-free per-player IMPACT table (pid -> dict of impact features)
# ---------------------------------------------------------------------------
def _zscore(series: pd.Series) -> pd.Series:
    s = series.astype(float)
    mu, sd = s.mean(), s.std()
    return (s - mu) / sd if sd > 1e-9 else s * 0.0


def build_impact_table() -> dict:
    """Returns {pid(int): {impact_z, onoff_z, rapm_z, adj_impact_z(LEAK), consensus_z(LEAK),
    confidence}}. PRIMARY (leak-free) = onoff_z (2024-25) & rapm_z (2024-25)."""
    impact = {}

    # --- on_off_features (2024-25, prior-season) -> leak-free ---
    oo = pd.read_parquet(os.path.join(ROOT, "data", "cache", "on_off_features.parquet"))
    oo = oo[oo["season"] == "2024-25"].copy()
    # on_off_impact_z is already z-scored in the file; keep it.
    for r in oo.itertuples(index=False):
        pid = int(r.player_id)
        impact.setdefault(pid, {})
        impact[pid]["onoff_z"] = float(r.on_off_impact_z) if np.isfinite(r.on_off_impact_z) else np.nan
        impact[pid]["onoff_diff"] = float(r.on_off_diff) if np.isfinite(r.on_off_diff) else np.nan

    # --- player_plusminus.json: rapm_2024_25 (leak-free) + adj_impact 2025-26 (LEAK) ---
    with open(os.path.join(ROOT, "data", "cache", "intel_outcome", "player_plusminus.json")) as f:
        pm = json.load(f)
    # rapm 2024-25 players -> z-score the rapm_per100 (prior season => leak-free)
    rapm_players = pm.get("rapm_2024_25", {}).get("players", {})
    if rapm_players:
        rdf = pd.DataFrame([
            {"pid": int(k), "rapm": v.get("rapm_per100"), "conf": v.get("confidence", np.nan)}
            for k, v in rapm_players.items() if v.get("rapm_per100") is not None
        ])
        rdf["rapm_z"] = _zscore(rdf["rapm"])
        for r in rdf.itertuples(index=False):
            impact.setdefault(int(r.pid), {})
            impact[int(r.pid)]["rapm_z"] = float(r.rapm_z)
            impact[int(r.pid)]["rapm_conf"] = float(r.conf) if np.isfinite(r.conf) else np.nan
    # adj_impact 2025-26 (SAME-SEASON season-aggregate => LEAK-FLAGGED secondary)
    pm_players = pm.get("players", {})
    if pm_players:
        adf = pd.DataFrame([
            {"pid": int(k), "adj": v.get("adj_impact"), "conf": v.get("confidence", np.nan),
             "minutes": v.get("minutes", np.nan)}
            for k, v in pm_players.items() if v.get("adj_impact") is not None
        ])
        adf["adj_z"] = _zscore(adf["adj"])
        for r in adf.itertuples(index=False):
            impact.setdefault(int(r.pid), {})
            impact[int(r.pid)]["adj_impact_z_LEAK"] = float(r.adj_z)
            impact[int(r.pid)]["pm_conf"] = float(r.conf) if np.isfinite(r.conf) else np.nan

    # --- who_decides_consensus.json consensus_z (sparse ~45 players, blends 2025-26 => LEAK) ---
    with open(os.path.join(ROOT, "data", "cache", "intel_outcome", "who_decides_consensus.json")) as f:
        wd = json.load(f)
    for rec in list(wd.get("consensus_top", [])) + list(wd.get("disagreements", [])):
        try:
            pid = int(rec["pid"])
        except (KeyError, ValueError, TypeError):
            continue
        cz = rec.get("consensus_z")
        if cz is not None:
            impact.setdefault(pid, {})
            impact[pid]["consensus_z_LEAK"] = float(cz)

    # --- PRIMARY composite stable-impact z = mean of available leak-free z's (onoff_z, rapm_z) ---
    for pid, d in impact.items():
        zs = [d[k] for k in ("onoff_z", "rapm_z") if np.isfinite(d.get(k, np.nan))]
        d["impact_z"] = float(np.mean(zs)) if zs else np.nan
    return impact


def attach_impact(bets, impact: dict) -> tuple:
    """Attach impact keys onto each bet dict by pid. Returns (bets, coverage dict)."""
    keys = ["impact_z", "onoff_z", "rapm_z", "adj_impact_z_LEAK", "consensus_z_LEAK"]
    cov = {k: 0 for k in keys}
    for b in bets:
        d = impact.get(b["pid"], {})
        for k in keys:
            v = d.get(k, np.nan)
            b[k] = v
            if np.isfinite(v):
                cov[k] += 1
    return bets, cov


# ---------------------------------------------------------------------------
# 2. Tests
# ---------------------------------------------------------------------------
def _vals(bets, key):
    return np.array([b.get(key, np.nan) for b in bets], dtype=float)


def orthogonality(bets, stat, key):
    sub = [b for b in bets if b["stat"] == stat]
    sig = _vals(sub, key)
    pred = _vals(sub, "pred")
    act = np.array([b["actual"] for b in sub], dtype=float)
    resid = act - pred
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30 or np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    return float(np.corrcoef(sig[m], resid[m])[0, 1]), int(m.sum())


def predictability_by_tercile(bets, stat, key):
    """Does high |impact| -> smaller |residual| (more predictable)?  Reports
    mean |actual-pred| in low/mid/high tercile of the impact MAGNITUDE."""
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 45:
        return None
    mag = np.abs(_vals(sub, key))
    aerr = np.abs(np.array([b["actual"] - b["pred"] for b in sub]))
    lo, hi = np.nanpercentile(mag, [33.333, 66.667])
    out = {}
    for nm, msk in [("low", mag <= lo), ("mid", (mag > lo) & (mag <= hi)), ("high", mag > hi)]:
        if msk.sum() >= 10:
            out[nm] = {"mae": float(np.mean(aerr[msk])), "n": int(msk.sum())}
    # also signed-impact tercile MAE (high positive vs low)
    return out


def tercile_roi(bets, stat, key, edge_min=0.0):
    """ROI by SIGNED-impact tercile (low/mid/high impact players)."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(key, np.nan))]
    if len(sub) < 45:
        return None
    sig = _vals(sub, key)
    lo, hi = np.nanpercentile(sig, [33.333, 66.667])
    out = {}
    for nm, msk in [("low", sig <= lo), ("mid", (sig > lo) & (sig <= hi)), ("high", sig > hi)]:
        bb = [sub[i] for i in range(len(sub)) if msk[i]]
        out[nm] = ig.roi(bb, predictor="pred", edge_min=edge_min)
    return out


def magnitude_roi(bets, stat, key, edge_min=0.0):
    """ROI for high-|impact| players (top tercile of |impact|) vs all -- the
    SELECTION test: bet only the players the model can predict reliably."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(key, np.nan))]
    if len(sub) < 45:
        return None
    mag = np.abs(_vals(sub, key))
    thi = np.nanpercentile(mag, 66.667)
    hi = [sub[i] for i in range(len(sub)) if mag[i] > thi]
    lo = [sub[i] for i in range(len(sub)) if mag[i] <= np.nanpercentile(mag, 33.333)]
    return {"all": ig.roi(sub, edge_min=edge_min),
            "highImpact": ig.roi(hi, edge_min=edge_min),
            "lowImpact": ig.roi(lo, edge_min=edge_min)}


def fit_beta(rows, stat, key):
    sub = [b for b in rows if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 30:
        return None
    sig = np.array([b[key] for b in sub])
    resid = np.array([b["actual"] - b["pred"] for b in sub])
    if np.std(sig) < 1e-9:
        return None
    return float(np.cov(sig, resid)[0, 1] / np.var(sig))


def point_tilt_heldout(bets, stat, key):
    """Fit beta on EARLY half, apply to LATE half, compare ROI raw vs adj on LATE."""
    ds = sorted({b["gdate"] for b in bets})
    if len(ds) < 4:
        return None
    mid = ds[len(ds) // 2]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    beta = fit_beta(early, stat, key)
    if beta is None:
        return None
    late_stat = [b for b in late if b["stat"] == stat]
    flips = 0
    for b in late_stat:
        if np.isfinite(b.get(key, np.nan)) and np.isfinite(b.get("pred", np.nan)):
            adj = b["pred"] + beta * b[key]
            b["_pred_adj"] = adj
            if (b["pred"] > b["line"]) != (adj > b["line"]):
                flips += 1
    raw = ig.roi(late_stat, predictor="pred")
    adj = ig.roi([b for b in late_stat if "_pred_adj" in b], predictor="_pred_adj")
    return {"beta": beta, "raw": raw, "adj": adj, "flips": flips, "n_late": len(late_stat)}


# ---------------------------------------------------------------------------
# 3. Driver
# ---------------------------------------------------------------------------
def run_corpus(corpus, impact, edge_min_ast=0.0):
    print(f"\n{'='*74}\n CORPUS: {corpus}\n{'='*74}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'}) | joined n={len(bets)}")
    if not coh["coherent"]:
        print(" !! corrupt corpus -- REFUSE to grade"); return
    bets, cov = attach_impact(bets, impact)
    print(" impact coverage (bets with finite signal):")
    for k, n in cov.items():
        print(f"    {k:22s} {n}/{len(bets)} ({100*n/max(len(bets),1):.0f}%)")

    primary = "impact_z"  # leak-free composite
    for stat in STATS:
        nstat = len([b for b in bets if b["stat"] == stat])
        ncov = len([b for b in bets if b["stat"] == stat and np.isfinite(b.get(primary, np.nan))])
        if ncov < 45:
            print(f"\n  --- {stat.upper()}: only {ncov} bets w/ impact_z (<45) skip ---")
            continue
        print(f"\n  --- {stat.upper()}  (n={nstat}, impact-covered={ncov}) ---")

        # (0) orthogonality: primary + each leak-free component + leaked sensitivity
        print("   orthogonality corr(signal, actual-pred):")
        for key in ["impact_z", "onoff_z", "rapm_z", "adj_impact_z_LEAK", "consensus_z_LEAK"]:
            r, n = orthogonality(bets, stat, key)
            flag = ""
            if r is not None and abs(r) >= 0.05:
                flag = "  <-- non-trivial"
            tag = " [LEAK]" if key.endswith("_LEAK") else ""
            print(f"     {key:20s}{tag:7s} r={None if r is None else round(r,3)} (n={n}){flag}")

        # (b) predictability: high-|impact| -> smaller MAE?
        pb = predictability_by_tercile(bets, stat, primary)
        if pb:
            print("   |residual| MAE by |impact_z| tercile (smaller=more predictable):")
            print("     " + "  ".join(f"{nm}: MAE={pb[nm]['mae']:.2f}(n{pb[nm]['n']})" for nm in pb))

        # (b) ROI by SIGNED impact tercile (selection)
        tr = tercile_roi(bets, stat, primary)
        if tr:
            print("   ROI by SIGNED impact_z tercile: " + " ".join(
                f"{nm}={tr[nm]['roi_pct']:+.1f}%(n{tr[nm]['n']})" for nm in ("low", "mid", "high")))
        # (b) ROI high-|impact| vs all (the SELECTION test)
        mr = magnitude_roi(bets, stat, primary)
        if mr:
            print(f"   SELECTION ROI: all={mr['all']['roi_pct']:+.1f}%(n{mr['all']['n']}) "
                  f"highImpact={mr['highImpact']['roi_pct']:+.1f}%(n{mr['highImpact']['n']}) "
                  f"lowImpact={mr['lowImpact']['roi_pct']:+.1f}%(n{mr['lowImpact']['n']})")

        # (a) POINT tilt held-out
        pt = point_tilt_heldout(bets, stat, primary)
        if pt:
            lift = pt["adj"]["roi_pct"] - pt["raw"]["roi_pct"]
            print(f"   POINT tilt (beta={pt['beta']:+.3f} fit-early, grade-late, flips={pt['flips']}/{pt['n_late']}):")
            print(f"     raw={pt['raw']['roi_pct']:+.2f}%(n{pt['raw']['n']}) -> "
                  f"adj={pt['adj']['roi_pct']:+.2f}%(n{pt['adj']['n']})  LIFT={lift:+.2f}pp")


def main():
    impact = build_impact_table()
    n_primary = sum(1 for d in impact.values() if np.isfinite(d.get("impact_z", np.nan)))
    print(f"Built impact table: {len(impact)} players, {n_primary} with leak-free impact_z "
          f"(onoff_z & rapm_z, 2024-25 prior-season).")
    # Family A (big sample) + Family C (cross-season independent) + Family B (thin same-season)
    run_corpus("extended_oos_canonical.csv", impact)
    run_corpus("regular_season_2024_25_oddsapi.csv", impact)
    run_corpus("regular_season_2025_26_oddsapi.csv", impact)


if __name__ == "__main__":
    main()
