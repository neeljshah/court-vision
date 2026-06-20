"""ledger_hygiene_report.py -- P2 ledger-pollution honesty: read-only hygiene reconcile.

Surfaces a structured HONEST health summary of ledger pollution without mutating
or re-endorsing any ledger file.  NON-GATING: this report is informational only.

Flags detected:
  1. FLAT-PRIOR POLLUTED: model_prob in {0.4655, 0.5345} (base-rate fallback, not
     an individualised calibrated prediction).
  2. SYNTHETIC: sport/bet_id contains 'test_', game_id too short, or
     executed=True with channel='paper' (invariant violation).
  3. MALFORMED: missing {bet_id, status, sport, taken_decimal} or unknown status.
  4. DUPLICATE: rows sharing the same (bet_id, status) composite key.
  5. SETTLED_WITHOUT_CLV: settled rows with clv_pct absent or None.
  6. ORPHAN_SHIPS: improve-ledger SHIP proposals with no matching graded row.

CONTRACT (binding):
  * READ-ONLY. Never writes, appends, or mutates any ledger file or row.
  * UNITS ONLY. No dollar / pnl / roi / profit key anywhere in any output.
  * Non-gating: pass_=False is NEVER raised; informational only. Always exits 0.
  * Never raises. On load error or missing ledger -> INSUFFICIENT_DATA sentinel.
  * ASCII only. <= 300 LOC. Build only under scripts/platformkit/pm_trading/.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/pm_trading/test_ledger_hygiene_report.py -q
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Flat-prior sentinel values (degenerate base-rate fallbacks, not calibrated probs)
FLAT_PRIOR_PROBS = frozenset({0.4655, 0.5345})
_FLAT_PRIOR_ROUND = 4

_KNOWN_STATUSES = frozenset({"open", "settled", "policy_stamp", "rejected"})
_REQUIRED_FIELDS = ("bet_id", "status", "sport", "taken_decimal")
_MIN_GAME_ID_LEN = 6

_BANNED_OUTPUT_KEYS = frozenset({
    "dollar", "dollars", "pnl", "roi", "profit", "dollar_stake",
    "dollar_value", "net_pnl", "realized_pnl", "unrealized_pnl", "bankroll",
    "revenue", "stake_dollars",
})

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
_NOTE = ("NON-GATING hygiene report: calibration, not edge. "
         "No ledger file was mutated. Units only, no dollar P&L.")


@dataclass
class HygieneReport:
    """Structured honest health summary.  status: OK|POLLUTED|INSUFFICIENT_DATA."""
    total_rows: int = 0
    flat_prior_count: int = 0
    flat_prior_bet_ids: List[str] = field(default_factory=list)
    synthetic_count: int = 0
    malformed_count: int = 0
    duplicate_count: int = 0
    settled_without_clv_count: int = 0
    orphan_ship_count: int = 0
    orphan_ship_details: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "OK"
    note: str = _NOTE
    audited_at: str = ""


# ---------------------------------------------------------------------------
# Internal helpers (all pure; no IO except _read_jsonl)
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL rows. Missing / unreadable file -> []."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        rows.append(obj)
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return rows


def _is_flat_prior(row: Dict[str, Any]) -> bool:
    raw = row.get("model_prob")
    if raw is None:
        return False
    try:
        return round(float(raw), _FLAT_PRIOR_ROUND) in FLAT_PRIOR_PROBS
    except (TypeError, ValueError):
        return False


def _is_synthetic(row: Dict[str, Any]) -> bool:
    sport = str(row.get("sport") or "").lower()
    bid = str(row.get("bet_id") or "").lower()
    if "test_" in sport or "test_" in bid:
        return True
    gid = str(row.get("game_id") or "")
    if gid and len(gid) < _MIN_GAME_ID_LEN:
        return True
    if row.get("executed") is True and str(row.get("channel") or "") == "paper":
        return True
    return False


def _is_malformed(row: Dict[str, Any]) -> bool:
    for f in _REQUIRED_FIELDS:
        if row.get(f) is None:
            return True
    sv = str(row.get("status") or "").strip().lower()
    return sv not in _KNOWN_STATUSES


def _find_duplicates(rows: List[Dict[str, Any]]) -> int:
    """Count excess copies sharing a (bet_id|status) composite key."""
    seen: Dict[str, int] = {}
    for row in rows:
        k = "%s|%s" % (str(row.get("bet_id") or ""),
                       str(row.get("status") or "").strip().lower())
        seen[k] = seen.get(k, 0) + 1
    return sum(n - 1 for n in seen.values() if n > 1)


def _orphan_ships() -> tuple:
    """Delegate to improve.ledger_reconcile. Returns (count, details)."""
    try:
        from scripts.platformkit.improve.ledger_reconcile import reconcile
        r = reconcile()
        return int(r.get("n_orphan_ship", 0)), list(r.get("orphan_ships", []))
    except Exception:  # noqa: BLE001
        return 0, []


def _assert_no_banned_keys(report: HygieneReport) -> None:
    bad = _BANNED_OUTPUT_KEYS & set(vars(report).keys())
    if bad:
        raise AssertionError("Banned key in HygieneReport: %s" % sorted(bad))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(
    ledger_path: Optional[Path] = None,
    *,
    raw_rows: Optional[List[Dict[str, Any]]] = None,
    check_orphan_ships: bool = True,
) -> HygieneReport:
    """Build a read-only hygiene report.  Never raises; no file is mutated."""
    audited_at = datetime.now(timezone.utc).isoformat()

    if raw_rows is not None:
        rows = list(raw_rows)
    else:
        if ledger_path is None:
            ledger_path = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
        rows = _read_jsonl(Path(ledger_path))
        if not rows and not Path(ledger_path).exists():
            r = HygieneReport(
                status=INSUFFICIENT_DATA,
                audited_at=audited_at,
                note="NON-GATING hygiene report: ledger not found at %s" % ledger_path,
            )
            _assert_no_banned_keys(r)
            return r

    flat_prior_count = 0
    flat_prior_ids: List[str] = []
    synthetic = malformed = settled_no_clv = 0

    for row in rows:
        if _is_flat_prior(row):
            flat_prior_count += 1
            if len(flat_prior_ids) < 50:
                flat_prior_ids.append(str(row.get("bet_id") or ""))
        if _is_synthetic(row):
            synthetic += 1
        if _is_malformed(row):
            malformed += 1
        if str(row.get("status") or "").strip().lower() == "settled":
            if row.get("clv_pct") is None:
                settled_no_clv += 1

    dups = _find_duplicates(rows)
    orphan_n, orphan_d = (0, []) if not check_orphan_ships else _orphan_ships()

    any_poll = flat_prior_count or synthetic or malformed or dups or settled_no_clv or orphan_n
    report = HygieneReport(
        total_rows=len(rows),
        flat_prior_count=flat_prior_count,
        flat_prior_bet_ids=flat_prior_ids,
        synthetic_count=synthetic,
        malformed_count=malformed,
        duplicate_count=dups,
        settled_without_clv_count=settled_no_clv,
        orphan_ship_count=orphan_n,
        orphan_ship_details=orphan_d,
        status="POLLUTED" if any_poll else "OK",
        audited_at=audited_at,
    )
    _assert_no_banned_keys(report)
    return report


def to_dict(report: HygieneReport) -> Dict[str, Any]:
    """Convert a HygieneReport to a JSON-serializable plain dict."""
    d: Dict[str, Any] = {
        "status": report.status,
        "total_rows": report.total_rows,
        "flat_prior_count": report.flat_prior_count,
        "flat_prior_bet_ids": report.flat_prior_bet_ids,
        "synthetic_count": report.synthetic_count,
        "malformed_count": report.malformed_count,
        "duplicate_count": report.duplicate_count,
        "settled_without_clv_count": report.settled_without_clv_count,
        "orphan_ship_count": report.orphan_ship_count,
        "orphan_ship_details": report.orphan_ship_details,
        "note": report.note,
        "audited_at": report.audited_at,
    }
    bad = _BANNED_OUTPUT_KEYS & set(d.keys())
    if bad:
        raise AssertionError("Banned key in to_dict output: %s" % sorted(bad))
    return d


# ---------------------------------------------------------------------------
# CLI entry point (non-gating: always exits 0)
# ---------------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Ledger hygiene report (P2, non-gating, READ-ONLY). Always exits 0."
    )
    p.add_argument("--path", type=Path, default=None)
    p.add_argument("--json", action="store_true", default=False)
    p.add_argument("--no-orphan-ships", action="store_true", default=False)
    args = p.parse_args(argv)

    report = build_report(
        ledger_path=args.path,
        check_orphan_ships=not args.no_orphan_ships,
    )

    if args.json:
        print(json.dumps(to_dict(report), indent=2, default=str))
    else:
        print("[ledger_hygiene_report] status=%s  rows=%d  "
              "flat_prior=%d  synthetic=%d  malformed=%d  "
              "duplicate=%d  settled_no_clv=%d  orphan_ships=%d"
              % (report.status, report.total_rows,
                 report.flat_prior_count, report.synthetic_count,
                 report.malformed_count, report.duplicate_count,
                 report.settled_without_clv_count, report.orphan_ship_count))
        if report.flat_prior_bet_ids:
            print("  flat_prior_ids (first %d): %s"
                  % (len(report.flat_prior_bet_ids), report.flat_prior_bet_ids[:5]))
        for entry in report.orphan_ship_details[:5]:
            print("  orphan_ship: %s" % entry.get("ship_name", ""))
    return 0


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["build_report", "to_dict", "HygieneReport", "FLAT_PRIOR_PROBS", "INSUFFICIENT_DATA"]
