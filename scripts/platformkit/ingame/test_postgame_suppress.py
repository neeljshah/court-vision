"""Per-file tests for postgame_suppress.py -- post-game suppression verdict.

Workstream R6-1-postgame-suppress.

Acceptance criteria:
  (A) game with state='post' in finals list  -> suppress_bet=True, freshness='stale',
      reason='game_complete_finals_list'  regardless of commence_time or captured_at.
  (B) game with completed=True in finals list -> suppress_bet=True.
  (C) game with state='final' (case-insensitive) -> suppress_bet=True.
  (D) live/scheduled game (no finals entry, future commence) -> suppress_bet=False.
  (E) missing state with FUTURE commence -> NOT suppressed (timeout arm safe).
  (F) commence_time + MAX_GAME_DURATION_H < now -> suppress_bet=True, reason=timeout.
  (G) commence_time in future -> NOT suppressed by timeout arm.
  (H) missing commence_time (no state_map entry) -> timeout arm skipped -> not suppressed.
  (I) state_map arm: completed=True in state_map -> suppressed.
  (J) no $ field in any verdict path.
  (K) STATUS_FINAL_OVERTIME in state -> suppressed.
  (L) empty finals list + no commence -> not suppressed.
  (M) non-matching game_id in finals list -> not suppressed.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_postgame_suppress.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.ingame.postgame_suppress import (
    MAX_GAME_DURATION_H,
    suppress_verdict,
)

# Pinned reference "now" for all deterministic tests.
_NOW = datetime(2026, 6, 19, 22, 0, 0, tzinfo=timezone.utc)

# A future commence time (2 h from _NOW).
_FUTURE = "2026-06-19T23:30:00Z"
# A past commence time long enough to exceed timeout (8 h before _NOW).
_PAST_LONG = "2026-06-19T14:00:00Z"
# A commence time just 1 h before _NOW (inside the max_game_duration window).
_PAST_SHORT = "2026-06-19T21:00:00Z"


# --------------------------------------------------------------------------- #
# Arm 1: finals list                                                           #
# --------------------------------------------------------------------------- #

class TestFinalsListArm:
    def test_state_post_suppressed(self):
        """(A) state='post' in finals list -> suppressed."""
        finals = [{"game_id": "123", "state": "post", "completed": False}]
        v = suppress_verdict("123", finals=finals, now=_NOW)
        assert v["suppress_bet"] is True
        assert v["freshness"] == "stale"
        assert v["reason"] == "game_complete_finals_list"

    def test_completed_true_suppressed(self):
        """(B) completed=True in finals list -> suppressed."""
        finals = [{"game_id": "456", "state": "in", "completed": True}]
        v = suppress_verdict("456", finals=finals, now=_NOW)
        assert v["suppress_bet"] is True

    def test_state_final_suppressed(self):
        """(C) state='final' (case-insensitive) -> suppressed."""
        finals = [{"game_id": "789", "state": "final", "completed": False}]
        v = suppress_verdict("789", finals=finals, now=_NOW)
        assert v["suppress_bet"] is True

    def test_status_final_overtime_suppressed(self):
        """(K) STATUS_FINAL_OVERTIME in state -> suppressed."""
        finals = [{"game_id": "999", "state": "STATUS_FINAL_OVERTIME",
                   "completed": False}]
        v = suppress_verdict("999", finals=finals, now=_NOW)
        assert v["suppress_bet"] is True

    def test_non_matching_game_id_not_suppressed(self):
        """(M) game_id not in finals list -> not suppressed."""
        finals = [{"game_id": "111", "state": "post", "completed": True}]
        v = suppress_verdict("999", finals=finals, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is False

    def test_empty_finals_not_suppressed(self):
        """(L) empty finals list + no commence -> not suppressed."""
        v = suppress_verdict("123", finals=[], now=_NOW)
        assert v["suppress_bet"] is False

    def test_live_game_not_suppressed(self):
        """(D) live/in-progress game without completed flag -> not suppressed."""
        finals = [{"game_id": "321", "state": "in", "completed": False}]
        v = suppress_verdict("321", finals=finals, now=_NOW,
                             commence_time=_PAST_SHORT)
        assert v["suppress_bet"] is False
        assert v["freshness"] == "live"


# --------------------------------------------------------------------------- #
# Arm 2: state_map                                                             #
# --------------------------------------------------------------------------- #

class TestStateMapArm:
    def test_completed_true_in_state_map(self):
        """(I) completed=True in state_map -> suppressed."""
        sm = {"123": {"completed": True, "state": "post"}}
        v = suppress_verdict("123", state_map=sm, now=_NOW)
        assert v["suppress_bet"] is True
        assert v["reason"] == "game_complete_state_map"

    def test_state_map_live_not_suppressed(self):
        """state_map with completed=False and state='in' -> not suppressed."""
        sm = {"123": {"completed": False, "state": "in"}}
        v = suppress_verdict("123", state_map=sm, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is False

    def test_state_map_missing_key_not_suppressed(self):
        """game_id not in state_map -> not suppressed by state_map arm."""
        sm = {"999": {"completed": True, "state": "post"}}
        v = suppress_verdict("123", state_map=sm, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is False


# --------------------------------------------------------------------------- #
# Arm 3: timeout                                                               #
# --------------------------------------------------------------------------- #

class TestTimeoutArm:
    def test_past_long_suppressed(self):
        """(F) commence + MAX_GAME_DURATION_H < now -> suppressed by timeout."""
        # _PAST_LONG = 14:00; _NOW = 22:00; gap = 8 h > 5 h default
        v = suppress_verdict("X1", commence_time=_PAST_LONG, now=_NOW)
        assert v["suppress_bet"] is True
        assert v["reason"] == "game_complete_timeout"
        assert v["freshness"] == "stale"

    def test_future_commence_not_suppressed(self):
        """(G) future commence -> timeout arm does NOT suppress."""
        v = suppress_verdict("X2", commence_time=_FUTURE, now=_NOW)
        assert v["suppress_bet"] is False

    def test_within_duration_not_suppressed(self):
        """commence 1 h before now, duration 5 h -> still within window."""
        # _PAST_SHORT = 21:00; _NOW = 22:00; deadline = 21:00 + 5h = 02:00 next day
        v = suppress_verdict("X3", commence_time=_PAST_SHORT, now=_NOW)
        assert v["suppress_bet"] is False

    def test_missing_commence_not_suppressed(self):
        """(H) no commence_time -> timeout arm skipped -> not suppressed."""
        v = suppress_verdict("X4", now=_NOW)
        assert v["suppress_bet"] is False

    def test_future_commence_in_state_map_not_suppressed(self):
        """(E) missing explicit state, future commence in state_map -> not suppressed."""
        sm = {"X5": {"completed": False, "state": "pre",
                     "commence_time": _FUTURE}}
        v = suppress_verdict("X5", state_map=sm, now=_NOW)
        assert v["suppress_bet"] is False

    def test_commence_from_state_map(self):
        """Timeout arm reads commence_time from state_map when not passed directly."""
        sm = {"X6": {"completed": False, "state": "pre",
                     "commence_time": _PAST_LONG}}
        v = suppress_verdict("X6", state_map=sm, now=_NOW)
        assert v["suppress_bet"] is True
        assert v["reason"] == "game_complete_timeout"

    def test_custom_max_duration(self):
        """Custom max_game_duration_h overrides the default."""
        # _PAST_SHORT is 1 h before now; with max=0.5h it should suppress
        v = suppress_verdict("X7", commence_time=_PAST_SHORT, now=_NOW,
                             max_game_duration_h=0.5)
        assert v["suppress_bet"] is True
        # With max=2h it should NOT suppress (1 h < 2 h)
        v2 = suppress_verdict("X7", commence_time=_PAST_SHORT, now=_NOW,
                              max_game_duration_h=2.0)
        assert v2["suppress_bet"] is False


# --------------------------------------------------------------------------- #
# Priority ordering (finals list beats timeout, state_map beats timeout)      #
# --------------------------------------------------------------------------- #

class TestPriorityOrdering:
    def test_finals_beats_timeout(self):
        """finals list suppresses even when commence is in the future."""
        finals = [{"game_id": "P1", "state": "post", "completed": True}]
        v = suppress_verdict("P1", finals=finals, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is True
        assert v["reason"] == "game_complete_finals_list"

    def test_state_map_beats_timeout(self):
        """state_map suppresses even when commence is in the future."""
        sm = {"P2": {"completed": True, "state": "post",
                     "commence_time": _FUTURE}}
        v = suppress_verdict("P2", state_map=sm, now=_NOW)
        assert v["suppress_bet"] is True
        assert v["reason"] == "game_complete_state_map"


# --------------------------------------------------------------------------- #
# Honesty: no $ field                                                          #
# --------------------------------------------------------------------------- #

class TestNoMoneyField:
    @pytest.mark.parametrize("scenario,kwargs", [
        ("suppressed_finals",
         {"finals": [{"game_id": "A", "state": "post", "completed": True}]}),
        ("suppressed_timeout",
         {"commence_time": _PAST_LONG}),
        ("not_suppressed",
         {"commence_time": _FUTURE}),
        ("not_suppressed_empty",
         {}),
    ])
    def test_no_dollar_sign(self, scenario, kwargs):
        """(J) No $ field in any verdict path."""
        import json
        v = suppress_verdict("A", now=_NOW, **kwargs)
        serialized = json.dumps(v, ensure_ascii=True)
        assert "$" not in serialized, (
            "$ field found in verdict for scenario %s: %s" % (scenario, serialized)
        )

    def test_verdict_keys_only(self):
        """Verdict contains exactly the documented keys."""
        v = suppress_verdict("X", now=_NOW)
        assert set(v.keys()) == {"suppress_bet", "freshness", "reason"}


# --------------------------------------------------------------------------- #
# Edge cases                                                                   #
# --------------------------------------------------------------------------- #

class TestEdgeCases:
    def test_none_finals_not_suppressed(self):
        """finals=None is safe (treated as no finals data)."""
        v = suppress_verdict("E1", finals=None, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is False

    def test_none_state_map_not_suppressed(self):
        """state_map=None is safe."""
        v = suppress_verdict("E2", state_map=None, now=_NOW,
                             commence_time=_FUTURE)
        assert v["suppress_bet"] is False

    def test_garbage_finals_entry_skipped(self):
        """Non-dict entries in finals list are skipped, not raised."""
        finals = [None, "not-a-dict", 42,
                  {"game_id": "E3", "state": "post", "completed": True}]
        v = suppress_verdict("E3", finals=finals, now=_NOW)  # type: ignore[arg-type]
        assert v["suppress_bet"] is True

    def test_bad_commence_string_not_suppressed(self):
        """Unparseable commence_time -> timeout arm skipped -> not suppressed."""
        v = suppress_verdict("E4", commence_time="not-a-date", now=_NOW)
        assert v["suppress_bet"] is False

    def test_game_id_string_coercion(self):
        """game_id is coerced to str so int-keyed finals lists work."""
        finals = [{"game_id": 123, "state": "post", "completed": True}]
        v = suppress_verdict("123", finals=finals, now=_NOW)
        assert v["suppress_bet"] is True

    def test_freshness_live_when_not_suppressed(self):
        """Not-suppressed verdict always returns freshness='live'."""
        v = suppress_verdict("L1", finals=[], now=_NOW, commence_time=_FUTURE)
        assert v["freshness"] == "live"

    def test_freshness_stale_when_suppressed(self):
        """Suppressed verdict always returns freshness='stale'."""
        finals = [{"game_id": "S1", "state": "post", "completed": True}]
        v = suppress_verdict("S1", finals=finals, now=_NOW)
        assert v["freshness"] == "stale"
