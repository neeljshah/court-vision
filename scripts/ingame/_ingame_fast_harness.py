"""_ingame_fast_harness.py — score in-game intelligence adjustments in SECONDS
against the cached baseline projection table (data/cache/ingame_eval_cache.parquet,
built by build_ingame_eval_cache.py). The in-game analog of _pts_oof_harness.

Contract:
    from scripts.ingame._ingame_fast_harness import load_eval_frame, score_adjustment
    df = load_eval_frame()
    # adjust(df) -> array of REMAINING-projection multipliers (1.0 = no change),
    # aligned row-for-row to df. Leak-safe: derive ONLY from columns present in df
    # (period, score_margin, game_remaining_sec, pf, cur_min, cur, stat, ...).
    def adjust(d):
        m = np.ones(len(d))
        hit = (d["stat"]=="pts") & (d["pf"]>=5) & (d["period"]>=3)
        m[hit.values] = 0.85          # foul-trouble scorer fade, e.g.
        return m
    score_adjustment(df, adjust, label="my_rule", stats=("pts",))

new_proj = cur + (routed - cur) * mult ; MAE compared vs the deployed `routed`.
Reports overall / per-stat / per-bucket and the 200g AND 500g replication subsets.
"""
from __future__ import annotations
import os
import numpy as np

_CACHE = os.path.join("data", "cache", "ingame_eval_cache.parquet")


def load_eval_frame(path: str = _CACHE):
    import pandas as pd
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not built yet — run: python scripts/ingame/build_ingame_eval_cache.py --max-games 0")
    df = pd.read_parquet(path)
    df["game_id"] = df["game_id"].astype(str)
    return df


def _first_n_games(df, n: int):
    """Chronological first-n unique games (game_date, game_id) — mirrors the
    replication-gate subsets."""
    order = (df[["game_date", "game_id"]].drop_duplicates()
             .sort_values(["game_date", "game_id"]).head(n))
    keys = set(map(tuple, order.values.tolist()))
    mask = [(d, g) in keys for d, g in zip(df["game_date"], df["game_id"])]
    return df[np.array(mask)]


def _mae(sub, proj_col):
    return float((sub[proj_col] - sub["truth"]).abs().mean())


def score_adjustment(df, adjust, label: str, stats=("pts", "reb", "ast"),
                     subsets=(200, 500), verbose: bool = True) -> dict:
    import pandas as pd
    d = df.copy()
    mult = np.asarray(adjust(d), dtype=float)
    if mult.shape[0] != len(d):
        raise ValueError(f"adjust returned {mult.shape[0]} mults for {len(d)} rows")
    rem = (d["routed"] - d["cur"]).to_numpy(float)
    d["adj"] = d["cur"].to_numpy(float) + rem * mult
    n_changed = int((np.abs(mult - 1.0) > 1e-9).sum())

    def _report(frame, scope):
        out = {}
        tgt = frame[frame["stat"].isin(stats)]
        out["base"] = _mae(tgt, "routed"); out["new"] = _mae(tgt, "adj")
        out["delta"] = out["new"] - out["base"]
        out["pct"] = (out["delta"] / out["base"] * 100) if out["base"] else 0.0
        out["n"] = len(tgt); out["scope"] = scope
        return out

    full = _report(d, "full")
    sub_reports = {}
    ngames = d["game_id"].nunique()
    for n in subsets:
        if ngames >= n:
            sub_reports[n] = _report(_first_n_games(d, n), f"{n}g")

    # per-stat + per-bucket on full
    per_stat = {}
    for s in stats:
        ds = d[d["stat"] == s]
        if len(ds):
            per_stat[s] = {"base": _mae(ds, "routed"), "new": _mae(ds, "adj"), "n": len(ds)}
            per_stat[s]["pct"] = (per_stat[s]["new"] - per_stat[s]["base"]) / per_stat[s]["base"] * 100 if per_stat[s]["base"] else 0.0

    # regression check on the OTHER core stats (must not get worse)
    others = [s for s in ("pts", "reb", "ast") if s not in stats]
    other_reg = {}
    for s in others:
        ds = d[d["stat"] == s]
        if len(ds):
            other_reg[s] = (_mae(ds, "adj") - _mae(ds, "routed"))

    passed = (full["delta"] < 0 and all(r["delta"] < 0 for r in sub_reports.values())
              and all(v <= 1e-6 for v in other_reg.values()))

    if verbose:
        print(f"\n========== {label}  (stats={stats}, {n_changed:,} rows adjusted) ==========")
        print(f"  FULL ({full['n']:,} rows, {ngames} games): base={full['base']:.4f} "
              f"new={full['new']:.4f} delta={full['delta']:+.4f} ({full['pct']:+.2f}%)")
        for n, r in sub_reports.items():
            print(f"  {n}g subset: base={r['base']:.4f} new={r['new']:.4f} "
                  f"delta={r['delta']:+.4f} ({r['pct']:+.2f}%)  "
                  f"{'WIN' if r['delta']<0 else 'lose'}")
        for s, v in per_stat.items():
            print(f"    {s}: base={v['base']:.4f} new={v['new']:.4f} ({v['pct']:+.2f}%) n={v['n']}")
        if other_reg:
            print(f"    other-stat regression (must be <=0): "
                  + ", ".join(f"{s}:{v:+.4f}" for s, v in other_reg.items()))
        print(f"  GATE (beat base on full AND 200g AND 500g, no other-stat regression): "
              f"{'PASS' if passed else 'FAIL'}")
    return {"label": label, "full": full, "subsets": sub_reports,
            "per_stat": per_stat, "other_reg": other_reg, "pass": bool(passed),
            "n_changed": n_changed}
