"""
log_prop_lines.py — Daily prop-line history collector (PRED-18).

The single highest-leverage prediction feature — the market line — cannot be
built today: the system has no historical prop-line dataset (only ~3 live
slates have ever run, and prop_residuals.json's `line` field is just the
realised result relabelled, not a real book line).

This collector fixes that going forward. Run once per slate day, it snapshots
the current Pinnacle prop lines into data/output/prop_line_history.json. Over
a season that file becomes the labelled (player, game, line) dataset the
per-game models need to add a market-line feature — the move that breaks the
~0.48 R² ceiling.

Usage (wire into the daily run):
    python scripts/log_prop_lines.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date
from typing import Callable, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_HISTORY_PATH = os.path.join(PROJECT_DIR, "data", "output", "prop_line_history.json")


def _pinnacle_source() -> List[dict]:
    """Current Pinnacle player-prop lines as [{player, stat, line, source}]."""
    try:
        from src.data.pinnacle_monitor import get_all_prop_signals
        signals = get_all_prop_signals()
    except Exception as exc:  # noqa: BLE001
        print(f"[log_prop_lines] Pinnacle source unavailable: {exc}")
        return []

    out: List[dict] = []
    for key, sig in (signals or {}).items():
        line = sig.get("line")
        if line is None:
            continue
        player, _, stat = str(key).partition("|")
        out.append({"player": player, "stat": stat,
                    "line": float(line), "source": "pinnacle"})
    return out


def load_line_history(history_path: Optional[str] = None) -> List[dict]:
    """Load the accumulated prop-line history (empty list if none yet)."""
    path = history_path or _HISTORY_PATH
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_market_line(player: str, stat: str, on_or_before: Optional[str] = None,
                    history_path: Optional[str] = None) -> Optional[float]:
    """Most recent logged line for a player+stat on or before a date.

    Returns None when no line has been logged — the per-game models then
    treat the market-line feature as missing.
    """
    player_l = str(player).lower().strip()
    rows = [r for r in load_line_history(history_path)
            if str(r.get("player", "")).lower().strip() == player_l
            and r.get("stat") == stat
            and (on_or_before is None or str(r.get("date", "")) <= on_or_before)]
    if not rows:
        return None
    rows.sort(key=lambda r: str(r.get("date", "")))
    return float(rows[-1]["line"])


def snapshot_prop_lines(
    date_str: Optional[str] = None,
    history_path: Optional[str] = None,
    source_fn: Optional[Callable[[], List[dict]]] = None,
) -> int:
    """Append today's prop lines to the history store.

    Idempotent per (date, player, stat, source) — re-running on the same day
    does not duplicate rows.

    Returns the number of new line records appended.
    """
    date_str = date_str or str(_date.today())
    history_path = history_path or _HISTORY_PATH
    source_fn = source_fn or _pinnacle_source

    history = load_line_history(history_path)
    seen = {(r.get("date"), r.get("player"), r.get("stat"), r.get("source"))
            for r in history}

    added = 0
    for rec in source_fn():
        key = (date_str, rec.get("player"), rec.get("stat"), rec.get("source"))
        if key in seen:
            continue
        history.append({"date": date_str, **rec})
        seen.add(key)
        added += 1

    os.makedirs(os.path.dirname(history_path), exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)
    print(f"[log_prop_lines] {date_str}: +{added} lines "
          f"({len(history)} total in history)")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily prop-line history collector")
    ap.add_argument("--date", default=None, help="Slate date YYYY-MM-DD")
    args = ap.parse_args()
    snapshot_prop_lines(date_str=args.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
