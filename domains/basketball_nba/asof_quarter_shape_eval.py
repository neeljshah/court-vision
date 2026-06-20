"""domains.basketball_nba.asof_quarter_shape_eval -- CLI accuracy harness.

Builds asof_quarter_shape and prints row count + coverage + corr(diff_asof,
diff_realized) per metric. ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse

import pandas as pd

from domains.basketball_nba.asof_quarter_shape import (
    _LINESCORES_DEFAULT,
    _METRICS,
    _OUT_DEFAULT,
    _derive_realized,
    build_asof_quarter_shape,
)


def run_eval(linescores_path: str = _LINESCORES_DEFAULT,
             out_path: str = _OUT_DEFAULT, min_prior: int = 5) -> None:
    ls = pd.read_parquet(linescores_path)
    dest = build_asof_quarter_shape(linescores=ls, out_path=out_path)
    df = pd.read_parquet(dest)
    print(f"asof_quarter_shape: {len(df)} rows -> {dest}")

    realized = _derive_realized(ls)
    for m in _METRICS:
        realized[f"diff_{m}_realized"] = realized[f"home_{m}"] - realized[f"away_{m}"]
    merged = df.merge(
        realized[["event_id"] + [f"diff_{m}_realized" for m in _METRICS]],
        on="event_id", how="inner")

    covered = merged[(merged["home_n_prior"] >= min_prior)
                     & (merged["away_n_prior"] >= min_prior)]
    print(f"coverage (both >= {min_prior} prior games): "
          f"{len(covered) / max(len(merged), 1):.1%} (n={len(covered)})")
    for m in _METRICS:
        sub = covered.dropna(subset=[f"diff_{m}_asof", f"diff_{m}_realized"])
        if len(sub) > 0:
            corr = sub[f"diff_{m}_asof"].corr(sub[f"diff_{m}_realized"])
            print(f"  {m:22s}: corr(diff_asof, diff_realized) n={len(sub)}: {corr:.4f}")


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate asof_quarter_shape feature quality")
    parser.add_argument("--linescores", default=_LINESCORES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    run_eval(args.linescores, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
