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


def _split_matchup(matchup: str) -> Tuple[Optional[str], Optional[str]]:
    """Split a 'Away@Home' / 'Away vs Home' matchup -> (away_label, home_label).

    The frontend/paper rows store the game ONLY as a 'matchup' string (no separate
    home/away fields), so the close resolver MUST recover the two team labels from
    it. The repo convention is AWAY first ('San Francisco Giants@Atlanta Braves' =>
    away=Giants, home=Braves), confirmed against settled scores. Returns
    (None, None) when no separator is present.
    """
    s = str(matchup or "")
    for sep in (" @ ", "@", " vs. ", " vs ", " v ", " at ", " - "):
        if sep in s:
            away, _, home = s.partition(sep)
            away, home = away.strip(), home.strip()
            if away and home:
                return away, home
    return None, None


def game_key_for_bet(bet: Dict[str, Any]) -> Optional[str]:
    """line_store game_key from bet: event_id first, else sport|home|away[|date].

    home/away are taken from explicit fields when present, else recovered from the
    'matchup' string (the paper rows carry only a matchup). The date component is
    appended ONLY when an explicit game_date is given: the write ts is NOT the
    game's UTC date (a bet recorded the day before tip buckets the close under the
    GAME date), so a ts-derived date narrows to the wrong file and misses the close.
    Omitting it lets line_store scan the sport's files and match exactly on
    home/away -- still leak-free (get_close only returns pre-commence quotes).
    """
    eid = str(bet.get("event_id") or "").strip()
    if eid:
        return eid
    sp = str(bet.get("sport") or "").strip()
    h = str(bet.get("home") or "").strip()
    a = str(bet.get("away") or "").strip()
    if not (h and a):
        a2, h2 = _split_matchup(bet.get("matchup", ""))
        if h2 and a2:
            h, a = h2, a2
    if not (sp and h and a):
        return None
    d = str(bet.get("game_date") or "").strip()[:10]
    return ("%s|%s|%s|%s" % (sp, h, a, d)) if d else ("%s|%s|%s" % (sp, h, a))


def close_from_store(
    bet: Dict[str, Any], *, base: Optional[Path] = None
) -> Optional[Tuple[float, float, bool, Optional[str], Optional[str]]]:
    """(home_dec, away_dec, is_true_close, close_book_home, close_book_away) from
    line_store, or None. Never raises.

    close_book_{home,away} is the book that supplied the winning quote for that
    side (line_store.get_close's own per-row 'book' field, preserved through --
    it was already there, just previously discarded by callers). None when the
    quote row carries no book. Additive only: existing 3-tuple callers must
    unpack the first 3 elements, never assume the tuple length.
    """
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
    book_h = str(hr.get("book")) if hr.get("book") else None
    book_a = str(ar.get("book")) if ar.get("book") else None
    return float(ch), float(ca), bool(is_true), book_h, book_a


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
