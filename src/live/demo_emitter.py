"""demo_emitter.py — synthetic event source for offseason / demo mode.

When ``DEMO_MODE`` is on, the orchestrator skips real NBA polling
and this module instead injects a slow trickle of plausible game
events into the shared event bus so the web dashboard has something
to render. Useful for:

  * offseason demos to investors / friends
  * smoke-testing a fresh deployment in <30s
  * exercising the WS bridge + dashboard end-to-end

The trickle simulates a 4Q close NBA game with two stars trading
buckets, drifting lines, and a couple of foul events. Loops forever.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Dict, Optional

from src.live.event_bus import (
    EventBus,
    TOPIC_BET_RECOMMENDED,
    TOPIC_LINES_REFRESHED,
    TOPIC_PBP_FOUL,
    TOPIC_PBP_MADE_SHOT,
    TOPIC_PBP_PERIOD_END,
    TOPIC_PBP_TURNOVER,
    TOPIC_PROJECTION_UPDATED,
    TOPIC_SNAPSHOT_UPDATED,
    get_bus,
)

log = logging.getLogger("demo_emitter")


# ── canned game state ──────────────────────────────────────────────────
_GAME_ID = "0042500999"

_PLAYERS = [
    {"player_id": 203999, "name": "Nikola Jokic", "team": "DEN",
     "line_pts": 28.5, "line_reb": 12.5, "line_ast": 8.5,
     "season_pts_avg": 30.0, "season_reb_avg": 13.0, "season_ast_avg": 9.5},
    {"player_id": 1629029, "name": "Luka Doncic", "team": "DAL",
     "line_pts": 32.5, "line_reb": 8.5, "line_ast": 9.5,
     "season_pts_avg": 33.0, "season_reb_avg": 9.0, "season_ast_avg": 10.0},
    {"player_id": 203954, "name": "Joel Embiid", "team": "PHI",
     "line_pts": 31.5, "line_reb": 10.5, "line_ast": 4.5,
     "season_pts_avg": 33.5, "season_reb_avg": 10.5, "season_ast_avg": 4.8},
    {"player_id": 1628369, "name": "Jayson Tatum", "team": "BOS",
     "line_pts": 26.5, "line_reb": 8.5, "line_ast": 5.5,
     "season_pts_avg": 27.5, "season_reb_avg": 8.5, "season_ast_avg": 5.0},
]

_BOOKS = ["pin", "bov", "fd", "pp"]


class DemoEmitter:
    """Spawns one asyncio task that fires synthetic events on a loop."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 tick_seconds: float = 4.0) -> None:
        self.bus = bus or get_bus()
        self.tick_seconds = tick_seconds
        self._stopped = False
        self._task: Optional[asyncio.Task] = None
        # mutable game state
        self._period = 1
        self._clock_s = 12 * 60  # seconds remaining in current period
        self._home_score = 0
        self._away_score = 0
        self._player_stats: Dict[int, Dict[str, float]] = {
            p["player_id"]: {"pts": 0.0, "reb": 0.0, "ast": 0.0,
                             "min": 0.0, "pf": 0.0, "stl": 0.0, "blk": 0.0,
                             "tov": 0.0}
            for p in _PLAYERS
        }
        # line drift state
        self._lines: Dict[tuple, float] = {}
        for p in _PLAYERS:
            for stat in ("pts", "reb", "ast"):
                base = p[f"line_{stat}"]
                for book in _BOOKS:
                    self._lines[(p["player_id"], stat, book)] = base

    # ── lifecycle ─────────────────────────────────────────────────
    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="demo_emitter")
        log.info("demo emitter started (tick=%.1fs)", self.tick_seconds)

    async def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    # ── main loop ─────────────────────────────────────────────────
    async def _run(self) -> None:
        while not self._stopped:
            try:
                await self._one_tick()
            except Exception as exc:  # noqa: BLE001
                log.warning("demo emitter tick failed: %s", exc)
            await asyncio.sleep(self.tick_seconds)

    async def _one_tick(self) -> None:
        # 1. advance clock by ~20-40 sec of game time
        elapsed = random.randint(20, 45)
        self._clock_s -= elapsed
        if self._clock_s <= 0:
            self._period += 1
            self._clock_s = 12 * 60
            await self.bus.publish(TOPIC_PBP_PERIOD_END, {
                "game_id": _GAME_ID,
                "period": self._period - 1,
                "clock": "PT00M00.00S",
                "description": f"End of Q{self._period - 1}",
                "ts": time.time(),
            })
            if self._period > 4:
                # Reset to a fresh game so the loop is forever-live.
                self._period = 1
                self._clock_s = 12 * 60
                self._home_score = 0
                self._away_score = 0
                for stats in self._player_stats.values():
                    for k in stats:
                        stats[k] = 0.0

        # 2. simulate per-player events for the tick
        for p in _PLAYERS:
            stats = self._player_stats[p["player_id"]]
            stats["min"] += elapsed / 60.0
            event_roll = random.random()
            if event_roll < 0.45:
                pts_made = random.choice([2, 2, 2, 3])
                stats["pts"] += pts_made
                if p["team"] == "DEN" or p["team"] == "PHI":
                    self._home_score += pts_made
                else:
                    self._away_score += pts_made
                await self.bus.publish(TOPIC_PBP_MADE_SHOT, {
                    "game_id": _GAME_ID, "player_id": p["player_id"],
                    "player_name": p["name"], "team_tricode": p["team"],
                    "period": self._period, "clock": self._format_clock(),
                    "description": f"{p['name'].split()[-1]} {pts_made}PT made",
                    "score_home": self._home_score,
                    "score_away": self._away_score,
                    "action_number": int(time.time() * 1000) % 10_000_000,
                    "ts": time.time(),
                })
            elif event_roll < 0.55:
                stats["reb"] += 1
            elif event_roll < 0.65:
                stats["ast"] += 1
            elif event_roll < 0.75:
                stats["pf"] += 1
                await self.bus.publish(TOPIC_PBP_FOUL, {
                    "game_id": _GAME_ID, "player_id": p["player_id"],
                    "player_name": p["name"], "team_tricode": p["team"],
                    "period": self._period, "clock": self._format_clock(),
                    "description": f"P.FOUL — {p['name'].split()[-1]}",
                    "action_number": int(time.time() * 1000) % 10_000_000,
                    "ts": time.time(),
                })
            elif event_roll < 0.78:
                stats["tov"] += 1
                await self.bus.publish(TOPIC_PBP_TURNOVER, {
                    "game_id": _GAME_ID, "player_id": p["player_id"],
                    "player_name": p["name"], "team_tricode": p["team"],
                    "period": self._period, "clock": self._format_clock(),
                    "description": f"TURNOVER — {p['name'].split()[-1]}",
                    "action_number": int(time.time() * 1000) % 10_000_000,
                    "ts": time.time(),
                })

        # 3. broadcast a fresh snapshot
        snap = self._build_snapshot()
        await self.bus.publish(TOPIC_SNAPSHOT_UPDATED, {
            "game_id": _GAME_ID, "snapshot": snap,
        })

        # 4. derive projections (simple pace extrapolation)
        rows = self._build_projection_rows(snap)
        await self.bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": _GAME_ID, "rows": rows, "source": "demo",
        })

        # 5. drift lines + emit lines.refreshed once per tick
        for k in list(self._lines.keys()):
            self._lines[k] = max(0.5, self._lines[k] + random.choice(
                [-0.5, 0, 0, 0, 0.5]))
        await self.bus.publish(TOPIC_LINES_REFRESHED, {
            "date": time.strftime("%Y-%m-%d"),
            "counts": {b: len(_PLAYERS) * 3 for b in _BOOKS},
        })

        # 6. compute + emit top bets directly (skip the disk-line lookup
        #    in the real DecisionEngine — demo lines live in memory).
        for bet in self._build_top_bets(rows):
            await self.bus.publish(TOPIC_BET_RECOMMENDED, bet)

    # ── helpers ───────────────────────────────────────────────────
    def _format_clock(self) -> str:
        m = self._clock_s // 60
        s = self._clock_s % 60
        return f"PT{m:02d}M{s:02d}.00S"

    def _build_snapshot(self) -> Dict[str, Any]:
        players = []
        for p in _PLAYERS:
            s = self._player_stats[p["player_id"]]
            players.append({
                "player_id": p["player_id"], "name": p["name"],
                "team": p["team"],
                "pts": int(s["pts"]), "reb": int(s["reb"]),
                "ast": int(s["ast"]), "pf": int(s["pf"]),
                "stl": int(s["stl"]), "blk": int(s["blk"]),
                "tov": int(s["tov"]),
                "min": round(s["min"], 1),
            })
        return {
            "game_id": _GAME_ID, "game_status": "LIVE",
            "home_team": "DEN", "away_team": "DAL",
            "home_score": self._home_score, "away_score": self._away_score,
            "period": self._period, "clock": self._format_clock(),
            "players": players,
        }

    def _build_projection_rows(self, snap: Dict[str, Any]) -> list:
        """Pace-extrapolate each player's stats to a 36-min projection."""
        rows = []
        regulation_min = 48.0
        period_elapsed = (4 - self._period) * 12 + (12 - self._clock_s / 60.0)
        game_progress = max(0.05, min(1.0, period_elapsed / regulation_min))
        for p in snap["players"]:
            for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
                cur = p.get(stat, 0) or 0
                pace = cur / game_progress if game_progress > 0 else cur
                # Add a small projection_source tag so the explain panel has
                # signal to surface.
                src = "demo_pace"
                if stat in ("pts", "ast", "fg3m") and (p.get("pf") or 0) >= 4:
                    src = "demo_pace+foul_residual"
                if stat == "pts" and pace > p.get("pts", 0) * 2.0:
                    src = "demo_pace+heat_check"
                rows.append({
                    "player_id": p["player_id"], "name": p["name"],
                    "team": p["team"], "stat": stat,
                    "current": cur, "projected_final": round(pace, 1),
                    "delta": 0.0,
                    "projection_source": src,
                    "foul_factor": 0.92 if (p.get("pf") or 0) >= 4 else 1.0,
                    "blow_factor": 1.0,
                    "heat_check_shrinkage": 0.85 if pace > cur * 2.0 else 1.0,
                    "matchup_reason": "matchup_applied:demo vs demo",
                })
        return rows

    def _build_top_bets(self, rows: list) -> list:
        bets = []
        for p in _PLAYERS:
            for stat in ("pts", "reb", "ast"):
                row = next((r for r in rows
                            if r["player_id"] == p["player_id"]
                            and r["stat"] == stat), None)
                if row is None:
                    continue
                book = random.choice(_BOOKS)
                line = self._lines[(p["player_id"], stat, book)]
                proj = float(row["projected_final"])
                # Decide side based on whether proj > line.
                side = "over" if proj > line else "under"
                # Simple normal-CDF approximation for hit prob.
                sigma = {"pts": 5.0, "reb": 2.2, "ast": 1.6}[stat]
                z = (proj - line) / sigma
                # cheap erf
                p_over = 0.5 * (1.0 + _erf(z / 1.41421356))
                p_hit = p_over if side == "over" else (1.0 - p_over)
                odds = -110
                payout = 100 / 110
                ev = p_hit * payout - (1.0 - p_hit)
                if ev < 0.01:
                    continue
                tier = ("S" if ev >= 0.08 else
                        "A" if ev >= 0.04 else "B")
                bets.append({
                    "game_id": _GAME_ID, "player_id": p["player_id"],
                    "name": p["name"], "team": p["team"],
                    "stat": stat, "side": side, "line": line,
                    "book": book, "odds": odds, "ev": ev,
                    "kelly": min(0.25, max(0.0, ev / payout)),
                    "tier": tier, "projected_final": proj,
                    "current": row["current"], "delta": 0.0,
                    "why": (f"{tier}: {p['name']} {stat.upper()} "
                            f"{side.upper()} {line} @ {book} {odds} | "
                            f"proj {proj:.1f} (p={p_hit*100:.1f}%, "
                            f"EV={ev*100:+.1f}%)"),
                    "reason": "demo",
                })
        return bets


def _erf(x: float) -> float:
    import math
    return math.erf(x)
