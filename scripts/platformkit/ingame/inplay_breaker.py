"""scripts.platformkit.ingame.inplay_breaker -- median-CLV breaker glue for the
in-play paper channel.

WHY: execution.circuit_breaker (rolling median-CLV volume breaker, pre-registered
2026-07-15) was wired into the pregame prop channel only -- the in-play paper
daytrader had NO self-halt. This thin adapter loads the paper ledger's
channel=="paper_ingame" rows and asks allow_placement() whether one more in-game
placement is allowed: a bad graded stretch (negative rolling median CLV) CAPS the
channel to BREAKER_CAPPED_MAX_PER_DAY placements instead of letting it bleed.

SUPPRESS-ONLY: this can only ever turn a would-be bet into no_bet, never the
reverse. A MISSING or empty ledger is not an error -- it yields no graded rows,
which allow_placement already reads as CAPPED.

FAIL-CLOSED on error (CORRECTED 2026-09-17, execution readiness audit defect #7).
allow() used to return allowed=True on any exception, on the reasoning that "a
broken breaker can never freeze measurement". That reasoning does not hold: the
grade pair is captured in inplay_daytrader.on_tick BEFORE this gate runs and is
never gated by it, so measurement continues either way -- the only thing a
failure suppressed was the placement, which is exactly what an unreadable safety
interlock should suppress. An interlock whose state cannot be read is not known
to be clear. PAPER / UNITS only; no $ anywhere.

Per-file test: python -m pytest tests/platformkit/ingame/test_inplay_breaker.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHANNEL = "paper_ingame"

# READ-TIME CLV-series separation: the maker series this channel writes today.
# Any future taker fallback must write a DIFFERENT series tag and gets its own
# pool -- it can never silently blend into the maker statistics here.
MAKER_SERIES = "paper_ingame_maker"


def _row_series(row: Dict[str, Any]) -> str:
    """The CLV series a ledger row belongs to.

    CORRECTED 2026-09-01 (EXECUTION_ENFORCEMENT_MATRIX R9): this docstring
    used to claim "untagged legacy rows predate any taker path, so by
    construction they are the maker series". That is FALSE against real
    rows -- record_ingame_bet (paper_ingame.py) ALWAYS stamps taken_book
    (default "paper_ingame"), so the taken_book fallback below fires before
    the MAKER_SERIES fallback ever does. Measured against the real ledger:
    every existing paper_ingame row is (clv_series=None,
    taken_book="paper_ingame") -> series=="paper_ingame" != MAKER_SERIES ->
    EXCLUDED from the maker pool. The maker pool is genuinely EMPTY today.
    The direction is safe (empty pool -> median None -> capped placement),
    but no row here should be read as "maker" just because it is untagged.
    See scripts/platformkit/pm_trading/clv_beatrate_rollup.py for the
    maker/taker/legacy rollup that reports this honestly.
    """
    gate = row.get("exec_gate") if isinstance(row.get("exec_gate"), dict) else {}
    return str(row.get("clv_series") or gate.get("clv_series")
               or row.get("taken_book") or MAKER_SERIES)


class LedgerUnreadable(Exception):
    """The breaker's own input could not be read -- state unknown, not clear."""


def _load_channel_rows(ledger_path: Optional[Path],
                       series: str = MAKER_SERIES) -> List[Dict[str, Any]]:
    """The ledger's paper_ingame rows for ONE CLV series.

    An ABSENT ledger is a legitimate empty history ([] -> CAPPED upstream). A
    ledger that exists but cannot be read raises LedgerUnreadable, so allow()
    can fail CLOSED instead of mistaking an unreadable file for a clean one.

    An unparseable LINE is the same problem in miniature: skipping it silently
    turns a garbled ledger into an empty one, which reads as a clean history.
    Exactly one case is benign -- a partial FINAL line, which is what a
    concurrent append looks like mid-write. A bad line with any line after it
    means the file is garbled and raises. Blank lines are always ignored.

    ponytail: full-ledger scan per ENTER tick, O(total ledger). Fine while the
    shared jsonl is small (in-game bets are rare); switch to a tail-read or
    BREAKER_WINDOW_DAYS date-window if the ledger grows past ~100k lines."""
    try:
        if ledger_path is None:
            from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
            ledger_path = DEFAULT_LEDGER
        path = Path(ledger_path)
        if not path.is_file():
            return []
        rows: List[Dict[str, Any]] = []
        bad_line: Optional[int] = None
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                if bad_line is not None:
                    # Another line followed the bad one, so it was not the
                    # trailing partial write a concurrent append leaves.
                    raise LedgerUnreadable(
                        "unparseable ledger line %d of %s" % (bad_line, path))
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    bad_line = lineno
                    continue
                if (isinstance(row, dict) and row.get("channel") == CHANNEL
                        and _row_series(row) == series):
                    rows.append(row)
        return rows
    except LedgerUnreadable:
        raise  # already the right exception -- do not re-wrap its message
    except Exception as exc:  # noqa: BLE001 -- surfaced, never a silent empty read
        raise LedgerUnreadable(str(exc)) from exc


def allow(market: str, now: datetime,
          ledger_path: Optional[Path] = None,
          series: str = MAKER_SERIES) -> Dict[str, Any]:
    """One-more-placement verdict for the in-play channel (per CLV series). FAIL-CLOSED."""
    try:
        from scripts.platformkit.execution.circuit_breaker import allow_placement
        rows = _load_channel_rows(ledger_path, series=series)
        return allow_placement(rows, market, now.isoformat())
    except Exception as exc:  # noqa: BLE001 -- unknown breaker state blocks placement
        logger.warning("inplay_breaker failed closed: %s", exc)
        return {"allowed": False, "state": "ERROR_FAIL_CLOSED", "reason": "breaker_error"}


__all__ = ["CHANNEL", "MAKER_SERIES", "allow"]
