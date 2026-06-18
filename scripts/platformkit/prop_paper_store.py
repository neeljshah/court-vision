"""scripts.platformkit.prop_paper_store -- pure ledger I/O + summary for prop_paper.

Split out of prop_paper.py to keep each file <=300 LOC. This module owns the
append-only JSONL store, the idempotency key, and the per-stat summary math. It
holds NO board / settlement logic (that lives in prop_paper.py). Pure local I/O,
no network, no real money. Public functions NEVER raise.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = _HERE.parents[1] / "data" / "frontend" / "prop_ledger.jsonl"

_SUMMARY_NOTE = (
    "PAPER prop record. Calibration is the yardstick (mean model_p_over vs "
    "realized hit_rate); paper_roi is small-N paper P&L at the taken price, NOT a "
    "proven $-edge. CLV-vs-close (mean_clv_pct / pct_beat_close) is now captured "
    "from the line history: the CLOSING line is APPROXIMATED by the LAST logged "
    "line before kickoff, so CLV is only as honest as the cadence. TODO/accrual: "
    "the loop must run up to kickoff over the tournament for the history to fill in "
    "-- CLV is the yardstick, still no beat-the-close $-edge claim is made here."
)


def now_iso(now: Optional[str] = None) -> str:
    return now or datetime.now(timezone.utc).isoformat()


def identity(row: Dict[str, Any]) -> tuple:
    """Idempotency key for a prop bet (open or settled twin share it).

    Deliberately EXCLUDES as_of: a cadence loop rebuilds the board every cycle and
    each refresh stamps a fresh as_of (the taken-line timestamp). Keying on as_of
    would re-record every prop every tick and explode the ledger. We key on the
    intrinsic prop -- (match, player, stat, line, side) -- so each distinct prop is
    recorded ONCE at first sight; as_of is still STORED in the record (it dates the
    taken line), just not part of the dedup key.
    """
    return (
        str(row.get("match")), str(row.get("player")), str(row.get("stat")),
        str(row.get("line")), str(row.get("side")),
    )


def append(target: Path, record: Dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def load_ledger(ledger_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every JSONL line. Missing file -> empty list. Never raises."""
    target = Path(ledger_path) if ledger_path is not None else DEFAULT_LEDGER
    if not target.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with target.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # tolerate a partial trailing write
    except Exception:  # noqa: BLE001
        return out
    return out


def paper_pnl(result: str, taken_price: Optional[float]) -> Optional[float]:
    """Unit-stake paper P&L at the taken decimal price. None for pick'em; 0 push."""
    if taken_price is None:
        return None
    if result == "win":
        try:
            return round(float(taken_price) - 1.0, 6)
        except (TypeError, ValueError):
            return None
    if result == "loss":
        return -1.0
    return 0.0  # push


def _bucket() -> Dict[str, Any]:
    return {"n": 0, "_wins": 0, "_decisive": 0, "_pnl": 0.0, "_priced": 0,
            "_p_sum": 0.0, "_clv_sum": 0.0, "_clv_n": 0, "_clv_beats": 0}


def _finalize(b: Dict[str, Any]) -> Dict[str, Any]:
    decisive = b.pop("_decisive")
    wins = b.pop("_wins")
    priced = b.pop("_priced")
    pnl = b.pop("_pnl")
    p_sum = b.pop("_p_sum")
    clv_sum = b.pop("_clv_sum")
    clv_n = b.pop("_clv_n")
    clv_beats = b.pop("_clv_beats")
    return {
        "n": b["n"],
        "hit_rate": round(wins / decisive, 4) if decisive else None,
        "paper_roi": round(pnl / priced, 4) if priced else None,
        "n_priced": priced,
        "mean_model_p_over": round(p_sum / b["n"], 4) if b["n"] else None,
        # CLV-vs-close over PRICED settled bets only (pick'em rows have clv None).
        "n_clv": clv_n,
        "mean_clv_pct": round(clv_sum / clv_n, 4) if clv_n else None,
        "pct_beat_close": round(100.0 * clv_beats / clv_n, 4) if clv_n else None,
    }


def prop_summary(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Per-stat and overall summary over SETTLED prop bets. hit_rate excludes
    pushes; paper_roi is over priced bets only. Honest small-N framing. Never
    raises."""
    overall = _bucket()
    by_stat: Dict[str, Any] = {}
    try:
        for r in load_ledger(ledger_path):
            if r.get("status") != "settled":
                continue
            result = r.get("result")
            buckets = (overall, by_stat.setdefault(str(r.get("stat")), _bucket()))
            for b in buckets:
                b["n"] += 1
                try:
                    b["_p_sum"] += float(r.get("model_p_over") or 0.0)
                except (TypeError, ValueError):
                    pass
                if result in ("win", "loss"):
                    b["_decisive"] += 1
                    b["_wins"] += 1 if result == "win" else 0
                pnl = r.get("paper_pnl")
                if pnl is not None:
                    try:
                        b["_pnl"] += float(pnl)
                        b["_priced"] += 1
                    except (TypeError, ValueError):
                        pass
                clv = r.get("clv_pct")
                if clv is not None:
                    try:
                        c = float(clv)
                        b["_clv_sum"] += c
                        b["_clv_n"] += 1
                        b["_clv_beats"] += 1 if c > 0.0 else 0
                    except (TypeError, ValueError):
                        pass
        return {
            "overall": _finalize(overall),
            "by_stat": {k: _finalize(v) for k, v in by_stat.items()},
            "note": _SUMMARY_NOTE,
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_summary failed: %s", exc)
        return {"overall": _finalize(overall), "by_stat": {},
                "note": _SUMMARY_NOTE, "status": "error: %s" % type(exc).__name__}


__all__ = [
    "DEFAULT_LEDGER", "now_iso", "identity", "append", "load_ledger",
    "paper_pnl", "prop_summary",
]
