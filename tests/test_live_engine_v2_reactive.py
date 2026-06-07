"""tests/test_live_engine_v2_reactive.py — Phase C regression set."""
from __future__ import annotations

import asyncio
import csv
import os
from typing import Any, Dict, List

import pytest

from src.live.event_bus import (
    EventBus,
    TOPIC_BET_RECOMMENDED,
    TOPIC_LINES_REFRESHED,
    TOPIC_LINEUP_DEFENDER_CHANGED,
    TOPIC_PBP_FOUL,
    TOPIC_PBP_PERIOD_END,
    TOPIC_PROJECTION_UPDATED,
)


# ── reactive_projector ──────────────────────────────────────────────────
def _fake_snap(game_id="0042400315"):
    return {
        "game_id": game_id, "game_status": "LIVE", "period": 4,
        "clock": "PT05M00.00S",
        "home_team": "DEN", "away_team": "LAL",
        "home_score": 95, "away_score": 90,
        "players": [{"player_id": 1, "name": "Jokic", "team": "DEN",
                     "pts": 22, "min": 30, "pf": 2}],
    }


def test_reactive_projector_reprojects_on_foul():
    from src.prediction.reactive_projector import ReactiveProjector

    bus = EventBus()
    seen: List[Dict[str, Any]] = []

    async def cap(t, e):
        seen.append(e)

    bus.subscribe(TOPIC_PROJECTION_UPDATED, cap)

    proj_calls = {"n": 0}

    def fake_project(snap):
        proj_calls["n"] += 1
        # First call returns 30; second returns 28 (delta = -2)
        val = 30.0 if proj_calls["n"] == 1 else 28.0
        return [{"player_id": 1, "stat": "pts", "projected_final": val,
                 "current": 22.0, "name": "Jokic", "team": "DEN"}]

    rp = ReactiveProjector(bus=bus, snapshot_loader=lambda gid: _fake_snap(gid),
                           project_fn=fake_project)
    rp.register()

    async def run():
        # First fire seeds the cache (delta=0).
        await bus.publish(TOPIC_PBP_FOUL, {
            "game_id": "0042400315", "player_id": 1, "action_number": 1,
        })
        await asyncio.sleep(0)
        # Second fire — delta should now be -2.
        await bus.publish(TOPIC_PBP_FOUL, {
            "game_id": "0042400315", "player_id": 1, "action_number": 2,
        })
        await asyncio.sleep(0)

    asyncio.run(run())
    assert len(seen) == 2
    assert seen[1]["deltas"]["pts"] == pytest.approx(-2.0)


def test_reactive_projector_emits_full_slate_on_period_end():
    from src.prediction.reactive_projector import ReactiveProjector

    bus = EventBus()
    seen = []

    async def cap(t, e):
        seen.append(e)

    bus.subscribe(TOPIC_PROJECTION_UPDATED, cap)

    def fake_project(snap):
        return [
            {"player_id": 1, "stat": "pts", "projected_final": 32.0,
             "current": 22.0, "name": "Jokic", "team": "DEN"},
            {"player_id": 2, "stat": "pts", "projected_final": 18.0,
             "current": 12.0, "name": "MPJ", "team": "DEN"},
        ]

    rp = ReactiveProjector(bus=bus, snapshot_loader=lambda gid: _fake_snap(gid),
                           project_fn=fake_project)
    rp.register()

    async def run():
        await bus.publish(TOPIC_PBP_PERIOD_END, {"game_id": "0042400315"})
        await asyncio.sleep(0)

    asyncio.run(run())
    assert len(seen) == 1
    assert len(seen[0]["rows"]) == 2


def test_reactive_projector_stamps_defender_on_change():
    from src.prediction.reactive_projector import ReactiveProjector

    bus = EventBus()
    stamped_defs: List = []

    def fake_project(snap):
        stamped_defs.append(snap.get("matchups", {}).get(1))
        return [{"player_id": 1, "stat": "pts", "projected_final": 30.0,
                 "current": 22.0, "name": "Jokic", "team": "DEN"}]

    rp = ReactiveProjector(bus=bus,
                           snapshot_loader=lambda gid: _fake_snap(gid),
                           project_fn=fake_project)
    rp.register()

    async def run():
        await bus.publish(TOPIC_LINEUP_DEFENDER_CHANGED, {
            "game_id": "0042400315", "offense_id": 1,
            "new_defender_id": 99,
        })
        await asyncio.sleep(0)

    asyncio.run(run())
    assert stamped_defs == [99]


# ── decision_engine ─────────────────────────────────────────────────────
def _seed_lines_csv(dirpath, date_str, player_id, stat, line, over, under, book="pin"):
    """Write one CSV row. Decision engine now requires three-book consensus
    (pin + bov + fd) before emitting a bet; tests that need a bet to surface
    should call _seed_three_book(...) instead."""
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(dirpath, f"{date_str}_{book}.csv")
    new = not os.path.exists(p)
    with open(p, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "captured_at", "book", "game_id", "player_id", "player_name",
            "team", "stat", "line", "over_price", "under_price",
            "market_status", "is_alt_line"])
        if new:
            w.writeheader()
        w.writerow({"captured_at": "2026-05-26T20:00:00", "book": book,
                    "game_id": "0042400315", "player_id": player_id,
                    "player_name": "Jokic", "team": "DEN", "stat": stat,
                    "line": line, "over_price": over, "under_price": under,
                    "market_status": "open", "is_alt_line": ""})
    return p


def _seed_three_book(dirpath, date_str, player_id, stat, line, over, under):
    """Seed pin/bov/fd CSVs with the same (player, stat, line) so the
    decision engine's three-book consensus filter lets the bet through."""
    for book in ("pin", "bov", "fd"):
        _seed_lines_csv(dirpath, date_str, player_id, stat, line, over,
                        under, book=book)


def test_decision_engine_emits_recommendation(tmp_path):
    from src.prediction.decision_engine import DecisionEngine, LineCache

    date_str = "2026-05-26"
    lc = LineCache(lines_dir=str(tmp_path))
    # Realistic in-play edge: line 24.5, proj 27 → ~67% over → ~10% EV at
    # -110. Big enough to fire all tiers, small enough not to hit the 50%
    # EV ceiling (which is reserved for phantom-edge model failures).
    _seed_three_book(str(tmp_path), date_str, "1", "pts", 24.5, -110, -110)
    lc.refresh(date_str)

    bus = EventBus()
    bets: List[Dict[str, Any]] = []

    async def cap(t, e):
        bets.append(e)

    bus.subscribe(TOPIC_BET_RECOMMENDED, cap)

    de = DecisionEngine(bus=bus, line_cache=lc, top_n=5, throttle_ms=0)
    de.register()

    async def run():
        await bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": "0042400315",
            "rows": [{"player_id": "1", "name": "Jokic", "team": "DEN",
                      "stat": "pts", "projected_final": 27.0, "current": 22.0,
                      "delta": 2.0}],
        })
        await asyncio.sleep(0.01)

    asyncio.run(run())
    assert bets, "engine should have emitted at least one bet"
    top = bets[0]
    assert top["stat"] == "pts"
    assert top["side"] == "over"
    assert top["tier"] in ("S", "A", "B")
    assert top["ev"] > 0.04
    assert "Jokic" in top["why"]


def test_decision_engine_skips_under_floor(tmp_path):
    from src.prediction.decision_engine import DecisionEngine, LineCache

    date_str = "2026-05-26"
    lc = LineCache(lines_dir=str(tmp_path))
    # Wash: line 26, proj 26 → ~50% hit → near-zero EV at -110.
    _seed_three_book(str(tmp_path), date_str, "1", "pts", 26.0, -110, -110)
    lc.refresh(date_str)

    bus = EventBus()
    bets = []

    async def cap(t, e):
        bets.append(e)

    bus.subscribe(TOPIC_BET_RECOMMENDED, cap)

    de = DecisionEngine(bus=bus, line_cache=lc, top_n=5, throttle_ms=0,
                        emit_floor_ev=0.02)
    de.register()

    async def run():
        await bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": "0042400315",
            "rows": [{"player_id": "1", "name": "Jokic", "team": "DEN",
                      "stat": "pts", "projected_final": 26.0, "current": 22.0}],
        })
        await asyncio.sleep(0.01)

    asyncio.run(run())
    assert bets == []


def test_decision_engine_reranks_on_line_refresh(tmp_path):
    from src.prediction.decision_engine import DecisionEngine, LineCache

    date_str = "2026-05-26"
    lc = LineCache(lines_dir=str(tmp_path))
    _seed_three_book(str(tmp_path), date_str, "1", "pts", 24.5, -110, -110)
    lc.refresh(date_str)

    bus = EventBus()
    bets = []

    async def cap(t, e):
        bets.append(e)

    bus.subscribe(TOPIC_BET_RECOMMENDED, cap)

    de = DecisionEngine(bus=bus, line_cache=lc, top_n=5, throttle_ms=0)
    de.register()

    async def run():
        await bus.publish(TOPIC_PROJECTION_UPDATED, {
            "game_id": "0042400315",
            "rows": [{"player_id": "1", "name": "Jokic", "team": "DEN",
                      "stat": "pts", "projected_final": 27.0, "current": 22.0}],
        })
        await asyncio.sleep(0.01)
        n0 = len(bets)
        await bus.publish(TOPIC_LINES_REFRESHED, {"date": date_str, "counts": {}})
        await asyncio.sleep(0.01)
        assert len(bets) > n0   # should rerank and re-emit

    asyncio.run(run())


def test_kelly_fraction_capped():
    from src.prediction.decision_engine import kelly_fraction
    # 90% hit at -110 → naive Kelly is huge; should clamp at 0.25.
    assert kelly_fraction(0.90, -110) == pytest.approx(0.25)
    # Negative edge → 0.
    assert kelly_fraction(0.30, -110) == 0.0


def test_classify_tier_thresholds():
    from src.prediction.decision_engine import classify_tier
    assert classify_tier(0.10, 1.5) == "S"
    assert classify_tier(0.10, 0.0) == "A"   # high EV but no delta
    assert classify_tier(0.05, 0.0) == "A"
    assert classify_tier(0.02, 0.0) == "B"
    assert classify_tier(0.005, 0.0) == "C"
