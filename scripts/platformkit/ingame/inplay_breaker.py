"""scripts.platformkit.ingame.inplay_breaker -- median-CLV breaker glue for the
in-play paper channel.

WHY: execution.circuit_breaker (rolling median-CLV volume breaker, pre-registered
2026-07-15) was wired into the pregame prop channel only -- the in-play paper
daytrader had NO self-halt. This thin adapter loads the paper ledger's
channel=="paper_ingame" rows and asks allow_placement() whether one more in-game
placement is allowed: a bad graded stretch (negative rolling median CLV) CAPS the
channel to BREAKER_CAPPED_MAX_PER_DAY placements instead of letting it bleed.

SUPPRESS-ONLY + FAIL-OPEN (binding): this can only ever turn a would-be bet into
no_bet; any error (missing ledger, bad rows, import failure) returns allowed=True
so a broken breaker can never freeze measurement. Capture is upstream and always
runs regardless. PAPER / UNITS only; no $ anywhere.

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
    """The CLV series a ledger row belongs to. Untagged legacy rows predate any
    taker path, so by construction they are the maker series."""
    gate = row.get("exec_gate") if isinstance(row.get("exec_gate"), dict) else {}
    return str(row.get("clv_series") or gate.get("clv_series")
               or row.get("taken_book") or MAKER_SERIES)


def _load_channel_rows(ledger_path: Optional[Path],
                       series: str = MAKER_SERIES) -> List[Dict[str, Any]]:
    """The ledger's paper_ingame rows for ONE CLV series (never raises; [] on any problem).

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
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if (isinstance(row, dict) and row.get("channel") == CHANNEL
                        and _row_series(row) == series):
                    rows.append(row)
        return rows
    except Exception as exc:  # noqa: BLE001 -- fail-open, never sink a tick
        logger.debug("inplay_breaker ledger load failed: %s", exc)
        return []


def allow(market: str, now: datetime,
          ledger_path: Optional[Path] = None,
          series: str = MAKER_SERIES) -> Dict[str, Any]:
    """One-more-placement verdict for the in-play channel (per CLV series). FAIL-OPEN."""
    try:
        from scripts.platformkit.execution.circuit_breaker import allow_placement
        rows = _load_channel_rows(ledger_path, series=series)
        return allow_placement(rows, market, now.isoformat())
    except Exception as exc:  # noqa: BLE001 -- a broken breaker never blocks measurement
        logger.warning("inplay_breaker failed open: %s", exc)
        return {"allowed": True, "state": "ERROR_FAIL_OPEN", "reason": "breaker_error"}


__all__ = ["CHANNEL", "MAKER_SERIES", "allow"]
