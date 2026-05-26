"""reconcile_settlements.py — R24_Q8 settlement reconciliation tool.

Reads ``data/pnl_ledger.csv`` and, for every recently settled real (non-synthetic)
bet, re-derives the expected outcome straight from the cached quarter-box JSON
files (the same source the auto-settle daemon uses) and compares it to the
status the ledger actually recorded.

Goal: catch bugs in `scripts/auto_settle_daemon.py` and `src.betting.pnl_ledger.
settle_bet` — e.g. UNDER on a shot stat off by 0.5, OT vs regulation confusion,
alt-line vs primary line mismatch, sign flips.

We do NOT touch the books' real settlement APIs — we don't have credentials.
What we re-compute is the NBA-box-truth re-derivation, treating the boxscore
as ground truth and the daemon's status as the candidate to verify.

Mismatch categories
-------------------
  * ``expected_won_got_lost``        — false-loss (real bankroll harm)
  * ``expected_lost_got_won``        — false-win (fake profit)
  * ``expected_push_got_won``        — push not detected (paid out as win)
  * ``expected_push_got_lost``       — push not detected (paid out as loss)
  * ``expected_won_got_push``        — push wrongly assigned
  * ``expected_lost_got_push``       — push wrongly assigned
  * ``actual_stat_disagreement``     — ledger ``actual_stat`` != boxscore (could
                                       be official-scoring correction)
  * ``boxscore_missing``             — no q1..qN files for game (can't verify)
  * ``player_dnp_but_settled``       — player not in box, but bet was settled
                                       won/lost/push (daemon should have voided)
  * ``ok``                           — ledger matches expected

CLI
---
    python scripts/reconcile_settlements.py [--days 7] [--out PATH]

Exit code 0 always (this is a reporter, not a gate); use the JSON for
follow-up actions. ``--strict`` flips exit-code 1 if any non-`ok` mismatch
is found.

Output JSON shape
-----------------
    {
      "as_of":              ISO timestamp,
      "window_days":        int,
      "ledger_path":        str,
      "qb_dir":             str,
      "n_total_settled":    int,    # status in {won,lost,push} across all time
      "n_in_window":        int,
      "n_real_settled":     int,    # in-window AND non-synthetic
      "n_verified":         int,    # in-window AND boxscore present
      "n_matched":          int,
      "n_mismatched":       int,
      "mismatch_categories":{ <category>: int, ... },
      "mismatches":         [ {...per-bet detail...}, ... ],
      "all_synthetic":      bool,
    }
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

# Reuse the OT-aware summer + stat-name map already proven in production.
from scripts.auto_settle_daemon import (         # noqa: E402
    sum_quarter_box_full,
    DEFAULT_QB_DIR,
    _player_key,
)

DEFAULT_LEDGER  = PROJECT_DIR / "data" / "pnl_ledger.csv"
DEFAULT_OUT_DIR = PROJECT_DIR / "data" / "cache"

VALID_SETTLED = {"won", "lost", "push"}

# Tolerance for "actual stat agrees with boxscore" (boxscore may round 1.0).
_STAT_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Synthetic detection.                                                        #
# --------------------------------------------------------------------------- #
def is_synthetic_row(row: Dict[str, Any]) -> bool:
    """Heuristic: bets built by scripts/build_pnl_ledger_*.py use a
    `Player_<id>` placeholder name and/or a `SYN` team tag.

    Real ledger rows have a human name like "Nikola Jokic" with a real team
    abbreviation; this is the cheapest reliable separator without needing a
    new schema column.
    """
    player = str(row.get("player", "") or "")
    team   = str(row.get("team", "") or "").upper()
    if team == "SYN":
        return True
    if player.startswith("Player_"):
        # All synth builders use this exact prefix + a numeric id.
        rest = player[len("Player_"):]
        if rest and rest.isdigit():
            return True
    return False


# --------------------------------------------------------------------------- #
# Status re-derivation (mirrors src.betting.pnl_ledger._resolve_status).      #
# --------------------------------------------------------------------------- #
def _resolve_expected_status(line: float, side: str, actual: float) -> str:
    if abs(actual - line) < 1e-9:
        return "push"
    over_wins = actual > line
    if (side == "OVER" and over_wins) or (side == "UNDER" and not over_wins):
        return "won"
    return "lost"


# --------------------------------------------------------------------------- #
# Date filtering.                                                             #
# --------------------------------------------------------------------------- #
def _parse_iso_any(s: str) -> Optional[_dt.datetime]:
    """Parse an ISO timestamp tolerant of trailing 'Z' / timezone suffixes."""
    if not s:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(txt)
    except ValueError:
        return None


def _in_window(row: Dict[str, Any], cutoff: _dt.datetime,
               *, field: str = "placed_at") -> bool:
    ts_raw = row.get(field, "")
    ts = _parse_iso_any(ts_raw)
    if ts is None:
        # Try the alternate field (e.g. settled_at) as a fallback.
        alt = "settled_at" if field == "placed_at" else "placed_at"
        ts = _parse_iso_any(row.get(alt, ""))
        if ts is None:
            return False
    # Compare as naive — strip tz if needed.
    if ts.tzinfo is not None:
        ts = ts.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return ts >= cutoff


# --------------------------------------------------------------------------- #
# Ledger loading.                                                             #
# --------------------------------------------------------------------------- #
def load_ledger(path: Path = DEFAULT_LEDGER) -> List[Dict[str, Any]]:
    if not Path(path).exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(r)
    return rows


# --------------------------------------------------------------------------- #
# Per-bet reconciliation.                                                     #
# --------------------------------------------------------------------------- #
def _match_player_in_totals(bet: Dict[str, Any],
                             totals: Dict[str, Dict[str, Any]],
                             ) -> Optional[Dict[str, Any]]:
    pname = bet.get("player", "")
    pkey  = _player_key(pname)
    for nm, row in totals.items():
        if _player_key(nm) == pkey:
            return row
    pid = str(bet.get("player_id") or "").strip()
    if pid and pid != "0":
        for row in totals.values():
            if str(row.get("player_id") or "") == pid:
                return row
    return None


def reconcile_bet(bet: Dict[str, Any],
                   qb_dir: Path = DEFAULT_QB_DIR,
                   *,
                   _totals_cache: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
                   ) -> Dict[str, Any]:
    """Return one reconciliation record for a single ledger row.

    The caller may pass a `_totals_cache` (game_id -> totals) so a slate of
    bets on the same game doesn't re-load the same JSONs each call.
    """
    bet_id   = str(bet.get("bet_id", ""))
    game_id  = str(bet.get("game_id", "") or "").strip()
    status   = str(bet.get("status", "") or "").lower()
    side     = str(bet.get("side", "") or "").upper()
    stat     = str(bet.get("stat", "") or "").lower()

    base: Dict[str, Any] = {
        "bet_id": bet_id,
        "game_id": game_id,
        "player": bet.get("player", ""),
        "stat": stat,
        "side": side,
        "line": None,
        "ledger_status": status,
        "ledger_actual_stat": None,
        "expected_status": None,
        "boxscore_actual_stat": None,
        "category": "ok",
        "delta_actual_stat": None,
    }

    # Numeric line.
    try:
        line = float(bet.get("line", ""))
        base["line"] = line
    except (TypeError, ValueError):
        base["category"] = "actual_stat_disagreement"
        base["note"] = "ledger line not numeric"
        return base

    # Ledger's recorded actual.
    try:
        ledger_actual = float(bet.get("actual_stat", ""))
        base["ledger_actual_stat"] = ledger_actual
    except (TypeError, ValueError):
        ledger_actual = None

    if not game_id:
        base["category"] = "boxscore_missing"
        base["note"] = "no game_id on row"
        return base

    # Boxscore totals (OT-aware sum across all period files).
    if _totals_cache is not None and game_id in _totals_cache:
        totals = _totals_cache[game_id]
    else:
        totals = sum_quarter_box_full(game_id, qb_dir)
        if _totals_cache is not None:
            _totals_cache[game_id] = totals

    if not totals:
        base["category"] = "boxscore_missing"
        base["note"] = f"no q1..qN files for game {game_id}"
        return base

    match = _match_player_in_totals(bet, totals)
    if match is None:
        # Daemon should have voided this; if it instead won/lost/push'd,
        # that's a settlement bug worth flagging.
        base["category"] = "player_dnp_but_settled"
        base["note"] = "player not in any quarter box for this game"
        return base

    if stat not in match or match[stat] is None:
        base["category"] = "boxscore_missing"
        base["note"] = f"stat '{stat}' not in boxscore for player"
        return base

    box_actual = float(match[stat])
    base["boxscore_actual_stat"] = box_actual

    if ledger_actual is not None:
        delta = box_actual - ledger_actual
        base["delta_actual_stat"] = round(delta, 4)
        if abs(delta) > 0.5:
            # Off by more than half a stat — boxscore changed or daemon used
            # wrong source.
            base["category"] = "actual_stat_disagreement"
            base["note"] = (
                f"box={box_actual} ledger={ledger_actual} delta={delta:+.2f}"
            )
            return base

    expected = _resolve_expected_status(line, side, box_actual)
    base["expected_status"] = expected

    if expected == status:
        base["category"] = "ok"
        return base

    # Categorize the directional mismatch precisely.
    base["category"] = f"expected_{expected}_got_{status}"
    return base


# --------------------------------------------------------------------------- #
# Top-level reconcile().                                                      #
# --------------------------------------------------------------------------- #
def reconcile(days: int = 7,
              ledger_path: Path = DEFAULT_LEDGER,
              qb_dir: Path = DEFAULT_QB_DIR,
              include_synthetic: bool = False,
              ) -> Dict[str, Any]:
    """Run end-to-end reconciliation. Returns the report dict (no I/O)."""
    ledger_path = Path(ledger_path)
    qb_dir = Path(qb_dir)
    rows = load_ledger(ledger_path)

    settled_all = [r for r in rows
                    if str(r.get("status", "")).lower() in VALID_SETTLED]

    cutoff = _dt.datetime.utcnow() - _dt.timedelta(days=int(days))
    in_window = [r for r in settled_all if _in_window(r, cutoff)]

    if include_synthetic:
        real = in_window
    else:
        real = [r for r in in_window if not is_synthetic_row(r)]

    all_synthetic = (len(in_window) > 0 and len(real) == 0)

    totals_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
    per_bet: List[Dict[str, Any]] = []
    matched = 0
    mismatched = 0
    verified = 0
    cat_counts: Dict[str, int] = {}

    for bet in real:
        rec = reconcile_bet(bet, qb_dir, _totals_cache=totals_cache)
        cat = rec["category"]
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        if cat != "boxscore_missing":
            verified += 1
        if cat == "ok":
            matched += 1
        else:
            mismatched += 1
            per_bet.append(rec)

    return {
        "as_of":            _dt.datetime.utcnow().isoformat(timespec="seconds"),
        "window_days":      int(days),
        "ledger_path":      str(ledger_path),
        "qb_dir":           str(qb_dir),
        "n_total_settled":  len(settled_all),
        "n_in_window":      len(in_window),
        "n_real_settled":   len(real),
        "n_verified":       verified,
        "n_matched":        matched,
        "n_mismatched":     mismatched,
        "mismatch_categories": cat_counts,
        "mismatches":       per_bet[:500],   # cap detail to keep file small
        "all_synthetic":    all_synthetic,
        "note":             (
            "All in-window settled bets are synthetic — nothing to verify."
            if all_synthetic else ""
        ),
    }


# --------------------------------------------------------------------------- #
# Atomic dump.                                                                #
# --------------------------------------------------------------------------- #
def _atomic_dump_json(payload: Dict[str, Any], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
    os.replace(tmp, path)


def default_out_path(out_dir: Path = DEFAULT_OUT_DIR) -> Path:
    today = _dt.datetime.utcnow().strftime("%Y-%m-%d")
    return Path(out_dir) / f"settlement_reconciliation_{today}.json"


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-derive settlement outcomes from quarter-box totals "
                    "and report any mismatches vs the ledger."
    )
    ap.add_argument("--days", type=int, default=7,
                     help="Only consider bets placed within the last N days (default 7)")
    ap.add_argument("--ledger", type=str, default=str(DEFAULT_LEDGER),
                     help="Path to pnl_ledger.csv (default data/pnl_ledger.csv)")
    ap.add_argument("--qb-dir", type=str, default=str(DEFAULT_QB_DIR),
                     help="Path to quarter_box directory")
    ap.add_argument("--out", type=str, default=None,
                     help="Output JSON path (default data/cache/settlement_reconciliation_<date>.json)")
    ap.add_argument("--include-synthetic", action="store_true",
                     help="Don't filter out synthetic Player_<id> / team=SYN rows")
    ap.add_argument("--strict", action="store_true",
                     help="Exit 1 if any non-ok mismatch is found")
    args = ap.parse_args(argv)

    report = reconcile(
        days=args.days,
        ledger_path=Path(args.ledger),
        qb_dir=Path(args.qb_dir),
        include_synthetic=args.include_synthetic,
    )
    out_path = Path(args.out) if args.out else default_out_path()
    _atomic_dump_json(report, out_path)
    print(json.dumps({
        "out": str(out_path),
        "n_real_settled": report["n_real_settled"],
        "n_verified":     report["n_verified"],
        "n_matched":      report["n_matched"],
        "n_mismatched":   report["n_mismatched"],
        "categories":     report["mismatch_categories"],
        "all_synthetic":  report["all_synthetic"],
    }, indent=2))
    if args.strict and report["n_mismatched"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
