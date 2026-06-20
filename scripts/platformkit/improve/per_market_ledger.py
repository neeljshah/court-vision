r"""scripts.platformkit.improve.per_market_ledger -- per-market recalibration ledger.

Segments the self-improve SHIP readout by market (sport:side-type, e.g. "nba:moneyline")
so each segment has its own honest Brier/BSS/ECE row.  Markets below MIN_MARKET_N
emit INSUFFICIENT_DATA -- never a fabricated green.

CONTRACT:
  - append-only JSONL; each row keyed by (ts, market).
  - No dollar field: no key matching /(\$|roi|pnl|profit)/ in any row.
  - status in {"SHIP", "HOLD", "REJECT", "INSUFFICIENT_DATA"}.
  - calibration != edge (see CALIBRATION_NOTE).

Usage:
  ledger = PerMarketLedger(path)
  ledger.record_batch(settled_rows)
  rows = ledger.rows_for_market("nba:moneyline")
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.improve._market_metrics import (
    readout_for_segment as _readout_for_segment,
    verdict_from_readout as _verdict_from_readout,
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

MIN_MARKET_N: int = 30
"""Minimum settled rows per market; below this -> INSUFFICIENT_DATA."""

BRIER_IMPROVE_TOL: float = 0.005
BRIER_REGRESS_TOL: float = 0.005

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_HERE = Path(__file__).resolve().parent
_DEFAULT_LEDGER = _HERE.parents[2] / "data" / "frontend" / "improve_ledger_segmented.jsonl"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _assert_no_banned_keys(row: Dict[str, Any]) -> None:
    """Raise ValueError if any key matches the banned money-field pattern."""
    for k in _all_keys(row):
        if _BANNED_KEY_RE.search(k):
            raise ValueError(
                f"Banned key '{k}' in ledger row violates no-dollar-field contract."
            )


def _all_keys(obj: Any) -> List[str]:
    """Recursively collect all dict keys."""
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _infer_market(row: Dict[str, Any]) -> str:
    """Derive a market key from a settled row.  Falls back to 'unknown'."""
    if "market" in row and row["market"]:
        return str(row["market"]).lower()
    sport = str(row.get("sport", "unknown")).lower()
    bet_type = str(
        row.get("bet_type") or row.get("side_type") or row.get("market_type") or ""
    ).lower()
    if bet_type:
        return f"{sport}:{bet_type}"
    return sport


# ---------------------------------------------------------------------------
# Core segmenter
# ---------------------------------------------------------------------------


def segment_by_market(
    settled_rows: Sequence[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group settled rows by their inferred market key."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in settled_rows:
        mkt = _infer_market(r)
        groups.setdefault(mkt, []).append(r)
    return groups


def grade_market_segment(
    market: str,
    rows: List[Dict[str, Any]],
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Produce a single ledger row for one market segment.

    Under MIN_MARKET_N -> INSUFFICIENT_DATA (no fabricated readout).
    Otherwise -> status from _verdict_from_readout (SHIP/HOLD/REJECT).
    """
    ts = ts or _now_iso()
    n = len(rows)
    base: Dict[str, Any] = {
        "ts": ts,
        "market": market,
        "note": CALIBRATION_NOTE,
    }
    if n < MIN_MARKET_N:
        row: Dict[str, Any] = {
            **base,
            "status": "INSUFFICIENT_DATA",
            "n": n,
            "min_n": MIN_MARKET_N,
            "reason": (
                f"only {n} settled rows for market '{market}'; need >= {MIN_MARKET_N} "
                "for a meaningful readout. No calibration claimed."
            ),
        }
    else:
        readout = _readout_for_segment(rows)
        status = _verdict_from_readout(readout)
        row = {**base, "status": status, "readout": readout}

    _assert_no_banned_keys(row)
    return row


# ---------------------------------------------------------------------------
# PerMarketLedger class
# ---------------------------------------------------------------------------


class PerMarketLedger:
    """Append-only per-market recalibration ledger.

    Segments a settled-rows batch by market and writes one JSONL row per market.
    Under-N markets emit INSUFFICIENT_DATA -- never a green row from noise.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _DEFAULT_LEDGER

    def record_batch(
        self,
        settled_rows: Sequence[Dict[str, Any]],
        ts: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Segment, grade, append to JSONL; return list of ledger rows."""
        ts = ts or _now_iso()
        segments = segment_by_market(settled_rows)
        ledger_rows: List[Dict[str, Any]] = []
        for market, rows in sorted(segments.items()):
            row = grade_market_segment(market, rows, ts=ts)
            ledger_rows.append(row)
        self._append_rows(ledger_rows)
        return ledger_rows

    def all_rows(self) -> List[Dict[str, Any]]:
        """Return all rows in the ledger (chronological JSONL order)."""
        return _read_jsonl(self.path)

    def rows_for_market(self, market: str) -> List[Dict[str, Any]]:
        """Return ledger rows for a specific market key (exact match, lowercase)."""
        mkt = market.lower()
        return [r for r in self.all_rows() if str(r.get("market", "")).lower() == mkt]

    def latest_row_per_market(self) -> Dict[str, Dict[str, Any]]:
        """Return the latest ledger row for each market (last JSONL occurrence wins)."""
        latest: Dict[str, Dict[str, Any]] = {}
        for row in self.all_rows():
            mkt = str(row.get("market", "")).lower()
            if mkt:
                latest[mkt] = row
        return latest

    def _append_rows(self, rows: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

_ZERO_SHIPS_NOTE: str = (
    "ratchet has not promoted a version yet: n_promoted=0. "
    "This is honest -- no calibration improvement has cleared all 5 gates."
)


def count_promoted(ledger_path: Optional[Path] = None) -> int:
    """Count SHIP rows in the ledger (proxy for real version promotions).

    Returns 0 when the ledger is absent -- never fabricates a green count.
    """
    path = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows = _read_jsonl(path)
    return sum(1 for r in rows if str(r.get("status", "")).upper() == "SHIP")


def batch_summary(
    ledger_rows: List[Dict[str, Any]],
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Return a summary dict from a just-recorded batch of ledger rows.

    Fields (no $ key):
      n_markets      -- number of market segments in this batch
      n_promoted     -- cumulative SHIP count from the ledger on disk (honest)
      n_ship         -- SHIP rows in this batch
      n_hold         -- HOLD rows in this batch
      n_reject       -- REJECT rows in this batch
      n_insufficient -- INSUFFICIENT_DATA rows in this batch
      honest_note    -- calibration disclaimer; augmented when n_promoted==0
      note           -- CALIBRATION_NOTE alias
    """
    counters: Dict[str, int] = {"SHIP": 0, "HOLD": 0, "REJECT": 0, "INSUFFICIENT_DATA": 0}
    for row in ledger_rows:
        s = str(row.get("status", "")).upper()
        if s in counters:
            counters[s] += 1

    n_promoted = count_promoted(ledger_path)
    honest_note = (
        _ZERO_SHIPS_NOTE if n_promoted == 0 else CALIBRATION_NOTE
    )
    summary: Dict[str, Any] = {
        "n_markets": len(ledger_rows),
        "n_promoted": n_promoted,
        "n_ship": counters["SHIP"],
        "n_hold": counters["HOLD"],
        "n_reject": counters["REJECT"],
        "n_insufficient": counters["INSUFFICIENT_DATA"],
        "honest_note": honest_note,
        "note": CALIBRATION_NOTE,
    }
    _assert_no_banned_keys(summary)
    return summary


def record_per_market(
    settled_rows: Sequence[Dict[str, Any]],
    ledger_path: Optional[Path] = None,
    ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One-shot: segment, grade, append.  Returns ledger rows."""
    return PerMarketLedger(ledger_path).record_batch(settled_rows, ts=ts)


__all__ = [
    "PerMarketLedger",
    "record_per_market",
    "segment_by_market",
    "grade_market_segment",
    "batch_summary",
    "count_promoted",
    "MIN_MARKET_N",
    "CALIBRATION_NOTE",
]
