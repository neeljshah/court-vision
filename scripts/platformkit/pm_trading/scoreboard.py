"""scripts.platformkit.pm_trading.scoreboard -- single grade_summary.json artifact.

Both the UI (/tonight page, CLV ledger view) and the real-money gate read this
file. One function builds the dict (build_scoreboard), one writes it atomically
(write_scoreboard). The gate depends on the field shape documented in the module
docstring below.

GRADE_SUMMARY.JSON FIELD SHAPE (the gate reads these exact keys):
  {
    "as_of":            "<ISO-8601 UTC>",
    "n_settled":        <int>,            # ALL settled rows (with or without a close)
    "n_clv":            <int>,            # true-close sample backing mean_clv_pct
    "n_no_close":       <int>,            # settled rows with no captured close
    "min_clv_n":        <int>,            # MIN_CLV_N floor (small-N noise guard)
    "mean_clv_pct":     <float|str>,      # mean CLV %, or "INSUFFICIENT_DATA" below floor
    "pct_beat_close":   <float|null>,     # % of settled rows where clv_pct > 0
    "n_true_close":     <int>,            # rows settled with a true (non-proxy) close
    "n_proxy_close":    <int>,            # rows settled with a proxy close
    "flat_unit_wins":   <int>,            # settled wins (flat-unit track record)
    "flat_unit_losses": <int>,            # settled losses
    "flat_unit_clv":    <float|null>,     # mean CLV over won+lost (push excluded)
    "by_sport": {
      "<sport_id>": {
        "n":               <int>,
        "mean_clv_pct":    <float|null>,
        "pct_beat_close":  <float|null>,
        "n_true_close":    <int>,
        "n_proxy_close":   <int>,
        "flat_unit_wins":  <int>,
        "flat_unit_losses":<int>
      },
      ...
    },
    "honest_note":      "<string>"
  }

GATE CRITERIA (pre-registered constants; decision-only, never auto-authorises):
  GATE_MIN_N         = 500    settled rows CARRYING A clv_pct required -- i.e. the
                              n_clv/n_true_close sample, NOT n_settled (which counts
                              no-close rows too and would inflate the denominator).
  GATE_CLV_LB_PCT    = 0.0    bootstrap 95 % lower bound on mean_clv_pct > this
  GATE_PCT_BEAT_CLOSE= 55.0   pct_beat_close >= this
  ROI is NEVER a gate criterion.
  These constants are advisory copies. realmoney_gate.evaluate recomputes eligibility
  from the ledger rows themselves (_settled_clv_rows), so this file cannot spoof it.

INVARIANTS: <=300 LOC; ASCII only; no secrets; no $-edge field; no ROI anywhere.
Build only under scripts/platformkit/.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger_io import load_rows, ledger_path as _canonical_ledger

# ---------------------------------------------------------------------------
# Pre-registered real-money gate thresholds (decision-only; no auto-authorise)
# ---------------------------------------------------------------------------
GATE_MIN_N: int = 500
GATE_CLV_LB_PCT: float = 0.0        # bootstrap 95 % lower bound must exceed this
GATE_PCT_BEAT_CLOSE: float = 55.0   # pct_beat_close >= this
# NOTE: ROI is NEVER a criterion.

# Min true-close sample before a mean CLV is reported as a number. Below it the
# small-N mean is noise, so mean_clv_pct is reported as INSUFFICIENT_DATA and the
# count is surfaced as n_clv. This MIRRORS scripts.platformkit.paper.paper_today
# (MIN_CLV_N=8) so grade_summary.json is consistent with paper_today/pnl_series.
MIN_CLV_N: int = 8

_HONEST_NOTE = (
    "CLV (closing-line value) is the honest track-record yardstick. "
    "A positive mean_clv_pct means bets were placed at a BETTER number than "
    "the closing price on average. This is a measurement tool, not a profit "
    "claim. The real-money gate is DECISION-ONLY; a human flip is always "
    "required. No $ edge is asserted anywhere in this file."
)

# Canonical output path: same data/ tree as the ledger (gitignored/local-only).
_HERE = Path(__file__).resolve().parent
_DEFAULT_OUT = _HERE.parents[2] / "data" / "frontend" / "grade_summary.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _settled_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ALL settled rows (status=='settled'), whether or not a close was captured.

    n_settled and the flat-unit win/loss record count over THIS population so a
    settled bet with no captured close (clv_status='no_close') still shows up as a
    real settled bet. CLV stats are computed over the narrower _clv_subset below.
    """
    return [r for r in rows if r.get("status") == "settled"]


def _clv_subset(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The subset of rows carrying a clv_pct (a captured close). CLV-only stats
    (mean_clv_pct, pct_beat_close, true/proxy close counts) are computed over this."""
    return [r for r in rows if r.get("clv_pct") is not None]


def _sport_bucket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate over a sport's settled rows. n + flat-unit record count ALL settled
    rows; CLV stats count only the clv-bearing subset. Pure."""
    n = len(rows)
    clv_rows = _clv_subset(rows)
    n_clv = len(clv_rows)
    # flat-unit record: win/loss from settled outcome (push excluded) over ALL settled
    wins = sum(1 for r in rows if r.get("outcome") == "win")
    losses = sum(1 for r in rows if r.get("outcome") == "loss")
    if n == 0:
        return {
            "n": 0,
            "mean_clv_pct": None,
            "pct_beat_close": None,
            "n_true_close": 0,
            "n_proxy_close": 0,
            "n_no_close": 0,
            "flat_unit_wins": 0,
            "flat_unit_losses": 0,
        }
    clvs = [float(r["clv_pct"]) for r in clv_rows]
    beats = sum(1 for c in clvs if c > 0.0)
    # CLV mean over TRUE-CLOSE rows only (a proxy close is a weaker substitute and
    # must not contaminate the headline mean); proxies stay in n_proxy_close.
    true_clvs = [float(r["clv_pct"]) for r in clv_rows
                 if not bool(r.get("clv_is_proxy", False))]
    n_true = len(true_clvs)
    n_proxy = sum(1 for r in clv_rows if r.get("clv_is_proxy", False))
    return {
        "n": n,
        "mean_clv_pct": (round(sum(true_clvs) / n_true, 6) if n_true else None),
        "pct_beat_close": (round(100.0 * beats / n_clv, 4) if n_clv else None),
        "n_true_close": n_true,
        "n_proxy_close": n_proxy,
        "n_no_close": n - n_clv,
        "flat_unit_wins": wins,
        "flat_unit_losses": losses,
    }


def build_scoreboard(*, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Load the ledger and compute grade_summary fields over SETTLED bets.

    Parameters
    ----------
    rows : list of dicts, optional
        Injected rows (for tests / deterministic use). When None, loads the
        canonical ledger via clv_ledger_io.load_rows.

    Returns
    -------
    dict
        Fields documented in the module docstring. N settled is the count of rows
        that are status='settled' AND carry a clv_pct; rows without a close (no
        clv_pct) are excluded from CLV stats but counted separately as n_no_close.
        Empty ledger -> zeros/nulls, never a crash.

    Notes
    -----
    NO $, ROI, or edge field anywhere. CLV and counts only.
    """
    if rows is None:
        rows = load_rows()

    settled = _settled_rows(rows)
    n = len(settled)               # ALL settled rows (the real settled count)
    clv_rows = _clv_subset(settled)
    n_clv_rows = len(clv_rows)     # settled rows that carry a captured close

    if n == 0:
        return {
            "as_of": _now_iso(),
            "n_settled": 0,
            "n_clv": 0,
            "n_no_close": 0,
            "min_clv_n": MIN_CLV_N,
            "mean_clv_pct": "INSUFFICIENT_DATA",
            "pct_beat_close": None,
            "n_true_close": 0,
            "n_proxy_close": 0,
            "flat_unit_wins": 0,
            "flat_unit_losses": 0,
            "flat_unit_clv": None,
            "by_sport": {},
            "honest_note": _HONEST_NOTE,
        }

    clvs = [float(r["clv_pct"]) for r in clv_rows]
    beats = sum(1 for c in clvs if c > 0.0)
    # CLV mean YARDSTICK over TRUE-CLOSE rows only: a proxy close (clv_is_proxy=True)
    # is a weaker substitute and must NOT contaminate the headline mean. Proxies stay
    # in n_clv_rows and surface separately as n_proxy_close. n_clv == n_true_close.
    true_clvs = [float(r["clv_pct"]) for r in clv_rows
                 if not bool(r.get("clv_is_proxy", False))]
    n_true = len(true_clvs)
    n_proxy = sum(1 for r in clv_rows if r.get("clv_is_proxy", False))

    # flat-unit win/loss record counts over ALL settled rows (a no-close win is still
    # a win); flat_unit_clv averages only the decided rows that HAVE a close.
    wins = sum(1 for r in settled if r.get("outcome") == "win")
    losses = sum(1 for r in settled if r.get("outcome") == "loss")
    decided = [r for r in clv_rows if r.get("outcome") in ("win", "loss")]
    flat_unit_clv: Optional[float] = None
    if decided:
        dc = [float(r["clv_pct"]) for r in decided]
        flat_unit_clv = round(sum(dc) / len(dc), 6)

    # per-sport breakdown
    sports = sorted({str(r.get("sport", "unknown")) for r in settled})
    by_sport: Dict[str, Any] = {
        sp: _sport_bucket([r for r in settled if str(r.get("sport", "unknown")) == sp])
        for sp in sports
    }

    # Small-N CLV floor on the TRUE-CLOSE sample (n_true), not n_settled: below
    # MIN_CLV_N true closes the mean is noise, so report INSUFFICIENT_DATA (never a
    # fabricated number) and surface n_clv. The gate reads n_settled/n_true_close, so
    # n_settled stays a real count; only the human-facing mean_clv_pct is suppressed.
    mean_clv_pct: Any = round(sum(true_clvs) / n_true, 6) \
        if n_true >= MIN_CLV_N else "INSUFFICIENT_DATA"

    return {
        "as_of": _now_iso(),
        "n_settled": n,
        "n_clv": n_true,
        "n_no_close": n - n_clv_rows,
        "min_clv_n": MIN_CLV_N,
        "mean_clv_pct": mean_clv_pct,
        # % beating the close is over the CLV-measured population only (a row with no
        # captured close can neither beat nor miss it), so the denominator is n_clv_rows.
        "pct_beat_close": (round(100.0 * beats / n_clv_rows, 4) if n_clv_rows else None),
        "n_true_close": n_true,
        "n_proxy_close": n_proxy,
        "flat_unit_wins": wins,
        "flat_unit_losses": losses,
        "flat_unit_clv": flat_unit_clv,
        "by_sport": by_sport,
        "honest_note": _HONEST_NOTE,
    }


def write_scoreboard(*, out_path: Optional[Path] = None) -> Path:
    """Build grade_summary.json and write it atomically via tmp+os.replace.

    Parameters
    ----------
    out_path : Path, optional
        Destination. Defaults to data/frontend/grade_summary.json (same tree as
        the CLV ledger, gitignored/local-only).

    Returns
    -------
    Path
        The resolved path that was written.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    board = build_scoreboard()
    payload = json.dumps(board, indent=2, default=str) + "\n"
    # Atomic write: write to a temp file in the same directory, then os.replace.
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


__all__ = ["build_scoreboard", "write_scoreboard", "GATE_MIN_N",
           "GATE_CLV_LB_PCT", "GATE_PCT_BEAT_CLOSE", "MIN_CLV_N"]
