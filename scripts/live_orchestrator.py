"""live_orchestrator.py — entry point for Live Engine v2.

Spins up every component in one asyncio loop:

    pbp_poller          — emits pbp.* events every --pbp-interval
    lineup_tracker      — emits lineup.defender_changed every
                          --lineup-interval
    parallel_scraper    — emits lines.refreshed every
                          --line-scrape-interval
    box_snapshot_poller — emits snapshot.updated + projection.updated
                          every --snapshot-interval
    reactive_projector  — listens to pbp.* + lineup events, emits
                          projection.updated synchronously
    decision_engine     — listens to projection.updated + lines.refreshed,
                          emits bet.recommended
    alert_dedup         — wraps every bet.recommended; emits dedup'd
                          alerts via the existing webhook notifier
    dashboard           — rich TUI (optional, flag-gated)

CLI
---
    python scripts/live_orchestrator.py --game-id 0042500315
    python scripts/live_orchestrator.py --game-id 0042500315 --enable-dashboard
    python scripts/live_orchestrator.py --game-id 0042500315 --headless

Graceful shutdown on SIGINT (Ctrl-C).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.alert_dedup import AlertDedup  # noqa: E402
from src.live.event_bus import (  # noqa: E402
    TOPIC_BET_RECOMMENDED, TOPIC_PREGAME_INFO, TOPIC_SNAPSHOT_UPDATED,
    get_bus, reset_bus_for_tests,
)
from src.live.time_utils import slate_date  # noqa: E402
from src.prediction.decision_engine import DecisionEngine  # noqa: E402
from src.prediction.reactive_projector import ReactiveProjector  # noqa: E402

log = logging.getLogger("live_orchestrator")

HEARTBEAT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "daemon_heartbeats",
    "live_orchestrator.txt")


class LiveOrchestrator:
    """One-class wiring of all Live Engine v2 components.

    Each component is constructed lazily so unit tests can swap in
    mocks via ``components_for_test`` without spinning up real pollers.
    """

    def __init__(self, *,
                 game_ids: List[str],
                 date_str: Optional[str] = None,
                 pbp_interval_sec: float = 10.0,
                 snapshot_interval_sec: float = 30.0,
                 lineup_interval_sec: float = 30.0,
                 line_scrape_interval_sec: float = 30.0,
                 enable_dashboard: bool = False,
                 enable_alerts: bool = True,
                 books: Optional[List[str]] = None,
                 demo_mode: bool = False) -> None:
        self.game_ids = game_ids
        self.date_str = date_str or slate_date().isoformat()
        self.pbp_interval_sec = pbp_interval_sec
        self.snapshot_interval_sec = snapshot_interval_sec
        self.lineup_interval_sec = lineup_interval_sec
        self.line_scrape_interval_sec = line_scrape_interval_sec
        self.enable_dashboard = enable_dashboard
        self.enable_alerts = enable_alerts
        # dk_inplay and fd_inplay are intentionally excluded from this default list.
        # scripts/courtvision_tonight.ps1 launches standalone in-play scrapers that
        # are the single authoritative writers of <date>_{dk,fd}_inplay.csv.
        # Having the orchestrator also write those files would create a dual-writer
        # race (no lock) producing duplicate / ragged rows in the in-play line
        # history.  Single-owner rule: one process writes one file.
        self.books = books or [
            "pin", "bov", "fd", "dk", "betrivers", "pointsbet", "pp",
            "oddsapi",
        ]
        self.demo_mode = demo_mode

        self.bus = get_bus()
        self.alert_dedup: Optional[AlertDedup] = None
        self.projector: Optional[ReactiveProjector] = None
        self.decision: Optional[DecisionEngine] = None
        self.dashboard = None
        self._tasks: List[asyncio.Task] = []
        self._stopped = False

    # ── wiring ───────────────────────────────────────────────────────
    async def start(self) -> None:
        log.info("starting Live Engine v2 for games %s (demo=%s)",
                 self.game_ids, self.demo_mode)

        # Phase C — reactive wiring
        self.projector = ReactiveProjector(bus=self.bus)
        self.projector.register()
        # In demo mode the synthetic emitter already emits bet.recommended
        # rows directly, so skip the disk-line decision engine to avoid
        # double counting + empty-CSV gates.
        if not self.demo_mode:
            self.decision = DecisionEngine(bus=self.bus, top_n=5,
                                            throttle_ms=250)
            self.decision.register()

        # Phase D — alert dedup wiring
        if self.enable_alerts:
            self.alert_dedup = AlertDedup(
                cooldown_sec=300.0, delta_floor=0.3,
                digest_window_sec=60.0, min_severity="medium",
            )
            self.bus.subscribe(TOPIC_BET_RECOMMENDED, self._on_bet_for_alerts)

        if self.demo_mode:
            # Demo path — single synthetic emitter, no NBA / book scraping.
            from src.live.demo_emitter import DemoEmitter
            emitter = DemoEmitter(bus=self.bus, tick_seconds=4.0)
            await emitter.start()
            # Keep a handle so stop() can cancel it.
            self._tasks.append(emitter._task)  # type: ignore[arg-type]
        else:
            # Phase B — real pollers
            from scripts.box_snapshot_poller import BoxSnapshotPoller
            from scripts.lineup_tracker import LineupTracker
            from scripts.parallel_scraper import ParallelScraper
            from scripts.pbp_poller import PBPPoller

            pbp = PBPPoller(self.game_ids, bus=self.bus,
                            interval_sec=self.pbp_interval_sec)
            lineup = LineupTracker(self.game_ids, bus=self.bus,
                                   interval_sec=self.lineup_interval_sec)
            scraper = ParallelScraper(books=self.books, bus=self.bus,
                                      interval_sec=self.line_scrape_interval_sec)
            box = BoxSnapshotPoller(self.game_ids, bus=self.bus,
                                    interval_sec=self.snapshot_interval_sec,
                                    date_str=self.date_str)

            self._tasks.append(asyncio.create_task(pbp.run_forever(),
                                                   name="pbp_poller"))
            self._tasks.append(asyncio.create_task(lineup.run_forever(),
                                                   name="lineup_tracker"))
            self._tasks.append(asyncio.create_task(scraper.run_forever(),
                                                   name="parallel_scraper"))
            self._tasks.append(asyncio.create_task(box.run_forever(),
                                                   name="box_snapshot_poller"))

        # Digest flusher (one-second cadence).
        self._tasks.append(asyncio.create_task(self._digest_flusher(),
                                               name="alert_digest_flusher"))
        # Heartbeat writer for the daemon watchdog.
        self._tasks.append(asyncio.create_task(self._heartbeat_loop(),
                                               name="heartbeat"))
        # Pregame info loop — runs in real mode (not demo) so the dashboard
        # has matchup + tipoff info before the boxscore CDN starts serving.
        if not self.demo_mode and self.game_ids and self.game_ids[0] != "DEMO":
            self._tasks.append(asyncio.create_task(
                self._pregame_info_loop(), name="pregame_info"))

        # Phase D — dashboard last so it shows everything once it boots.
        if self.enable_dashboard:
            from scripts.live_dashboard_v2 import DashboardApp
            self.dashboard = DashboardApp(bus=self.bus, refresh_per_second=4)
            self.dashboard.register()
            self._tasks.append(asyncio.create_task(
                self.dashboard.run(), name="dashboard"))

        log.info("Live Engine v2 spawned %d background tasks",
                 len(self._tasks))

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        log.info("Live Engine v2 stop requested")
        if self.alert_dedup is not None:
            try:
                for sev, body in self.alert_dedup.flush_all():
                    log.info("[final-digest %s] %s", sev, body)
            except Exception:  # noqa: BLE001
                pass
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        log.info("Live Engine v2 stopped")

    async def wait_forever(self) -> None:
        try:
            while not self._stopped:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    # ── helpers ──────────────────────────────────────────────────────
    async def _on_bet_for_alerts(self, topic: str, event: Dict[str, Any]) -> None:
        if self.alert_dedup is None:
            return
        try:
            action, payload, severity = self.alert_dedup.maybe_alert(
                player=str(event.get("name") or event.get("player_id") or "?"),
                stat=str(event.get("stat") or ""),
                side=str(event.get("side") or ""),
                line=float(event.get("line") or 0),
                book=str(event.get("book") or ""),
                odds=int(event.get("odds") or 0),
                projection_old=None,
                projection_new=float(event.get("projected_final") or 0.0),
                ev_new=float(event.get("ev") or 0.0),
                severity=self._severity_for(event.get("tier")),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("alert_dedup raised: %s", exc)
            return
        if action == "emit" and self.dashboard is not None:
            try:
                self.dashboard.state.on_alert(severity or "medium", payload)
            except Exception:  # noqa: BLE001
                pass
        if action == "emit":
            self._dispatch_webhook(severity or "medium", payload, event)

    @staticmethod
    def _severity_for(tier: Optional[str]) -> str:
        return {"S": "high", "A": "medium", "B": "low"}.get(tier or "", "low")

    @staticmethod
    def _dispatch_webhook(severity: str, payload: str,
                          event: Dict[str, Any]) -> None:
        try:
            from src.notifications.webhook_alerts import WebhookNotifier
            notifier = WebhookNotifier(min_severity="medium")
            notifier.send("LIVE_BET", payload, severity=severity,
                          tags={"player": event.get("name"),
                                "stat": event.get("stat"),
                                "side": event.get("side")})
        except Exception as exc:  # noqa: BLE001
            log.warning("webhook dispatch failed: %s", exc)

    async def _digest_flusher(self) -> None:
        while not self._stopped:
            if self.alert_dedup is not None:
                try:
                    for sev, body in self.alert_dedup.pending_digests():
                        self._dispatch_webhook(sev, body,
                                               {"name": "digest"})
                        if self.dashboard is not None:
                            self.dashboard.state.on_alert(sev, body)
                except Exception as exc:  # noqa: BLE001
                    log.warning("digest flush failed: %s", exc)
            await asyncio.sleep(1.0)

    async def _heartbeat_loop(self) -> None:
        while not self._stopped:
            try:
                os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
                with open(HEARTBEAT_PATH, "w", encoding="utf-8") as fh:
                    fh.write(str(int(time.time())))
            except OSError:
                pass
            await asyncio.sleep(10.0)

    async def _pregame_info_loop(self) -> None:
        """Periodically probe cdn.nba.com for matchup + tipoff info.

        Broadcasts a ``pregame.info`` event each time so the dashboard
        can render the pregame card BEFORE the boxscore CDN begins
        publishing (which happens at tipoff). Backs off to 5 min once
        the game flips to LIVE / FINAL since the snapshot stream
        provides better data after that point.
        """
        from src.live.pregame_probe import probe_game
        # Tight cadence pre-tipoff so the countdown is fresh; relax to
        # 5 min once the live snapshot poller is in charge.
        tight = 30.0
        loose = 300.0
        loop = asyncio.get_event_loop()
        while not self._stopped:
            any_live = False
            for gid in self.game_ids:
                try:
                    payload = await loop.run_in_executor(None, probe_game, gid)
                except Exception as exc:  # noqa: BLE001
                    log.warning("pregame probe failed for %s: %s", gid, exc)
                    payload = None
                if payload:
                    await self.bus.publish(TOPIC_PREGAME_INFO, payload)
                status = (payload or {}).get("game_status_text") or ""
                if status.lower() in ("live", "halftime", "end of period"):
                    any_live = True
            await asyncio.sleep(loose if any_live else tight)


# ── CLI ─────────────────────────────────────────────────────────────────
def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game-id", required=True,
                    help="NBA game ID (e.g. 0042500315). Comma-separate for multi.")
    ap.add_argument("--date", default=None,
                    help="Slate date YYYY-MM-DD; default: today.")
    ap.add_argument("--pbp-interval", type=float, default=10.0)
    ap.add_argument("--snapshot-interval", type=float, default=30.0)
    ap.add_argument("--lineup-interval", type=float, default=30.0)
    ap.add_argument("--line-scrape-interval", type=float, default=30.0)
    # dk_inplay/fd_inplay omitted: courtvision_tonight.ps1 owns those files (single-writer rule).
    ap.add_argument("--books",
                    default="pin,bov,fd,dk,betrivers,pointsbet,pp,oddsapi")
    ap.add_argument("--enable-dashboard", action="store_true")
    ap.add_argument("--headless", action="store_true",
                    help="Disable dashboard explicitly (overrides --enable-dashboard).")
    ap.add_argument("--no-alerts", action="store_true")
    ap.add_argument("--demo-mode", action="store_true",
                    help="Inject a synthetic game via demo_emitter; no real "
                         "NBA / book scraping. Useful for offseason demos.")
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    game_ids = [g.strip() for g in args.game_id.split(",") if g.strip()]
    orch = LiveOrchestrator(
        game_ids=game_ids,
        date_str=args.date,
        pbp_interval_sec=args.pbp_interval,
        snapshot_interval_sec=args.snapshot_interval,
        lineup_interval_sec=args.lineup_interval,
        line_scrape_interval_sec=args.line_scrape_interval,
        enable_dashboard=(args.enable_dashboard and not args.headless),
        enable_alerts=not args.no_alerts,
        books=[b.strip() for b in args.books.split(",") if b.strip()],
        demo_mode=args.demo_mode,
    )
    await orch.start()

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _handle_signal():
        stop_event.set()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                pass
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await orch.stop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
