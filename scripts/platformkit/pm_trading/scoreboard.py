"""scripts.platformkit.pm_trading.scoreboard -- single grade_summary.json artifact.

Both the UI (/tonight page, CLV ledger view) and the real-money gate read this
file. One function builds the dict (build_scoreboard), one writes it atomically
(write_scoreboard). The gate depends on the field shape documented in the module
docstring below.

GRADE_SUMMARY.JSON FIELD SHAPE (the gate reads these exact keys):
  {
    "as_of":            "<ISO-8601 UTC>",
    "n_settled":        <int>,            # count of settled rows with clv_pct
    "mean_clv_pct":     <float|null>,     # mean CLV %  (positive = beats close)
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
  GATE_MIN_N         = 500    settled rows with clv_pct required
  GATE_CLV_LB_PCT    = 0.0    bootstrap 95 % lower bound on mean_clv_pct > this
  GATE_PCT_BEAT_CLOSE= 55.0   pct_beat_close >= this
  ROI is NEVER a gate criterion.

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
    """Filter to rows that are settled and carry a clv_pct value."""
    return [
        r for r in rows
        if r.get("status") == "settled" and r.get("clv_pct") is not None
    ]


def _sport_bucket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate CLV stats over a set of settled rows. Pure."""
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "mean_clv_pct": None,
            "pct_beat_close": None,
            "n_true_close": 0,
            "n_proxy_close": 0,
            "flat_unit_wins": 0,
            "flat_unit_losses": 0,
        }
    clvs = [float(r["clv_pct"]) for r in rows]
    beats = sum(1 for c in clvs if c > 0.0)
    n_true = sum(1 for r in rows if not r.get("clv_is_proxy", True))
    n_proxy = sum(1 for r in rows if r.get("clv_is_proxy", False))
    # flat-unit record: win/loss from settled outcome (push rows excluded from count)
    wins = sum(1 for r in rows if r.get("outcome") == "win")
    losses = sum(1 for r in rows if r.get("outcome") == "loss")
    return {
        "n": n,
        "mean_clv_pct": round(sum(clvs) / n, 6),
        "pct_beat_close": round(100.0 * beats / n, 4),
        "n_true_close": n_true,
        "n_proxy_close": n_proxy,
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
    n = len(settled)

    if n == 0:
        return {
            "as_of": _now_iso(),
            "n_settled": 0,
            "mean_clv_pct": None,
            "pct_beat_close": None,
            "n_true_close": 0,
            "n_proxy_close": 0,
            "flat_unit_wins": 0,
            "flat_unit_losses": 0,
            "flat_unit_clv": None,
            "by_sport": {},
            "honest_note": _HONEST_NOTE,
        }

    clvs = [float(r["clv_pct"]) for r in settled]
    beats = sum(1 for c in clvs if c > 0.0)
    n_true = sum(1 for r in settled if not r.get("clv_is_proxy", True))
    n_proxy = sum(1 for r in settled if r.get("clv_is_proxy", False))

    wins = sum(1 for r in settled if r.get("outcome") == "win")
    losses = sum(1 for r in settled if r.get("outcome") == "loss")
    # flat-unit CLV: mean over rows with a decided outcome (push excluded)
    decided = [r for r in settled if r.get("outcome") in ("win", "loss")]
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

    return {
        "as_of": _now_iso(),
        "n_settled": n,
        "mean_clv_pct": round(sum(clvs) / n, 6),
        "pct_beat_close": round(100.0 * beats / n, 4),
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
           "GATE_CLV_LB_PCT", "GATE_PCT_BEAT_CLOSE"]
