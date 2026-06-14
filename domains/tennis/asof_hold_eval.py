"""domains.tennis.asof_hold_eval — CLI evaluation harness for asof_hold.py.

Runs build_asof_hold and prints:
  - row count + output path
  - coverage (both players >= min_prior matches)
  - corr(hold_diff_asof, hold_diff_realized) on covered rows
  - MAE of as-of hold vs realized hold, vs flat-0.62 baseline

Called by domains/tennis/asof_hold.py's _cli(); can also be invoked directly.

ACCURACY ONLY — NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from domains.tennis.asof_hold import (
    _MATCH_STATS_DEFAULT,
    _MATCHES_DEFAULT,
    _OUT_DEFAULT,
    _STATS_COLS,
    build_asof_hold,
    _derive_realized,
)


def run_eval(
    match_stats_path: str = _MATCH_STATS_DEFAULT,
    matches_path: str = _MATCHES_DEFAULT,
    out_path: str = _OUT_DEFAULT,
    min_prior: int = 5,
) -> None:
    """Build asof_hold parquet and print evaluation metrics."""
    ms = pd.read_parquet(match_stats_path)
    mt = pd.read_parquet(matches_path)
    dest = build_asof_hold(match_stats=ms, matches=mt, out_path=out_path)
    df = pd.read_parquet(dest)

    # ---- Coverage ----
    cov = ((df["p1_n_prior"] >= min_prior) & (df["p2_n_prior"] >= min_prior)).mean()
    print(f"asof_hold: {len(df)} rows -> {dest}")
    print(f"coverage (both >={min_prior} prior matches): {cov:.1%}")

    # ---- Realized stats for comparison ----
    avail = [c for c in _STATS_COLS if c in ms.columns]
    ms_r = _derive_realized(ms[avail].copy())
    ms_r["hold_diff_realized"] = ms_r["p1_hold_realized"] - ms_r["p2_hold_realized"]

    merged = df.merge(
        ms_r[["event_id", "p1_hold_realized", "p2_hold_realized", "hold_diff_realized"]],
        on="event_id", how="inner",
    )
    merged["hold_diff_asof"] = merged["p1_hold_pct_asof"] - merged["p2_hold_pct_asof"]

    # ---- Signal check: differential correlation ----
    covered = merged[
        (merged["p1_n_prior"] >= min_prior) & (merged["p2_n_prior"] >= min_prior)
    ].dropna(subset=["hold_diff_asof", "hold_diff_realized"])
    if len(covered) > 0:
        corr = covered["hold_diff_asof"].corr(covered["hold_diff_realized"])
        print(f"corr(hold_diff_asof, hold_diff_realized) covered (n={len(covered)}): {corr:.4f}")

    # ---- MAE vs flat 0.62 ----
    valid = merged.dropna(subset=["p1_hold_pct_asof", "p1_hold_realized"])
    if len(valid) > 0:
        mae_asof = (valid["p1_hold_pct_asof"] - valid["p1_hold_realized"]).abs().mean()
        mae_flat = (0.62 - valid["p1_hold_realized"]).abs().mean()
        print(f"MAE asof hold vs realized  (n={len(valid)}): {mae_asof:.4f}")
        print(f"MAE flat 0.62 vs realized  (n={len(valid)}): {mae_flat:.4f}")
        lift = mae_flat - mae_asof
        print(f"MAE lift vs flat baseline: {lift:+.4f} ({'better' if lift > 0 else 'worse'})")

    # ---- Surface breakdown ----
    for surf in ("Hard", "Clay", "Grass"):
        surf_col = f"p1_hold_pct_{surf.lower()}_asof"
        surf_rows = merged[merged["surface"] == surf].dropna(subset=[surf_col, "p1_hold_realized"])
        if len(surf_rows) > 0:
            mae_s = (surf_rows[surf_col] - surf_rows["p1_hold_realized"]).abs().mean()
            mae_f = (0.62 - surf_rows["p1_hold_realized"]).abs().mean()
            print(f"  {surf:6s}: MAE asof={mae_s:.4f}  flat={mae_f:.4f}  n={len(surf_rows)}")

    with pd.option_context("display.max_columns", None, "display.width", 240):
        print(df.head(3).to_string())


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate asof_hold feature quality")
    parser.add_argument("--match-stats", default=_MATCH_STATS_DEFAULT)
    parser.add_argument("--matches", default=_MATCHES_DEFAULT)
    parser.add_argument("--out-path", default=_OUT_DEFAULT)
    parser.add_argument("--min-prior", type=int, default=5)
    args = parser.parse_args()
    run_eval(args.match_stats, args.matches, args.out_path, args.min_prior)


if __name__ == "__main__":
    _cli()
