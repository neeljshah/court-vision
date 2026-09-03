"""Focused tests for the overnight bridge supervisor."""
from __future__ import annotations

import json
import subprocess

from scripts.platformkit import bridge_supervisor


def test_untracked_count_ignores_games_with_usable_output(tmp_path):
    queue = tmp_path / "footage_queue_kbo.json"
    queue.write_text(json.dumps([
        {"game_id": "a"}, {"game_id": "b"}, {"game_id": "c"},
    ]), encoding="utf-8")

    # b is fully tracked; c is a thin 103-row false pass and still counts as work.
    remaining = bridge_supervisor.untracked_count(queue, {"b": 9000, "c": 103})

    assert remaining == 2


def test_unreadable_queue_does_not_raise(tmp_path):
    bad = tmp_path / "footage_queue_broken.json"
    bad.write_text("{not json", encoding="utf-8")

    assert bridge_supervisor.untracked_count(bad, {}) == 0


def test_refill_uses_plural_sports_flag(monkeypatch):
    """--sport (singular) is rejected by the expander and refills nothing."""
    seen = {}

    class _FakePopen:
        def __init__(self, command, **kwargs):
            seen["command"] = command

        def poll(self):
            return 0

    monkeypatch.setattr(bridge_supervisor.subprocess, "Popen", _FakePopen)
    bridge_supervisor._REFILLS_IN_FLIGHT.clear()

    bridge_supervisor.refill("tennis")

    assert "--sports" in seen["command"]
    assert "--sport" not in seen["command"]


def test_refill_reports_sports_it_cannot_refill(monkeypatch, capsys):
    """A lane with no expander source must say so, not silently no-op."""
    called = []
    monkeypatch.setattr(bridge_supervisor.subprocess, "Popen",
                        lambda *a, **k: called.append(a))

    # football IS refillable now; use a sport with no expander source.
    bridge_supervisor.refill("lacrosse")

    assert not called
    assert "no expander source" in capsys.readouterr().out


def test_every_lane_has_a_real_adapter():
    """A lane with no adapter downloads and uploads a game, then the pod exits 2
    with "unknown sport". Four lanes (nhl, cricket, handball, volleyball) ran
    that way and burned bandwidth all night producing nothing."""
    from scripts.platformkit.adapter_run import ADAPTERS
    from scripts.platformkit.track_daemon import CLIP_SPORTS, SPORT_ADAPTER

    orphans = []
    for _, queues in bridge_supervisor.LANES:
        for queue in queues:
            sport = queue.replace("footage_queue_", "").replace(".json", "")
            if sport in CLIP_SPORTS or SPORT_ADAPTER.get(sport, sport) in ADAPTERS:
                continue
            orphans.append(sport)

    assert not orphans, "lanes with no adapter: %s" % sorted(orphans)


def test_refill_never_blocks_the_poll_loop(monkeypatch):
    """A refill must be launched, not waited on, and not duplicated per sport.

    The regression: refill used subprocess.run(timeout=1800), so the supervisor
    stopped publishing status for as long as the expander took -- and the
    expander runs yt-dlp searches. bridge_liveness then read a stale snapshot,
    reported DOWN, and a watchdog started a second supervisor; each spawned its
    own seven lane workers. On 2026-09-02 that left 17 orphan workers with no
    supervisor owning them. Every supervisor stopped logging directly after
    "lane football down to N untracked -- refilling".
    """
    launched = []

    class _FakePopen:
        def __init__(self, command, **kwargs):
            launched.append(command)
            self.returncode = None

        def poll(self):
            return None  # still running

    monkeypatch.setattr(bridge_supervisor.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(bridge_supervisor.subprocess, "run", _no_blocking_run)
    bridge_supervisor._REFILLS_IN_FLIGHT.clear()

    bridge_supervisor.refill("tennis")
    assert len(launched) == 1

    # A second call while the first is still running must not launch another.
    bridge_supervisor.refill("tennis")
    assert len(launched) == 1

    # A different sport is independent.
    bridge_supervisor.refill("soccer")
    assert len(launched) == 2


def _no_blocking_run(*args, **kwargs):
    raise AssertionError("refill must not call subprocess.run -- it blocks the heartbeat")
