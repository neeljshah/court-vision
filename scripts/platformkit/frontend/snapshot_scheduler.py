"""scripts.platformkit.frontend.snapshot_scheduler — multi-sport odds snapshot scheduler.

HONEST (binding): this module only ACCUMULATES timestamped snapshots for
line-movement / freshness / CLV tracking.  Markets are efficient; NO model edge
is ever claimed.  The forward-CLV candidates produced here are the RAW
opener->closer records that ``clv.py`` grades at settlement — we do NOT compute
a CLV edge number here.

Orchestrates :mod:`scripts.platformkit.frontend.odds_snapshot` over every
platform sport and exposes an opener-vs-closer pairing so the CLV grading loop
has a ready-made candidate list.

Snapshots write to gitignored-local
``data/domains/<sport>/odds_snapshots/snapshots.jsonl`` (append-only).
NEVER writes ``data/registry/``.

CLI::

    python -m scripts.platformkit.frontend.snapshot_scheduler capture
    python -m scripts.platformkit.frontend.snapshot_scheduler candidates <sport>
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.frontend.odds_snapshot import (
    load_snapshots,
    snapshot_sport,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ constants -

SPORTS: Tuple[str, ...] = (
    "basketball_nba",
    "mlb_sbro",
    "soccer_fd",
    "tennis_atp",
)

_HONEST_BANNER = (
    "SNAPSHOT SCHEDULER — accumulates timestamped odds for line-movement / "
    "freshness / CLV tracking only.  Markets are efficient; no model edge is "
    "ever claimed.  Opener->closer records are graded by clv.py at settlement."
)

_HONEST_NOTE_MANIFEST = (
    "Raw timestamped snapshots only: opener->closer history for CLV grading. "
    "Markets efficient; no edge claimed."
)

_HONEST_NOTE_CANDIDATES = (
    "Raw opener->closer pairs for forward CLV grading (clv.py grades at "
    "settlement).  This is NOT a CLV edge number.  Markets efficient; no edge."
)


# --------------------------------------------------------------- capture_once -

def capture_once(
    sports: Sequence[str] = SPORTS,
    feed=None,
    root: Optional[Path] = None,
    ts_utc: Optional[str] = None,
) -> Dict:
    """Snapshot odds for every sport in ``sports`` in a single pass.

    Calls :func:`odds_snapshot.snapshot_sport` for each sport inside a
    try/except so one failing sport never aborts the others.  ``feed`` is
    injected as-is; when ``None`` the default ``EspnFreeFeed`` is used
    (lazy-imported inside ``snapshot_sport`` — no network at import time).

    Parameters
    ----------
    sports:
        Iterable of platform sport ids (default: ``SPORTS``).
    feed:
        :class:`~scripts.platformkit.frontend.feed.OddsFeed` to inject, or
        ``None`` to use ``EspnFreeFeed``.  Tests MUST inject a fake feed.
    root:
        Repo-root override (``Path``).  Defaults to the real repo root.
    ts_utc:
        ISO-8601 UTC timestamp string.  Defaults to ``now(UTC)``.

    Returns
    -------
    dict
        Manifest with keys ``ts``, ``sports`` (per-sport row counts + paths),
        ``total_rows``, ``honest_note``.
    """
    ts = ts_utc or datetime.now(timezone.utc).isoformat()
    per_sport: Dict[str, Dict] = {}
    total = 0

    for sport in sports:
        try:
            path = snapshot_sport(sport, feed=feed, root=root, ts_utc=ts)
            # Count rows written at this exact ts (cheap: reread is small)
            rows = [r for r in load_snapshots(sport, root=root)
                    if r.get("ts") == ts]
            n = len(rows)
            per_sport[sport] = {"rows": n, "path": str(path)}
            total += n
            logger.info("capture_once: %s -> %d rows @ %s", sport, n, ts)
        except Exception as exc:  # never crash the multi-sport loop
            logger.error("capture_once: sport=%s failed: %s", sport, exc)
            per_sport[sport] = {"rows": 0, "path": None, "error": str(exc)}

    return {
        "ts": ts,
        "sports": per_sport,
        "total_rows": total,
        "honest_note": _HONEST_NOTE_MANIFEST,
    }


# --------------------------------------------------- forward_clv_candidates --

def forward_clv_candidates(sport: str, root: Optional[Path] = None) -> Dict:
    """Return opener-vs-closer pairs for forward CLV grading.

    Reads all accumulated snapshots for ``sport`` via
    :func:`odds_snapshot.load_snapshots`, groups by
    ``(game_id, book, market, side)``, and for each key with **>=2**
    distinct timestamps emits one candidate record with the opener (earliest
    ts) and closer (latest ts) odds and lines.

    This is intentionally close to ``odds_snapshot.line_movement`` in
    structure (both use ``load_snapshots`` + sort-by-ts grouping), but is
    framed as forward-CLV candidates rather than movement deltas, and
    carries ``n_snapshots`` for the grading loop.  DRY: we reuse
    ``load_snapshots`` directly and keep the logic minimal.

    The actual CLV truth metric is computed by ``clv.py`` at settlement.
    We do NOT compute a CLV edge number here.

    Parameters
    ----------
    sport:
        Platform sport id.
    root:
        Repo-root override.  Defaults to the real repo root.

    Returns
    -------
    dict
        ``{"sport", "n_candidates", "candidates": [...], "honest_note"}``.
        Each candidate has ``game_id, book, market, side, opener_odds,
        opener_ts, closer_odds, closer_ts, opener_line, closer_line,
        n_snapshots``.
    """
    rows = load_snapshots(sport, root=root)
    grouped: Dict[Tuple, List[Dict]] = {}
    for r in rows:
        key: Tuple = (
            r.get("game_id"),
            r.get("book"),
            r.get("market"),
            r.get("side"),
        )
        grouped.setdefault(key, []).append(r)

    candidates: List[Dict] = []
    for key, recs in grouped.items():
        if len(recs) < 2:
            continue  # need at least opener + one later snapshot
        ordered = sorted(recs, key=lambda x: str(x.get("ts", "")))
        opener = ordered[0]
        closer = ordered[-1]
        game_id, book, market, side = key
        candidates.append({
            "game_id": game_id,
            "book": book,
            "market": market,
            "side": side,
            "opener_odds": opener.get("decimal_odds"),
            "opener_ts": opener.get("ts"),
            "closer_odds": closer.get("decimal_odds"),
            "closer_ts": closer.get("ts"),
            "opener_line": opener.get("line"),
            "closer_line": closer.get("line"),
            "n_snapshots": len(recs),
        })

    return {
        "sport": sport,
        "n_candidates": len(candidates),
        "candidates": candidates,
        "honest_note": _HONEST_NOTE_CANDIDATES,
    }


# ---------------------------------------------------------------- CLI _main --

def _main(argv: Optional[List[str]] = None) -> int:
    """CLI entry-point.

    Usage::

        python -m scripts.platformkit.frontend.snapshot_scheduler capture [<sport>]
        python -m scripts.platformkit.frontend.snapshot_scheduler candidates <sport>
        python -m scripts.platformkit.frontend.snapshot_scheduler line-movement <sport>
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = list(sys.argv[1:] if argv is None else argv)
    print(_HONEST_BANNER)
    print()

    if not args:
        print("usage:")
        print("  snapshot_scheduler capture [<sport>]")
        print("  snapshot_scheduler candidates <sport>")
        print("  snapshot_scheduler line-movement <sport>")
        return 2

    cmd = args[0].lower()

    if cmd == "capture":
        sports: Sequence[str] = SPORTS
        if len(args) >= 2:
            sports = [args[1]]
        manifest = capture_once(sports=sports)
        print(json.dumps(manifest, indent=2))
        return 0

    if cmd == "candidates":
        if len(args) < 2:
            print("error: candidates requires a <sport> argument")
            return 2
        sport = args[1]
        result = forward_clv_candidates(sport)
        print(json.dumps(result, indent=2))
        return 0

    if cmd in ("line-movement", "line_movement"):
        if len(args) < 2:
            print("error: line-movement requires a <sport> argument")
            return 2
        sport = args[1]
        from scripts.platformkit.frontend.odds_snapshot import line_movement
        result = line_movement(sport)
        print(json.dumps(result, indent=2))
        return 0

    print(f"unknown command: {cmd!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())


__all__ = [
    "SPORTS",
    "capture_once",
    "forward_clv_candidates",
]
