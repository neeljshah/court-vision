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

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(bridge_supervisor.subprocess, "run", fake_run)

    bridge_supervisor.refill("tennis")

    assert "--sports" in seen["command"]
    assert "--sport" not in seen["command"]


def test_refill_reports_sports_it_cannot_refill(monkeypatch, capsys):
    """A lane with no expander source must say so, not silently no-op."""
    called = []
    monkeypatch.setattr(bridge_supervisor.subprocess, "run",
                        lambda *a, **k: called.append(a))

    bridge_supervisor.refill("football")

    assert not called
    assert "no expander source" in capsys.readouterr().out
