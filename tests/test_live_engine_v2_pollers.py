"""tests/test_live_engine_v2_pollers.py — Phase B regression set.

Mocks every external API call so the suite runs in <1s.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import List

import pytest

from src.live.event_bus import (
    EventBus,
    TOPIC_LINES_REFRESHED,
    TOPIC_LINEUP_DEFENDER_CHANGED,
    TOPIC_PBP_FOUL,
    TOPIC_PBP_MADE_SHOT,
    TOPIC_PROJECTION_UPDATED,
    TOPIC_SNAPSHOT_UPDATED,
)


# ── helpers ─────────────────────────────────────────────────────────────
def _write_live_snapshot(tmpdir, game_id: str, status: str = "LIVE"):
    snap = {
        "game_id": game_id, "game_status": status, "period": 4,
        "clock": "PT05M00.00S",
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 95, "away_score": 90,
        "players": [{"player_id": 1, "name": "X", "team": "DEN", "pts": 20,
                     "min": 28, "pf": 2}],
    }
    p = os.path.join(tmpdir, f"{game_id}_1234.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(snap, fh)
    return p


# ── pbp_poller ──────────────────────────────────────────────────────────
def test_pbp_poller_classifies_and_emits(tmp_path):
    from scripts.pbp_poller import PBPPoller
    gid = "0042400315"
    _write_live_snapshot(str(tmp_path), gid)

    plays = [
        {"actionNumber": 1, "actionType": "Foul", "period": 1, "clock": "PT11M00S",
         "description": "P.FOUL", "personId": 1},
        {"actionNumber": 2, "actionType": "Made Shot", "period": 1,
         "clock": "PT10M00S", "description": "3PT", "personId": 1},
        {"actionNumber": 3, "actionType": "Period", "subType": "end",
         "period": 1, "clock": "PT00M00S", "description": "End of Q1"},
    ]
    bus = EventBus()
    seen: List = []

    async def cap(t, e):
        seen.append((t, e["action_number"]))

    bus.subscribe("pbp.*", cap)
    poller = PBPPoller([gid], bus=bus, live_dir=str(tmp_path),
                       fetch_fn=lambda g: plays)

    async def run():
        await poller.poll_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    topics = [t for t, _ in seen]
    assert TOPIC_PBP_FOUL in topics
    assert TOPIC_PBP_MADE_SHOT in topics
    assert any("period_end" in t for t in topics)


def test_pbp_poller_skips_non_live_game(tmp_path):
    from scripts.pbp_poller import PBPPoller
    gid = "0042400315"
    _write_live_snapshot(str(tmp_path), gid, status="FINAL")
    bus = EventBus()
    seen = []

    async def cap(t, e):
        seen.append(t)

    bus.subscribe("pbp.*", cap)
    poller = PBPPoller([gid], bus=bus, live_dir=str(tmp_path),
                       fetch_fn=lambda g: [
                           {"actionNumber": 1, "actionType": "Foul"}])

    async def run():
        await poller.poll_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    assert seen == []


def test_pbp_poller_diffs_against_last_seen(tmp_path):
    from scripts.pbp_poller import PBPPoller
    gid = "0042400315"
    _write_live_snapshot(str(tmp_path), gid)

    bus = EventBus()
    seen = []

    async def cap(t, e):
        seen.append(e["action_number"])

    bus.subscribe("pbp.*", cap)
    calls = {"n": 0}
    plays_v1 = [{"actionNumber": 1, "actionType": "Foul"}]
    plays_v2 = [{"actionNumber": 1, "actionType": "Foul"},
                {"actionNumber": 2, "actionType": "Foul"}]

    def fake_fetch(g):
        calls["n"] += 1
        return plays_v1 if calls["n"] == 1 else plays_v2

    poller = PBPPoller([gid], bus=bus, live_dir=str(tmp_path),
                       fetch_fn=fake_fetch)

    async def run():
        await poller.poll_once()
        await asyncio.sleep(0)
        await poller.poll_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    assert seen == [1, 2]   # play 1 NOT re-emitted


# ── lineup_tracker ──────────────────────────────────────────────────────
def test_lineup_tracker_emits_on_defender_change(tmp_path):
    from scripts.lineup_tracker import LineupTracker
    gid = "0042400315"
    _write_live_snapshot(str(tmp_path), gid)

    bus = EventBus()
    seen = []

    async def cap(t, e):
        seen.append((e["offense_id"], e["new_defender_id"]))

    bus.subscribe(TOPIC_LINEUP_DEFENDER_CHANGED, cap)

    poll_n = {"n": 0}

    def fake_fetch(g):
        poll_n["n"] += 1
        if poll_n["n"] == 1:
            return [{"personIdOff": 100, "defensivePersonId": 200,
                     "matchupMinutes": 5.0}]
        return [{"personIdOff": 100, "defensivePersonId": 300,
                 "matchupMinutes": 6.0}]

    tracker = LineupTracker([gid], bus=bus, live_dir=str(tmp_path),
                            fetch_fn=fake_fetch)

    async def run():
        await tracker.poll_once()
        await asyncio.sleep(0)
        await tracker.poll_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    # First tick — establish baseline (counts as new defender vs None).
    # Second tick — actual change. Both should emit at least once.
    assert any(d == 300 for _, d in seen)


# ── parallel_scraper ────────────────────────────────────────────────────
def test_parallel_scraper_writes_and_publishes(tmp_path):
    from scripts.parallel_scraper import ParallelScraper
    bus = EventBus()
    refreshed = []

    async def cap(t, e):
        refreshed.append(e)

    bus.subscribe(TOPIC_LINES_REFRESHED, cap)

    async def fake_pin(_session):
        return [{"captured_at": "2026-05-26T18:00:00", "book": "pin",
                 "player_name": "X", "stat": "pts", "line": 26.5,
                 "over_price": -110, "under_price": -110}]

    s = ParallelScraper(books=["pin"], lines_dir=str(tmp_path),
                        bus=bus, fetchers={"pin": fake_pin})

    async def run():
        await s.tick_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    assert refreshed
    assert refreshed[0]["counts"]["pin"] == 1
    files = os.listdir(str(tmp_path))
    assert any("_pin.csv" in f for f in files)


# ── box_snapshot_poller ─────────────────────────────────────────────────
def test_box_snapshot_poller_emits_snapshot_and_projection(tmp_path):
    from scripts.box_snapshot_poller import BoxSnapshotPoller
    gid = "0042400315"

    bus = EventBus()
    snapshot_events = []
    projection_events = []

    async def cap_snap(t, e):
        snapshot_events.append(e["game_id"])

    async def cap_proj(t, e):
        projection_events.append(len(e["rows"]))

    bus.subscribe(TOPIC_SNAPSHOT_UPDATED, cap_snap)
    bus.subscribe(TOPIC_PROJECTION_UPDATED, cap_proj)

    live_snap = {
        "game_id": gid, "game_status": "LIVE", "period": 4,
        "clock": "PT05M00.00S",
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 95, "away_score": 90, "players": [],
    }

    def fake_poll(gids, **kw):
        return {gid: live_snap}

    def fake_project(snap):
        return [{"player_id": 1, "stat": "pts", "projected_final": 30.0,
                 "current": 20.0, "name": "X", "team": "DEN"}] * 3

    p = BoxSnapshotPoller([gid], bus=bus, live_dir=str(tmp_path),
                          poll_once_fn=fake_poll, project_fn=fake_project)

    async def run():
        await p.tick_once()
        await asyncio.sleep(0)

    asyncio.run(run())
    assert snapshot_events == [gid]
    assert projection_events == [3]
