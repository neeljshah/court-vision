"""box_snapshot_poller.py — 30-sec box-score snapshot poller.

The legacy ``live_inplay_daemon.py`` polls every 5 min via
``scripts.live_game_poll.poll_once``; for in-play decisions that's
6x too slow. This poller runs at 30s default, reuses the SAME
``poll_once`` helper so file shape stays identical, and emits two
events per LIVE snapshot:

  snapshot.updated   payload: {game_id, snapshot}
  projection.updated payload: {game_id, rows}  (one entry per player/stat)

The rows come from ``src.prediction.live_engine.project_from_snapshot``
— i.e. exactly the same projection pipeline the 5-min daemon uses,
just fired ~10x more often.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.event_bus import (  # noqa: E402
    EventBus, TOPIC_PROJECTION_UPDATED, TOPIC_SNAPSHOT_UPDATED, get_bus,
)
from src.live.latency_optimizer import is_game_live  # noqa: E402
from src.live.time_utils import slate_date  # noqa: E402

log = logging.getLogger("box_snapshot_poller")

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
HEARTBEAT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "daemon_heartbeats",
    "box_snapshot_poller.txt")


class BoxSnapshotPoller:
    """30-sec cadence snapshot poller + projection broadcaster."""

    def __init__(self, game_ids: Iterable[str], *,
                 bus: Optional[EventBus] = None,
                 interval_sec: float = 30.0,
                 live_dir: str = LIVE_DIR,
                 date_str: Optional[str] = None,
                 poll_once_fn=None,
                 project_fn=None) -> None:
        self.game_ids = list(game_ids)
        self.bus = bus or get_bus()
        self.interval_sec = interval_sec
        self.live_dir = live_dir
        self.date_str = date_str or slate_date().isoformat()
        # Late-bound for tests.
        if poll_once_fn is None:
            from scripts.live_game_poll import poll_once as poll_once_fn
        if project_fn is None:
            from src.prediction.live_engine import (
                project_from_snapshot as project_fn,
            )
        self._poll_once = poll_once_fn
        self._project = project_fn
        self._stopped = False

    async def tick_once(self) -> Dict[str, int]:
        """One pass across the slate. Returns ``{game_id: row_count}``."""
        loop = asyncio.get_event_loop()
        try:
            snapshots = await loop.run_in_executor(
                None, lambda: self._poll_once(
                    self.game_ids, live_dir=self.live_dir,
                    sleep_fn=lambda _s: None, api_sleep=0.0,
                )
            ) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("poll_once failed: %s", exc)
            snapshots = {}

        out: Dict[str, int] = {}
        for gid, snap in (snapshots or {}).items():
            await self.bus.publish(TOPIC_SNAPSHOT_UPDATED, {
                "game_id": gid, "snapshot": snap,
            })
            if not is_game_live(snap):
                out[gid] = 0
                continue
            try:
                rows = self._project(snap)
            except Exception as exc:  # noqa: BLE001
                log.warning("project_from_snapshot(%s) failed: %s", gid, exc)
                out[gid] = 0
                continue
            await self.bus.publish(TOPIC_PROJECTION_UPDATED, {
                "game_id": gid, "rows": rows, "source": "snapshot",
            })
            out[gid] = len(rows or [])

        _write_heartbeat()
        return out

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.tick_once()
            except Exception as exc:  # noqa: BLE001
                log.error("box_snapshot_poller crashed: %s", exc)
            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        self._stopped = True


def _write_heartbeat() -> None:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--game-ids",
        default=None,
        help=(
            "Comma-separated NBA game ids to poll (e.g. 0042500401,0042500402). "
            "When omitted, ids are auto-discovered from games_lookup.json for --date."
        ),
    )
    ap.add_argument(
        "--date",
        default=None,
        help=(
            "Slate date YYYY-MM-DD for auto-discovery (default: today ET). "
            "Ignored when --game-ids is supplied."
        ),
    )
    ap.add_argument("--interval-sec", type=float, default=30.0)
    return ap.parse_args(argv)


def _discover_game_ids(date: Optional[str] = None) -> List[str]:
    """Auto-discover tonight's NBA game ids from games_lookup.json.

    Imports golive_discover_game_ids (G-001 helper) which reads
    games_lookup.json (nba_stats_official entries for *date*) and falls
    back to ScoreboardV2 when needed.  Returns an empty list on failure so
    the poller starts but idles until a game goes live.
    """
    try:
        from scripts.golive_discover_game_ids import discover, _today_et
        target_date = date or _today_et()
        raw = discover(target_date)
        gids = [g.strip() for g in raw.split(",") if g.strip()]
        log.info("auto-discovered %d game id(s) for %s: %s",
                 len(gids), target_date, gids or "(none)")
        return gids
    except Exception as exc:  # noqa: BLE001
        log.warning("auto-discovery failed: %s — poller will idle", exc)
        return []


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    if args.game_ids:
        # Explicit --game-ids path: unchanged behaviour.
        gids = [g.strip() for g in args.game_ids.split(",") if g.strip()]
    else:
        # Auto-discovery mode: omitting --game-ids discovers today's live gids.
        gids = _discover_game_ids(args.date)
    poller = BoxSnapshotPoller(gids, interval_sec=args.interval_sec,
                               date_str=args.date)
    await poller.run_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
