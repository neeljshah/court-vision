"""pbp_poller.py — async play-by-play poller for Live Engine v2.

Every ``--interval-sec`` (default 10) we call ``fetch_pbp_v3`` for
each live game, diff against the last-seen ``actionNumber``, and
publish typed events to the shared event bus.

Event topics produced
---------------------
pbp.made_shot      action ∈ {"Made Shot"} OR isFieldGoal + shotResult=Made
pbp.foul           action == "Foul"
pbp.sub            action == "Substitution"
pbp.turnover       action == "Turnover"
pbp.timeout        action == "Timeout"
pbp.period_end     action == "End Period" / "End of Period"

Each event payload always has: ``game_id``, ``action_number``,
``period``, ``clock``, ``description``, plus the raw play under
``raw``.

CV_PBP_QUALIFIERS — when ON, ``_event_from_play`` promotes
``subType`` and ``qualifiers`` (and derived boolean flags) out of
``raw`` into first-class event fields.  Byte-identical when OFF:
no new keys are added to the event dict and the ``raw`` field is
unchanged.  Downstream heads that consume qualifier fields must
gate on the same flag independently.

Skips polling when the snapshot in ``data/live/`` says the game
isn't LIVE (via ``is_game_live``). Coalesces duplicate plays
emitted twice via ``EventCoalescer`` (window 2s).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Set

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.event_bus import (  # noqa: E402
    EventBus, TOPIC_PBP_FOUL, TOPIC_PBP_MADE_SHOT, TOPIC_PBP_PERIOD_END,
    TOPIC_PBP_SUB, TOPIC_PBP_TIMEOUT, TOPIC_PBP_TURNOVER, get_bus,
)
from src.live.latency_optimizer import EventCoalescer, is_game_live  # noqa: E402

log = logging.getLogger("pbp_poller")

# CV_PBP_QUALIFIERS — when "1"/"true", promotes subType + qualifiers out of
# `raw` into first-class event fields (sub_type, qualifiers, shot_action_number,
# possession, in_penalty, and per-qualifier boolean flags: offensive_foul,
# technical, flagrant, and_1, fastbreak, ejection).
# When unset / "0" / "false" the event payload is byte-identical to the
# baseline schema (only the pre-existing keys are present; `raw` unchanged).
_PBP_QUALIFIERS: bool = (
    os.environ.get("CV_PBP_QUALIFIERS", "0").strip().lower() in ("1", "true", "yes")
)

LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")
HEARTBEAT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "daemon_heartbeats", "pbp_poller.txt")


# ── action-type classification ──────────────────────────────────────────
def _classify(play: Dict[str, Any]) -> Optional[str]:
    """Return the matching topic for ``play`` or None to drop it."""
    atype = (play.get("actionType") or "").strip()
    subtype = (play.get("subType") or "").strip().lower()
    # Made shot — both v3 spelling and legacy v2 spelling.
    if atype in ("Made Shot", "Made shot"):
        return TOPIC_PBP_MADE_SHOT
    if play.get("isFieldGoalMade") is True:
        return TOPIC_PBP_MADE_SHOT
    if atype == "Foul":
        return TOPIC_PBP_FOUL
    if atype == "Substitution":
        return TOPIC_PBP_SUB
    if atype == "Turnover":
        return TOPIC_PBP_TURNOVER
    if atype == "Timeout":
        return TOPIC_PBP_TIMEOUT
    # End-of-period markers vary by season; check both common forms.
    if atype in ("End Period", "Period End", "End of Period"):
        return TOPIC_PBP_PERIOD_END
    if atype == "Period" and "end" in subtype:
        return TOPIC_PBP_PERIOD_END
    return None


def _event_from_play(game_id: str, play: Dict[str, Any]) -> Dict[str, Any]:
    """Project the raw play into our canonical event payload.

    When CV_PBP_QUALIFIERS is ON, first-class qualifier fields are added:
    ``sub_type``, ``qualifiers`` (list), ``shot_action_number``, ``possession``,
    ``in_penalty``, and per-qualifier boolean shortcuts (``offensive_foul``,
    ``technical``, ``flagrant``, ``and_1``, ``fastbreak``, ``ejection``).

    When CV_PBP_QUALIFIERS is OFF the output is byte-identical to the
    pre-qualifier schema — no new keys are emitted.
    """
    event: Dict[str, Any] = {
        "game_id": game_id,
        "action_number": play.get("actionNumber"),
        "period": play.get("period"),
        "clock": play.get("clock"),
        "description": play.get("description"),
        "player_id": play.get("personId"),
        "player_name": play.get("playerName"),
        "team_id": play.get("teamId"),
        "team_tricode": play.get("teamTricode"),
        "score_home": play.get("scoreHome"),
        "score_away": play.get("scoreAway"),
        "raw": play,
    }
    if _PBP_QUALIFIERS:
        # Promote subType and qualifiers to first-class fields.
        sub_type: str = str(play.get("subType") or "").strip().lower()
        qualifiers: List[str] = [
            str(q).strip().lower()
            for q in (play.get("qualifiers") or [])
            if q
        ]
        event["sub_type"] = sub_type
        event["qualifiers"] = qualifiers
        event["shot_action_number"] = play.get("shotActionNumber")
        event["possession"] = play.get("possession")
        # Derived boolean shortcuts — convenient for downstream consumers.
        event["in_penalty"] = "inpenalty" in qualifiers
        event["and_1"] = "and1" in qualifiers or "and-1" in qualifiers
        event["fastbreak"] = "fastbreak" in qualifiers or "fastbreak" in sub_type
        # Foul-type booleans (populated when actionType normalises to "Foul").
        event["offensive_foul"] = sub_type in {"offensive", "offensive charge"}
        event["technical"] = sub_type in {"technical", "double technical"}
        event["flagrant"] = sub_type in {"flagrant 1", "flagrant 2",
                                          "flagrant1", "flagrant2"}
        # Ejection: CDN carries a separate "ejection" actionType OR the
        # qualifier appears on certain flagrant-2 rows.
        _atype = str(play.get("actionType") or "").strip().lower()
        event["ejection"] = (
            _atype == "ejection"
            or "ejection" in qualifiers
            or sub_type in {"flagrant 2", "flagrant2"}
        )
    return event


# ── snapshot helpers ────────────────────────────────────────────────────
def _latest_snapshot_for(game_id: str, live_dir: str) -> Optional[Dict[str, Any]]:
    """Return the most-recent JSON snapshot for ``game_id`` (None if absent)."""
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


# ── main poller ─────────────────────────────────────────────────────────
class PBPPoller:
    """Polls play-by-play for one or more game IDs, emits typed events."""

    def __init__(self, game_ids: Iterable[str], *,
                 bus: Optional[EventBus] = None,
                 interval_sec: float = 10.0,
                 live_dir: str = LIVE_DIR,
                 fetch_fn=None,
                 coalescer: Optional[EventCoalescer] = None) -> None:
        self.game_ids: List[str] = list(game_ids)
        self.bus = bus or get_bus()
        self.interval_sec = interval_sec
        self.live_dir = live_dir
        # Last seen actionNumber per game id; new plays >= last+1 emit.
        self._last_seen: Dict[str, int] = {}
        # Late binding so tests can monkey-patch.
        if fetch_fn is None:
            from scripts.nba_api_v3_patch import fetch_pbp_v3 as fetch_fn
        self._fetch = fetch_fn
        self.coalescer = coalescer or EventCoalescer(window_seconds=2.0)
        self._stopped = False

    async def poll_once(self) -> int:
        """One pass across every game. Returns total events published.

        The fetch is offloaded to a thread executor — without that, a sync
        urllib/requests call inside this async function would block the
        FastAPI event loop while NBA API timeouts unwind, freezing the
        entire web server (and /api/health) for 30+ seconds per cycle.
        """
        published = 0
        loop = asyncio.get_event_loop()
        for gid in self.game_ids:
            snap = _latest_snapshot_for(gid, self.live_dir)
            if not is_game_live(snap):
                continue
            try:
                plays = await loop.run_in_executor(None, self._fetch, gid)
            except Exception as exc:  # noqa: BLE001
                log.warning("fetch_pbp_v3(%s) raised: %s", gid, exc)
                continue
            published += await self._dispatch_new(gid, plays)
        _write_heartbeat()
        return published

    async def _dispatch_new(self, game_id: str,
                            plays: List[Dict[str, Any]]) -> int:
        last = self._last_seen.get(game_id, -1)
        new_max = last
        published = 0
        for play in plays:
            try:
                anum = int(play.get("actionNumber") or 0)
            except (TypeError, ValueError):
                continue
            if anum <= last:
                continue
            topic = _classify(play)
            if topic is None:
                if anum > new_max:
                    new_max = anum
                continue
            key = (game_id, anum)
            if not self.coalescer.should_emit(key):
                if anum > new_max:
                    new_max = anum
                continue
            event = _event_from_play(game_id, play)
            await self.bus.publish(topic, event)
            published += 1
            if anum > new_max:
                new_max = anum
        if new_max > last:
            self._last_seen[game_id] = new_max
        return published

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                log.error("pbp_poller iteration crashed: %s", exc)
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
    ap.add_argument("--game-ids", required=True,
                    help="Comma-separated NBA game IDs to poll.")
    ap.add_argument("--interval-sec", type=float, default=10.0)
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    gids = [g.strip() for g in args.game_ids.split(",") if g.strip()]
    poller = PBPPoller(gids, interval_sec=args.interval_sec)
    await poller.run_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
