"""Per-file tests for predict_service.stale_drop (BE-R3-2 stale-game drop).

Verifies (STALE-NEVER-GREEN):
  * a game_state='post' record is dropped (the NBA Spurs/Knicks bug),
  * a past-tipoff-beyond-grace record is dropped even when state is not 'post',
  * a genuinely-live (recent tipoff) record is KEPT,
  * a 'pre' future record is KEPT,
  * markets + edges of a dropped game are removed too (nothing lingers),
  * a day rollover (inject a future now) ages out yesterday's whole slate.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    predict_service/test_stale_drop.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from predict_service.contracts import (
    GAME_STATE_LIVE,
    GAME_STATE_POST,
    GAME_STATE_PRE,
    EdgeRow,
    MarketRow,
    PredictionRecord,
)
from predict_service.stale_drop import (
    PAST_TIPOFF_GRACE_SECONDS,
    drop_stale_records,
    is_stale_record,
    tipoff_past_grace,
)

NOW = datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc)


def _rec(gid, tipoff, state):
    return PredictionRecord(
        sport="nba", game_id=gid, home="H", away="A", tipoff=tipoff,
        pregame_probs={"home_ml": 0.55}, game_state=state)


def _mkt(gid):
    return MarketRow(sport="nba", game_id=gid, market_type="moneyline", side="home")


def _edge(gid):
    return EdgeRow(game_id=gid, market_type="moneyline", side="home",
                   model_prob=0.55, market_prob=0.5, ev=0.0)


# --- the documented NBA bug ------------------------------------------------

def test_post_state_spurs_knicks_row_is_dropped():
    # game_id 401859967, tipoff 2026-06-14, game_state='post' must be suppressed.
    rec = _rec("401859967", "2026-06-14T00:30Z", GAME_STATE_POST)
    assert is_stale_record(rec, NOW) is True
    kept, mkts, edges = drop_stale_records([rec], [_mkt("401859967")],
                                           [_edge("401859967")], now=NOW)
    assert kept == []
    assert mkts == [] and edges == []


def test_post_state_dropped_even_with_future_tipoff():
    # state wins: a 'post' record drops regardless of tipoff parse.
    rec = _rec("g", "2026-12-31T00:00Z", GAME_STATE_POST)
    assert is_stale_record(rec, NOW) is True


# --- past-tipoff-beyond-grace (no explicit post) ---------------------------

def test_past_tipoff_beyond_grace_dropped():
    # A 'pre' record (started but never got a live/post signal -- stuck/abandoned)
    # whose tipoff is beyond grace must drop. State is deliberately NOT 'live':
    # an explicitly-live game is kept regardless of tipoff age (see below) so its
    # prior survives for the in-game carry; the grace heuristic is only consulted
    # for non-live, non-post records.
    old = NOW - timedelta(seconds=PAST_TIPOFF_GRACE_SECONDS + 60)
    rec = _rec("g", old.isoformat(), GAME_STATE_PRE)
    assert is_stale_record(rec, NOW) is True


def test_long_running_live_game_kept_for_carry():
    # Load-bearing invariant: an explicitly-LIVE game is NEVER stale, no matter how
    # long it has run (extra innings / OT), so its leak-free pregame prior remains
    # available for the in-game pregame_carry reprice (p0_source=PRIOR).
    old = NOW - timedelta(seconds=PAST_TIPOFF_GRACE_SECONDS + 3600)
    rec = _rec("g", old.isoformat(), GAME_STATE_LIVE)
    assert is_stale_record(rec, NOW) is False
    kept, _, _ = drop_stale_records([rec], [], [], now=NOW)
    assert len(kept) == 1


def test_recent_tipoff_within_grace_kept_as_live():
    recent = NOW - timedelta(minutes=30)  # tipped 30 min ago -> still live
    rec = _rec("g", recent.isoformat(), GAME_STATE_LIVE)
    assert is_stale_record(rec, NOW) is False
    kept, _, _ = drop_stale_records([rec], [], [], now=NOW)
    assert len(kept) == 1


def test_future_pre_game_kept():
    future = NOW + timedelta(hours=6)
    rec = _rec("g", future.isoformat(), GAME_STATE_PRE)
    assert is_stale_record(rec, NOW) is False


def test_missing_tipoff_judged_by_state_only():
    assert tipoff_past_grace(None, NOW) is False
    assert is_stale_record(_rec("g", None, GAME_STATE_PRE), NOW) is False
    assert is_stale_record(_rec("g", None, GAME_STATE_POST), NOW) is True


# --- day rollover: yesterday's whole slate ages out ------------------------

def test_day_rollover_ages_out_yesterday_slate():
    # MLB-style slate: all yesterday (2026-06-20), all post. Tomorrow's now -> empty.
    recs = [_rec(f"g{i}", "2026-06-20T20:10Z", GAME_STATE_POST) for i in range(5)]
    mkts = [_mkt(f"g{i}") for i in range(5)]
    edges = [_edge(f"g{i}") for i in range(5)]
    kept, km, ke = drop_stale_records(recs, mkts, edges, now=NOW)
    assert kept == [] and km == [] and ke == []


def test_mixed_slate_keeps_only_future():
    stale = _rec("old", "2026-06-20T20:10Z", GAME_STATE_POST)
    live = _rec("live", (NOW - timedelta(minutes=20)).isoformat(), GAME_STATE_LIVE)
    fut = _rec("fut", (NOW + timedelta(hours=3)).isoformat(), GAME_STATE_PRE)
    kept, _, _ = drop_stale_records([stale, live, fut], [], [], now=NOW)
    assert {r.game_id for r in kept} == {"live", "fut"}


def test_naive_now_is_coerced_to_utc():
    naive = datetime(2026, 6, 21, 3, 0)  # no tzinfo
    rec = _rec("g", "2026-06-14T00:30Z", GAME_STATE_POST)
    kept, _, _ = drop_stale_records([rec], [], [], now=naive)
    assert kept == []
