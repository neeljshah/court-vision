"""void_dnp_settles.py — R25_R2 ledger-DNP void utility.

R24_Q8's settlement reconciliation surfaced N bets where the ledger had
status in {won, lost, push} but the cached quarter_box JSONs do NOT contain
that player (i.e. the daemon's _match_player would have called them DNP).

This script:
  1. Re-runs the reconciliation, isolating `player_dnp_but_settled` rows.
  2. For each, consults the FULL-GAME boxscore_<gid>.json (R25_R2 fallback).
     If the player DID play (full box has them), the ledger row is left alone
     (it was correctly settled against the official total).
     If the player did NOT play (full box also absent), the ledger row is
     eligible for voiding via src.betting.pnl_ledger.void_bet.
  3. **Dry-run by default.** Pass --commit to actually void. A backup of the
     ledger is taken to data/pnl_ledger.csv.bak.<UTC-ts> before any write.

Usage
-----
    python scripts/void_dnp_settles.py              # dry-run
    python scripts/void_dnp_settles.py --commit     # backup + void
    python scripts/void_dnp_settles.py --ledger PATH --qb-dir DIR --full-box-dir DIR

Output JSON shape
-----------------
    {
      "as_of":              ISO timestamp,
      "dry_run":            bool,
      "ledger_backup":      str | null,
      "n_candidates":       int,
      "n_player_did_play":  int,     # full-box says they played -> SKIP
      "n_truly_dnp":        int,     # full-box also absent -> would void
      "n_voided":           int,     # only > 0 when --commit
      "skipped":            [ {bet_id, reason}, ... ],
      "voided":             [ {bet_id, reason, bankroll_after?}, ... ],
    }
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.auto_settle_daemon import (   # noqa: E402
    DEFAULT_QB_DIR, DEFAULT_FULL_BOX_DIR,
    sum_quarter_box_full, _load_full_box_player, _match_player,
)
from scripts.reconcile_settlements import (   # noqa: E402
    load_ledger, VALID_SETTLED,
)

DEFAULT_LEDGER = PROJECT_DIR / "data" / "pnl_ledger.csv"


def find_dnp_candidates(rows: List[Dict[str, Any]],
                         qb_dir: Path,
                         ) -> List[Dict[str, Any]]:
    """Return ledger rows whose status is in {won,lost,push} but whose
    player is absent from every cached quarter_box JSON for game_id.
    """
    cands: List[Dict[str, Any]] = []
    totals_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in rows:
        status = str(r.get("status", "") or "").lower()
        if status not in VALID_SETTLED:
            continue
        gid = str(r.get("game_id", "") or "").strip()
        if not gid:
            continue
        if gid not in totals_cache:
            totals_cache[gid] = sum_quarter_box_full(gid, qb_dir)
        t = totals_cache[gid]
        if not t:
            continue   # no QB at all -> not a DNP candidate, just unverifiable
        match = _match_player(r, t)
        if match is None:
            cands.append(r)
    return cands


def classify(cands: List[Dict[str, Any]],
              full_box_dir: Path,
              ) -> Dict[str, List[Dict[str, Any]]]:
    """Split into 'player_did_play' (skip) vs 'truly_dnp' (void)."""
    out: Dict[str, List[Dict[str, Any]]] = {"player_did_play": [], "truly_dnp": []}
    for r in cands:
        gid = str(r.get("game_id", "") or "").strip()
        fb = _load_full_box_player(gid, r, full_box_dir)
        if fb is None:
            out["truly_dnp"].append(r)
        else:
            out["player_did_play"].append(r)
    return out


def run(ledger_path: Path = DEFAULT_LEDGER,
        qb_dir: Path = DEFAULT_QB_DIR,
        full_box_dir: Path = DEFAULT_FULL_BOX_DIR,
        commit: bool = False,
        ) -> Dict[str, Any]:
    """Execute the void-or-skip plan. dry-run unless commit=True."""
    ledger_path = Path(ledger_path)
    qb_dir = Path(qb_dir)
    full_box_dir = Path(full_box_dir)

    rows = load_ledger(ledger_path)
    cands = find_dnp_candidates(rows, qb_dir)
    classes = classify(cands, full_box_dir)

    report: Dict[str, Any] = {
        "as_of":             _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "dry_run":           not commit,
        "ledger_backup":     None,
        "n_candidates":      len(cands),
        "n_player_did_play": len(classes["player_did_play"]),
        "n_truly_dnp":       len(classes["truly_dnp"]),
        "n_voided":          0,
        "skipped":           [
            {"bet_id": r.get("bet_id"),
             "reason": "player_in_full_box",
             "game_id": r.get("game_id"),
             "player": r.get("player")}
            for r in classes["player_did_play"]
        ],
        "voided":            [],
    }

    if commit and classes["truly_dnp"]:
        # Backup before mutating.
        ts  = _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        bak = ledger_path.with_suffix(f".csv.bak.{ts}")
        shutil.copy2(ledger_path, bak)
        report["ledger_backup"] = str(bak)
        # Lazy import — voiding mutates the ledger.
        from src.betting import pnl_ledger as _ledger
        for r in classes["truly_dnp"]:
            bid = r.get("bet_id")
            try:
                v = _ledger.void_bet(bid)
                report["voided"].append({
                    "bet_id": bid, "reason": "dnp",
                    "bankroll_after": v.get("bankroll_after"),
                })
                report["n_voided"] += 1
            except (KeyError, ValueError) as exc:
                report["voided"].append({
                    "bet_id": bid, "reason": "void_failed",
                    "error": str(exc),
                })
    else:
        # In dry-run, list what would have been voided.
        report["voided"] = [
            {"bet_id": r.get("bet_id"),
             "reason": "dnp_dryrun",
             "game_id": r.get("game_id"),
             "player": r.get("player")}
            for r in classes["truly_dnp"]
        ]
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Audit ledger for player_dnp_but_settled rows and void "
                    "the truly-DNP cases (default: dry-run)."
    )
    ap.add_argument("--ledger",       type=str, default=str(DEFAULT_LEDGER))
    ap.add_argument("--qb-dir",       type=str, default=str(DEFAULT_QB_DIR))
    ap.add_argument("--full-box-dir", type=str, default=str(DEFAULT_FULL_BOX_DIR))
    ap.add_argument("--commit", action="store_true",
                     help="Actually void (backup taken first). Default = dry-run.")
    ap.add_argument("--out", type=str, default=None,
                     help="Optional JSON output path.")
    args = ap.parse_args(argv)

    rpt = run(
        ledger_path=Path(args.ledger),
        qb_dir=Path(args.qb_dir),
        full_box_dir=Path(args.full_box_dir),
        commit=args.commit,
    )
    print(json.dumps({k: v for k, v in rpt.items() if k not in ("skipped", "voided")},
                      indent=2, default=str))
    print(f"  voided detail (first 5): {rpt['voided'][:5]}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rpt, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
