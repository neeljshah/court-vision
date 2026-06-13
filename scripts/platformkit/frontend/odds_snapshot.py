"""scripts.platformkit.frontend.odds_snapshot — timestamped odds snapshot ledger.

HONEST (binding): markets are efficient — NO model edge is ever claimed.  This
module just ACCUMULATES timestamped price snapshots so we can later measure
line-movement / freshness (the #1 honest money lane) and CLV.  ``line_movement``
returns the RAW first-vs-latest movement record; the headline CLV truth metric is
computed by the existing ``clv.py`` at settlement — this is only the raw history
that feeds it.

Snapshots append to gitignored-local
``data/domains/<sport>/odds_snapshots/snapshots.jsonl`` (append-only, flush+fsync).
NEVER writes ``data/registry/``.  Default feed = EspnFreeFeed (free live); inject
any OddsFeed for tests (no network).
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed

logger = logging.getLogger(__name__)

_HONEST_NOTE = (
    "Raw timestamped odds snapshots: the line-movement / freshness record. "
    "Markets are efficient; no model edge is claimed. CLV is computed by clv.py."
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _snapshot_path(root: Optional[Path], sport: str) -> Path:
    base = Path(root) if root is not None else _repo_root()
    return base / "data" / "domains" / sport / "odds_snapshots" / "snapshots.jsonl"


def _default_feed() -> OddsFeed:
    from scripts.platformkit.frontend.feed_espn import EspnFreeFeed
    return EspnFreeFeed()


def _flatten(games: List[GameOdds], ts: str, sport: str) -> List[Dict[str, Any]]:
    """GameOdds list -> one flat snapshot row per quote (timestamped)."""
    rows: List[Dict[str, Any]] = []
    for g in games:
        for q in g.quotes:
            rows.append({
                "ts": ts,
                "game_id": g.game_id,
                "sport": sport,
                "home": g.home,
                "away": g.away,
                "commence_time": g.commence_time,
                "book": q.book,
                "market": q.market,
                "side": q.side,
                "decimal_odds": q.decimal_odds,
                "line": q.line,
                "source": g.source,
            })
    return rows


def _append_rows(path: Path, rows: List[Dict[str, Any]]) -> None:
    """Append rows to the JSONL ledger (create parent; flush+fsync; append-only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def snapshot_sport(
    sport: str,
    feed: Optional[OddsFeed] = None,
    root: Optional[Path] = None,
    ts_utc: Optional[str] = None,
) -> Path:
    """Fetch current odds for ``sport`` and append a timestamped snapshot.

    feed defaults to EspnFreeFeed (free live).  ts_utc defaults to now (UTC ISO).
    Returns the snapshots.jsonl path.  Never raises on a feed error (logs + writes
    whatever parsed, possibly zero rows).
    """
    ts = ts_utc or datetime.now(timezone.utc).isoformat()
    f = feed if feed is not None else _default_feed()
    try:
        games = f.fetch(sport)
    except Exception as exc:  # never crash the snapshot loop
        logger.error("snapshot_sport: feed.fetch(%s) failed: %s", sport, exc)
        games = []
    rows = _flatten(games, ts, sport)
    path = _snapshot_path(root, sport)
    _append_rows(path, rows)
    logger.info("snapshot_sport %s: wrote %d rows -> %s", sport, len(rows), path)
    return path


def load_snapshots(sport: str, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every snapshot row for ``sport`` (in append order).  [] if absent."""
    path = _snapshot_path(root, sport)
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def line_movement(sport: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """First-vs-latest decimal_odds movement per (game_id, book, market, side).

    HONEST: this is the RAW freshness / line-movement record, NOT a CLV claim.
    Returns {"sport","n_keys","movements":[{key fields, first, latest, delta,
    first_ts, latest_ts, line_first, line_latest}], "honest_note"}.
    """
    rows = load_snapshots(sport, root)
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("game_id"), r.get("book"), r.get("market"), r.get("side"))
        grouped.setdefault(key, []).append(r)
    movements: List[Dict[str, Any]] = []
    for key, recs in grouped.items():
        ordered = sorted(recs, key=lambda x: str(x.get("ts", "")))
        first, latest = ordered[0], ordered[-1]
        f_odds = first.get("decimal_odds")
        l_odds = latest.get("decimal_odds")
        delta = None
        if f_odds is not None and l_odds is not None:
            delta = round(float(l_odds) - float(f_odds), 6)
        game_id, book, market, side = key
        movements.append({
            "game_id": game_id,
            "book": book,
            "market": market,
            "side": side,
            "first": f_odds,
            "latest": l_odds,
            "delta": delta,
            "first_ts": first.get("ts"),
            "latest_ts": latest.get("ts"),
            "line_first": first.get("line"),
            "line_latest": latest.get("line"),
        })
    return {
        "sport": sport,
        "n_keys": len(movements),
        "movements": movements,
        "honest_note": _HONEST_NOTE,
    }


def _main(argv: Optional[List[str]] = None) -> int:
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m scripts.platformkit.frontend.odds_snapshot <sport>")
        return 2
    sport = args[0]
    path = snapshot_sport(sport)
    rows = load_snapshots(sport)
    captured = sum(1 for r in rows if r.get("sport") == sport)
    print(_HONEST_NOTE)
    print(f"  sport={sport}  snapshot -> {path}")
    print(f"  total rows captured (all snapshots): {captured}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = ["snapshot_sport", "load_snapshots", "line_movement"]
