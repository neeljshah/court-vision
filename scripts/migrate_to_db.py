"""migrate_to_db.py — One-time (idempotent) migration of CSV/JSON bet history
into database/courtvision.db.

Sources (gracefully skipped if absent):
  * data/pnl_ledger.csv
  * data/models/bet_log.json

Idempotency: uses INSERT OR IGNORE so running twice is safe.

Usage:
    python scripts/migrate_to_db.py --dry-run   # count rows, no writes
    python scripts/migrate_to_db.py             # write to DB
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from database.bet_db import BetDB  # noqa: E402

_LEDGER_CSV = PROJECT_DIR / "data" / "pnl_ledger.csv"
_BET_LOG    = PROJECT_DIR / "data" / "models" / "bet_log.json"


# ── CSV column mapping ─────────────────────────────────────────────────────────

def _csv_row_to_bet(row: Dict[str, str]) -> Dict[str, Any]:
    """Map a pnl_ledger.csv row to a BetDB insert dict."""
    def _fv(k: str) -> Any:
        return row.get(k) or None

    status_raw = (row.get("status") or "open").strip().upper()
    status_map = {
        "OPEN":    "pending",
        "WON":     "won",
        "LOST":    "lost",
        "PUSH":    "push",
        "VOIDED":  "voided",
        "INTENDED":"intended",
    }
    status = status_map.get(status_raw, "pending")

    side_raw = (row.get("side") or "").strip().upper()
    side = "over" if side_raw == "OVER" else ("under" if side_raw == "UNDER" else side_raw.lower())

    # Use placed_at as created_at; derive date from it.
    placed_at = _fv("placed_at") or ""
    date_part = placed_at[:10] if placed_at else ""

    return {
        "bet_id":       row.get("bet_id") or None,
        "created_at":   placed_at or None,
        "date":         date_part,
        "game_id":      _fv("game_id"),
        "player_id":    _fv("player_id"),
        "player_name":  row.get("player") or "",
        "stat":         (row.get("stat") or "").lower(),
        "line":         row.get("line"),
        "side":         side,
        "book":         row.get("book") or "",
        "odds":         row.get("american_odds"),
        "stake":        row.get("stake"),
        "kelly_size":   _fv("kelly_pct"),
        "model_ev_pct": _fv("model_edge"),
        "model_p_hit":  _fv("model_prob"),
        "status":       status,
        "settled_at":   _fv("settled_at"),
        "actual_stat":  _fv("actual_stat"),
        "pnl":          _fv("profit_loss"),
        "source":       "migrated",
        "notes":        row.get("strategy") or None,
    }


# ── JSON mapping ───────────────────────────────────────────────────────────────

def _stable_id(rec: Dict[str, Any]) -> str:
    """Derive a deterministic UUID-like ID from content fields for idempotency."""
    key = f"{rec.get('player','')}/{rec.get('stat','')}/{rec.get('book_line','')}/{rec.get('date','')}/{rec.get('odds','')}"
    h = hashlib.sha1(key.encode()).hexdigest()[:32]
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _json_row_to_bet(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Map a bet_log.json entry to a BetDB insert dict."""
    side_raw = (rec.get("direction") or rec.get("side") or "").strip().lower()
    status_map = {
        "paper":   "intended",
        "pending": "pending",
        "open":    "pending",
        "won":     "won",
        "lost":    "lost",
        "push":    "push",
        "voided":  "voided",
    }
    status = status_map.get((rec.get("status") or "paper").lower(), "intended")
    date   = rec.get("date") or ""
    return {
        "bet_id":       _stable_id(rec),
        "created_at":   date + "T00:00:00Z" if date else None,
        "date":         date,
        "game_id":      rec.get("game_id"),
        "player_id":    rec.get("player_id"),
        "player_name":  rec.get("player") or "",
        "stat":         (rec.get("stat") or "").lower(),
        "line":         rec.get("book_line"),
        "side":         side_raw,
        "book":         rec.get("book") or "unknown",
        "odds":         rec.get("odds"),
        "stake":        rec.get("stake"),
        "kelly_size":   rec.get("kelly_size"),
        "model_p_hit":  rec.get("confidence"),           # stored as text ("high"…)
        "status":       status,
        "source":       "migrated",
        "notes":        rec.get("rationale"),
    }


# ── loaders ────────────────────────────────────────────────────────────────────

def _load_csv() -> List[Dict[str, str]]:
    if not _LEDGER_CSV.exists():
        return []
    with open(_LEDGER_CSV, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_json() -> List[Dict[str, Any]]:
    if not _BET_LOG.exists():
        return []
    try:
        data = json.loads(_BET_LOG.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


# ── main ───────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False) -> Dict[str, int]:
    db = BetDB()

    csv_rows  = _load_csv()
    json_rows = _load_json()

    print(f"Found {len(csv_rows)} rows in pnl_ledger.csv")
    print(f"Found {len(json_rows)} entries in bet_log.json")

    csv_inserted  = 0
    json_inserted = 0
    errors        = 0

    for row in csv_rows:
        try:
            bet = _csv_row_to_bet(row)
            if not dry_run:
                db.insert_bet(bet)
            csv_inserted += 1
        except Exception as exc:
            print(f"  [WARN] CSV row skipped: {exc} — {row.get('bet_id')}")
            errors += 1

    for rec in json_rows:
        try:
            bet = _json_row_to_bet(rec)
            if not dry_run:
                db.insert_bet(bet)
            json_inserted += 1
        except Exception as exc:
            print(f"  [WARN] JSON entry skipped: {exc}")
            errors += 1

    total = csv_inserted + json_inserted
    if dry_run:
        print(f"\n[dry-run] Would migrate {csv_inserted} CSV + {json_inserted} JSON = {total} bets ({errors} skipped)")
    else:
        print(f"\nMigrated {csv_inserted} CSV + {json_inserted} JSON = {total} bets ({errors} skipped)")
        print(f"DB path: {db.path}")

    return {"csv": csv_inserted, "json": json_inserted, "errors": errors}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Migrate CSV/JSON bet history to SQLite")
    ap.add_argument("--dry-run", action="store_true",
                    help="Count rows without writing to DB")
    args = ap.parse_args()
    result = run(dry_run=args.dry_run)
    sys.exit(0 if result["errors"] == 0 else 1)
