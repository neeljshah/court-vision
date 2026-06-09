"""scripts/apply_teammate_out.py — apply A3 teammate-OUT redistribution
to an existing fresh-slate parquet and write a boosted copy + audit table.

The model has no `teammate_out` feature. When a high-usage player is OUT
his stat production has to be redistributed to teammates — this script
does that as a post-prediction pass using observed series-average MPG as
redistribution weights.

Usage (defaults are wired for tonight's SAS@OKC):
    python scripts/apply_teammate_out.py
    python scripts/apply_teammate_out.py --team OKC --date 2026-05-26

Inputs:
  data/cache/intel_<date>/slate_fresh_<date>.parquet  (existing slate)
  data/cache/intel_<date>/wcf_player_series_avg.csv   (minute weights)
  data/injuries_<date>.json                            (OUT player list)

Outputs:
  data/cache/intel_<date>/slate_with_teammate_out_<date>.parquet
  data/cache/intel_<date>/teammate_out_audit_<date>.csv
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import pandas as pd  # noqa: E402

from src.prediction.teammate_out_override import (  # noqa: E402
    MAX_BOOST, load_out_player_ids, redistribute_usage,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Apply teammate-OUT usage redistribution to a slate")
    ap.add_argument("--date", default="2026-05-26",
                    help="Slate date YYYY-MM-DD (default: 2026-05-26).")
    ap.add_argument("--team", default="OKC",
                    help="Team abbreviation with OUT players to redistribute "
                         "for (default: OKC).")
    ap.add_argument("--max-boost", type=float, default=MAX_BOOST,
                    help=f"Multiplicative cap on q50 (default: {MAX_BOOST}).")
    args = ap.parse_args()

    intel_dir = os.path.join(PROJECT_DIR, "data", "cache",
                              f"intel_{args.date}")
    slate_path = os.path.join(intel_dir, f"slate_fresh_{args.date}.parquet")
    wcf_path = os.path.join(intel_dir, "wcf_player_series_avg.csv")
    inj_path = os.path.join(PROJECT_DIR, "data", f"injuries_{args.date}.json")

    if not os.path.exists(slate_path):
        print(f"[fail] slate parquet missing: {slate_path}")
        return 2
    if not os.path.exists(wcf_path):
        print(f"[fail] weights CSV missing: {wcf_path}")
        return 2
    if not os.path.exists(inj_path):
        print(f"[fail] injuries JSON missing: {inj_path}")
        return 2

    slate_df = pd.read_parquet(slate_path)
    weights_df = pd.read_csv(wcf_path)

    out_ids = load_out_player_ids(inj_path, args.team, slate_df=slate_df)
    if not out_ids:
        print(f"[info] no OUT players for {args.team} found in slate. "
              f"Writing slate copy unchanged.")
    out_names = (slate_df[(slate_df["team"] == args.team) &
                          (slate_df["player_id"].isin(out_ids))]
                  .drop_duplicates("player_id")
                  [["player_id", "player"]].values.tolist())
    print(f"\n  Slate: {slate_path}")
    print(f"  Team: {args.team}  Date: {args.date}  MaxBoost: {args.max_boost}x")
    print(f"  OUT players ({len(out_ids)}):")
    for pid, nm in out_names:
        print(f"    {pid}  {nm}")

    adjusted_df, audit = redistribute_usage(
        slate_df, out_ids, args.team, weights_df, max_boost=args.max_boost,
    )

    # Persist outputs.
    out_pq = os.path.join(intel_dir,
                          f"slate_with_teammate_out_{args.date}.parquet")
    out_audit = os.path.join(intel_dir,
                              f"teammate_out_audit_{args.date}.csv")
    adjusted_df.to_parquet(out_pq, index=False)
    audit.to_csv(out_audit, index=False)
    print(f"\n  -> {out_pq}")
    print(f"  -> {out_audit}  ({len(audit)} boosted rows)")

    # Per-player redistribution summary, focused on PTS for headline view.
    if not audit.empty:
        pts = audit[audit["stat"] == "pts"].copy()
        pts["boost_pct"] = ((pts["ratio"] - 1.0) * 100).round(1)
        pts = pts.sort_values("bump", ascending=False)
        print("\n  ===== PTS redistribution (largest bumps first) =====")
        print(f"  {'player':<26} {'old_q50':>8} {'bump':>7} {'new_q50':>8}  {'boost%':>7}")
        for _, r in pts.iterrows():
            print(f"  {r['player']:<26} {r['old_q50']:>8.2f} {r['bump']:>7.2f} "
                  f"{r['new_q50']:>8.2f}  {r['boost_pct']:>+6.1f}%")

        # Show full multi-stat per-player view for the top 6 absorbers.
        print("\n  ===== Per-player stat deltas (top absorbers) =====")
        top_players = (audit.groupby("player_id")["bump"].sum()
                            .sort_values(ascending=False).head(6).index.tolist())
        for pid in top_players:
            sub = audit[audit["player_id"] == pid]
            nm = sub["player"].iloc[0]
            stats_summary = "  ".join(
                f"{r['stat'].upper()} {r['old_q50']:.2f}->{r['new_q50']:.2f}"
                f"({(r['ratio']-1)*100:+.0f}%)"
                for _, r in sub.iterrows()
            )
            print(f"   {nm:<26}  {stats_summary}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
