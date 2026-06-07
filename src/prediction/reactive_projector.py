"""reactive_projector.py — event-driven re-projection for Live Engine v2.

Subscribes to the event bus and re-projects affected players
IMMEDIATELY on relevant events — instead of waiting for the next
30-sec box snapshot tick.

Wired events
------------
pbp.foul       → reproject affected player using current snapshot
                 (foul_residual already in live_engine path)
pbp.sub        → reproject incoming + outgoing player (minute_factor
                 swings on subs)
pbp.period_end → full slate reproject (the period heads model fires
                 only at boundaries)
lineup.defender_changed → reproject offensive player; the new defender
                 id feeds defender_matchup_residual

Emits ``projection.updated`` with payload:
    {game_id, player_id, rows: [single row per stat], reason, delta}

``delta`` is the change in projected_final for each stat vs the prior
row (None when no prior cached).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.live.event_bus import (
    EventBus,
    TOPIC_LINEUP_DEFENDER_CHANGED,
    TOPIC_PBP_FOUL,
    TOPIC_PBP_PERIOD_END,
    TOPIC_PBP_SUB,
    TOPIC_PROJECTION_UPDATED,
    TOPIC_SNAPSHOT_UPDATED,
    get_bus,
)

log = logging.getLogger("reactive_projector")


def _default_snapshot_loader(game_id: str) -> Optional[Dict[str, Any]]:
    """Return the latest cached snapshot for ``game_id``.

    Reads from the canonical ``data/live/`` directory via
    ``src.data.live.latest_snapshot_path`` + ``load_live_state``.
    """
    try:
        from src.data.live import latest_snapshot_path, load_live_state
        path = latest_snapshot_path(game_id)
        if not path:
            return None
        return load_live_state(path)
    except Exception:
        return None


def _default_project_fn(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Wrapper around live_engine.project_from_snapshot."""
    from src.prediction.live_engine import project_from_snapshot
    return project_from_snapshot(snap)


class ReactiveProjector:
    """Listens for live events, re-projects affected players on demand.

    The hot path is a tight loop: subscribe → fetch latest snapshot
    → run live_engine.project_from_snapshot → publish delta. Latency
    target is single-digit ms per event (the projection math itself
    is the bulk of the cost).
    """

    def __init__(self, *,
                 bus: Optional[EventBus] = None,
                 snapshot_loader=None,
                 project_fn=None) -> None:
        self.bus = bus or get_bus()
        self._load_snap = snapshot_loader or _default_snapshot_loader
        self._project = project_fn or _default_project_fn
        # Cache last projected_final per (game_id, player_id, stat) so we
        # can compute deltas to surface to operators / dashboards.
        self._last_proj: Dict[Tuple[str, int, str], float] = {}
        self._registered = False

    # ── lifecycle ───────────────────────────────────────────────────
    def register(self) -> None:
        """Subscribe to all bus topics this projector reacts to.

        Idempotent — calling twice doesn't double-subscribe.
        """
        if self._registered:
            return
        self.bus.subscribe(TOPIC_PBP_FOUL, self._on_player_event)
        self.bus.subscribe(TOPIC_PBP_SUB, self._on_player_event)
        self.bus.subscribe(TOPIC_PBP_PERIOD_END, self._on_period_end)
        self.bus.subscribe(TOPIC_LINEUP_DEFENDER_CHANGED, self._on_defender_change)
        # Also passively observe snapshot updates so we can refresh the
        # delta-cache without missing baseline changes from the 30-sec
        # box-snapshot poller.
        self.bus.subscribe(TOPIC_SNAPSHOT_UPDATED, self._on_snapshot)
        self._registered = True

    # ── handlers ────────────────────────────────────────────────────
    async def _on_player_event(self, topic: str, event: Dict[str, Any]) -> None:
        game_id = event.get("game_id")
        player_id = event.get("player_id")
        if not game_id or player_id is None:
            return
        snap = self._load_snap(game_id)
        if not snap:
            return
        await self._reproject_player(game_id, int(player_id), snap,
                                     reason=topic)

    async def _on_period_end(self, topic: str, event: Dict[str, Any]) -> None:
        game_id = event.get("game_id")
        if not game_id:
            return
        snap = self._load_snap(game_id)
        if not snap:
            return
        await self._reproject_full_slate(game_id, snap, reason=topic)

    async def _on_defender_change(self, topic: str, event: Dict[str, Any]) -> None:
        game_id = event.get("game_id")
        offense_id = event.get("offense_id")
        if not game_id or offense_id is None:
            return
        snap = self._load_snap(game_id)
        if not snap:
            return
        # Stamp the new defender id into the snapshot's matchups dict so
        # defender_matchup_residual picks it up on this reprojection.
        new_def = event.get("new_defender_id")
        if new_def is not None:
            matchups = snap.setdefault("matchups", {})
            try:
                matchups[int(offense_id)] = int(new_def)
            except (TypeError, ValueError):
                pass
        await self._reproject_player(game_id, int(offense_id), snap,
                                     reason=topic)

    async def _on_snapshot(self, topic: str, event: Dict[str, Any]) -> None:
        """Refresh the delta cache so post-snapshot deltas reflect reality."""
        snap = event.get("snapshot")
        if not snap:
            return
        game_id = event.get("game_id") or snap.get("game_id")
        if not game_id:
            return
        try:
            rows = self._project(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot project failed: %s", exc)
            return
        self._update_cache(game_id, rows)

    # ── projection core ─────────────────────────────────────────────
    async def _reproject_player(self, game_id: str, player_id: int,
                                snap: Dict[str, Any], *, reason: str) -> None:
        try:
            all_rows = self._project(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("reactive project failed (%s): %s", reason, exc)
            return
        # Filter to the affected player only.
        rows = [r for r in all_rows if self._row_pid(r) == player_id]
        if not rows:
            return
        deltas: Dict[str, float] = {}
        for r in rows:
            stat = r.get("stat")
            key = (game_id, player_id, str(stat))
            new = float(r.get("projected_final") or 0.0)
            prev = self._last_proj.get(key)
            r["delta"] = (new - prev) if prev is not None else 0.0
            deltas[str(stat)] = r["delta"]
            self._last_proj[key] = new
        await self.bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": game_id,
            "player_id": player_id,
            "rows": rows,
            "reason": reason,
            "deltas": deltas,
            "source": "reactive",
        })

    async def _reproject_full_slate(self, game_id: str,
                                    snap: Dict[str, Any], *,
                                    reason: str) -> None:
        try:
            rows = self._project(snap)
        except Exception as exc:  # noqa: BLE001
            log.warning("reactive full slate failed (%s): %s", reason, exc)
            return
        # Compute deltas per row.
        for r in rows:
            pid = self._row_pid(r)
            stat = r.get("stat")
            if pid is None or stat is None:
                continue
            key = (game_id, pid, str(stat))
            new = float(r.get("projected_final") or 0.0)
            prev = self._last_proj.get(key)
            r["delta"] = (new - prev) if prev is not None else 0.0
            self._last_proj[key] = new
        await self.bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": game_id,
            "rows": rows,
            "reason": reason,
            "source": "reactive",
        })

    # ── helpers ─────────────────────────────────────────────────────
    def _update_cache(self, game_id: str,
                      rows: List[Dict[str, Any]]) -> None:
        for r in rows:
            pid = self._row_pid(r)
            stat = r.get("stat")
            if pid is None or stat is None:
                continue
            try:
                self._last_proj[(game_id, pid, str(stat))] = \
                    float(r.get("projected_final") or 0.0)
            except (TypeError, ValueError):
                continue

    @staticmethod
    def _row_pid(row: Dict[str, Any]) -> Optional[int]:
        pid = row.get("player_id")
        if pid is None:
            return None
        try:
            return int(pid)
        except (TypeError, ValueError):
            return None
