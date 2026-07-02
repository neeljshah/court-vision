"""prop_close_capture -- snapshot live two-way prop prices for our OPEN in-game props.

This is the prop analog of line_snapshot_daemon: run it on a cadence while games are
live and it records the CURRENT two-way (Over/Under) price of every open in-game prop
bet into prop_close_store. The LAST snapshot before a prop's market suspends is its
closing line -- which finally makes in-game props CLV-measurable (today they settle
win/loss only, clv_status='no_close').

Honest + non-fabricating: it only records a price the live book actually shows (both
sides present). A prop with no live two-way (one-sided / market suspended / no game
live) is simply not snapshotted -- get_close stays None and the settler keeps
'no_close'. Default live source is prop_draftkings_live (real in-play two-way O/U);
quote_fn is injectable so the core is offline-testable.

Scope: IN-GAME props (channel 'paper_ingame_prop'), which have a real two-way book.
Pregame DFS props (Underdog) have no two-way price and stay un-measurable here.

Per-file test: scripts/platformkit/clv/test_prop_close_capture.py
Run:  python -m scripts.platformkit.clv.prop_close_capture
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from scripts.platformkit.clv import prop_close_store as _store
from scripts.platformkit.clv_ledger import load_ledger

_INGAME_CHANNEL = "paper_ingame_prop"
# (over_dec, under_dec) keyed by a date-independent (player, stat, line) match key.
QuoteFn = Callable[[str], Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _match_key(player: Any, stat: Any, line: Any) -> str:
    """Date-independent key so a live feed quote (no game_date) matches our bet."""
    try:
        line_s = "%.4g" % float(line)
    except (TypeError, ValueError):
        line_s = _store._norm(line)
    return "|".join([_store._norm(player), _store._norm(stat), line_s])


def _default_quote_fn(sport: str) -> List[Tuple[str, float, float]]:
    """Live DK two-way props -> [(match_key, over_dec, under_dec)]. Never raises."""
    try:
        from scripts.platformkit.odds_provider.prop_draftkings_live import fetch_props
    except Exception:  # noqa: BLE001 -- missing adapter -> no quotes, not a crash
        return []
    rows = fetch_props(sport)
    if isinstance(rows, dict):  # UNAVAILABLE envelope
        return []
    out: List[Tuple[str, float, float]] = []
    for r in rows or []:
        try:
            out.append((_match_key(r.player, r.stat, r.line),
                        float(r.over_price), float(r.under_price)))
        except (AttributeError, TypeError, ValueError):
            continue
    return out


def _open_ingame_props(ledger: Sequence[Dict[str, Any]], sport: str
                       ) -> List[Dict[str, Any]]:
    return [r for r in ledger
            if r.get("channel") == _INGAME_CHANNEL
            and r.get("status") != "settled"
            and str(r.get("sport") or "").lower() == sport.lower()]


def capture_once(sport: str = "mlb", *,
                 ledger: Optional[Sequence[Dict[str, Any]]] = None,
                 quote_fn: Optional[QuoteFn] = None,
                 open_fn: Optional[Callable[[Sequence[Dict[str, Any]], str],
                                            List[Dict[str, Any]]]] = None,
                 default_quote_fn: Optional[QuoteFn] = None,
                 source: str = "draftkings_live",
                 store_path: str = _store.DEFAULT_STORE,
                 now: Optional[str] = None) -> Dict[str, Any]:
    """Snapshot the current two-way price of every open prop for *sport*.

    Defaults capture OPEN IN-GAME props off the live DK feed (the original M16
    behavior). Pass ``open_fn`` (e.g. open PREGAME props), ``default_quote_fn``
    (e.g. the pregame DK two-way feed) and ``source`` to capture another channel.
    """
    rows = list(ledger) if ledger is not None else load_ledger()
    _open = open_fn or _open_ingame_props
    opens = _open(rows, sport)
    result = {"sport": sport, "open_props": len(opens), "captured": 0,
              "no_live_price": 0}
    if not opens:
        return result  # nothing open -> skip the network fetch entirely

    qf = quote_fn or default_quote_fn or _default_quote_fn
    quotes = qf(sport) or []
    lookup: Dict[str, Tuple[float, float]] = {}
    for q in quotes:
        try:
            mk, o, u = q[0], float(q[1]), float(q[2])
        except (IndexError, TypeError, ValueError):
            continue
        lookup[mk] = (o, u)

    ts = now or _now_iso()
    for r in opens:
        mk = _match_key(r.get("prop_player"), r.get("prop_stat"), r.get("line"))
        price = lookup.get(mk)
        if price is None:
            result["no_live_price"] += 1
            continue
        key = _store.key_for_row(r)
        if key and _store.record_quote(key, price[0], price[1], ts,
                                       source=source,
                                       store_path=store_path):
            result["captured"] += 1
        else:
            result["no_live_price"] += 1
    return result


def capture_all(sports: Sequence[str] = ("mlb",), **kw: Any) -> Dict[str, Any]:
    out = {"by_sport": {}, "captured": 0}
    for s in sports:
        r = capture_once(s, **kw)
        out["by_sport"][s] = r
        out["captured"] += r["captured"]
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    res = capture_all()
    print("prop_close_capture:", res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
