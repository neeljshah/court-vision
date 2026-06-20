"""domains.tennis.asof_return_eval -- CLI accuracy harness for asof_return.py.

Builds asof_return and prints coverage + corr(diff_asof, diff_realized) + MAE vs a
flat baseline, per metric (return_won, break_pct), overall and by surface.

ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from domains.tennis.asof_hold import _STATS_COLS
from domains.tennis.asof_return import (
    _MATCH_STATS_DEFAULT,
    _MATCHES_DEFAULT,
    _METRICS,
    _OUT_DEFAULT,
    _SURFACES,
    _derive_realized_return,
    build_asof_return,
)

_FLAT = {"return_won": 0.38, "break_pct": 0.22}  # rough population priors


def run_eval(
    match_stats_path: str = _MATCH_STATS_DEFAULT,
    matches_path: str = _MATCHES_DEFAULT,
    out_path: str = _OUT_DEFAULT,
    min_prior: int = 5,
) -> None:
    ms = pd.read_parquet(match_stats_path)
    mt = pd.read_parquet(matches_path)
    dest = build_asof_return(match_stats=ms, matches=mt, out_path=out_path)
    df = pd.read_parquet(dest)
    print(f"asof_return: {len(df)} rows -> {dest}")

    avail = [c for c in _STATS_COLS if c in ms.columns]
    ms_r = _derive_realized_return(ms[avail].copy())
    for m in _METRICS:
        ms_r[f"diff_{m}_realized"] = ms_r[f"p1_{m}_realized"] - ms_r[f"p2_{m}_realized"]

    merged = df.merge(
        ms_r[["event_id"] + [f"p1_{m}_realized" for m in _METRICS]
             + [f"diff_{m}_realized" for m in _METRICS]],
        on="event_id", how="inner",
    )
    for m in _METRICS:
        sub = merged.dropna(subset=[f"diff_{m}_asof", f"diff_{m}_realized"])
        sub = sub[(sub.get("p1_{0}_n_prior".format(m), 0) >= min_prior)
                  & (sub.get("p2_{0}_n_prior".format(m), 0) >= min_prior)]
        if len(sub) > 0:
            corr = sub[f"diff_{m}_asof"].corr(sub[f"diff_{m}_realized"])
            print(f"{m:11s}: corr(diff_asof, diff_realized) covered (n={len(sub)}): {corr:.4f}")
        valid = merged.dropna(subset=[f"p1_{m}_asof", f"p1_{m}_realized"])
        if len(valid) > 0:
            mae_asof = (valid[f"p1_{m}_asof"] - valid[f"p1_{m}_realized"]).abs().mean()
            mae_flat = (_FLAT[m] - valid[f"p1_{m}_realized"]).abs().mean()
            print(f"{m:11s}: MAE asof={mae_asof:.4f}  flat({_FLAT[m]})={mae_flat:.4f}  "
                  f"lift={mae_flat - mae_asof:+.4f}  (n={len(valid)})")
        for surf in _SURFACES:
            col = f"p1_{m}_{surf.lower()}_asof"
            rows = merged.dropna(subset=[col, f"p1_{m}_realized"])
            if "surface" in rows.columns:
                rows = rows[rows["surface"] == surf]
            if len(rows) > 0:
                mae_s = (rows[col] - rows[f"p1_{m}_realized"]).abs().mean()
                print(f"  {m:11s} {surf:5s}: MAE asof={mae_s:.4f}  n={len(rows)}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate asof_return feature quality")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    run_eval(args.match_stats, args.matches, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
