"""preregister_tonight_intended.py - D7 follow-up.

Writes the 9 tonight bets from
    data/cache/intel_2026-05-26/tonight_bets_registered.json
into the canonical ledger (data/pnl_ledger.csv) with status="INTENDED".

Why a custom writer instead of src.betting.pnl_ledger.place_bet():
    - place_bet() forces status="open" (the closest non-INTENDED enum)
    - place_bet() deducts stake from bankroll on every call
    - the user has explicitly told us: bets are INTENDED, NOT placed; do
      NOT touch the bankroll value

How to flip an intended bet to actualized (after firing it at Pinnacle):
    Option A (recommended) - edit the status column directly:
        open data/pnl_ledger.csv -> change "INTENDED" -> "open" on the row,
        update placed_at to the real placement timestamp, save.
        Then `python scripts/place_bet.py` style settle later will work.

    Option B - delete the INTENDED row and re-fire through place_bet.py:
        python scripts/place_bet.py --player "Keldon Johnson" --stat pts \
            --side OVER --line 6.5 --book pinnacle --odds +105 --stake 260 \
            --no-slate-validate --force-stale

Run: python scripts/preregister_tonight_intended.py
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import (  # noqa: E402
    LEDGER_CSV,
    LEDGER_COLS,
    _atomic_write_rows,
    _file_lock,
    _load_ledger,
)

SOURCE_JSON = os.path.join(
    PROJECT_DIR, "data", "cache", "intel_2026-05-26", "tonight_bets_registered.json",
)

INTENDED_STATUS = "INTENDED"


def _name_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", stripped.lower().strip())


def _deterministic_bet_id(bet: Dict) -> str:
    """wcfg5_<player_key>_<stat>_<side>_<line>"""
    player_key = _name_key(bet["player"])
    return (
        f"wcfg5_{player_key}_{bet['stat'].lower()}_"
        f"{bet['side'].lower()}_{str(bet['line']).replace('.', 'p')}"
    )


def main() -> int:
    with open(SOURCE_JSON, encoding="utf-8") as fh:
        src = json.load(fh)
    bets = src.get("bets") or []
    if not bets:
        print(f"[fail] no bets in {SOURCE_JSON}")
        return 1
    print(f"[info] source: {SOURCE_JSON}  n_bets={len(bets)}")
    placed_at_iso = datetime.now().isoformat(timespec="seconds")
    game_id = src.get("game_id", "")
    new_rows: List[Dict] = []
    bet_ids: List[str] = []
    for b in bets:
        bet_id = _deterministic_bet_id(b)
        bet_ids.append(bet_id)
        line   = float(b["line"])
        model  = b.get("model_q50")
        edge   = (float(model) - line) if model is not None else None
        new_rows.append({
            "bet_id":         bet_id,
            "placed_at":      placed_at_iso,
            "game_id":        game_id,
            "player_id":      "",
            "player":         b["player"],
            "team":           b.get("team", ""),
            "stat":           b["stat"].lower(),
            "line":           f"{line:.2f}",
            "side":           b["side"].upper(),
            "book":           b.get("book", "pin"),
            "american_odds":  str(int(b["odds"])),
            "stake":          f"{float(b['stake']):.2f}",
            "model_pred":     "" if model is None else f"{float(model):.4f}",
            "model_prob":     "",
            "model_edge":     "" if edge is None else f"{edge:+.4f}",
            "kelly_pct":      f"{float(b.get('kelly_adj_pct', 0)):.4f}"
                              if b.get("kelly_adj_pct") is not None else "",
            "status":         INTENDED_STATUS,
            "settled_at":     "",
            "actual_stat":    "",
            "profit_loss":    "",
            "bankroll_after": "",
            "strategy":       "tonight_wcfg5_intended",
        })

    with _file_lock():
        existing = _load_ledger()
        existing_ids = {r.get("bet_id") for r in existing}
        appended = 0
        for row in new_rows:
            if row["bet_id"] in existing_ids:
                print(f"[skip] already in ledger: {row['bet_id']}")
                continue
            existing.append(row)
            appended += 1
        _atomic_write_rows(LEDGER_CSV, LEDGER_COLS, existing)

    print(f"[ok] appended {appended} rows to {LEDGER_CSV}")
    print(f"[ok] status used: {INTENDED_STATUS}")
    print(f"[ok] bankroll: UNTOUCHED (intended, not placed)")
    print()
    print("Bet IDs written:")
    for bid in bet_ids:
        print(f"  - {bid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
