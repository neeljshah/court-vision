"""domains.soccer.asof_xg_proxy_eval -- CLI accuracy harness for asof_xg_proxy.

Builds asof_xg_proxy and prints coverage + corr(as-of xG diffs, realized goal diff) using
matches.parquet (fthg/ftag). ACCURACY ONLY -- NO MARKET EDGE CLAIMED (xg = shots proxy).
"""
from __future__ import annotations

import argparse

import pandas as pd

from domains.soccer.asof_xg_proxy import _OUT_DEFAULT, _MATCH_STATS_DEFAULT, build_asof_xg_proxy

_MATCHES = "data/domains/soccer/matches.parquet"


def run_eval(match_stats_path: str = _MATCH_STATS_DEFAULT,
             out_path: str = _OUT_DEFAULT, min_prior: int = 5) -> None:
    ms = pd.read_parquet(match_stats_path)
    dest = build_asof_xg_proxy(match_stats=ms, out_path=out_path)
    df = pd.read_parquet(dest)
    print(f"asof_xg_proxy: {len(df)} rows -> {dest}")

    mt = pd.read_parquet(_MATCHES)[["event_id", "fthg", "ftag"]].copy()
    mt["event_id"] = mt["event_id"].astype(str)
    mt["goal_diff_realized"] = pd.to_numeric(mt["fthg"], errors="coerce") - \
        pd.to_numeric(mt["ftag"], errors="coerce")
    merged = df.merge(mt[["event_id", "goal_diff_realized"]], on="event_id", how="inner")
    covered = merged[(merged["home_n_prior"] >= min_prior)
                     & (merged["away_n_prior"] >= min_prior)]
    print(f"coverage (both >= {min_prior} prior): "
          f"{len(covered) / max(len(merged), 1):.1%} (n={len(covered)})")
    for col in ("diff_xg_for_asof", "diff_xg_against_asof", "diff_xg_supremacy_asof"):
        sub = covered.dropna(subset=[col, "goal_diff_realized"])
        if len(sub) > 0:
            corr = sub[col].corr(sub["goal_diff_realized"])
            print(f"  {col:24s}: corr vs realized goal diff n={len(sub)}: {corr:.4f}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate asof_xg_proxy feature quality")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    run_eval(args.match_stats, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
