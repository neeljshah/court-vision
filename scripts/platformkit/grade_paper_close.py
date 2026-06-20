"""scripts.platformkit.grade_paper_close -- captured-close resolution for grading.

Split out of grade_paper.py to keep each file <=300 LOC. This module owns the
line_store lookup that resolves a bet's TRUE/PROXY closing line (levels 2-3 of the
grade_paper close-resolution precedence). The line_store import is GUARDED:
unavailable -> close_from_store returns None and the grader degrades to levels 4-5.

HONESTY: a close is only returned when it is genuinely present in the store; a
missing close is None (NEVER fabricated), so the grader records clv_pct=None and
the row renders VOID/pending rather than an inferred proxy.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
never claims an edge. Never raises.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from scripts.platformkit.odds_provider.line_store import get_close as _ls_get_close
    from scripts.platformkit.odds_provider.markets import MONEYLINE as _MONEYLINE
    _LINE_STORE_OK = True
except Exception:  # noqa: BLE001
    _ls_get_close = None  # type: ignore[assignment]
    _MONEYLINE = "moneyline"  # type: ignore[assignment]
    _LINE_STORE_OK = False


def game_key_for_bet(bet: Dict[str, Any]) -> Optional[str]:
    """line_store game_key from bet: event_id first, else sport|home|away|date."""
    eid = str(bet.get("event_id") or "").strip()
    if eid:
        return eid
    sp = str(bet.get("sport") or "").strip()
    h = str(bet.get("home") or "").strip()
    a = str(bet.get("away") or "").strip()
    if not (sp and h and a):
        return None
    ts = str(bet.get("ts") or "")
    d = ts[:10] if len(ts) >= 10 else ""
    return ("%s|%s|%s|%s" % (sp, h, a, d)) if d else ("%s|%s|%s" % (sp, h, a))


def close_from_store(
    bet: Dict[str, Any], *, base: Optional[Path] = None
) -> Optional[Tuple[float, float, bool]]:
    """(home_dec, away_dec, is_true_close) from line_store, or None. Never raises."""
    if not _LINE_STORE_OK or _ls_get_close is None:
        return None
    gk = game_key_for_bet(bet)
    if gk is None:
        return None
    try:
        res = _ls_get_close(gk, **({} if base is None else {"base": base}))
    except Exception:  # noqa: BLE001
        logger.debug("line_store.get_close failed for %r", gk, exc_info=True)
        return None
    if res is None:
        return None
    closes, is_true = res
    hr = closes.get((_MONEYLINE, "home"))
    ar = closes.get((_MONEYLINE, "away"))
    if hr is None or ar is None:
        return None
    ch, ca = hr.get("odds"), ar.get("odds")
    if ch is None or ca is None or float(ch) <= 1.0 or float(ca) <= 1.0:
        return None
    return float(ch), float(ca), bool(is_true)


def load_predictions(predictions_path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    """Optional predictions store -> {matchup: row}. Tolerant: missing file -> {}."""
    if predictions_path is None:
        from scripts.platformkit.clv_ledger import DEFAULT_LEDGER
        predictions_path = DEFAULT_LEDGER.parent / "paper_predictions.jsonl"
    p = Path(predictions_path)
    if not p.exists():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            mk = str(row.get("matchup", ""))
            if mk:
                out[mk] = row
    return out


def fetch_boards(
    fetch: Callable[[str], Dict[str, Any]], sports: List[str],
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, str]]:
    """Fetch each sport's scoreboard once. Returns (boards, feed_status).

    One bad feed never sinks the pass: a raising fetch -> status 'unavailable',
    empty games. Empty / blank sport tokens are skipped. Never raises.
    """
    boards: Dict[str, List[Dict[str, Any]]] = {}
    feed_status: Dict[str, str] = {}
    for sp in sports:
        if not sp:
            continue
        try:
            payload = fetch(sp)
        except Exception:  # noqa: BLE001 - one bad feed never sinks the pass
            payload = {"status": "unavailable", "games": []}
        feed_status[sp] = str(payload.get("status", "unknown"))
        boards[sp] = list(payload.get("games") or [])
    return boards, feed_status


__all__ = ["game_key_for_bet", "close_from_store", "load_predictions",
           "fetch_boards", "_LINE_STORE_OK"]
