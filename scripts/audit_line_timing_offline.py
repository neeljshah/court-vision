"""audit_line_timing_offline.py — offline line-source audit for prop CSVs.

Budget-friendly diagnostic that runs BEFORE spending Odds API units:
  * Duplicate (player, date, stat) triplets with different closing_line values
    → suggests multiple snapshot times mixed in, or vendor disagreement
  * Distribution of closing_line vs actual_value per stat — a "naive over"
    bettor's hit-rate. If naive hit-rate is far from 50%, the lines are
    systematically off-market (a hint, not a proof, of stale/bad lines).
  * Per-stat coverage: how many bets have both a numeric line AND a numeric
    actual_value (i.e. the rows the backtest can score).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LINES_DIR = ROOT / "data" / "external" / "historical_lines"
OUT_PATH = ROOT / "data" / "cache" / "line_timing_offline_audit.json"

STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk", "tov"]


def main() -> None:
    rows = []
    for f in LINES_DIR.glob("*canonical*.csv"):
        df = pd.read_csv(f)
        df["__src__"] = f.name
        rows.append(df)
    df = pd.concat(rows, ignore_index=True)

    out = {
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_rows_total": len(df),
        "sources": df["__src__"].value_counts().to_dict(),
        "per_stat": {},
    }

    for stat in STATS:
        sub = df[df["stat"] == stat].copy()
        if sub.empty:
            out["per_stat"][stat] = {"n": 0}
            continue

        # Duplicate (player, date) triplets with different closing_line.
        dup_groups = (
            sub.groupby(["player", "date"])["closing_line"]
            .agg(["nunique", "count", "min", "max"])
            .query("nunique > 1")
        )
        n_dup = int(dup_groups.shape[0])
        max_spread = float(dup_groups["max"].sub(dup_groups["min"]).max()) if n_dup else 0.0

        sub2 = sub.dropna(subset=["closing_line", "actual_value"]).copy()
        hit_rate_over = (
            float((sub2["actual_value"] > sub2["closing_line"]).mean()) if len(sub2) else None
        )

        out["per_stat"][stat] = {
            "n": int(len(sub)),
            "n_scoreable": int(len(sub2)),
            "duplicate_player_date_count": n_dup,
            "max_intra_date_line_spread": max_spread,
            "naive_over_hit_rate_pct": (
                round(hit_rate_over * 100, 3) if hit_rate_over is not None else None
            ),
            "actual_mean": float(sub2["actual_value"].mean()) if len(sub2) else None,
            "line_mean": float(sub2["closing_line"].mean()) if len(sub2) else None,
            "actual_minus_line_mean": (
                float((sub2["actual_value"] - sub2["closing_line"]).mean())
                if len(sub2)
                else None
            ),
        }

    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
