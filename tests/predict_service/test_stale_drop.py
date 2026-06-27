"""Per-file tests for predict_service.stale_drop (STALE-NEVER-GREEN + live-keep).

The two invariants this guards (the second is the REGRESSION fix):
  * a FINISHED game (game_state == 'post') is ALWAYS purged so it never shows as a
    current prediction (the NBA-finished-row fix must hold);
  * a LIVE (in-progress) game is NEVER purged -- its record (and thus its leak-free
    pregame prior) MUST survive so the in-game pregame_carry path can reprice it.
    Before the fix, a live game whose tipoff was past the (small) grace was dropped,
    its prior vanished from latest.json, and live MLB games were not repriced.

Run (per-file ONLY -- a full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/predict_service/test_stale_drop.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from predict_service.contracts import (
    GAME_STATE_LIVE,
    GAME_STATE_POST,
    GAME_STATE_PRE,
    PredictionRecord,
)
from predict_service.stale_drop import (
    PAST_TIPOFF_GRACE_SECONDS,
    drop_stale_records,
    is_stale_record,
)

_NOW = datetime(2026, 6, 21, 2, 0, 0, tzinfo=timezone.utc)


def _rec(game_id: str, *, game_state: str, tipoff_offset_sec: float) -> PredictionRecord:
    """A record whose tipoff is *tipoff_offset_sec* seconds BEFORE _NOW (positive =
    in the past). game_state is the producer-derived authoritative state."""
    tip = (_NOW - timedelta(seconds=tipoff_offset_sec)).isoformat()
    return PredictionRecord(
        sport="mlb", game_id=game_id, home="NYY", away="BOS",
        tipoff=tip, pregame_probs={"home_ml": 0.57, "away_ml": 0.43},
        game_state=game_state)


# ---- the REGRESSION fix: a started-but-LIVE game keeps its record + prior -----

def test_live_game_past_short_grace_is_kept():
    """A live game whose tipoff is hours in the past (a long MLB game / extra
    innings) is NOT stale -- it is in progress, so its prior must survive."""
    # 3h after tipoff: past the OLD short grace, but the game is explicitly live.
    rec = _rec("LIVE1", game_state=GAME_STATE_LIVE, tipoff_offset_sec=3 * 3600)
    assert is_stale_record(rec, _NOW) is False
    kept, _, _ = drop_stale_records([rec], [], [], now=_NOW)
    assert [r.game_id for r in kept] == ["LIVE1"]
    # The leak-free pregame prior is still present on the surviving record.
    assert kept[0].pregame_probs.get("home_ml") == 0.57


def test_live_game_keeps_prior_while_finished_sibling_is_purged():
    """End-to-end on the slate: a live game stays (prior available for the in-game
    carry) while a finished sibling is purged (finished-as-prediction fix holds)."""
    live = _rec("LIVE1", game_state=GAME_STATE_LIVE, tipoff_offset_sec=3 * 3600)
    done = _rec("DONE1", game_state=GAME_STATE_POST, tipoff_offset_sec=4 * 3600)
    kept, mkts, edges = drop_stale_records([live, done], [], [], now=_NOW)
    ids = {r.game_id for r in kept}
    assert "LIVE1" in ids            # live kept -> prior survives -> repriceable
    assert "DONE1" not in ids        # finished purged -> never shown as prediction


# ---- the existing finished-game purge MUST still hold ------------------------

def test_post_game_is_always_stale():
    """A finished ('post') game is purged even if its tipoff is recent."""
    rec = _rec("DONE1", game_state=GAME_STATE_POST, tipoff_offset_sec=10 * 60)
    assert is_stale_record(rec, _NOW) is True
    kept, _, _ = drop_stale_records([rec], [], [], now=_NOW)
    assert kept == []


def test_post_game_drops_its_markets_and_edges():
    """A dropped game leaves nothing behind on the surface (markets/edges gated)."""
    class _M:
        def __init__(self, gid):
            self.game_id = gid

    live = _rec("LIVE1", game_state=GAME_STATE_LIVE, tipoff_offset_sec=30 * 60)
    done = _rec("DONE1", game_state=GAME_STATE_POST, tipoff_offset_sec=30 * 60)
    mkts = [_M("LIVE1"), _M("DONE1")]
    edges = [_M("DONE1")]
    kept, kmkts, kedges = drop_stale_records([live, done], mkts, edges, now=_NOW)
    assert {r.game_id for r in kept} == {"LIVE1"}
    assert {m.game_id for m in kmkts} == {"LIVE1"}
    assert kedges == []  # the only edge belonged to the dropped finished game


# ---- a genuinely abandoned (non-live) past-tipoff game still ages out --------

def test_pre_game_past_generous_grace_is_stale():
    """A 'pre' record that never got a live/post signal, well past the grace, is an
    abandoned/stale row and ages out (stale-never-green)."""
    rec = _rec("OLD1", game_state=GAME_STATE_PRE,
               tipoff_offset_sec=PAST_TIPOFF_GRACE_SECONDS + 600)
    assert is_stale_record(rec, _NOW) is True


def test_pre_game_before_grace_is_kept():
    """A 'pre' record whose tipoff just passed (within grace) is kept (it may be a
    just-started game whose live signal has not arrived yet)."""
    rec = _rec("FRESH1", game_state=GAME_STATE_PRE, tipoff_offset_sec=10 * 60)
    assert is_stale_record(rec, _NOW) is False
