"""CORRECTED cross-season conditioner test. The crosstime_oof parquet saved
dataset-row columns where opp_pace/n_out are all-NaN and 'std_min' is mislabeled
(~minutes, not minutes-volatility). Fix: join the leak-free rolling-origin preds
to calibration_frame_v2's CORRECT as-of conditioners (opp_pace ~99.8, std_min
~4.8, n_out ~1.0 — all non-null across 3 seasons) on (pid, date, stat='ast').

Then gate AST and split by pace / std_min / n_out per independent season.
A concentrator must hold (pre-registered sign + positive favored slice) in EVERY
season tested, else NOT robust.
"""
from __future__ import annotations
import glob, os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIT = os.path.join(ROOT, "data", "cache", "pit")
CAL = os.path.join(ROOT, "data", "cache", "calibration_frame_v2.parquet")
THR = 101.9


def _payout(o, w):
    return (-100.0 if not w else (100.0/abs(o)*100.0 if o < 0 else o/100.0*100.0))


def roi(df):
    n = w = 0; pnl = 0.0
    for r in df.itertuples(index=False):
        if abs(r.pred-r.line) < 1e-9 or abs(r.actual-r.line) < 1e-9:
            continue
        over = r.pred > r.line
        won = (over and r.actual > r.line) or (not over and r.actual < r.line)
        n += 1; w += int(won); pnl += _payout(r.over_odds if over else r.under_odds, won)
    return {"n": n, "win": 100*w/n if n else 0, "roi": pnl/(n*100)*100 if n else 0}


def load_cal():
    cf = pd.read_parquet(CAL, columns=["player_id", "date", "stat", "opp_pace", "std_min", "n_out", "rest_days", "is_b2b"])
    cf = cf[cf.stat == "ast"].copy()
    cf["d"] = pd.to_datetime(cf["date"]).dt.strftime("%Y-%m-%d")
    cf = cf.drop_duplicates(["player_id", "d"])
    return cf.set_index(["player_id", "d"])[["opp_pace", "std_min", "n_out", "rest_days", "is_b2b"]]


def analyze(path, cal):
    df = pd.read_parquet(path)
    tag = os.path.basename(path).replace("crosstime_oof_ast_", "").replace(".parquet", "")
    df["d"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    # join correct conditioners
    for c in ["opp_pace", "std_min", "n_out", "rest_days", "is_b2b"]:
        df[c] = [cal["opp_pace" if c == "opp_pace" else c].get((int(p), d), np.nan)
                 if (int(p), d) in cal.index else np.nan for p, d in zip(df.pid, df.d)]
    # simpler robust join
    j = df.merge(cal.reset_index().rename(columns={"player_id": "pid"}), on=["pid", "d"], how="left", suffixes=("", "_c"))
    for c in ["opp_pace", "std_min", "n_out", "rest_days", "is_b2b"]:
        if c+"_c" in j:
            j[c] = j[c+"_c"]
    cov = j["std_min"].notna().mean()
    g = j[(abs(j.pred-j.line) >= 0.75) & (j.line <= 7.5)].copy()
    gg = roi(g)
    print(f"\n===== {tag} (n={len(df)}, cond-cov={cov:.0%}) =====")
    print(f"  GATED AST: n={gg['n']} win={gg['win']:.1f}% roi={gg['roi']:+.2f}%")
    res = {}
    # pace
    gp = g[np.isfinite(g.opp_pace)]
    hi, lm = roi(gp[gp.opp_pace > THR]), roi(gp[gp.opp_pace <= THR])
    print(f"  PACE(>{THR}): HIGH {hi['roi']:+.1f}%(n{hi['n']}) vs LOW+MID {lm['roi']:+.1f}%(n{lm['n']}) diff={hi['roi']-lm['roi']:+.1f}pp")
    res["pace"] = (hi, lm)
    # stab (low std_min favored)
    gs = g[np.isfinite(g.std_min)]
    med = gs.std_min.median()
    lo, hihi = roi(gs[gs.std_min <= med]), roi(gs[gs.std_min > med])
    print(f"  STAB std_min(med={med:.2f}): LOW {lo['roi']:+.1f}%(n{lo['n']}) vs HIGH {hihi['roi']:+.1f}%(n{hihi['n']}) diff={lo['roi']-hihi['roi']:+.1f}pp")
    res["stab"] = (lo, hihi)
    # nout (out>0 favored)
    gn = g[np.isfinite(g.n_out)]
    o, z = roi(gn[gn.n_out > 0]), roi(gn[gn.n_out <= 0])
    print(f"  NOUT: out>0 {o['roi']:+.1f}%(n{o['n']}) vs out=0 {z['roi']:+.1f}%(n{z['n']}) diff={o['roi']-z['roi']:+.1f}pp")
    res["nout"] = (o, z)
    return tag, res


if __name__ == "__main__":
    cal = load_cal()
    paths = sorted(glob.glob(os.path.join(PIT, "crosstime_oof_ast_*.parquet")))
    out = [analyze(p, cal) for p in paths]
    print("\n=== CORRECTED CROSS-SEASON VERDICT (favored slice must be positive AND beat other in EVERY season) ===")
    for cond in ("pace", "stab", "nout"):
        ok_all = True; parts = []
        for tag, res in out:
            a, b = res[cond]
            ok = a["roi"] > b["roi"] and a["roi"] > 0 and a["n"] >= 15
            ok_all = ok_all and ok
            parts.append(f"{tag[-7:]}:{a['roi']:+.0f}(n{a['n']})vs{b['roi']:+.0f}{'✓' if ok else '✗'}")
        print(f"  {cond:5s} {'ROBUST' if ok_all else 'NOT robust'}: " + " | ".join(parts))
