"""grade_pregame_layers.py -- grade base vs calibrated vs live-adjusted vs actual.

Reads ``data/cache/pregame_layer_log.jsonl`` (the per-prediction log written by
``src/prediction/pregame_layer_log.py`` whenever CV_LAYER_LOG=1 is set on a
serving run), joins each row's (player_id, date, stat) to the canonical
gamelog actual, and reports per-stat MAE and ROI for the three layers:

  * base       - the raw model projection
  * after_cal  - base after pregame_calibration.apply()  (NULL when off)
  * after_live - base after live_adjustment.adjust_projection() (NULL when off)

The point of this script is that the live-adjustment layer is ~neutral on
historical reconstruction (docs/VS_VEGAS_ASSESSMENT.md sec 4) BY CONSTRUCTION
(production OOF already saw DNP/context features). The layer's edge — if any —
exists only on the LIVE feed. This grader is how we finally get a real A/B
across many nights once CV_LAYER_LOG has been on for a while.

Usage:
    python scripts/grade_pregame_layers.py
    python scripts/grade_pregame_layers.py --since 2026-06-01
    python scripts/grade_pregame_layers.py --log path/to/other_log.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG = _ROOT / "data" / "cache" / "pregame_layer_log.jsonl"
_NBA_DIR = _ROOT / "data" / "nba"

# Mirror scripts/run_gate1_full_analysis.STAT_COLS so we read the same actuals.
STAT_COLS = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
             "stl": "STL", "blk": "BLK", "tov": "TOV"}


def _parse_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.split("T")[0], fmt.split("T")[0]).date()
        except ValueError:
            continue
    return None


def _load_actual(pid: int, target_date, stat: str):
    col = STAT_COLS.get(stat.lower())
    if col is None:
        return None
    for season in ("2023-24", "2024-25", "2025-26"):
        path = _NBA_DIR / f"gamelog_{pid}_{season}.json"
        if not path.exists():
            continue
        try:
            for r in json.load(open(path, encoding="utf-8")):
                d = _parse_date(r.get("GAME_DATE", ""))
                if d and d == target_date:
                    v = r.get(col)
                    if v is None:
                        return None
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
        except Exception:
            continue
    return None


def _payout(odds, won):
    if not won:
        return -100.0
    if odds is None:
        odds = -110.0
    if odds < 0:
        return 100.0 / abs(odds) * 100.0
    return odds / 100.0 * 100.0


def _settle(layer_pred, line, actual, over_odds, under_odds):
    if layer_pred is None or actual is None:
        return None
    if abs(actual - line) < 1e-9:
        return None  # push
    bet_over = layer_pred > line
    if abs(layer_pred - line) < 1e-9:
        return None  # no bet (no direction)
    won = (bet_over and actual > line) or (not bet_over and actual < line)
    return _payout(over_odds if bet_over else under_odds, won)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=str(_DEFAULT_LOG))
    ap.add_argument("--since", default=None,
                    help="YYYY-MM-DD; grade only logs on or after this date")
    args = ap.parse_args()

    path = Path(args.log)
    if not path.exists():
        print(f"no log file at {path}", file=sys.stderr)
        return 1
    since = _parse_date(args.since) if args.since else None

    # per-stat per-layer accumulator: {(stat, layer) -> dict(n, ae, bet_n, w, pnl)}
    acc = defaultdict(lambda: {"n": 0, "ae": 0.0, "bet_n": 0, "w": 0, "pnl": 0.0})
    total_rows = scored = 0
    layers_present = defaultdict(int)

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_rows += 1
            d = _parse_date(rec.get("date"))
            if d is None:
                continue
            if since and d < since:
                continue
            actual = _load_actual(rec["player_id"], d, rec["stat"])
            if actual is None:
                continue
            scored += 1
            line_val = rec["line"]; stat = rec["stat"]
            over_odds = rec.get("over_odds"); under_odds = rec.get("under_odds")
            for layer in ("base", "after_cal", "after_live"):
                pred = rec.get(layer)
                if pred is None:
                    continue
                layers_present[layer] += 1
                a = acc[(stat, layer)]
                a["n"] += 1
                a["ae"] += abs(float(pred) - actual)
                res = _settle(float(pred), line_val, actual, over_odds, under_odds)
                if res is not None:
                    a["bet_n"] += 1
                    a["w"] += int(res > 0)
                    a["pnl"] += res

    print(f"log rows: {total_rows:,}   joined to actuals: {scored:,}")
    print("layers present:", dict(layers_present))
    if not scored:
        print("nothing graded yet — run with CV_LAYER_LOG=1 on a few game-nights "
              "first, then re-run.")
        return 0

    print(f"\n{'stat':<5} {'layer':<10} {'n':>5} {'MAE':>7} "
          f"{'bet_n':>6} {'win%':>7} {'ROI%':>8}")
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        for layer in ("base", "after_cal", "after_live"):
            a = acc.get((stat, layer))
            if not a or a["n"] == 0:
                continue
            mae = a["ae"] / a["n"]
            bw = a["w"] / a["bet_n"] * 100 if a["bet_n"] else 0
            roi = a["pnl"] / (a["bet_n"] * 100) * 100 if a["bet_n"] else 0
            print(f"{stat:<5} {layer:<10} {a['n']:>5,d} {mae:>7.3f} "
                  f"{a['bet_n']:>6,d} {bw:>6.1f}% {roi:>+7.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
