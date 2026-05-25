"""register_bankroll.py — initialise or update the bankroll record.

Creates data/pnl_bankroll.csv with one deposit row so the health check
and P&L report have a starting balance to report against.

Usage:
    python scripts/register_bankroll.py --amount 1000
    python scripts/register_bankroll.py --amount 500 --note "top-up May"
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="Register starting bankroll")
    parser.add_argument("--amount", type=float, required=True, help="Deposit amount in $")
    parser.add_argument("--note", default="initial deposit", help="Memo string")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "pnl_bankroll.csv"

    fieldnames = ["ts", "type", "amount", "note", "balance"]
    new_row = True if not path.exists() else False

    existing = []
    if path.exists():
        with open(path, newline="") as f:
            existing = list(csv.DictReader(f))

    running = sum(float(r["amount"]) for r in existing if r["type"] == "deposit")
    running -= sum(float(r["amount"]) for r in existing if r["type"] == "withdraw")
    balance = running + args.amount

    row = {
        "ts": datetime.utcnow().isoformat(timespec="seconds"),
        "type": "deposit",
        "amount": f"{args.amount:.2f}",
        "note": args.note,
        "balance": f"{balance:.2f}",
    }

    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if new_row:
            writer.writeheader()
        writer.writerow(row)

    print(f"Bankroll updated: +${args.amount:.2f}  |  balance=${balance:.2f}")
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
