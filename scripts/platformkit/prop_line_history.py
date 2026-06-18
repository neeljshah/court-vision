"""scripts.platformkit.prop_line_history -- CLOSING-LINE capture + true CLV for props.

The paper prop loop (prop_loop / prop_paper) can prove CALIBRATION and a small-N
paper_roi at the TAKEN price, but it cannot judge CLV-vs-close because nobody logs
how a prop line moved. This module closes that gap, paper-only, with no $-edge claim:

  * log_board_lines: every tick, append one row per PRICED edge to a JSONL time
    series (data/frontend/prop_line_history.jsonl). Pick'em rows (no real two-way
    price) can't have CLV and are skipped. No dedup -- it is a time series.
  * closing_snapshot: the LAST logged price for an exact prop is the CLOSING-line
    proxy. We log up to kickoff, so the final logged line approximates the close.
  * clv_vs_close: devig the closing two-way (odds_shop.devig_twoway) -> fair close
    prob for the taken side; compare the taken price's implied prob. SAME sign
    convention as clv_ledger: POSITIVE = took a BETTER number than the close.

HONESTY: closing is APPROXIMATED by the last logged line; it is only as good as the
cadence. Real CLV needs the loop to run up to kickoff over the tournament so the
history accrues. CLV here is the honest yardstick, NOT a profit / $-edge claim.

Public functions NEVER raise -- they degrade to None / [] / a no-op.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_line_history.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.odds_shop import devig_twoway

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
DEFAULT_HISTORY = _HERE.parents[1] / "data" / "frontend" / "prop_line_history.jsonl"


def _now_iso(now: Optional[str] = None) -> str:
    return now or datetime.now(timezone.utc).isoformat()


def _priced(over_price: Any, under_price: Any) -> Optional[tuple]:
    """(over, under) as decimals > 1.0, else None. A real two-way price only."""
    try:
        op = float(over_price)
        up = float(under_price)
    except (TypeError, ValueError):
        return None
    if op <= 1.0 or up <= 1.0:
        return None
    return op, up


def log_board_lines(
    board: Dict[str, Any], *, path: Optional[Path] = None, now: Optional[str] = None
) -> Dict[str, Any]:
    """Append one row per PRICED edge in *board* to the line-history JSONL.

    Each row: {match, player, stat, line, over_price, under_price, source, ts}. It
    is a TIME SERIES -- no dedup; the loop calls this every tick up to kickoff so the
    last row for a prop becomes the closing-line proxy. Only edges with a real
    two-way price (Underdog / sportsbook) are logged; pick'em (no price) can't have
    CLV and is skipped. Never raises -- returns {logged, skipped, status}.
    """
    target = Path(path) if path is not None else DEFAULT_HISTORY
    out = {"logged": 0, "skipped": 0}
    try:
        edges = (board or {}).get("edges") or []
        ts = _now_iso(now)
        rows: List[str] = []
        for edge in edges:
            if not isinstance(edge, dict):
                out["skipped"] += 1
                continue
            pr = _priced(edge.get("over_price"), edge.get("under_price"))
            if pr is None:
                out["skipped"] += 1
                continue
            op, up = pr
            rows.append(json.dumps({
                "match": edge.get("match"),
                "player": edge.get("player"),
                "stat": edge.get("stat"),
                "line": edge.get("line"),
                "over_price": op,
                "under_price": up,
                "source": edge.get("source"),
                "ts": ts,
            }, default=str))
        if rows:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(rows) + "\n")
            out["logged"] = len(rows)
        out["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 -- public fn must never raise
        logger.warning("log_board_lines failed: %s", exc)
        out["status"] = "error: %s" % type(exc).__name__
    return out


def load_history(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every JSONL line of the line history. Missing file -> []. Never raises."""
    target = Path(path) if path is not None else DEFAULT_HISTORY
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


def _matches(row: Dict[str, Any], match, player, stat, line, source) -> bool:
    """Exact prop identity (source optional: None means any source)."""
    if (str(row.get("match")) != str(match) or str(row.get("player")) != str(player)
            or str(row.get("stat")) != str(stat) or str(row.get("line")) != str(line)):
        return False
    if source is not None and str(row.get("source")) != str(source):
        return False
    return True


def closing_snapshot(
    history_rows: List[Dict[str, Any]], match, player, stat, line, source=None
) -> Optional[Dict[str, Any]]:
    """The LAST logged price for an exact prop = the closing-line proxy.

    We log up to kickoff, so the final logged line approximates the close. Scans
    *history_rows* for rows matching (match, player, stat, line[, source]) and
    returns {over_price, under_price, ts} for the latest ts, or None if none /
    none priced. Never raises.
    """
    try:
        best: Optional[Dict[str, Any]] = None
        for row in history_rows or []:
            if not isinstance(row, dict):
                continue
            if not _matches(row, match, player, stat, line, source):
                continue
            pr = _priced(row.get("over_price"), row.get("under_price"))
            if pr is None:
                continue
            ts = str(row.get("ts") or "")
            if best is None or ts >= str(best.get("ts") or ""):
                best = {"over_price": pr[0], "under_price": pr[1], "ts": ts}
        return best
    except Exception:  # noqa: BLE001
        return None


def clv_vs_close(
    taken_side: Optional[str],
    taken_price: Any,
    close_over: Any,
    close_under: Any,
) -> Optional[float]:
    """CLV % of a taken prop bet vs the CLOSING two-way line. None-safe -> None.

    Devig the closing (over, under) to a no-vig fair prob for the taken side via the
    vetted Shin solver (odds_shop.devig_twoway). The taken price implies
    taken_p = 1/taken_price. SAME sign as clv_ledger.compute_clv:

        clv_pct = (fair_close - taken_p) / taken_p * 100.0

    POSITIVE = took a BETTER number than the close (taken price implies a lower prob
    than the fair close = you are paid as if the outcome is less likely). NEGATIVE =
    worse number. Returns the clv_pct float, or None on any bad / missing input.
    Never raises.
    """
    try:
        side = str(taken_side or "").strip().lower()
        if side not in ("over", "under"):
            return None
        tp = float(taken_price)
        if tp <= 1.0:
            return None
        pr = _priced(close_over, close_under)
        if pr is None:
            return None
        fair_over, fair_under = devig_twoway(pr[0], pr[1])
        fair_close = fair_over if side == "over" else fair_under
        if not (fair_close > 0.0):
            return None
        taken_p = 1.0 / tp
        return round((fair_close - taken_p) / taken_p * 100.0, 6)
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "DEFAULT_HISTORY",
    "log_board_lines",
    "load_history",
    "closing_snapshot",
    "clv_vs_close",
]
