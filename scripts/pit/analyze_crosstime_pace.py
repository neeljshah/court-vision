"""Cross-season decisive test for H1: does opp_pace concentrate the gated AST
edge on INDEPENDENT regular seasons? Reads the saved leak-free rolling-origin
OOF (crosstime_oof_ast_<corpus>.parquet) so we are not coverage-blocked.

For each corpus: gate AST (|pred-line|>=0.75, line<=7.5), split by opp_pace
(fixed 101.9 threshold, §8d), report high vs low+mid ROI + win + n + coherence.
H1 confirms cross-season iff high-pace beats low+mid with high-pace positive.
"""
from __future__ import annotations

import os
import sys
import glob
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
THR = 101.9


def _payout(odds, win):
    if not win:
        return -100.0
    return (100.0 / abs(odds) * 100.0) if odds < 0 else (odds / 100.0 * 100.0)


def settle_roi(df):
    n = w = 0
    pnl = 0.0
    for r in df.itertuples(index=False):
        if abs(r.pred - r.line) < 1e-9 or abs(r.actual - r.line) < 1e-9:
            continue
        over = r.pred > r.line
        won = (over and r.actual > r.line) or (not over and r.actual < r.line)
        odds = r.over_odds if over else r.under_odds
        n += 1
        w += int(won)
        pnl += _payout(odds, won)
    return {"n": n, "win": 100 * w / n if n else 0, "roi": pnl / (n * 100) * 100 if n else 0}


def coherence(df):
    def blind(over):
        n = 0
        pnl = 0.0
        for r in df.itertuples(index=False):
            if abs(r.actual - r.line) < 1e-9:
                continue
            won = (over and r.actual > r.line) or (not over and r.actual < r.line)
            odds = r.over_odds if over else r.under_odds
            n += 1
            pnl += _payout(odds, won)
        return pnl / (n * 100) * 100 if n else 0
    return blind(True) + blind(False)


def cond_split(g, col, hi_mask, lo_mask, hi_name, lo_name):
    gg = g[np.isfinite(g[col])]
    rh = settle_roi(gg[hi_mask(gg)])
    rl = settle_roi(gg[lo_mask(gg)])
    return rh, rl


def analyze(path):
    df = pd.read_parquet(path)
    tag = os.path.basename(path).replace("crosstime_oof_ast_", "").replace(".parquet", "")
    print(f"\n===== {tag}  (n={len(df)}) =====")
    print(f"  coherence (blind O+U) = {coherence(df):+.1f}%  ({'OK' if coherence(df) < 0 else 'CORRUPT'})")
    allg = settle_roi(df)
    print(f"  ALL AST: n={allg['n']} win={allg['win']:.1f}% roi={allg['roi']:+.2f}%")
    g = df[(abs(df.pred - df.line) >= 0.75) & (df.line <= 7.5)].copy()
    gg = settle_roi(g)
    print(f"  GATED (edge>=.75,line<=7.5): n={gg['n']} win={gg['win']:.1f}% roi={gg['roi']:+.2f}%")
    res = {}
    # H1 pace: high opp_pace concentrates
    rh, rl = cond_split(g, "opp_pace", lambda d: d.opp_pace > THR, lambda d: d.opp_pace <= THR, "HIGH", "LOW+MID")
    print(f"  PACE (thr={THR}): HIGH +{rh['roi']:.1f}%(n{rh['n']}) vs LOW+MID {rl['roi']:+.1f}%(n{rl['n']}) diff={rh['roi']-rl['roi']:+.1f}pp")
    res["pace"] = (rh, rl)
    # C-stab: low std_min concentrates (PRE-REG low > high)
    if "std_min" in g.columns:
        med = np.nanmedian(g["std_min"][np.isfinite(g["std_min"])])
        rlo, rhi = cond_split(g, "std_min", lambda d: d.std_min <= med, lambda d: d.std_min > med, "LOW", "HIGH")
        print(f"  STAB std_min(med={med:.1f}): LOW {rlo['roi']:+.1f}%(n{rlo['n']}) vs HIGH {rhi['roi']:+.1f}%(n{rhi['n']}) diff={rlo['roi']-rhi['roi']:+.1f}pp")
        res["stab"] = (rlo, rhi)
    # C-nout: out>0 concentrates (PRE-REG out>0 > out=0)
    if "n_out" in g.columns:
        ro, rz = cond_split(g, "n_out", lambda d: d.n_out > 0, lambda d: d.n_out <= 0, "OUT>0", "OUT=0")
        print(f"  NOUT: out>0 {ro['roi']:+.1f}%(n{ro['n']}) vs out=0 {rz['roi']:+.1f}%(n{rz['n']}) diff={ro['roi']-rz['roi']:+.1f}pp")
        res["nout"] = (ro, rz)
    return tag, res


if __name__ == "__main__":
    paths = sorted(glob.glob(os.path.join(PIT, "crosstime_oof_ast_*.parquet")))
    if not paths:
        print("no crosstime_oof_ast_*.parquet yet")
        sys.exit(0)
    out = [analyze(p) for p in paths]
    print("\n=== CROSS-SEASON CONCENTRATION VERDICT (concentrator must hold in EVERY season) ===")
    for cond in ("pace", "stab", "nout"):
        line = []
        ok_all = True
        for tag, res in out:
            if cond not in res:
                continue
            a, b = res[cond]
            ok = a["roi"] > b["roi"] and a["roi"] > 0
            ok_all = ok_all and ok
            line.append(f"{tag}:{a['roi']:+.0f}(n{a['n']})vs{b['roi']:+.0f}(n{b['n']}){'+' if ok else 'x'}")
        if line:
            print(f"  {cond:5s} {'CONCENTRATES ALL' if ok_all else 'NOT robust'}: " + " | ".join(line))
