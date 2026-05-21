"""
send_daily_slate.py — Push today's bet slate to Telegram.

Reads data/output/slate_{date}.json, formats a compact table,
and sends via src.monitoring.telegram_alerter.send_alert().

Usage:
    python scripts/send_daily_slate.py [--date YYYY-MM-DD]
    # Default: today

Exits 0 whether or not Telegram creds are set (never crashes on missing creds).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_OUTPUT_DIR = os.path.join(PROJECT_DIR, "data", "output")


def _find_slate_file(date_str: str) -> Path | None:
    """Return path to slate_YYYYMMDD.json or None if not found."""
    p = Path(_OUTPUT_DIR) / f"slate_{date_str.replace('-', '')}.json"
    if p.exists():
        return p
    p2 = Path(_OUTPUT_DIR) / f"slate_{date_str}.json"
    return p2 if p2.exists() else None


def format_slate_message(bets: list[dict], date_str: str) -> str:
    """Format bet list as a compact Telegram-friendly text table."""
    if not bets:
        return f"CourtVision — {date_str}\nNo bets for today."

    lines = [f"<b>CourtVision — {date_str}</b>", f"{len(bets)} bet(s) today:", ""]
    for bet in bets[:20]:  # Cap at 20 to stay under Telegram 4096 char limit
        player = bet.get("player", bet.get("player_name", "?"))
        stat = bet.get("stat", "?")
        dirn = bet.get("direction", "?")
        line = bet.get("line", bet.get("ou_line", "?"))
        edge = bet.get("edge_pct", bet.get("edge", 0))
        edge_str = f"{float(edge) * 100:.1f}%" if edge else "?"
        lines.append(f"• {player} — {stat} {dirn} {line}  [edge {edge_str}]")

    if len(bets) > 20:
        lines.append(f"...and {len(bets) - 20} more")

    return "\n".join(lines)


def send_daily_slate(date_str: str | None = None) -> bool:
    """Load slate and send to Telegram. Returns True if sent, False otherwise."""
    if date_str is None:
        date_str = str(date.today())

    slate_path = _find_slate_file(date_str)
    if not slate_path:
        msg = f"CourtVision — {date_str}\nNo slate file found for {date_str}."
        print(f"  [send_daily_slate] {msg}")
    else:
        try:
            bets = json.loads(slate_path.read_text(encoding="utf-8"))
            if isinstance(bets, dict):
                bets = bets.get("bets", list(bets.values()) if bets else [])
        except Exception as e:
            print(f"  [send_daily_slate] Could not read {slate_path}: {e}")
            bets = []
        msg = format_slate_message(bets, date_str)

    from src.monitoring.telegram_alerter import send_alert

    ok = send_alert(msg)
    if ok:
        print(f"  [send_daily_slate] Sent slate for {date_str} to Telegram.")
    else:
        print(f"  [send_daily_slate] Telegram not configured or send failed (creds missing).")
    return ok


def main() -> None:
    p = argparse.ArgumentParser(description="Send today's bet slate to Telegram")
    p.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    args = p.parse_args()
    send_daily_slate(args.date)


if __name__ == "__main__":
    main()
