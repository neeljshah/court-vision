"""live_dashboard_v2.py — rich-powered terminal UI for Live Engine v2.

Full-screen, event-driven dashboard. Subscribes to the event bus
and re-renders on every bus event (no polling).

Distinct from the legacy `scripts/live_dashboard.py` which is a
one-shot snapshot pretty-printer; this is the always-on TUI.

Panes
-----
HEADER  game card: teams, score, period, clock, momentum arrow
LEFT    on-court lineups for both teams + star foul counts
CENTER  top 5 live bets (tier badge + sparkline of EV last 5min)
RIGHT   last 10 PBP events with timestamps
BOTTOM  alerts feed (last 5) + daemon health strip

Colour conventions
------------------
green   upside (positive EV, projection ticking up)
red     downside (negative EV, projection ticking down)
gold    S-tier bets
cyan    PBP timestamps
dim     idle / non-LIVE games
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.event_bus import (  # noqa: E402
    TOPIC_BET_RECOMMENDED, TOPIC_LINES_REFRESHED,
    TOPIC_PROJECTION_UPDATED, TOPIC_SNAPSHOT_UPDATED, EventBus, get_bus,
)

log = logging.getLogger("live_dashboard_v2")

# Sparkline glyphs ordered low → high.
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: List[float], width: int = 12) -> str:
    if not values:
        return " " * width
    vs = values[-width:]
    if len(vs) < width:
        vs = [vs[0]] * (width - len(vs)) + vs
    lo = min(vs)
    hi = max(vs)
    rng = hi - lo
    if rng < 1e-9:
        return _SPARK_CHARS[len(_SPARK_CHARS) // 2] * width
    out = ""
    for v in vs:
        idx = int(round((v - lo) / rng * (len(_SPARK_CHARS) - 1)))
        out += _SPARK_CHARS[idx]
    return out


class DashboardState:
    """Aggregates events into render-ready data structures."""

    def __init__(self) -> None:
        self.snapshots: Dict[str, Dict[str, Any]] = {}
        self.ev_history: Dict[Tuple[Any, str, str], Deque[Tuple[float, float]]] = {}
        self.top_bets: Dict[str, List[Dict[str, Any]]] = {}
        self.pbp_events: Deque[Dict[str, Any]] = deque(maxlen=10)
        self.alerts: Deque[Dict[str, Any]] = deque(maxlen=5)
        self.daemon_health: Dict[str, float] = {}
        self.renders: int = 0
        self.started_at = time.time()
        self.active_game_id: Optional[str] = None

    def on_snapshot(self, event: Dict[str, Any]) -> None:
        gid = event.get("game_id")
        snap = event.get("snapshot")
        if not gid or not snap:
            return
        self.snapshots[gid] = snap
        self.active_game_id = gid
        self.daemon_health["box_snapshot_poller"] = time.time()

    def on_pbp(self, topic: str, event: Dict[str, Any]) -> None:
        self.pbp_events.append({
            "ts": time.time(), "topic": topic,
            "period": event.get("period"), "clock": event.get("clock"),
            "description": event.get("description") or topic.replace("pbp.", ""),
            "player": event.get("player_name"),
            "score_home": event.get("score_home"),
            "score_away": event.get("score_away"),
        })
        self.daemon_health["pbp_poller"] = time.time()

    def on_projection(self, event: Dict[str, Any]) -> None:
        self.daemon_health["reactive_projector"] = time.time()

    def on_bet(self, event: Dict[str, Any]) -> None:
        gid = event.get("game_id")
        if not gid:
            return
        key = (event.get("player_id"), event.get("stat"), event.get("side"))
        hist = self.ev_history.setdefault(key, deque(maxlen=24))
        hist.append((time.time(), float(event.get("ev") or 0.0)))
        bets = self.top_bets.setdefault(gid, [])
        replaced = False
        for i, b in enumerate(bets):
            if (b.get("player_id"), b.get("stat"), b.get("side")) == key:
                bets[i] = event
                replaced = True
                break
        if not replaced:
            bets.append(event)
        bets.sort(key=lambda b: b.get("ev") or 0.0, reverse=True)
        self.top_bets[gid] = bets[:8]
        self.daemon_health["decision_engine"] = time.time()

    def on_lines(self, event: Dict[str, Any]) -> None:
        self.daemon_health["parallel_scraper"] = time.time()

    def on_alert(self, severity: str, msg: str) -> None:
        self.alerts.append({"ts": time.time(), "severity": severity, "msg": msg})


def _render_header(state: DashboardState):
    from rich.panel import Panel
    from rich.text import Text

    gid = state.active_game_id
    snap = state.snapshots.get(gid) if gid else None
    if not snap:
        return Panel(Text("Waiting for first snapshot…", style="dim"),
                     title="Game", border_style="dim")
    home = snap.get("home_team", "HOME")
    away = snap.get("away_team", "AWAY")
    hs = snap.get("home_score", 0) or 0
    as_ = snap.get("away_score", 0) or 0
    period = snap.get("period", "-")
    clock = snap.get("clock", "")
    status = snap.get("game_status", "")
    margin = hs - as_
    arrow = "▲" if margin > 0 else ("▼" if margin < 0 else "▬")
    arrow_style = "green" if margin > 0 else ("red" if margin < 0 else "white")
    body = Text()
    body.append(f"{away} {as_}  @  {home} {hs}  ", style="bold")
    body.append(f"{arrow} {abs(margin):+d}\n", style=arrow_style)
    body.append(f"Q{period}  {clock}  ", style="cyan")
    body.append(f"[{status}]", style="dim")
    return Panel(body, title=f"Game {gid}", border_style="blue")


def _render_lineups(state: DashboardState):
    from rich.panel import Panel
    from rich.table import Table

    gid = state.active_game_id
    snap = state.snapshots.get(gid) if gid else None
    if not snap or not snap.get("players"):
        return Panel("No lineup data yet", title="Lineups", border_style="dim")
    table = Table(show_header=True, header_style="bold magenta",
                  box=None, expand=True, pad_edge=False, padding=(0, 0))
    table.add_column("Player", overflow="fold")
    table.add_column("M", justify="right", width=3)
    table.add_column("P", justify="right", width=3)
    table.add_column("F", justify="right", width=2)
    on_court = [p for p in snap["players"] if (p.get("min") or 0) > 0]
    on_court.sort(key=lambda p: -(p.get("pts") or 0))
    for p in on_court[:10]:
        pf = int(p.get("pf") or 0)
        pf_style = "red" if pf >= 4 else ("yellow" if pf >= 3 else "white")
        # Use short name (first initial + last) so it always fits.
        name = (p.get("name") or "?").split()
        short = (f"{name[0][0]}. {name[-1]}" if len(name) > 1
                 else (name[0] if name else "?"))
        table.add_row(
            f"{short} ({p.get('team') or ''})",
            f"{int(p.get('min') or 0)}",
            f"{int(p.get('pts') or 0)}",
            f"[{pf_style}]{pf}[/{pf_style}]",
        )
    return Panel(table, title="On Court", border_style="cyan")


def _render_top_bets(state: DashboardState):
    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=True, header_style="bold magenta",
                  box=None, expand=True)
    table.add_column("Tier", width=4)
    table.add_column("Bet", overflow="ellipsis")
    table.add_column("EV", justify="right", width=7)
    table.add_column("K", justify="right", width=5)
    table.add_column("Spark", width=14)

    all_bets: List[Dict[str, Any]] = []
    for bets in state.top_bets.values():
        all_bets.extend(bets)
    all_bets.sort(key=lambda b: -(b.get("ev") or 0))
    if not all_bets:
        return Panel("No qualifying bets yet", title="Top Bets",
                     border_style="dim")

    for bet in all_bets[:5]:
        tier = bet.get("tier", "C")
        tier_colour = {"S": "gold1", "A": "green", "B": "white",
                       "C": "dim"}.get(tier, "white")
        ev = bet.get("ev") or 0.0
        ev_style = "green" if ev >= 0.05 else ("yellow" if ev >= 0.02 else "white")
        key = (bet.get("player_id"), bet.get("stat"), bet.get("side"))
        hist = list(state.ev_history.get(key, deque()))
        evs = [v for _, v in hist]
        spark = _sparkline(evs, width=12)
        label = (f"{bet.get('name', '?')} "
                 f"{(bet.get('stat') or '').upper()} "
                 f"{(bet.get('side') or '').upper()} {bet.get('line')} "
                 f"@ {bet.get('book')} {bet.get('odds'):+d}")
        table.add_row(
            f"[{tier_colour}]{tier}[/{tier_colour}]",
            label,
            f"[{ev_style}]{ev*100:+.1f}%[/{ev_style}]",
            f"{(bet.get('kelly') or 0)*100:.1f}%",
            spark,
        )
    return Panel(table, title="Top Bets (live)", border_style="green")


def _render_pbp(state: DashboardState):
    from rich.panel import Panel
    from rich.table import Table

    if not state.pbp_events:
        return Panel("Waiting for play-by-play…", title="PBP",
                     border_style="dim")
    table = Table(show_header=True, header_style="bold magenta",
                  box=None, expand=True)
    table.add_column("Time", width=10)
    table.add_column("Type", width=10)
    table.add_column("Detail")
    for ev in list(state.pbp_events)[-10:]:
        ts = datetime.fromtimestamp(ev["ts"]).strftime("%H:%M:%S")
        topic = ev["topic"].replace("pbp.", "")
        colour = {"made_shot": "green", "foul": "red",
                  "turnover": "yellow", "period_end": "cyan",
                  "sub": "white", "timeout": "blue"}.get(topic, "white")
        detail = ev.get("description") or ""
        if ev.get("player"):
            detail = f"{ev['player']} — {detail}"
        table.add_row(f"[cyan]{ts}[/cyan]",
                      f"[{colour}]{topic}[/{colour}]",
                      detail[:60])
    return Panel(table, title="Play-by-Play", border_style="cyan")


def _render_alerts_health(state: DashboardState):
    from rich.panel import Panel
    from rich.text import Text

    body = Text()
    if state.alerts:
        body.append("Recent alerts:\n", style="bold")
        for a in list(state.alerts):
            sev_colour = {"high": "red", "medium": "yellow",
                          "low": "white"}.get(a["severity"], "white")
            body.append(f"  ● {a['msg']}\n", style=sev_colour)
    else:
        body.append("No alerts yet.\n", style="dim")
    body.append("\nDaemons: ", style="bold")
    now = time.time()
    for name, last_ts in state.daemon_health.items():
        age = now - last_ts
        colour = "green" if age < 60 else ("yellow" if age < 180 else "red")
        body.append(f"{name}({int(age)}s) ", style=colour)
    body.append(f"   |   renders {state.renders}   uptime "
                f"{int(now - state.started_at)}s",
                style="dim")
    return Panel(body, title="Alerts + Health", border_style="magenta")


def build_layout(state: DashboardState):
    from rich.layout import Layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body"),
        Layout(name="footer", size=9),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="center", ratio=2),
        Layout(name="right", ratio=2),
    )
    layout["header"].update(_render_header(state))
    layout["left"].update(_render_lineups(state))
    layout["center"].update(_render_top_bets(state))
    layout["right"].update(_render_pbp(state))
    layout["footer"].update(_render_alerts_health(state))
    return layout


class DashboardApp:
    """Wires the event bus → state → rich Live render."""

    def __init__(self, *, bus: Optional[EventBus] = None,
                 refresh_per_second: int = 4) -> None:
        self.bus = bus or get_bus()
        self.refresh_per_second = refresh_per_second
        self.state = DashboardState()
        self._stopped = False

    def register(self) -> None:
        self.bus.subscribe(TOPIC_SNAPSHOT_UPDATED, self._snap_handler)
        self.bus.subscribe("pbp.*", self._pbp_handler)
        self.bus.subscribe(TOPIC_PROJECTION_UPDATED, self._proj_handler)
        self.bus.subscribe(TOPIC_BET_RECOMMENDED, self._bet_handler)
        self.bus.subscribe(TOPIC_LINES_REFRESHED, self._lines_handler)

    async def _snap_handler(self, topic, event):
        self.state.on_snapshot(event)

    async def _pbp_handler(self, topic, event):
        self.state.on_pbp(topic, event)

    async def _proj_handler(self, topic, event):
        self.state.on_projection(event)

    async def _bet_handler(self, topic, event):
        self.state.on_bet(event)

    async def _lines_handler(self, topic, event):
        self.state.on_lines(event)

    async def run(self) -> None:
        from rich.live import Live
        with Live(build_layout(self.state),
                  refresh_per_second=self.refresh_per_second,
                  screen=False) as live:
            while not self._stopped:
                live.update(build_layout(self.state))
                self.state.renders += 1
                await asyncio.sleep(1.0 / max(1, self.refresh_per_second))

    def stop(self) -> None:
        self._stopped = True

    def render_snapshot_text(self) -> str:
        """Plain-text render — used by tests + integration smoke."""
        from io import StringIO
        from rich.console import Console
        buf = StringIO()
        con = Console(file=buf, width=140, force_terminal=False, color_system=None)
        con.print(build_layout(self.state))
        return buf.getvalue()


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refresh-per-second", type=int, default=4)
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    app = DashboardApp(refresh_per_second=args.refresh_per_second)
    app.register()
    await app.run()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
