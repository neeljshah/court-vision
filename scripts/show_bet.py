"""show_bet.py - look up a bet by bet_id (probe R16_E7).

Usage:
    python scripts/show_bet.py <bet_id>
    python scripts/show_bet.py a7c3                # prefix match if unique
    python scripts/show_bet.py <bet_id> --json     # raw JSON dump

Returns exit code 0 on hit, 1 on not-found, 2 on ambiguous prefix.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import LEDGER_CSV  # noqa: E402


def find_bet(bet_id: str, ledger_path: str = LEDGER_CSV) -> List[Dict]:
    """Return all rows whose bet_id startswith the query (case-insensitive)."""
    if not os.path.exists(ledger_path):
        return []
    q = bet_id.lower().strip()
    if not q:
        return []
    matches: List[Dict] = []
    with open(ledger_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            bid = (r.get("bet_id") or "").lower()
            if bid == q or bid.startswith(q):
                matches.append(r)
            if bid == q:
                # Exact match short-circuits the prefix search.
                return [r]
    return matches


def _fmt_money(s: str) -> str:
    try:
        v = float(s)
        return f"${v:+.2f}" if v != 0 else "$0.00"
    except (TypeError, ValueError):
        return s or ""


def _odds_str(s: str) -> str:
    try:
        v = int(s)
        return f"{v:+d}"
    except (TypeError, ValueError):
        return s or ""


def format_bet(row: Dict) -> str:
    """Human-readable single-bet block."""
    book = (row.get("book") or "").upper()
    player = row.get("player") or "?"
    stat = (row.get("stat") or "").upper()
    side = row.get("side") or ""
    line = row.get("line") or ""
    odds = _odds_str(row.get("american_odds", ""))
    stake = row.get("stake") or "0"
    status = row.get("status") or "?"

    out = []
    out.append(f"bet_id:        {row.get('bet_id', '')}")
    out.append(f"placed_at:     {row.get('placed_at', '')}")
    out.append(f"  {book} - {player} {stat} {side} {line} @ {odds}")
    out.append(f"  stake:       ${float(stake):.2f}")
    out.append(f"  status:      {status}")
    out.append(f"  game_id:     {row.get('game_id') or '(blank)'}")
    out.append(f"  player_id:   {row.get('player_id') or '(blank)'}")
    out.append(f"  team:        {row.get('team') or '(blank)'}")
    out.append(f"  strategy:    {row.get('strategy') or 'default'}")
    if row.get("model_pred"):
        out.append(f"  model_pred:  {row['model_pred']}")
    if row.get("model_prob"):
        out.append(f"  model_prob:  {row['model_prob']}")
    if row.get("model_edge"):
        out.append(f"  model_edge:  {row['model_edge']}")
    if row.get("kelly_pct"):
        out.append(f"  kelly_pct:   {row['kelly_pct']}")
    if status in ("won", "lost", "push", "voided"):
        out.append(f"  settled_at:  {row.get('settled_at', '')}")
        out.append(f"  actual_stat: {row.get('actual_stat', '')}")
        out.append(f"  profit_loss: {_fmt_money(row.get('profit_loss', ''))}")
        out.append(f"  bankroll_after: ${float(row.get('bankroll_after') or 0):.2f}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Look up a bet by bet_id (full or prefix) in data/pnl_ledger.csv",
    )
    ap.add_argument("bet_id", help="full bet_id, or a unique prefix (>=4 chars)")
    ap.add_argument("--json", action="store_true", help="output raw JSON row(s)")
    ap.add_argument("--ledger", default=LEDGER_CSV,
                    help="ledger CSV path (default: data/pnl_ledger.csv)")
    args = ap.parse_args(argv)

    matches = find_bet(args.bet_id, args.ledger)
    if not matches:
        print(f"[fail] no bet found matching {args.bet_id!r}", file=sys.stderr)
        return 1
    if len(matches) > 1:
        # Ambiguous prefix: print one-line summary for each and exit 2.
        if args.json:
            print(json.dumps(matches, indent=2))
        else:
            print(f"[ambiguous] {len(matches)} matches:", file=sys.stderr)
            for r in matches:
                print(f"  {r.get('bet_id')}  {r.get('placed_at')}  "
                       f"{r.get('player')} {r.get('stat')} "
                       f"{r.get('side')} {r.get('line')}  status={r.get('status')}")
        return 2
    row = matches[0]
    if args.json:
        print(json.dumps(row, indent=2))
    else:
        print(format_bet(row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
