"""ledger_completeness_audit.py -- read-only CLV ledger completeness audit (BE8-4).

Produces clv_ledger_audit_report.json so the supervisor can surface the dup-key
blocker honestly.  Three dimensions:
  1. STATUS-AWARE DUPLICATE KEYS (same bet_id AND same status = replay collision).
     Open/settled twins share bet_id but differ in status -> NOT flagged.
  2. MISSING TIER on open rows (after policy_stamp enrichment).
  3. MISSING CLOSING LINE on settled rows (clv_pct absent/None).

CONTRACT: READ-ONLY. UNITS ONLY. No $/pnl/roi key. pass=False when any count>0.
Missing ledger -> UNAVAILABLE. Ledger bytes unchanged before/after. Never raises.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/pm_trading/test_ledger_completeness_audit.py -q
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

try:
    from scripts.platformkit import clv_ledger as _clv
    from scripts.platformkit.clv_ledger_status_dedup import status_key as _status_key
except ImportError:  # pragma: no cover
    _clv = None  # type: ignore[assignment]
    _status_key = None  # type: ignore[assignment]

DEFAULT_REPORT = _REPO / "data" / "frontend" / "ops" / "clv_ledger_audit_report.json"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
_OPEN, _SETTLED, _STAMP = "open", "settled", "policy_stamp"
_BANNED_KEYS = frozenset({"dollar", "pnl", "roi", "profit", "bankroll", "revenue",
                           "stake_dollars", "dollar_stake", "dollar_return"})


def _load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load JSONL rows. Missing file -> []. Never raises."""
    if _clv is not None:
        try:
            return _clv.load_ledger(path)
        except Exception:  # noqa: BLE001
            pass
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out.append(obj)
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return out


def _skey(row: Dict[str, Any]) -> str:
    """Status-aware key: '<bet_id>|<status>'. Inline fallback when import failed."""
    if _status_key is not None:
        try:
            return _status_key(row)
        except Exception:  # noqa: BLE001
            pass
    return "%s|%s" % (
        str(row.get("bet_id") or "").strip(),
        str(row.get("status") or "open").strip().lower(),
    )


def _stamps(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build bet_id -> first policy_stamp row map."""
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != _STAMP:
            continue
        bid = str(row.get("bet_id") or "").strip()
        if bid and bid not in out:
            out[bid] = row
    return out


def _has_tier(row: Dict[str, Any], stamp_map: Dict[str, Dict[str, Any]]) -> bool:
    """True when tier is set inline or via a policy_stamp sibling."""
    if row.get("tier") is not None:
        return True
    stamp = stamp_map.get(str(row.get("bet_id") or "").strip())
    return stamp is not None and stamp.get("tier") is not None


def _write_atomic(report: Dict[str, Any], out_path: Path) -> None:
    """Write report JSON atomically. Never raises."""
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(out_path.parent),
                                   prefix=out_path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
                fh.write("\n")
            os.replace(tmp, str(out_path))
        finally:
            try:
                if Path(tmp).exists():
                    os.unlink(tmp)
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass


def _clean(report: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in report.items() if k.lower() not in _BANNED_KEYS}


def run_audit(
    ledger_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    *,
    raw_rows: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Audit CLV ledger for dup keys, missing tier, missing closing lines.

    Returns dict: status/pass/dup_keys/dup_key_count/missing_tier/
    missing_closing_line/total_rows/total_open/total_settled/audited_at/
    ledger_path/report_path.  Never raises.  Ledger file never mutated.
    """
    audited_at = datetime.now(timezone.utc).isoformat()
    ledger_str, report_str = "raw_rows", "not_written"

    if raw_rows is not None:
        rows: List[Dict[str, Any]] = list(raw_rows)
    else:
        if ledger_path is not None:
            resolved = Path(ledger_path)
        elif _clv is not None:
            try:
                resolved = Path(_clv.DEFAULT_LEDGER)
            except Exception:  # noqa: BLE001
                resolved = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
        else:
            resolved = _REPO / "data" / "frontend" / "clv_ledger.jsonl"

        ledger_str = str(resolved)

        if not resolved.exists():
            rpt: Dict[str, Any] = {
                "status": "UNAVAILABLE", "pass": False,
                "dup_keys": [], "dup_key_count": 0,
                "missing_tier": 0, "missing_closing_line": 0,
                "total_rows": 0, "total_open": 0, "total_settled": 0,
                "audited_at": audited_at, "ledger_path": ledger_str,
                "report_path": "not_written",
                "error": "ledger not found: %s" % ledger_str,
            }
            out = Path(report_path) if report_path else DEFAULT_REPORT
            rpt["report_path"] = str(out)
            _write_atomic(_clean(rpt), out)
            return _clean(rpt)

        rows = _load_rows(resolved)
        rp = Path(report_path) if report_path else DEFAULT_REPORT
        report_str = str(rp)

    stamp_map = _stamps(rows)

    first_seen: Dict[str, int] = {}
    dup_set: set = set()
    for idx, row in enumerate(rows):
        k = _skey(row)
        if k in first_seen:
            dup_set.add(k)
        else:
            first_seen[k] = idx

    dup_keys = sorted(dup_set)
    total_open = total_settled = missing_tier = missing_closing_line = 0

    for row in rows:
        st = str(row.get("status") or "").strip().lower()
        if st == _OPEN:
            total_open += 1
            if not _has_tier(row, stamp_map):
                missing_tier += 1
        elif st == _SETTLED:
            total_settled += 1
            if row.get("clv_pct") is None:
                missing_closing_line += 1

    has_dups = bool(dup_keys)
    aud_pass = (not has_dups) and (missing_tier == 0) and (missing_closing_line == 0)

    report: Dict[str, Any] = {
        "status": "DUPS_FOUND" if has_dups else "CLEAN",
        "pass": aud_pass,
        "dup_keys": dup_keys,
        "dup_key_count": len(dup_keys),
        "missing_tier": missing_tier,
        "missing_closing_line": missing_closing_line,
        "total_rows": len(rows),
        "total_open": total_open,
        "total_settled": total_settled,
        "audited_at": audited_at,
        "ledger_path": ledger_str,
        "report_path": report_str,
    }

    if raw_rows is None or report_path is not None:
        out_path = Path(report_path) if report_path else DEFAULT_REPORT
        report["report_path"] = str(out_path)
        _write_atomic(_clean(report), out_path)

    return _clean(report)


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="CLV ledger completeness audit (BE8-4). READ-ONLY.")
    parser.add_argument("--path", type=Path, default=None,
                        help="Path to clv_ledger.jsonl")
    parser.add_argument("--report", type=Path, default=None,
                        help="Override report output path")
    parser.add_argument("--json", action="store_true", default=False,
                        help="Emit JSON to stdout")
    args = parser.parse_args(argv)

    result = run_audit(ledger_path=args.path, report_path=args.report)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        flag = "PASS" if result.get("pass") else "FAIL"
        print("[ledger_completeness_audit] %s  status=%s  dup_keys=%d  "
              "missing_tier=%d  missing_closing_line=%d  rows=%d"
              % (flag, result.get("status"), result.get("dup_key_count", 0),
                 result.get("missing_tier", 0), result.get("missing_closing_line", 0),
                 result.get("total_rows", 0)))
        for k in result.get("dup_keys", [])[:10]:
            print("  DUP: %s" % k)
        rp = result.get("report_path", "not_written")
        if rp != "not_written":
            print("  Report: %s" % rp)

    return 0 if result.get("pass") else 1


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["run_audit", "DEFAULT_REPORT", "INSUFFICIENT_DATA"]
