"""reconcile_edge_source.py — is the +15% headline the MODEL or market-following?

iter57_post55_resweep.py grades eval_2025_26_combined.csv and reports
+15.04% flat / +18.38% kb-iso. But its bet DIRECTION comes from devig(over,under)
— the MARKET's implied lean — not the model prediction. The model is never used.

This script grades the SAME eval corpus two ways and prints them side by side:
  A. MARKET-devig direction  (replicates iter57 — bet the side the market favors)
  B. MODEL-prediction direction (bet over iff model_pred > line)
Each with: no filters, and the full Iter-57 production filter stack.

If A is strongly +EV and B is not, the headline edge is market-following on an
in-sample-tuned filter set, NOT a model edge. Output -> stdout + JSON.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.run_gate1_full_analysis import _build_name_to_pid  # noqa: E402
from src.prediction.bet_thresholds import (  # noqa: E402
    edge_threshold_for,
    allowed_directions_for,
    is_line_excluded,
    is_direction_line_excluded,
)

EVAL_CSV = _ROOT / "data" / "cache" / "eval_2025_26_combined.csv"
OOF = _ROOT / "data" / "cache" / "pregame_oof.parquet"
OUT = _ROOT / "data" / "cache" / "reconcile_edge_source.json"

PAYOUT = 100.0 / 110.0  # -110 flat


def devig(over_odds: float, under_odds: float):
    def imp(o):
        return (abs(o) / (abs(o) + 100.0)) if o < 0 else (100.0 / (o + 100.0))
    po, pu = imp(over_odds), imp(under_odds)
    s = po + pu
    return (po / s, pu / s) if s > 0 else (0.5, 0.5)


def load_oof_index():
    df = pd.read_parquet(OOF)
    df = df[df["season"].astype(str).str.contains("2025-26", na=False) |
            (df["game_date"].astype(str) >= "2025-10-01")]
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    idx = {}
    for r in df.itertuples(index=False):
        idx[(int(r.player_id), r.game_date, str(r.stat).lower())] = float(r.oof_pred)
    return idx


def passes_filters(stat, direction, line):
    if direction not in allowed_directions_for(stat):
        return False
    if is_line_excluded(stat, line):
        return False
    if is_direction_line_excluded(stat, direction, line):
        return False
    return True


def grade(rows, mode, apply_filters, edge_gate=False):
    """mode: 'market' (devig lean) or 'model' (pred vs line)."""
    per = defaultdict(lambda: {"n": 0, "w": 0, "pnl": 0.0})
    n = w = 0
    pnl = 0.0
    for r in rows:
        stat = r["stat"]
        line = r["closing_line"]
        actual = r["actual_value"]
        if mode == "market":
            po, pu = devig(r["over_odds"], r["under_odds"])
            direction = "under" if pu >= po else "over"
        else:  # model
            pred = r.get("pred")
            if pred is None:
                continue
            if edge_gate and abs(pred - line) < edge_threshold_for(stat):
                continue
            direction = "over" if pred > line else "under"
        if apply_filters and not passes_filters(stat, direction, line):
            continue
        if abs(actual - line) < 1e-9:
            continue  # push
        hit = (actual > line) if direction == "over" else (actual < line)
        gain = PAYOUT if hit else -1.0
        n += 1
        w += int(hit)
        pnl += gain
        per[stat]["n"] += 1
        per[stat]["w"] += int(hit)
        per[stat]["pnl"] += gain
    return {
        "n": n, "beat_pct": w / n * 100 if n else 0.0,
        "roi_pct": pnl / n * 100 if n else 0.0,
        "per_stat": {s: {"n": v["n"], "beat_pct": v["w"]/v["n"]*100 if v["n"] else 0,
                         "roi_pct": v["pnl"]/v["n"]*100 if v["n"] else 0}
                     for s, v in per.items()},
    }


def main():
    name_to_pid = _build_name_to_pid()
    oof = load_oof_index()
    rows = []
    matched = 0
    with open(EVAL_CSV, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                rec = {
                    "stat": r["stat"].strip().lower(),
                    "closing_line": float(r["closing_line"]),
                    "actual_value": float(r["actual_value"]),
                    "over_odds": float(r["over_odds"]),
                    "under_odds": float(r["under_odds"]),
                    "date": r["date"].strip(),
                    "player": r["player"].strip().lower(),
                }
            except (ValueError, KeyError):
                continue
            pid = name_to_pid.get(rec["player"])
            rec["pred"] = oof.get((pid, rec["date"], rec["stat"])) if pid else None
            if rec["pred"] is not None:
                matched += 1
            rows.append(rec)

    print(f"eval rows: {len(rows):,} | model-pred matched: {matched:,} "
          f"({matched/len(rows)*100:.1f}%)\n")

    blocks = [
        ("A1. MARKET-devig direction, NO filters", grade(rows, "market", False)),
        ("A2. MARKET-devig direction, FULL Iter-57 filters", grade(rows, "market", True)),
        ("B1. MODEL-prediction direction, NO filters", grade(rows, "model", False)),
        ("B2. MODEL-prediction direction, FULL Iter-57 filters", grade(rows, "model", True)),
        ("B3. MODEL direction + edge-threshold gate + filters", grade(rows, "model", True, edge_gate=True)),
    ]
    out = {}
    for title, r in blocks:
        print("=" * 70)
        print(title)
        print(f"  N={r['n']:,}  beat={r['beat_pct']:.2f}%  ROI={r['roi_pct']:+.2f}%")
        for s, v in sorted(r["per_stat"].items()):
            print(f"    {s:<5} n={v['n']:>5,d} beat={v['beat_pct']:>6.2f}% ROI={v['roi_pct']:>+7.2f}%")
        print()
        out[title.split(".")[0]] = {"title": title, **r}

    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Results: {OUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
