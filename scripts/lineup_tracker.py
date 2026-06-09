"""lineup_tracker.py — defender-matchup poller for Live Engine v2.

Every ``--interval-sec`` (default 30) we call ``fetch_matchups_v3``
for each live game, diff against the last-seen
``primary defender per (offensive player)``, and emit
``lineup.defender_changed`` events when a new defender takes over.

We use ``matchupMinutes`` (or ``partialPossessions`` as a fallback)
as the rank key: the defender with the highest current value on a
given offensive player is the "primary" defender.

Event payload
-------------
{
  "game_id":     "0042400315",
  "offense_id":  203999,
  "offense_name": "Nikola Jokic",
  "old_defender_id": 1628369,
  "new_defender_id": 203952,
  "new_defender_name": "Aaron Gordon",
  "matchup_minutes": 8.2,
}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.event_bus import (  # noqa: E402
    EventBus, TOPIC_LINEUP_DEFENDER_CHANGED, get_bus,
)
from src.live.latency_optimizer import is_game_live  # noqa: E402

log = logging.getLogger("lineup_tracker")

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
HEARTBEAT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "daemon_heartbeats", "lineup_tracker.txt")


def _latest_snapshot_for(game_id: str, live_dir: str) -> Optional[Dict[str, Any]]:
    try:
        candidates = [f for f in os.listdir(live_dir)
                      if f.startswith(game_id + "_") and f.endswith(".json")]
    except FileNotFoundError:
        return None
    if not candidates:
        return None
    candidates.sort()
    path = os.path.join(live_dir, candidates[-1])
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _matchup_weight(row: Dict[str, Any]) -> float:
    """Higher = more time spent guarding. Used to pick the primary defender."""
    for key in ("matchupMinutes", "matchup_minutes",
                "partialPossessions", "partial_possessions"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _primary_defenders(rows: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Map offensive_player_id → row of the primary defender."""
    best: Dict[int, Tuple[float, Dict[str, Any]]] = {}
    for row in rows:
        # v3 endpoint uses different keys on different seasons; tolerate both.
        off_id = row.get("personIdOff") or row.get("offensivePersonId") or \
                 row.get("personId")
        if off_id is None:
            continue
        try:
            off_id = int(off_id)
        except (TypeError, ValueError):
            continue
        w = _matchup_weight(row)
        cur = best.get(off_id)
        if cur is None or w > cur[0]:
            best[off_id] = (w, row)
    return {pid: row for pid, (_, row) in best.items()}


def _defender_id_from(row: Dict[str, Any]) -> Optional[int]:
    for key in ("defensivePersonId", "personIdDef", "defenderPersonId"):
        v = row.get(key)
        if v is None:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


class LineupTracker:
    """Polls BoxScoreMatchupsV3 and emits defender-changed events."""

    def __init__(self, game_ids: Iterable[str], *,
                 bus: Optional[EventBus] = None,
                 interval_sec: float = 30.0,
                 live_dir: str = LIVE_DIR,
                 fetch_fn=None) -> None:
        self.game_ids = list(game_ids)
        self.bus = bus or get_bus()
        self.interval_sec = interval_sec
        self.live_dir = live_dir
        # Per game: {off_player_id: primary_defender_id}
        self._last_primary: Dict[str, Dict[int, int]] = {}
        if fetch_fn is None:
            from scripts.nba_api_v3_patch import fetch_matchups_v3 as _raw
            # boxscorematchupsv3 has no CDN equivalent and stats.nba.com
            # is regularly unreachable from cloud egress (Railway/Fly).
            # Fail fast — 3s timeout, no retries — so we don't spend 30+
            # seconds per cycle in a retry loop that will never succeed.
            fetch_fn = lambda gid: _raw(gid, timeout=3.0, retries=0)
        self._fetch = fetch_fn
        self._stopped = False

    async def poll_once(self) -> int:
        """One pass. The fetch is offloaded to a thread executor so a slow
        stats.nba.com response doesn't block the asyncio event loop (which
        would freeze /api/health and the WS broadcaster too)."""
        emitted = 0
        loop = asyncio.get_event_loop()
        for gid in self.game_ids:
            snap = _latest_snapshot_for(gid, self.live_dir)
            if not is_game_live(snap):
                continue
            try:
                rows = await loop.run_in_executor(None, self._fetch, gid)
            except Exception as exc:  # noqa: BLE001
                # Don't WARN — matchups unreachable from cloud egress is the
                # expected state, not a problem. Log at INFO so the signal
                # stays in logs for ops without dominating them.
                log.info("fetch_matchups_v3(%s) skipped: %s", gid, exc)
                continue
            emitted += await self._diff_and_emit(gid, rows)
        _write_heartbeat()
        return emitted

    async def _diff_and_emit(self, game_id: str,
                             rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        primary = _primary_defenders(rows)
        prior = self._last_primary.get(game_id, {})
        emitted = 0
        new_state: Dict[int, int] = {}
        for off_id, row in primary.items():
            new_def = _defender_id_from(row)
            if new_def is None:
                continue
            new_state[off_id] = new_def
            old_def = prior.get(off_id)
            if old_def == new_def:
                continue
            event = {
                "game_id": game_id,
                "offense_id": off_id,
                "offense_name": row.get("playerNameOff") or row.get("playerName"),
                "old_defender_id": old_def,
                "new_defender_id": new_def,
                "new_defender_name": row.get("defenderName") or
                                     row.get("playerNameDef"),
                "matchup_minutes": _matchup_weight(row),
            }
            await self.bus.publish(TOPIC_LINEUP_DEFENDER_CHANGED, event)
            emitted += 1
        self._last_primary[game_id] = new_state
        return emitted

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                log.error("lineup_tracker iteration crashed: %s", exc)
            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        self._stopped = True


def _write_heartbeat() -> None:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as fh:
            fh.write(str(int(asyncio.get_event_loop().time())))
    except OSError:
        pass


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game-ids", required=True)
    ap.add_argument("--interval-sec", type=float, default=30.0)
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    gids = [g.strip() for g in args.game_ids.split(",") if g.strip()]
    tracker = LineupTracker(gids, interval_sec=args.interval_sec)
    await tracker.run_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
