"""EXPERIMENT: does as-of opponent context (pace / stat-specific allowed) carry
exploitable signal the model's single `opp_def` rating misses?

Zero-retrain, leak-free. Uses the §2 "additive residual correction valid only if
orthogonal" path: a signal is only real if corr(signal, actual - oof_pred) != 0
(the model did NOT already absorb it). Then graded on real lines (selection /
tercile tilt), both-halves robust, reg/playoffs split, coherence-guarded.

Signals tested per bettable stat (stat-matched):
  - opp_pace            (H1: high pace => more possessions => more AST chances)
  - opp_def             (the single rating the model already has; control)
  - opp_<stat>_allowed_vs_league  (NEW: stat-specific defense vs league as-of)
  - opp_<stat>_allowed_asof       (NEW raw)

Run: python scripts/pit/exp_opp_conditioning.py
"""
from __future__ import annotations

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel_grade as ig  # noqa: E402

STATS = ["ast", "reb", "pts", "fg3m"]
# stat -> the matched opp-allowed signal stem
ALLOWED_STEM = {"ast": "ast", "reb": "reb", "pts": "pts", "fg3m": "fg3m"}


def _vals(bets, key):
    return np.array([b.get(key, np.nan) for b in bets], dtype=float)


def residual_corr(bets, stat, signal_key):
    """corr(signal, actual-pred) over this stat's bets with both present."""
    sub = [b for b in bets if b["stat"] == stat]
    sig = _vals(sub, signal_key)
    pred = _vals(sub, "pred")
    act = np.array([b["actual"] for b in sub], dtype=float)
    resid = act - pred
    m = np.isfinite(sig) & np.isfinite(resid)
    if m.sum() < 30:
        return None, int(m.sum())
    if np.std(sig[m]) < 1e-9:
        return None, int(m.sum())
    r = np.corrcoef(sig[m], resid[m])[0, 1]
    return r, int(m.sum())


def tercile_roi(bets, stat, signal_key, edge_min=0.0):
    """Split this stat's MODEL bets into low/mid/high tercile of signal; ROI each."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(signal_key, np.nan))]
    if len(sub) < 30:
        return None
    sig = _vals(sub, signal_key)
    lo, hi = np.nanpercentile(sig, [33.333, 66.667])
    out = {}
    for name, mask in [("low", lambda v: v <= lo),
                       ("mid", lambda v: lo < v <= hi),
                       ("high", lambda v: v > hi)]:
        bb = [b for b in sub if mask(b.get(signal_key))]
        out[name] = ig.roi(bb, predictor="pred", edge_min=edge_min)
    return out


def agreement_roi(bets, stat, signal_key, edge_min=0.0):
    """Bet only when the MODEL direction agrees with the defense signal:
    model says OVER and opp soft (signal>median) -> keep; model UNDER and opp
    stingy (signal<median) -> keep. vs all model bets for the stat."""
    sub = [b for b in bets if b["stat"] == stat and np.isfinite(b.get(signal_key, np.nan))]
    if len(sub) < 30:
        return None
    med = np.nanmedian(_vals(sub, signal_key))
    agree, all_b = [], []
    for b in sub:
        pred = b.get("pred")
        if pred is None or not np.isfinite(pred):
            continue
        all_b.append(b)
        over = pred > b["line"]
        soft = b[signal_key] > med
        if (over and soft) or ((not over) and (not soft)):
            agree.append(b)
    return {"all": ig.roi(all_b, edge_min=edge_min),
            "agree": ig.roi(agree, edge_min=edge_min)}


def temporal_halves(bets):
    ds = sorted(set(b["gdate"] for b in bets))
    if len(ds) < 4:
        return bets, []
    mid = ds[len(ds) // 2]
    early = [b for b in bets if b["gdate"] < mid]
    late = [b for b in bets if b["gdate"] >= mid]
    return early, late


def run_corpus(corpus, edge_min_ast=0.75):
    print(f"\n{'='*72}\n CORPUS: {corpus}\n{'='*72}")
    bets = ig.prepare(corpus)
    coh = ig.coherence(bets)
    print(f" coherence sum {coh['sum']:+.2f}% ({'OK' if coh['coherent'] else 'CORRUPT'})  | joined n={len(bets)}")
    if not coh["coherent"]:
        print(" !! corrupt corpus, skipping")
        return

    for stat in STATS:
        stem = ALLOWED_STEM[stat]
        sigs = {
            "opp_pace": "opp_pace",
            "opp_def": "opp_def",
            f"opp_{stem}_allowed_vsLg": f"opp_{stem}_allowed_vs_league",
            f"opp_{stem}_allowed_raw": f"opp_{stem}_allowed_asof",
        }
        nstat = len([b for b in bets if b["stat"] == stat])
        if nstat < 50:
            continue
        print(f"\n  --- {stat.upper()}  (n={nstat}) ---")
        # 1. residual orthogonality
        print("   residual corr(signal, actual-pred):")
        for label, key in sigs.items():
            r, n = residual_corr(bets, stat, key)
            flag = ""
            if r is not None and abs(r) >= 0.05:
                flag = "  <-- non-trivial"
            print(f"     {label:24s} r={r if r is None else round(r,3)} (n={n}){flag}")
        # 2. tercile ROI on the NEW vs_league signal + pace
        for label, key in [("pace", "opp_pace"), (f"{stem}_allowed_vsLg", f"opp_{stem}_allowed_vs_league")]:
            t = tercile_roi(bets, stat, key)
            if t:
                print(f"   tercile ROI by {label}: " + " ".join(
                    f"{nm}={t[nm]['roi_pct']:+.1f}%(n{t[nm]['n']})" for nm in ("low", "mid", "high")))
        # 3. agreement selection on vs_league
        ag = agreement_roi(bets, stat, f"opp_{stem}_allowed_vs_league")
        if ag:
            print(f"   agreement(vsLg): all={ag['all']['roi_pct']:+.1f}%(n{ag['all']['n']}) "
                  f"agree={ag['agree']['roi_pct']:+.1f}%(n{ag['agree']['n']})")


def run_halves(corpus):
    print(f"\n{'#'*72}\n BOTH-HALVES robustness on {corpus} (AST + REB, vs_league tercile)\n{'#'*72}")
    bets = ig.prepare(corpus)
    early, late = temporal_halves(bets)
    for stat in ("ast", "reb"):
        stem = ALLOWED_STEM[stat]
        key = f"opp_{stem}_allowed_vs_league"
        print(f"  {stat.upper()} high-{stem}-allowed tercile ROI:")
        for nm, half in [("early", early), ("late", late)]:
            t = tercile_roi(half, stat, key)
            if t:
                print(f"    {nm}: high={t['high']['roi_pct']:+.1f}%(n{t['high']['n']}) "
                      f"low={t['low']['roi_pct']:+.1f}%(n{t['low']['n']})")
        # pace too (H1)
        print(f"  {stat.upper()} high-pace tercile ROI:")
        for nm, half in [("early", early), ("late", late)]:
            t = tercile_roi(half, stat, "opp_pace")
            if t:
                print(f"    {nm}: high={t['high']['roi_pct']:+.1f}%(n{t['high']['n']}) "
                      f"low={t['low']['roi_pct']:+.1f}%(n{t['low']['n']})")


if __name__ == "__main__":
    # primary coherent window
    run_corpus("extended_oos_canonical.csv")
    run_halves("extended_oos_canonical.csv")
    # independent cross-season
    run_corpus("regular_season_2024_25_oddsapi.csv")
