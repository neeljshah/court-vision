"""Offline tests for the keyless ESPN settled-finals provider (settled_finals).

ZERO network: an injected http_get returns canned ESPN scoreboard payloads. Asserts:
  * only FINAL games are returned (in-progress / scheduled are excluded);
  * DEDUP is by game_id via seen_ids (NOT a high-water key filter);
  * BUG B regression: an OUT-OF-ORDER late final (earlier commence, later final, key <
    high-water) is STILL surfaced -- never key-skipped;
  * across a simulated RESTART no already-folded game (in seen_ids) is re-served.
"""
from __future__ import annotations

import sys
import pathlib

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.ingame import settled_finals as SF  # noqa: E402


def _ev(eid, date, state, completed=False, home="H", away="A"):
    return {
        "id": eid, "date": date,
        "competitions": [{
            "status": {"type": {"name": state, "completed": completed}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": home}},
                {"homeAway": "away", "team": {"displayName": away}},
            ],
        }],
    }


def _board(events):
    return lambda url: {"events": events}


def test_only_final_games_returned():
    feed = _board([
        _ev("1", "2026-06-10T00:00Z", "STATUS_FINAL", completed=True),
        _ev("2", "2026-06-10T03:00Z", "STATUS_IN_PROGRESS"),
        _ev("3", "2026-06-10T06:00Z", "STATUS_SCHEDULED"),
    ])
    got = SF.settled_since("nba", since="", http_get=feed, use_cache=False)
    ids = [g["game_id"] for g in got]
    assert ids == ["1"], ids  # only the completed final
    assert got[0]["key"].endswith("|1")
    assert got[0]["home"] == "H" and got[0]["away"] == "A"


def test_dedup_is_by_seen_ids_not_key():
    """Folding is decided by seen_ids (game_id), NOT a high-water key filter."""
    feed = _board([
        _ev("1", "2026-06-10T00:00Z", "STATUS_FINAL", completed=True),
        _ev("2", "2026-06-11T00:00Z", "STATUS_FINAL", completed=True),
        _ev("3", "2026-06-12T00:00Z", "STATUS_FINAL", completed=True),
    ])
    first = SF.settled_since("nba", since="", http_get=feed, use_cache=False)
    assert [g["game_id"] for g in first] == ["1", "2", "3"]  # ascending by key
    # mark game 1 folded -> only 2,3 remain (dedup by id, not by key)
    rest = SF.settled_since("nba", since="", seen_ids=["1"],
                            http_get=feed, use_cache=False)
    assert [g["game_id"] for g in rest] == ["2", "3"], rest
    # all folded -> nothing
    none = SF.settled_since("nba", since="", seen_ids=["1", "2", "3"],
                            http_get=feed, use_cache=False)
    assert none == []


def test_restart_never_skips_unseen_game():
    """Across a restart a game that becomes FINAL LATER is still surfaced; an
    already-folded game (in seen_ids) is not re-served. Dedup is by id, not by key.
    """
    # sweep 1: only game 1 is final (game 2 still in progress)
    sweep1 = _board([
        _ev("1", "2026-06-10T00:00Z", "STATUS_FINAL", completed=True),
        _ev("2", "2026-06-11T00:00Z", "STATUS_IN_PROGRESS"),
    ])
    got1 = SF.settled_since("nba", since="", http_get=sweep1, use_cache=False)
    assert [g["game_id"] for g in got1] == ["1"]
    seen = {g["game_id"] for g in got1}

    # RESTART + sweep 2: game 2 is now final -> surfaced; game 1 (seen) is not re-served.
    sweep2 = _board([
        _ev("1", "2026-06-10T00:00Z", "STATUS_FINAL", completed=True),
        _ev("2", "2026-06-11T00:00Z", "STATUS_FINAL", completed=True),
    ])
    got2 = SF.settled_since("nba", since="", seen_ids=sorted(seen),
                            http_get=sweep2, use_cache=False)
    assert [g["game_id"] for g in got2] == ["2"], got2  # the newly-final game, only it


def test_out_of_order_late_final_is_not_skipped():
    """BUG B regression: a game with EARLIER commence that finals AFTER a later-scheduled
    game must still be surfaced. A key filter ('key > high_water') would drop it because
    its '<commence>|<id>' key is LOWER than the already-advanced high-water; dedup-by-id
    surfaces it instead.
    """
    # game B (commence 22:00) finals first and advances the cursor; game A (commence
    # 19:00, an extra-innings game) finals LATER -> A's key < B's key.
    A = _ev("A", "2026-06-10T19:00Z", "STATUS_FINAL", completed=True)
    B = _ev("B", "2026-06-10T22:00Z", "STATUS_FINAL", completed=True)
    # sweep 1: only B is final; A still in progress
    sweep1 = _board([B, _ev("A", "2026-06-10T19:00Z", "STATUS_IN_PROGRESS")])
    got1 = SF.settled_since("mlb", since="", http_get=sweep1, use_cache=False)
    assert [g["game_id"] for g in got1] == ["B"]
    # cursor would now be B's key '...T22:00Z|B' -- HIGHER than A's '...T19:00Z|A'.
    hw = max(g["key"] for g in got1)
    assert hw > "2026-06-10T19:00Z|A"  # a key filter would skip A
    # sweep 2: A finals late (lower key). With dedup-by-id (B already seen), A IS folded.
    sweep2 = _board([A, B])
    got2 = SF.settled_since("mlb", since=hw, seen_ids=["B"],
                            http_get=sweep2, use_cache=False)
    assert [g["game_id"] for g in got2] == ["A"], got2  # NOT skipped despite key < hw


def test_dead_feed_degrades_to_empty_never_raises():
    def boom(url):
        raise RuntimeError("network down")
    got = SF.settled_since("nba", since="", http_get=boom, use_cache=False)
    assert got == []
    # unknown sport -> [] (no league path), never raises
    assert SF.settled_since("cricket", since="", http_get=_board([]),
                            use_cache=False) == []


def test_states_for_game_absent_adapter_returns_empty():
    # no settled_ingest adapter wired -> [] (game skipped, never fabricated)
    assert SF.states_for_game("nba", {"game_id": "1"}) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
