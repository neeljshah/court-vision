"""tests.platformkit.improve.test_settled_ingest -- honest settled DATA-IN (SI-P0-02 + A2).

Asserts the never-skip / never-double-count / never-read-green contract of
scripts.platformkit.improve.settled_ingest.ingest_settled:

  * NO DOUBLE-COUNT across two runs: a game folded on run 1, with its id in the seen union
    on run 2, is NOT re-surfaced; the high-water key is MONOTONIC (advances forward-only).
  * a DEAD-FEED signal (board fails to fetch/parse) -> DEGRADED + clock FROZEN, NOT IDLE
    (a dead feed must never read green).
  * an OFFSEASON empty result (board parses OK with zero finals) -> IDLE, NOT DEGRADED, and
    NEVER a fabricated game (zero clean games surfaced).

All network is INJECTED (canned ESPN boards, zero network). Per-file test only (full pytest
freezes the box). ASCII; stdlib + pytest deps.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import settled_ingest as si  # noqa: E402


# --------------------------------------------------------------------------- #
# Canned ESPN scoreboard boards (the shape settled_finals._final_games_from_board parses).
# --------------------------------------------------------------------------- #
def _final_event(event_id, date_iso):
    """One FINAL (completed) ESPN event with a home/away competition."""
    return {
        "id": str(event_id),
        "date": date_iso,
        "competitions": [{
            "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Home FC"}},
                {"homeAway": "away", "team": {"displayName": "Away FC"}},
            ],
        }],
    }


def _board(*events):
    return {"events": list(events)}


def _empty_board():
    """A parsed-OK board with zero events -- honest offseason / no-finals day."""
    return {"events": []}


def _states_with_win(_sport, _game):
    """Inject reconstructed in-game state rows carrying a confirmed positive outcome (==1)
    so the MF3 settle_audit lets the game through as CLEAN."""
    return [
        {"sport": _sport, "game_id": _game["game_id"], "asof_idx": 0,
         "state_diff": 3.0, "frac_elapsed": 0.5, "p0": 0.55, "outcome": 1.0},
        {"sport": _sport, "game_id": _game["game_id"], "asof_idx": 1,
         "state_diff": 6.0, "frac_elapsed": 0.9, "p0": 0.70, "outcome": 1.0},
    ]


def _getter(board):
    """An http_get that returns the same canned board for any url (zero network)."""
    def _get(_url):
        return board
    return _get


def _dead_getter():
    """An http_get that simulates a dead feed: every fetch raises."""
    def _get(_url):
        raise RuntimeError("ESPN unreachable")
    return _get


# --------------------------------------------------------------------------- #
# 1. NO double-count across two runs; watermark monotonic.                     #
# --------------------------------------------------------------------------- #
def test_no_double_count_across_two_runs_watermark_monotonic():
    board = _board(_final_event("401581234", "2026-06-18T23:05Z"))
    common = dict(sport="mlb", http_get=_getter(board),
                  states_for_game=_states_with_win, dates=["20260618"])

    run1 = si.ingest_settled(seen_ids=[], **common)
    assert run1.status == si.FRESH_NEW
    assert run1.degraded is False
    assert run1.n_clean == 1
    assert run1.folded_ids == ["401581234"]
    assert run1.high_water  # a non-empty display/order key was recorded

    # Run 2: the id is now in the seen union (as the loop would record it). The SAME board
    # must NOT re-surface the game -> IDLE, zero clean games (no double-count).
    run2 = si.ingest_settled(seen_ids=["401581234"], high_water=run1.high_water, **common)
    assert run2.status == si.IDLE
    assert run2.degraded is False
    assert run2.n_clean == 0
    assert run2.clean_games == []
    # high-water is MONOTONIC: it never regresses below run 1's value.
    assert run2.high_water >= run1.high_water


def test_checkpoint_seen_union_also_dedups():
    """The seen union includes the loop checkpoint's seen_ids, not just the caller's."""
    board = _board(_final_event("999", "2026-06-18T20:00Z"))
    res = si.ingest_settled(sport="mlb", http_get=_getter(board),
                            states_for_game=_states_with_win, dates=["20260618"],
                            seen_ids=[], checkpoint_seen_ids=["999"])
    assert res.status == si.IDLE
    assert res.n_clean == 0
    assert res.clean_games == []


# --------------------------------------------------------------------------- #
# 2. Dead feed -> DEGRADED (clock frozen), NOT IDLE, never green.              #
# --------------------------------------------------------------------------- #
def test_dead_feed_is_degraded_not_idle():
    res = si.ingest_settled(sport="mlb", http_get=_dead_getter(),
                            states_for_game=_states_with_win, dates=["20260618"])
    assert res.status == si.STALE
    assert res.degraded is True
    assert res.clock_advances is False   # FROZEN: a dead feed never reads green
    assert res.n_clean == 0
    assert res.clean_games == []


def test_malformed_board_is_degraded_not_idle():
    """A board that parses but has no `events` list (malformed body) is STALE, not IDLE."""
    res = si.ingest_settled(sport="mlb", http_get=_getter({"garbage": 1}),
                            states_for_game=_states_with_win, dates=["20260618"])
    assert res.status == si.STALE
    assert res.degraded is True
    assert res.clock_advances is False


# --------------------------------------------------------------------------- #
# 3. Offseason empty -> IDLE, NOT DEGRADED, no fabricated game.                #
# --------------------------------------------------------------------------- #
def test_offseason_empty_is_idle_not_degraded_and_no_fabrication():
    res = si.ingest_settled(sport="mlb", http_get=_getter(_empty_board()),
                            states_for_game=_states_with_win, dates=["20260618"])
    assert res.status == si.IDLE
    assert res.degraded is False
    assert res.clock_advances is True    # we verified nothing-new; honest-idle stays green
    assert res.n_clean == 0
    assert res.clean_games == []          # NEVER a fabricated game
    assert res.n_fetched_final == 0


def test_new_finals_without_states_is_idle_not_degraded():
    """New finals but NO wired states adapter -> honest IDLE (wiring gap), never DEGRADED
    and never a fabricated foldable game."""
    board = _board(_final_event("555", "2026-06-18T22:00Z"))
    res = si.ingest_settled(sport="mlb", http_get=_getter(board),
                            states_for_game=lambda *_a, **_k: [], dates=["20260618"])
    assert res.status == si.IDLE
    assert res.degraded is False
    assert res.n_new_unseen == 1          # the final WAS surfaced (not skipped)
    assert res.n_clean == 0               # but nothing foldable was fabricated
    assert res.clean_games == []


# --------------------------------------------------------------------------- #
# 4. MF3: an enriched batch with no real outcome label is DEGRADED, not 0-filled.
# --------------------------------------------------------------------------- #
def test_states_without_outcome_label_degrade_not_zero_fill():
    """States present but every outcome ABSENT -> the audit quarantines -> DEGRADED. The
    missing label is NEVER 0-filled into a clean observation."""
    def _states_no_label(_sport, _game):
        return [{"sport": _sport, "game_id": _game["game_id"], "asof_idx": 0,
                 "state_diff": 1.0, "frac_elapsed": 0.4, "p0": 0.5}]  # no 'outcome'
    board = _board(_final_event("777", "2026-06-18T21:00Z"))
    res = si.ingest_settled(sport="mlb", http_get=_getter(board),
                            states_for_game=_states_no_label, dates=["20260618"])
    assert res.status == si.DEGRADED
    assert res.degraded is True
    assert res.clock_advances is False
    assert res.n_clean == 0


# --------------------------------------------------------------------------- #
# 5. season-aware multi-day window + daemon adapter shape.                     #
# --------------------------------------------------------------------------- #
def test_date_window_is_multi_day_oldest_first():
    from datetime import datetime, timezone
    win = si.date_window(days=2, now=datetime(2026, 6, 19, tzinfo=timezone.utc))
    assert win == ["20260618", "20260619"]  # yesterday then today (oldest first)


def test_settled_games_fn_returns_only_clean_games():
    board = _board(_final_event("401581234", "2026-06-18T23:05Z"))
    out = si.settled_games_fn("mlb", since="", seen_ids=[], http_get=_getter(board),
                              states_for_game=_states_with_win, dates=["20260618"])
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["game_id"] == "401581234"

    # dead feed -> [] (the daemon then logs NO_CANDIDATE)
    dead = si.settled_games_fn("mlb", since="", seen_ids=[], http_get=_dead_getter(),
                               states_for_game=_states_with_win, dates=["20260618"])
    assert dead == []


def test_never_raises_on_garbage_inputs():
    # No http_get + unknown sport: returns an IngestSummary, never raises.
    res = si.ingest_settled(sport="not_a_sport", dates=["20260618"], http_get=_dead_getter())
    assert isinstance(res, si.IngestSummary)
