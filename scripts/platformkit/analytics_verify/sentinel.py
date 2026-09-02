"""scripts.platformkit.analytics_verify.sentinel -- independent recompute of the
headline numbers the webapp serves, diffed against the served JSON.

Reads the RAW ledgers (data/frontend/clv_ledger.jsonl via the shared
clv_ledger.load_ledger loader, and paper_predictions_graded.jsonl) and
re-derives grade_summary.json / paper_pnl_series.json fields independently of
their writers (scripts.platformkit.pm_trading.scoreboard /
scripts.platformkit.paper.bankroll_daemon). Every check gets a verdict:
  VERIFIED    -- |delta| <= tolerance
  DISCREPANT  -- exceeds tolerance
  STALE       -- served as_of older than 24h (still compared)
  UNCHECKABLE -- not purely derivable from the raw ledgers (reason given)

edge_claimed is always False. Calibration/CLV/units language only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_sentinel.py -q
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.paper import bankroll as _bank
from scripts.platformkit.paper import paper_today as _today
from scripts.platformkit.paper import pnl_normalize as _nz

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_FRONTEND = _ROOT / "data" / "frontend"
GRADE_SUMMARY_PATH = _FRONTEND / "grade_summary.json"
PNL_SERIES_PATH = _FRONTEND / "paper_pnl_series.json"
OUT_PATH = _ROOT / "data" / "cache" / "analytics_verify" / "sentinel_report.json"

MIN_CLV_N = 8
STALE_AFTER = timedelta(hours=24)

_HONEST_NOTE = (
    "Independent recompute of served headline stats from the raw CLV ledger, "
    "for VERIFIED/DISCREPANT/UNCHECKABLE diffing only. CLV (closing-line value) "
    "and units are measurement, not a profit or $ edge claim."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _get(d: Dict[str, Any], dotted: str) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_stale(as_of: Any) -> bool:
    if not isinstance(as_of, str):
        return False
    try:
        ts = datetime.fromisoformat(as_of)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (_now() - ts) > STALE_AFTER


def _check(
    stat: str, served_file: Path, served_key: str, served: Any, recomputed: Any,
    *, tolerance: float = 1e-6, reason: Optional[str] = None,
) -> Dict[str, Any]:
    # public schema (docs/ANALYTICS_CONTRACT.md): stat, served_value,
    # recomputed_value, delta, verdict -- served_file/served_key kept for context.
    row: Dict[str, Any] = {
        "stat": stat, "served_file": served_file.name, "served_key": served_key,
    }
    if reason is not None:
        row["verdict"] = "UNCHECKABLE"
        row["reason"] = reason
        return row
    if served is None or recomputed is None:
        row["verdict"] = "UNCHECKABLE"
        row["reason"] = "served or recomputed value missing/null"
        return row
    if isinstance(served, str) or isinstance(recomputed, str):
        # non-numeric sentinel values (e.g. "INSUFFICIENT_DATA") must match exactly
        row["served_value"] = served
        row["recomputed_value"] = recomputed
        row["verdict"] = "VERIFIED" if served == recomputed else "DISCREPANT"
        return row
    delta = abs(float(served) - float(recomputed))
    row["served_value"] = served
    row["recomputed_value"] = recomputed
    row["delta"] = round(delta, 6)
    row["tolerance"] = tolerance
    row["verdict"] = "VERIFIED" if delta <= tolerance else "DISCREPANT"
    return row


# ---------------------------------------------------------------------------
# grade_summary.json -- mirrors scripts.platformkit.pm_trading.scoreboard
# filtering (status=='settled'; clv_pct not null; clv_is_proxy excludes from
# the true-close mean). Uses the shared clv_ledger.load_ledger loader (same
# synthetic-row drop the writer relies on) but does its OWN aggregation.
# ---------------------------------------------------------------------------
def _recompute_grade_summary(clv_path: Optional[Path] = None,
                              rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if rows is None:
        rows = _clv.load_ledger(clv_path)
    settled = [r for r in rows if r.get("status") == "settled"]
    clv_rows = [r for r in settled if r.get("clv_pct") is not None]
    true_clvs = [float(r["clv_pct"]) for r in clv_rows
                 if not bool(r.get("clv_is_proxy", False))]
    beats = sum(1 for r in clv_rows if float(r["clv_pct"]) > 0.0)
    wins = sum(1 for r in settled if r.get("outcome") == "win")
    losses = sum(1 for r in settled if r.get("outcome") == "loss")
    n_clv_rows = len(clv_rows)
    mean_clv: Any = (round(sum(true_clvs) / len(true_clvs), 6)
                      if len(true_clvs) >= MIN_CLV_N else "INSUFFICIENT_DATA")
    return {
        "n_settled": len(settled),
        "n_clv": len(true_clvs),
        "mean_clv_pct": mean_clv,
        "pct_beat_close": (round(100.0 * beats / n_clv_rows, 4) if n_clv_rows else None),
        "flat_unit_wins": wins,
        "flat_unit_losses": losses,
    }


def grade_summary_checks(clv_path: Optional[Path] = None,
                          served_path: Optional[Path] = None,
                          rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    path = served_path or GRADE_SUMMARY_PATH
    served = _read_json(path)
    checks: List[Dict[str, Any]] = []
    fields = ["n_settled", "n_clv", "mean_clv_pct", "pct_beat_close",
              "flat_unit_wins", "flat_unit_losses"]
    if served is None:
        for f in fields:
            checks.append(_check(f, path, f, None, None,
                                  reason="served file missing/unreadable"))
        return checks
    recomputed = _recompute_grade_summary(clv_path, rows=rows)
    stale = _is_stale(served.get("as_of"))
    for f in fields:
        tol = 0.01 if f in ("mean_clv_pct", "pct_beat_close") else 1e-6
        row = _check(f, path, f, served.get(f), recomputed[f],
                      tolerance=tol)
        if stale and row["verdict"] != "UNCHECKABLE":
            row["verdict"] = "STALE"
            row["note"] = "served as_of is older than 24h"
        checks.append(row)
    return checks


# ---------------------------------------------------------------------------
# paper_pnl_series.json -- mirrors scripts.platformkit.paper.bankroll_daemon.tick:
# placed bets == clv_ledger rows with a usable taken price (paper_today._is_placed),
# settled, collapsed to one position per market (pnl_normalize.select_clv_positions,
# a shared normalization utility -- NOT the aggregation being verified), then
# flat-1-unit restaked (pnl_normalize.normalize_flat). Own aggregation from there.
# ---------------------------------------------------------------------------
def _recompute_pnl_summary(clv_path: Optional[Path] = None,
                            bankroll_path: Optional[Path] = None,
                            rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    # rows (pre-loaded via _clv.load_ledger, shared with grade_summary in the
    # same build_report() call) skips a second full read of the same file;
    # _is_placed is the same filter load_placed applies on top of load_ledger.
    placed = [r for r in rows if _today._is_placed(r)] if rows is not None \
        else _today.load_placed(clv_path)
    settled = [r for r in placed if r.get("status") == "settled"]
    settled = _nz.select_clv_positions(settled)
    flat = _nz.normalize_flat(settled)
    n_win = sum(1 for r in flat if r.get("outcome") == "win")
    n_loss = sum(1 for r in flat if r.get("outcome") == "loss")
    total_units = round(sum(float(r["unit_result"]) for r in flat), 6)
    start_units = float(_bank.read_config(bankroll_path)["start_units"])
    return {
        "n_bets": len(flat), "n_win": n_win, "n_loss": n_loss,
        "total_units": total_units,
        "current_units": round(start_units + total_units, 6),
    }


def pnl_series_checks(clv_path: Optional[Path] = None,
                       bankroll_path: Optional[Path] = None,
                       served_path: Optional[Path] = None,
                       rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    path = served_path or PNL_SERIES_PATH
    served = _read_json(path)
    fields = ["n_bets", "n_win", "n_loss", "total_units", "current_units"]
    checks: List[Dict[str, Any]] = []
    if served is None:
        for f in fields:
            checks.append(_check(f, path, f, None, None,
                                  reason="served file missing/unreadable"))
        return checks
    summary = served.get("summary")
    if not isinstance(summary, dict):
        for f in fields:
            checks.append(_check(f, path, f, None, None,
                                  reason="served summary block missing"))
        return checks
    recomputed = _recompute_pnl_summary(clv_path, bankroll_path, rows=rows)
    stale = _is_stale(served.get("generated_at"))
    for f in fields:
        tol = 0.01 if f in ("total_units", "current_units") else 1e-6
        row = _check(f, path, f, summary.get(f),
                      recomputed[f], tolerance=tol)
        if stale and row["verdict"] != "UNCHECKABLE":
            row["verdict"] = "STALE"
            row["note"] = "served generated_at is older than 24h"
        checks.append(row)
    return checks


def build_report(*, clv_path: Optional[Path] = None,
                  bankroll_path: Optional[Path] = None,
                  grade_summary_path: Optional[Path] = None,
                  pnl_series_path: Optional[Path] = None) -> Dict[str, Any]:
    rows = _clv.load_ledger(clv_path)  # single read, shared by both check sets below
    checks = (
        grade_summary_checks(clv_path, grade_summary_path, rows=rows)
        + pnl_series_checks(clv_path, bankroll_path, pnl_series_path, rows=rows)
    )
    n_verified = sum(1 for c in checks if c["verdict"] == "VERIFIED")
    n_discrepant = sum(1 for c in checks if c["verdict"] == "DISCREPANT")
    n_stale = sum(1 for c in checks if c["verdict"] == "STALE")
    n_uncheckable = sum(1 for c in checks if c["verdict"] == "UNCHECKABLE")
    # S71/F7: VERIFIED is a claim about checks that actually ran. With
    # n_verified == 0 (every check STALE or UNCHECKABLE) the honest headline is
    # the reason nothing was verified, never the word VERIFIED.
    if n_discrepant:
        overall = "DISCREPANT"
    elif n_verified:
        overall = "VERIFIED"
    elif n_stale:
        overall = "STALE"
    else:
        overall = "UNCHECKABLE" if n_uncheckable else "INSUFFICIENT"
    return {
        "as_of": _now().isoformat(),
        "edge_claimed": False,
        "honest_note": _HONEST_NOTE,
        "checks": checks,
        "n_verified": n_verified,
        "n_discrepant": n_discrepant,
        "n_stale": n_stale,
        "n_uncheckable": n_uncheckable,
        "overall": overall,
    }


def write_report(report: Dict[str, Any], out_path: Optional[Path] = None) -> Path:
    dest = Path(out_path) if out_path is not None else OUT_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, default=str) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, str(dest))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return dest


def _main() -> int:
    report = build_report()
    dest = write_report(report)
    print(
        "analytics_sentinel: overall=%s verified=%d discrepant=%d stale=%d "
        "uncheckable=%d -> %s"
        % (report["overall"], report["n_verified"], report["n_discrepant"],
           report["n_stale"], report["n_uncheckable"], dest)
    )
    return 0


__all__ = ["build_report", "write_report", "grade_summary_checks",
           "pnl_series_checks", "GRADE_SUMMARY_PATH", "PNL_SERIES_PATH", "OUT_PATH"]


if __name__ == "__main__":
    raise SystemExit(_main())
