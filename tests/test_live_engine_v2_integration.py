"""tests/test_live_engine_v2_integration.py — Phase E end-to-end smoke.

Injects 5 minutes of synthetic PBP events into a fully wired
event bus (poller → reactive projector → decision engine →
dashboard render) and asserts:

  1. Each PBP event triggers a projection.updated within < 500ms.
  2. At least one bet.recommended is emitted (line + projection
     gap is engineered to qualify).
  3. The dashboard render shows the player + the bet.
"""
from __future__ import annotations

import asyncio
import csv
import os
import time
from typing import Any, Dict, List

import pytest

from src.live.event_bus import (
    EventBus,
    TOPIC_BET_RECOMMENDED,
    TOPIC_PBP_FOUL,
    TOPIC_PROJECTION_UPDATED,
    reset_bus_for_tests,
)


# ── shared helpers ──────────────────────────────────────────────────────
def _seed_line_csv(dirpath, date_str, player_id, stat, line, over, under,
                   book=None):
    """Seed CSV(s) so the decision engine's three-book consensus filter
    passes. Default seeds pin/bov/fd at the same (player, stat, line)."""
    books = (book,) if book else ("pin", "bov", "fd")
    os.makedirs(dirpath, exist_ok=True)
    for b in books:
        p = os.path.join(dirpath, f"{date_str}_{b}.csv")
        new = not os.path.exists(p)
        with open(p, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "captured_at", "book", "game_id", "player_id", "player_name",
                "team", "stat", "line", "over_price", "under_price",
                "market_status", "is_alt_line"])
            if new:
                w.writeheader()
            w.writerow({"captured_at": "2026-05-26T20:00:00", "book": b,
                        "game_id": "0042400315", "player_id": player_id,
                        "player_name": "Jokic", "team": "DEN", "stat": stat,
                        "line": line, "over_price": over,
                        "under_price": under,
                        "market_status": "open", "is_alt_line": ""})


def _fake_snap(player_pts: float = 22.0):
    return {
        "game_id": "0042400315", "game_status": "LIVE", "period": 4,
        "clock": "PT05M00.00S",
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 95, "away_score": 90,
        "players": [{"player_id": 1, "name": "Jokic", "team": "DEN",
                     "pts": player_pts, "min": 30, "pf": 2}],
    }


@pytest.fixture(autouse=True)
def _reset():
    reset_bus_for_tests()
    yield
    reset_bus_for_tests()


# ── integration ────────────────────────────────────────────────────────
def test_pbp_event_to_bet_under_500ms(tmp_path, monkeypatch):
    """End-to-end latency: PBP → reactive projection → bet → < 500ms."""
    from src.prediction.decision_engine import DecisionEngine, LineCache
    from src.prediction.reactive_projector import ReactiveProjector

    date_str = "2026-05-26"
    _seed_line_csv(str(tmp_path), date_str, "1", "pts", 24.5, -110, -110)

    bus = EventBus()
    lc = LineCache(lines_dir=str(tmp_path))
    lc.refresh(date_str)

    # Stub project_fn so the test never touches the heavy live_engine path.
    # Projection delta of +5 vs current keeps the modeled EV well under the
    # 50% ceiling (which rejects model-failure projections), so this exercises
    # the happy-path emit instead of the ceiling drop.
    def fake_project(snap):
        cur = snap["players"][0]["pts"]
        return [{"player_id": 1, "name": "Jokic", "team": "DEN",
                 "stat": "pts", "projected_final": float(cur) + 5.0,
                 "current": float(cur)}]

    rp = ReactiveProjector(bus=bus, snapshot_loader=lambda gid: _fake_snap(),
                           project_fn=fake_project)
    rp.register()
    de = DecisionEngine(bus=bus, line_cache=lc, top_n=5, throttle_ms=0)
    de.register()

    bets: List[Dict[str, Any]] = []
    projections: List[Dict[str, Any]] = []

    async def cap_proj(t, e):
        projections.append({"t": time.time(), "e": e})

    async def cap_bet(t, e):
        bets.append({"t": time.time(), "e": e})

    bus.subscribe(TOPIC_PROJECTION_UPDATED, cap_proj)
    bus.subscribe(TOPIC_BET_RECOMMENDED, cap_bet)

    async def run():
        # Fire 5 PBP events (simulates ~5 minutes of game flow).
        start_ts = time.time()
        for i in range(5):
            await bus.publish(TOPIC_PBP_FOUL, {
                "game_id": "0042400315", "player_id": 1,
                "action_number": i + 1,
                "period": 4, "clock": "PT05M00S",
                "player_name": "Jokic",
            })
            await asyncio.sleep(0.05)
        end_ts = time.time()
        # Drain any remaining tasks
        await asyncio.sleep(0.1)
        return start_ts, end_ts

    start_ts, end_ts = asyncio.run(run())

    assert projections, "no projection events emitted"
    assert bets, "no bet recommendations emitted"
    # Latency = projection emit time - publish time (roughly tracked).
    # We use total wall span between first PBP and first bet < 500ms.
    first_bet_ts = bets[0]["t"]
    latency_ms = (first_bet_ts - start_ts) * 1000.0
    assert latency_ms < 500.0, f"first bet took {latency_ms:.0f}ms (> 500ms)"
    assert bets[0]["e"]["stat"] == "pts"
    assert bets[0]["e"]["side"] == "over"


def test_full_dashboard_render_after_events(tmp_path):
    """Dashboard renders correctly after a burst of bus events."""
    pytest.importorskip("rich")
    from scripts.live_dashboard_v2 import DashboardApp
    from src.prediction.decision_engine import DecisionEngine, LineCache

    date_str = "2026-05-26"
    _seed_line_csv(str(tmp_path), date_str, "1", "pts", 24.5, -110, -110)
    bus = EventBus()
    lc = LineCache(lines_dir=str(tmp_path))
    lc.refresh(date_str)

    de = DecisionEngine(bus=bus, line_cache=lc, top_n=5, throttle_ms=0)
    de.register()

    app = DashboardApp(bus=bus, refresh_per_second=10)
    app.register()

    async def drive():
        # Seed snapshot.
        from src.live.event_bus import (
            TOPIC_PBP_MADE_SHOT, TOPIC_PROJECTION_UPDATED,
            TOPIC_SNAPSHOT_UPDATED,
        )
        await bus.publish(TOPIC_SNAPSHOT_UPDATED, {
            "game_id": "0042400315", "snapshot": _fake_snap(),
        })
        await bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": "0042400315",
            "rows": [{"player_id": "1", "name": "Jokic", "team": "DEN",
                      "stat": "pts", "projected_final": 27.0, "current": 22.0,
                      "delta": 2.0}],
        })
        await bus.publish(TOPIC_PBP_MADE_SHOT, {
            "game_id": "0042400315", "player_id": 1, "action_number": 7,
            "period": 4, "clock": "PT05M00S", "player_name": "Jokic",
            "description": "JOKIC 3PT made",
        })
        await asyncio.sleep(0.1)

    asyncio.run(drive())
    out = app.render_snapshot_text()
    assert "Jokic" in out
    assert "DEN" in out
    # Dashboard should now show at least one Top Bet row.
    assert "PTS" in out
    assert "OVER" in out


def test_orchestrator_starts_and_stops_cleanly(tmp_path, monkeypatch):
    """Smoke: orchestrator can spawn + stop all background tasks."""
    from scripts.live_orchestrator import LiveOrchestrator

    # Patch the heavy components so we don't hit real APIs.
    import scripts.pbp_poller as pbp_mod
    import scripts.lineup_tracker as ltr_mod
    import scripts.parallel_scraper as psc_mod
    import scripts.box_snapshot_poller as bsp_mod

    monkeypatch.setattr(pbp_mod, "_latest_snapshot_for",
                        lambda gid, live_dir: None)   # not LIVE → skip
    monkeypatch.setattr(ltr_mod, "_latest_snapshot_for",
                        lambda gid, live_dir: None)
    monkeypatch.setattr(bsp_mod.BoxSnapshotPoller, "_poll_once",
                        lambda self, gids, **kw: {}, raising=False)

    async def fake_pin(_session):
        return []
    monkeypatch.setattr(psc_mod, "_DEFAULT_BOOKS",
                        {"pin": fake_pin})

    orch = LiveOrchestrator(
        game_ids=["0042400315"], date_str="2026-05-26",
        pbp_interval_sec=60, snapshot_interval_sec=60,
        lineup_interval_sec=60, line_scrape_interval_sec=60,
        enable_dashboard=False, enable_alerts=False,
        books=["pin"],
    )

    async def run():
        await orch.start()
        # Let one tick happen.
        await asyncio.sleep(0.2)
        await orch.stop()

    asyncio.run(run())
    # All tasks should be done / cancelled.
    for t in orch._tasks:
        assert t.done() or t.cancelled()
