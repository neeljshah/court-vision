"""analyze_routed_residuals.py — instant error analysis on the cached in-game
projection table. Finds where the DEPLOYED `routed` projection is systematically
biased by game-state (residual = routed - truth), so intelligence rules target a
REAL un-priced error rather than something the wired factors already handle.

    python scripts/ingame/analyze_routed_residuals.py [--cache PATH] [--stat pts]
"""
from __future__ import annotations
import argparse, os, sys
import numpy as np
sys.path.insert(0, ".")
from scripts.ingame._ingame_fast_harness import load_eval_frame

_DEF = os.path.join("data", "cache", "ingame_eval_cache.parquet")


def _slice(df, col, bins, labels):
    import pandas as pd
    return pd.cut(df[col], bins=bins, labels=labels)


def analyze(cache: str, stats):
    import pandas as pd
    df = load_eval_frame(cache)
    df["resid"] = df["routed"] - df["truth"]
    df["absmargin"] = df["score_margin"].abs()
    print(f"loaded {len(df):,} rows / {df['game_id'].nunique()} games\n")
    for s in stats:
        d = df[df["stat"] == s]
        if not len(d):
            continue
        print(f"================ {s.upper()}  (base MAE={d['resid'].abs().mean():.4f}, "
              f"mean bias={d['resid'].mean():+.4f}, n={len(d):,}) ================")
        for col, bins, labs in [
            ("period", [-1, 1, 2, 3, 10], ["Q1", "Q2", "Q3", "Q4+"]),
            ("absmargin", [-1, 5, 10, 20, 200], ["<=5", "6-10", "11-20", "20+"]),
            ("pf", [-1, 1, 2, 3, 4, 10], ["0-1", "2", "3", "4", "5+"]),
            ("cur_min", [-1, 12, 24, 32, 100], ["<12", "12-24", "24-32", "32+"]),
        ]:
            d2 = d.copy(); d2["b"] = _slice(d2, col, bins, labs)
            g = d2.groupby("b", observed=True)["resid"].agg(["mean", "count"])
            ga = d2.groupby("b", observed=True)["resid"].apply(lambda x: x.abs().mean())
            row = "  ".join(
                f"{lab}:bias{g.loc[lab,'mean']:+.2f}|mae{ga.loc[lab]:.2f}(n{int(g.loc[lab,'count'])})"
                for lab in labs if lab in g.index)
            print(f"  by {col:10s}: {row}")
        print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=_DEF)
    ap.add_argument("--stat", default=None, help="single stat, else pts/reb/ast")
    a = ap.parse_args()
    stats = [a.stat] if a.stat else ["pts", "reb", "ast"]
    analyze(a.cache, stats)
