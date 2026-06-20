"""predict_service.tests.test_produce_game_state -- BE-R3-1 acceptance tests.

Acceptance criteria (BE-R3-1-game-state-envelope):
  GS1. PredictionRecord.to_dict() includes 'game_state'.
  GS2. tipoff 6 days past + no live data -> game_state='post'.
  GS3. future tipoff (tomorrow) -> game_state='pre'.
  GS4. explicit live.state='post' in odds payload -> game_state='post'.
  GS5. explicit live.state='in_progress' -> game_state='live'.
  GS6. tipoff within typical game duration -> game_state='live'.
  GS7. no tipoff (None) -> game_state='pre' (safe default).
  GS8. PredictionRecord.to_dict() has NO $ field (honesty invariant preserved).
  GS9. PredictionRecord.from_dict() round-trips game_state unchanged.
  GS10. unknown game_state from_dict degrades safely to 'pre'.

Run (per-file only -- never run the full suite, it freezes the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_produce_game_state.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.contracts import (  # noqa: E402
    GAME_STATE_LIVE,
    GAME_STATE_POST,
    GAME_STATE_PRE,
    VALID_GAME_STATES,
    PredictionRecord,
)
from predict_service.produce import (  # noqa: E402
    _derive_game_state,
    _live_state_for,
    _record_for_game,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tipoff_past(days: float = 0.0, hours: float = 0.0) -> str:
    """Return an ISO-8601 tipoff that is *days* days + *hours* hours in the past."""
    dt = _now() - timedelta(days=days, hours=hours)
    return _iso(dt)


def _tipoff_future(hours: float = 3.0) -> str:
    """Return an ISO-8601 tipoff that is *hours* hours in the future."""
    dt = _now() + timedelta(hours=hours)
    return _iso(dt)


def _minimal_record(tipoff: Optional[str] = None,
                    game_state: str = GAME_STATE_PRE) -> PredictionRecord:
    return PredictionRecord(
        sport="nba",
        game_id="test_game_1",
        home="LAL",
        away="BOS",
        tipoff=tipoff,
        pregame_probs={"home_ml": 0.55},
        game_state=game_state,
        produced_at=_iso(_now()),
    )


def _has_dollar_key(obj: object) -> bool:
    if isinstance(obj, dict):
        return any("$" in str(k) or _has_dollar_key(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_dollar_key(i) for i in obj)
    return False


def _minimal_predict_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
    """Fake predict_fn that returns a usable pregame block."""
    return {"pregame": {"p_home_win": 0.55}}


def _payload_with_live_state(home: str, away: str,
                              live_state: str,
                              tipoff: Optional[str] = None) -> Dict[str, Any]:
    """Build a minimal aggregate payload with a live block for one event."""
    return {
        "events": [
            {
                "home": home,
                "away": away,
                "event_id": "ev1",
                "commence_time": tipoff or _tipoff_past(days=0.0, hours=2.5),
                "prices": {},
                "live": {"state": live_state},
            }
        ],
        "as_of": _iso(_now()),
    }


# ---------------------------------------------------------------------------
# GS1: to_dict() includes 'game_state'
# ---------------------------------------------------------------------------

def test_gs1_to_dict_includes_game_state():
    rec = _minimal_record(game_state=GAME_STATE_PRE)
    d = rec.to_dict()
    assert "game_state" in d, "GS1: 'game_state' must be present in to_dict() output"
    assert d["game_state"] == GAME_STATE_PRE


# ---------------------------------------------------------------------------
# GS2: tipoff 6 days past + no live data -> 'post'
# ---------------------------------------------------------------------------

def test_gs2_old_tipoff_no_live_is_post():
    tipoff = _tipoff_past(days=6)
    state = _derive_game_state(tipoff, live_state=None)
    assert state == GAME_STATE_POST, (
        "GS2: tipoff 6 days past + no live data must give game_state='post', "
        "got %r" % state
    )


# ---------------------------------------------------------------------------
# GS3: future tipoff -> 'pre'
# ---------------------------------------------------------------------------

def test_gs3_future_tipoff_is_pre():
    tipoff = _tipoff_future(hours=3)
    state = _derive_game_state(tipoff, live_state=None)
    assert state == GAME_STATE_PRE, (
        "GS3: future tipoff must give game_state='pre', got %r" % state
    )


# ---------------------------------------------------------------------------
# GS4: explicit live.state='post' -> 'post' (beats any heuristic)
# ---------------------------------------------------------------------------

def test_gs4_explicit_live_state_post():
    # tipoff is recent (would normally be 'live' by heuristic)
    tipoff = _tipoff_past(hours=1)
    state = _derive_game_state(tipoff, live_state="post")
    assert state == GAME_STATE_POST, (
        "GS4: explicit live_state='post' must give game_state='post', got %r" % state
    )


@pytest.mark.parametrize("ls", ["final", "ft", "complete", "finished", "closed"])
def test_gs4_explicit_post_synonyms(ls: str):
    tipoff = _tipoff_past(hours=1)
    state = _derive_game_state(tipoff, live_state=ls)
    assert state == GAME_STATE_POST, (
        "GS4: live_state=%r must map to 'post', got %r" % (ls, state)
    )


# ---------------------------------------------------------------------------
# GS5: explicit live.state='in_progress' -> 'live'
# ---------------------------------------------------------------------------

def test_gs5_explicit_live_state_in_progress():
    tipoff = _tipoff_past(hours=1)
    state = _derive_game_state(tipoff, live_state="in_progress")
    assert state == GAME_STATE_LIVE, (
        "GS5: live_state='in_progress' must give 'live', got %r" % state
    )


@pytest.mark.parametrize("ls", ["live", "in_progress", "inprogress",
                                  "half_time", "halftime"])
def test_gs5_explicit_live_synonyms(ls: str):
    tipoff = _tipoff_past(hours=1)
    state = _derive_game_state(tipoff, live_state=ls)
    assert state == GAME_STATE_LIVE, (
        "GS5: live_state=%r must map to 'live', got %r" % (ls, state)
    )


# ---------------------------------------------------------------------------
# GS6: tipoff within typical duration -> 'live' (heuristic path)
# ---------------------------------------------------------------------------

def test_gs6_tipoff_within_duration_is_live():
    tipoff = _tipoff_past(hours=1)  # 1 h ago, well within 2.5 h window
    state = _derive_game_state(tipoff, live_state=None)
    assert state == GAME_STATE_LIVE, (
        "GS6: tipoff 1 h past + no live_state must give 'live', got %r" % state
    )


# ---------------------------------------------------------------------------
# GS7: no tipoff (None) -> 'pre'
# ---------------------------------------------------------------------------

def test_gs7_none_tipoff_is_pre():
    state = _derive_game_state(None, live_state=None)
    assert state == GAME_STATE_PRE, (
        "GS7: None tipoff must give game_state='pre', got %r" % state
    )


def test_gs7_empty_string_tipoff_is_pre():
    state = _derive_game_state("", live_state=None)
    assert state == GAME_STATE_PRE, (
        "GS7: empty tipoff string must give game_state='pre', got %r" % state
    )


# ---------------------------------------------------------------------------
# GS8: to_dict() has NO $ field (honesty invariant preserved)
# ---------------------------------------------------------------------------

def test_gs8_no_dollar_field_in_to_dict():
    rec = _minimal_record(tipoff=_tipoff_future(), game_state=GAME_STATE_PRE)
    d = rec.to_dict()
    assert not _has_dollar_key(d), (
        "GS8: to_dict() must contain no $ key (honesty invariant)"
    )


# ---------------------------------------------------------------------------
# GS9: from_dict() round-trips game_state unchanged
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gs", list(VALID_GAME_STATES))
def test_gs9_round_trip_game_state(gs: str):
    rec = _minimal_record(game_state=gs)
    d = rec.to_dict()
    assert d["game_state"] == gs, "GS9: to_dict() must preserve game_state=%r" % gs
    rec2 = PredictionRecord.from_dict(d)
    assert rec2.game_state == gs, (
        "GS9: from_dict() must restore game_state=%r, got %r" % (gs, rec2.game_state)
    )


# ---------------------------------------------------------------------------
# GS10: unknown game_state in from_dict -> degrades safely to 'pre'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_gs", [None, "", "unknown", "LIVE", "Post", 42, object()])
def test_gs10_unknown_game_state_degrades_to_pre(bad_gs: Any):
    d = _minimal_record().to_dict()
    d["game_state"] = bad_gs
    try:
        rec = PredictionRecord.from_dict(d)
        assert rec.game_state == GAME_STATE_PRE, (
            "GS10: unknown game_state=%r must degrade to 'pre', got %r"
            % (bad_gs, rec.game_state)
        )
    except Exception as exc:
        pytest.fail(
            "GS10: from_dict() raised on bad game_state=%r: %s" % (bad_gs, exc)
        )


# ---------------------------------------------------------------------------
# Integration: _record_for_game wires game_state correctly
# ---------------------------------------------------------------------------

def test_integration_record_for_game_post():
    """_record_for_game must emit game_state='post' for a finished game.

    The assemble functions are imported directly into produce's namespace, so
    they must be patched there (predict_service.produce.*), not on the source
    module.
    """
    tipoff = _tipoff_past(days=6)
    game = {"game_id": "g1", "home": "LAL", "away": "BOS", "tipoff": tipoff}
    payload = {"events": [], "as_of": _iso(_now())}

    with patch("predict_service.produce.pregame_probs_record",
               return_value={"home_ml": 0.55}), \
         patch("predict_service.produce.model_probs_from_pregame",
               return_value={"home_ml": 0.55}), \
         patch("predict_service.produce.market_rows", return_value=[]), \
         patch("predict_service.produce.edge_rows", return_value=[]):
        built = _record_for_game(
            "nba", game, payload, _minimal_predict_fn, _iso(_now()))

    assert built is not None, "Integration: _record_for_game must not return None"
    rec: PredictionRecord = built["record"]
    assert rec.game_state == GAME_STATE_POST, (
        "Integration: finished game (6 days past) must have game_state='post', "
        "got %r" % rec.game_state
    )
    d = rec.to_dict()
    assert d["game_state"] == GAME_STATE_POST


def test_integration_record_for_game_live_state_override():
    """_record_for_game must emit game_state='post' when live.state='final'."""
    tipoff = _tipoff_past(hours=2)  # would be 'live' by heuristic
    home, away = "LAL", "BOS"
    payload = _payload_with_live_state(home, away, "final", tipoff=tipoff)
    game = {"game_id": "g2", "home": home, "away": away, "tipoff": tipoff}

    with patch("predict_service.produce.pregame_probs_record",
               return_value={"home_ml": 0.55}), \
         patch("predict_service.produce.model_probs_from_pregame",
               return_value={"home_ml": 0.55}), \
         patch("predict_service.produce.market_rows", return_value=[]), \
         patch("predict_service.produce.edge_rows", return_value=[]):
        built = _record_for_game(
            "nba", game, payload, _minimal_predict_fn, _iso(_now()))

    assert built is not None
    rec: PredictionRecord = built["record"]
    assert rec.game_state == GAME_STATE_POST, (
        "Integration: live.state='final' must override heuristic to 'post', "
        "got %r" % rec.game_state
    )
