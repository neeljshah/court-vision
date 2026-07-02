"""prop_close_capture_pregame -- snapshot the PREGAME two-way prop close.

The in-game capturer (prop_close_capture / M16) explicitly skips pregame props:
a DFS book (Underdog) posts no two-way price. But DraftKings DOES post a pregame
two-way (Over/Under) line for the same player/stat/line, and our pregame props are
only ever placed against such a priced line. So the honest pregame "close" = DK's
two-way line captured near game lock. Recording it makes pregame props CLV-
measurable instead of stuck at clv_status='no_close'.

Reuses prop_close_capture.capture_once (same store, same match key, same non-
fabricating record path) -- only the open-set filter (PREGAME props), the feed
(DK pregame two-way) and the source label differ. The LAST snapshot before tip is
the close, exactly like line_store serves a moneyline close near tip-off.

HONEST RAILS: PRICES not bets; records only a real two-way (both sides > 1.0);
local feed adapter; never raises; no $ field; no flag flip; no edge claim.

Per-file test: scripts/platformkit/clv/test_prop_close_capture_pregame.py
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from scripts.platformkit.clv import prop_close_capture as _base
from scripts.platformkit.clv import prop_close_store as _store

_INGAME_CHANNEL = "paper_ingame_prop"
_SOURCE = "sportsbook_pregame"


def _open_pregame_props(ledger: Sequence[Dict[str, Any]], sport: str
                        ) -> List[Dict[str, Any]]:
    """Open, not-yet-settled PREGAME props for *sport* (any channel that is NOT the
    in-game channel; the in-game capturer already covers that one)."""
    return [r for r in ledger
            if r.get("market_type") == "prop"
            and r.get("channel") != _INGAME_CHANNEL
            and r.get("status") != "settled"
            and str(r.get("sport") or "").lower() == sport.lower()]


def _pregame_quote_fn(sport: str) -> List[Tuple[str, float, float]]:
    """PREGAME two-way sportsbook props (the system's canonical best book line,
    default FanDuel) -> [(match_key, over_dec, under_dec)]. Never raises. Skips
    one-sided rows (a real close needs both Over and Under)."""
    try:
        from scripts.platformkit.odds_provider.prop_book_aggregate import (
            book_best_line_props)
    except Exception:  # noqa: BLE001 -- missing adapter -> no quotes, not a crash
        return []
    try:
        rows = book_best_line_props(sport)
    except Exception:  # noqa: BLE001
        return []
    if isinstance(rows, dict):  # UNAVAILABLE envelope
        return []
    out: List[Tuple[str, float, float]] = []
    for r in rows or []:
        try:
            o, u = float(r.over_price), float(r.under_price)
        except (AttributeError, TypeError, ValueError):
            continue  # one-sided / no price -> not a capturable close
        if o > 1.0 and u > 1.0:
            out.append((_base._match_key(r.player, r.stat, r.line), o, u))
    return out


def capture_once(sport: str = "mlb", **kw: Any) -> Dict[str, Any]:
    """Snapshot the pregame two-way close of every open pregame prop for *sport*."""
    kw.setdefault("open_fn", _open_pregame_props)
    kw.setdefault("default_quote_fn", _pregame_quote_fn)
    kw.setdefault("source", _SOURCE)
    return _base.capture_once(sport, **kw)


def capture_all(sports: Sequence[str] = ("mlb",), **kw: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"by_sport": {}, "captured": 0}
    for s in sports:
        r = capture_once(s, **kw)
        out["by_sport"][s] = r
        out["captured"] += int(r.get("captured", 0) or 0)
    return out


def main() -> int:  # pragma: no cover
    print("prop_close_capture_pregame:", capture_all())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["capture_once", "capture_all"]
