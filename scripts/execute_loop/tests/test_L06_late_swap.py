"""test_L06_late_swap.py — Tests for L06_late_swap.py

Six tests covering the full public API using mocked L20 and injected time.
No live network calls; no filesystem mutation.

Generator termination strategy
--------------------------------
watch_for_swaps is an infinite generator that stops only when _within_window()
returns False.  Every test that drives the generator injects a _now_fn that
advances past the lock+30min window after a fixed number of calls, guaranteeing
the generator exits via StopIteration rather than looping forever.
"""
from __future__ import annotations

import itertools
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_TEST_DIR    = Path(__file__).resolve().parent
_LOOP_DIR    = _TEST_DIR.parent
_PROJECT_DIR = _LOOP_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))
sys.path.insert(0, str(_LOOP_DIR))

import L06_late_swap as L06  # noqa: E402

# ── time helpers ──────────────────────────────────────────────────────────────
_LOCK_TIME_STR   = "2026-05-25T23:00:00+00:00"
_INSIDE_WINDOW   = datetime(2026, 5, 25, 20, 0, tzinfo=timezone.utc)   # 3 h before lock
_PAST_WINDOW     = datetime(2026, 5, 26,  0, 0, tzinfo=timezone.utc)   # 1 h past lock+30m


def _advancing_now_fn(inside_count: int = 1):
    """Return a _now_fn that returns _INSIDE_WINDOW for the first *inside_count*
    calls, then returns _PAST_WINDOW forever (which terminates the generator).
    """
    calls: dict = {"n": 0}
    def _fn():
        calls["n"] += 1
        return _INSIDE_WINDOW if calls["n"] <= inside_count else _PAST_WINDOW
    return _fn


# ── shared fixtures ───────────────────────────────────────────────────────────

def _make_injury(player: str, status: str = "OUT") -> "L06.InjuryUpdate":
    """Build a minimal InjuryUpdate for test use."""
    from L20_injury_feed import InjuryUpdate
    upd = InjuryUpdate(
        player=player,
        team="LAL",
        status=status,
        source="rotowire",
        body=f"{player} is {status}",
        timestamp="2026-05-25T18:00:00+00:00",
        severity="critical",
    )
    upd._hash = upd.compute_hash()
    return upd


def _make_slate(lock_time: str = _LOCK_TIME_STR):
    """Minimal slate-like object with a player pool."""
    slate = MagicMock()
    slate.lock_time = lock_time
    slate.salary_cap = 50_000
    slate.players = [
        {"name": "LeBron James",    "position": "SF", "salary": 9_800},
        {"name": "Anthony Davis",   "position": "PF", "salary": 9_600},
        {"name": "Austin Reaves",   "position": "SF", "salary": 5_200},
        {"name": "Rui Hachimura",   "position": "SF", "salary": 4_800},
        {"name": "D'Angelo Russell","position": "PG", "salary": 6_000},
        {"name": "Jarred Vanderbilt","position": "PF","salary": 4_200},
    ]
    return slate


def _make_lineup(
    lineup_id: str = "lu1",
    players: list | None = None,
    total_salary: int = 48_000,
    salary_cap: int = 50_000,
) -> dict:
    if players is None:
        players = ["LeBron James", "Anthony Davis", "D'Angelo Russell",
                   "Austin Reaves", "Rui Hachimura"]
    return {
        "lineup_id":    lineup_id,
        "players":      players,
        "total_salary": total_salary,
        "salary_cap":   salary_cap,
    }


_FPTS_DATA = {
    "LeBron James":        42.0,
    "lebron james":        42.0,
    "Anthony Davis":       47.0,
    "anthony davis":       47.0,
    "Austin Reaves":       25.0,
    "austin reaves":       25.0,
    "Rui Hachimura":       20.0,
    "rui hachimura":       20.0,
    "D'Angelo Russell":    28.0,
    "d'angelo russell":    28.0,
    "Jarred Vanderbilt":   18.0,
    "jarred vanderbilt":   18.0,
}


def _collect_signals(gen, max_items: int = 20) -> list:
    """Drain the generator up to max_items, catching StopIteration cleanly."""
    signals = []
    for sig in itertools.islice(gen, max_items):
        signals.append(sig)
    return signals


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Player in one lineup → SwapSignal produced, len(affected_lineups)==1
# ─────────────────────────────────────────────────────────────────────────────
def test_player_out_in_one_lineup_yields_signal():
    """Stubbed L20 emits OUT for LeBron James who is in exactly one lineup.
    watch_for_swaps should yield one SwapSignal with len(affected_lineups)==1.
    """
    slate  = _make_slate()
    lineup = _make_lineup("lu_001")   # contains LeBron James
    news   = _make_injury("LeBron James", "OUT")
    bets: list = []

    # First poll: return the news update; subsequent polls: empty (window closes on 2nd now() call)
    call_count: dict = {"n": 0}
    def _stub_run_all():
        call_count["n"] += 1
        return [news] if call_count["n"] == 1 else []

    with (
        patch.object(L06, "run_all_sources", side_effect=_stub_run_all),
        patch.object(L06, "diff_against_seen", side_effect=lambda u: u),
        patch.object(L06, "_send_alert", None),
    ):
        gen = L06.watch_for_swaps(
            slate, [lineup], bets,
            poll_seconds=0,
            fpts_data=_FPTS_DATA,
            _now_fn=_advancing_now_fn(inside_count=2),   # 2 polls inside, 3rd exits
        )
        signals = _collect_signals(gen)

    assert len(signals) == 1, f"Expected 1 SwapSignal, got {len(signals)}"
    sig = signals[0]
    assert sig.trigger_player.lower().startswith("lebron")
    assert sig.trigger_status == "OUT"
    assert len(sig.affected_lineups) == 1
    assert sig.affected_lineups[0] == "lu_001"
    assert sig.ev_swing_pp > L06._EV_SWING_THRESH


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Player not in any lineup → generator yields nothing
# ─────────────────────────────────────────────────────────────────────────────
def test_unrostered_player_yields_nothing():
    """Injury news for a player not in any lineup should produce no SwapSignal."""
    slate  = _make_slate()
    lineup = _make_lineup("lu_002", players=[
        "Anthony Davis", "D'Angelo Russell", "Austin Reaves",
    ])
    news = _make_injury("Stephen Curry", "OUT")   # not in any lineup
    bets: list = []

    call_count: dict = {"n": 0}
    def _stub_run_all():
        call_count["n"] += 1
        return [news] if call_count["n"] == 1 else []

    with (
        patch.object(L06, "run_all_sources", side_effect=_stub_run_all),
        patch.object(L06, "diff_against_seen", side_effect=lambda u: u),
        patch.object(L06, "_send_alert", None),
    ):
        gen = L06.watch_for_swaps(
            slate, [lineup], bets,
            poll_seconds=0,
            fpts_data=_FPTS_DATA,
            _now_fn=_advancing_now_fn(inside_count=2),
        )
        signals = _collect_signals(gen)

    assert len(signals) == 0, (
        f"Expected 0 signals for unrostered player, got {len(signals)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: EV swing < 5pp and low FPTS → no signal emitted
# ─────────────────────────────────────────────────────────────────────────────
def test_low_ev_swing_no_signal():
    """When model_p_side is already ~0.05 and proj_fpts is near zero,
    both EV and FPTS gates fail — no SwapSignal should be produced.
    """
    slate  = _make_slate()
    tiny_fpts = {"LeBron James": 0.1, "lebron james": 0.1}
    lineup = _make_lineup("lu_003", players=["LeBron James", "Anthony Davis"])

    # model_p_side ≈ OUT baseline (0.05) → swing ≈ 0.01 * 100 = 1pp
    bets = [{
        "bet_id": "bet_001",
        "player": "LeBron James",
        "stat": "pts", "side": "OVER", "line": 10.5,
        "model_p_side": 0.06,
    }]
    news = _make_injury("LeBron James", "OUT")

    call_count: dict = {"n": 0}
    def _stub_run_all():
        call_count["n"] += 1
        return [news] if call_count["n"] == 1 else []

    with (
        patch.object(L06, "run_all_sources", side_effect=_stub_run_all),
        patch.object(L06, "diff_against_seen", side_effect=lambda u: u),
        patch.object(L06, "_send_alert", None),
    ):
        gen = L06.watch_for_swaps(
            slate, [lineup], bets,
            poll_seconds=0,
            fpts_data=tiny_fpts,
            _now_fn=_advancing_now_fn(inside_count=2),
        )
        signals = _collect_signals(gen)

    assert len(signals) == 0, (
        f"Expected 0 signals for low EV swing, got {len(signals)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: recommend_swap_actions returns list[SwapAction] with valid drop/add
# ─────────────────────────────────────────────────────────────────────────────
def test_recommend_swap_actions_valid_pairs():
    """compute_swap_impact + recommend_swap_actions returns SwapActions with
    non-empty drop/add players, correct lineup_id, sorted by FPTS delta desc.

    The lineup intentionally omits Austin Reaves and Rui Hachimura so they are
    available as SF replacement candidates for LeBron James.
    """
    slate  = _make_slate()
    # Only 3 players rostered — SF replacements (Reaves, Hachimura) are available
    lineup = _make_lineup("lu_004", players=[
        "LeBron James", "Anthony Davis", "Jarred Vanderbilt",
    ], total_salary=33_600)
    news = _make_injury("LeBron James", "OUT")
    bets = [{
        "bet_id": "b01", "player": "LeBron James",
        "stat": "pts", "side": "OVER", "line": 25.5,
        "model_p_side": 0.58,     # large swing when OUT drops to 0.05
    }]

    signal = L06.compute_swap_impact(slate, lineup, news, _FPTS_DATA, bets)
    assert signal is not None, "Expected a SwapSignal for large EV swing"

    actions = L06.recommend_swap_actions(signal)

    assert isinstance(actions, list), "recommend_swap_actions must return a list"
    assert len(actions) > 0, "Expected at least one swap action"
    for act in actions:
        assert isinstance(act, L06.SwapAction)
        assert act.drop_player, "drop_player must not be empty"
        assert act.add_player,  "add_player must not be empty"
        assert act.drop_player != act.add_player, "drop and add must differ"
        assert act.lineup_id == "lu_004"

    # Must be sorted by proj_fpts_delta descending
    deltas = [a.projected_fpts_delta for a in actions]
    assert deltas == sorted(deltas, reverse=True), (
        "Actions must be sorted by FPTS delta desc"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: now > lock_time + 30min → WARN logged, no signal
# ─────────────────────────────────────────────────────────────────────────────
def test_past_lock_window_no_signal(caplog):
    """When now is beyond lock_time + 30 min the watcher logs WARN and stops."""
    # Lock set to 17:00 UTC; _PAST_WINDOW is 00:00 next day — well outside window
    slate  = _make_slate(lock_time="2026-05-25T17:00:00+00:00")
    lineup = _make_lineup("lu_005", players=["LeBron James", "Anthony Davis"])
    news   = _make_injury("LeBron James", "OUT")
    bets: list = []

    with (
        patch.object(L06, "run_all_sources", return_value=[news]),
        patch.object(L06, "diff_against_seen", side_effect=lambda u: u),
        patch.object(L06, "_send_alert", None),
        caplog.at_level(logging.WARNING, logger="L06_late_swap"),
    ):
        gen = L06.watch_for_swaps(
            slate, [lineup], bets,
            poll_seconds=0,
            fpts_data=_FPTS_DATA,
            _now_fn=lambda: _PAST_WINDOW,   # always past the window
        )
        signals = _collect_signals(gen)

    assert len(signals) == 0, "No signal expected past lock window"
    warn_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("window" in m.lower() or "lock" in m.lower() for m in warn_msgs), (
        f"Expected a WARN about lock window, got: {warn_msgs}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: L20.run_all_sources raises → caught, generator continues, no crash
# ─────────────────────────────────────────────────────────────────────────────
def test_l20_exception_caught_generator_continues(caplog):
    """If run_all_sources raises, L06 catches it, logs WARN, and continues.
    The generator must not propagate the exception.
    """
    slate  = _make_slate()
    lineup = _make_lineup("lu_006", players=["Anthony Davis"])
    bets: list = []

    call_count: dict = {"n": 0}
    def _flaky_run_all():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("Simulated L20 network failure")
        return []    # subsequent calls succeed with no updates

    raised = False

    with (
        patch.object(L06, "run_all_sources", side_effect=_flaky_run_all),
        patch.object(L06, "diff_against_seen", side_effect=lambda u: u),
        patch.object(L06, "_send_alert", None),
        caplog.at_level(logging.WARNING, logger="L06_late_swap"),
    ):
        gen = L06.watch_for_swaps(
            slate, [lineup], bets,
            poll_seconds=0,
            fpts_data=_FPTS_DATA,
            _now_fn=_advancing_now_fn(inside_count=3),
        )
        try:
            signals = _collect_signals(gen)
        except Exception as exc:
            raised = True
            pytest.fail(f"Generator crashed unexpectedly: {exc}")

    assert not raised, "Generator must not propagate L20 exceptions"
    warn_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(
        "l20" in m.lower() or "error" in m.lower() or "skip" in m.lower()
        for m in warn_msgs
    ), f"Expected a WARN about L20 failure, got: {warn_msgs}"
