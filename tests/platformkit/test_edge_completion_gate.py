"""Per-file tests for predict_service.edge_completion_gate.

Workstream BE-B-edge-completion-gate (QA iter 11 P1, iter 3 P1).

Acceptance criteria:
  (A) POST game: payload with game state 'post' + decision='bet' + stake_units 1.01
      + freshness {'status': 'fresh'} -> gate returns decision='no_bet',
      stake_units key absent, freshness.status='stale'.
  (B) UNKNOWN completion: no finals signal, fresh odds, future commence
      -> payload unchanged (no false suppression).
  (C) PREGAME FUTURE: future tipoff, no completion signal
      -> payload unchanged.
  (D) TIMEOUT arm: commence_time + DEFAULT_MAX_DURATION_H in the past
      -> suppressed.
  (E) FRESH ODDS but completed state -> freshness.status forced stale (stale-never-green).
  (F) No $ field in any gated or ungated payload.
  (G) suppressed=True and suppress_reason set when gated.
  (H) apply_games_gate gates only completed games in a mixed list.
  (I) game_id absent in payload -> passthrough (no false suppression).
  (J) freshness absent in payload -> stale sentinel dict added on suppression.
  (K) state_map arm: completed=True in state_map -> suppressed.
  (L) original payload dict is NOT mutated (deep copy contract).
  (M) Unknown state (no signal, no commence) -> passthrough (conservative).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    tests/platformkit/test_edge_completion_gate.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from predict_service.edge_completion_gate import (
    DEFAULT_MAX_DURATION_H,
    apply_game_gate,
    apply_games_gate,
)

# ------------------------------------------------------------------ #
# Fixtures / helpers                                                   #
# ------------------------------------------------------------------ #

_NOW = datetime(2026, 6, 19, 22, 0, 0, tzinfo=timezone.utc)
_FUTURE = "2026-06-19T23:30:00Z"          # 1.5 h from _NOW
_PAST_LONG = "2026-06-19T14:00:00Z"       # 8 h before _NOW (> 5 h)
_PAST_SHORT = "2026-06-19T21:30:00Z"      # 0.5 h before _NOW (< 5 h)


def _bet_payload(
    game_id: str = "401",
    decision: str = "bet",
    stake_units: float = 1.01,
    freshness_status: str = "fresh",
    tipoff: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a representative per-game edge/bestbets payload."""
    out: Dict[str, Any] = {
        "game_id": game_id,
        "home": "NYK",
        "away": "SAS",
        "decision": decision,
        "stake_units": stake_units,
        "freshness": {
            "status": freshness_status,
            "ok": freshness_status == "fresh",
            "fresh": freshness_status == "fresh",
            "stale": freshness_status != "fresh",
        },
        "model_prob": 0.62,
        "market_prob": 0.55,
        "edge_vs_market": 0.07,
        "tier": "B",
        "honest_note": "test",
    }
    if tipoff is not None:
        out["tipoff"] = tipoff
    out.update(extra)
    return out


def _finals_record(game_id: str, state: str = "post",
                   completed: bool = True) -> Dict[str, Any]:
    return {"game_id": game_id, "state": state, "completed": completed}


# ------------------------------------------------------------------ #
# (A) Core acceptance: post game suppressed                           #
# ------------------------------------------------------------------ #

class TestPostGameSuppressed:
    def test_decision_forced_no_bet(self):
        """(A) game state 'post' in finals -> decision='no_bet'."""
        p = _bet_payload(game_id="401", freshness_status="fresh")
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="401", finals=finals, now=_NOW)
        assert out["decision"] == "no_bet"

    def test_stake_units_removed(self):
        """(A) game state 'post' -> stake_units key absent in output."""
        p = _bet_payload(game_id="401", stake_units=1.01, freshness_status="fresh")
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="401", finals=finals, now=_NOW)
        assert "stake_units" not in out

    def test_freshness_status_forced_stale(self):
        """(A) game state 'post' + fresh odds -> freshness.status='stale'."""
        p = _bet_payload(game_id="401", freshness_status="fresh")
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="401", finals=finals, now=_NOW)
        assert isinstance(out.get("freshness"), dict)
        assert out["freshness"]["status"] == "stale"

    def test_freshness_ok_false(self):
        """(A) freshness.ok must be False on suppressed game."""
        p = _bet_payload(game_id="401", freshness_status="fresh")
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="401", finals=finals, now=_NOW)
        assert out["freshness"]["ok"] is False

    def test_suppressed_flag_set(self):
        """(G) suppressed=True and suppress_reason present."""
        p = _bet_payload(game_id="401")
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="401", finals=finals, now=_NOW)
        assert out.get("suppressed") is True
        assert isinstance(out.get("suppress_reason"), str)
        assert out["suppress_reason"]  # non-empty


# ------------------------------------------------------------------ #
# (B) Unknown completion -> no false suppression                      #
# ------------------------------------------------------------------ #

class TestUnknownCompletionPassthrough:
    def test_no_signal_future_commence_unchanged(self):
        """(B) No finals, fresh odds, future commence -> unchanged."""
        p = _bet_payload(game_id="402", freshness_status="fresh",
                         tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="402", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out
        assert out["freshness"]["status"] == "fresh"
        assert out.get("suppressed") is not True

    def test_no_commence_no_signal_unchanged(self):
        """(M) No commence, no signal -> passthrough (conservative)."""
        p = _bet_payload(game_id="403", freshness_status="fresh")
        out = apply_game_gate(p, game_id="403", finals=None, now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out

    def test_different_game_id_not_suppressed(self):
        """Non-matching game_id in finals -> not suppressed."""
        p = _bet_payload(game_id="999", freshness_status="fresh",
                         tipoff=_FUTURE)
        finals = [_finals_record("401", state="post", completed=True)]
        out = apply_game_gate(p, game_id="999", finals=finals, now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out


# ------------------------------------------------------------------ #
# (C) Pregame future -> unchanged                                     #
# ------------------------------------------------------------------ #

class TestPregameFutureUnchanged:
    def test_future_tipoff_no_suppression(self):
        """(C) Future tipoff, no finals entry -> unchanged."""
        p = _bet_payload(game_id="404", freshness_status="fresh",
                         tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="404", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert out["freshness"]["status"] == "fresh"

    def test_past_short_commence_not_timed_out(self):
        """Commence 0.5 h ago (< 5 h) -> timeout arm does NOT suppress."""
        p = _bet_payload(game_id="405", freshness_status="fresh",
                         tipoff=_PAST_SHORT)
        out = apply_game_gate(p, game_id="405", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out


# ------------------------------------------------------------------ #
# (D) Timeout arm                                                     #
# ------------------------------------------------------------------ #

class TestTimeoutArm:
    def test_past_long_commence_suppressed(self):
        """(D) 8 h past commence (> 5 h) -> timeout arm suppresses."""
        p = _bet_payload(game_id="406", freshness_status="fresh",
                         tipoff=_PAST_LONG)
        out = apply_game_gate(p, game_id="406", finals=[], now=_NOW,
                              commence_time=_PAST_LONG)
        assert out["decision"] == "no_bet"
        assert "stake_units" not in out
        assert out["freshness"]["status"] == "stale"

    def test_custom_max_duration_respected(self):
        """Custom max_duration_h=0.25 h triggers on 0.5 h old commence."""
        p = _bet_payload(game_id="407", freshness_status="fresh",
                         tipoff=_PAST_SHORT)
        out = apply_game_gate(p, game_id="407", finals=[], now=_NOW,
                              commence_time=_PAST_SHORT, max_duration_h=0.25)
        assert out["decision"] == "no_bet"
        assert "stake_units" not in out


# ------------------------------------------------------------------ #
# (E) Fresh odds + completed state -> stale-never-green              #
# ------------------------------------------------------------------ #

class TestFreshOddsButCompletedGame:
    def test_fresh_odds_completed_state_forces_stale(self):
        """(E) captured_at fresh, state='final' -> freshness.status='stale'."""
        p = _bet_payload(game_id="408", freshness_status="fresh")
        p["captured_at"] = "2026-06-19T21:59:00Z"  # very recent odds
        finals = [_finals_record("408", state="final", completed=True)]
        out = apply_game_gate(p, game_id="408", finals=finals, now=_NOW)
        assert out["freshness"]["status"] == "stale"
        assert out["decision"] == "no_bet"

    def test_completed_true_flag_alone_suppresses(self):
        """completed=True flag in finals -> suppressed even when state is not explicit."""
        p = _bet_payload(game_id="409", freshness_status="fresh")
        finals = [{"game_id": "409", "state": "in", "completed": True}]
        out = apply_game_gate(p, game_id="409", finals=finals, now=_NOW)
        assert out["decision"] == "no_bet"
        assert out["freshness"]["status"] == "stale"
        assert "stake_units" not in out


# ------------------------------------------------------------------ #
# (F) No $ field in any path                                         #
# ------------------------------------------------------------------ #

class TestNoDollarField:
    @pytest.mark.parametrize("scenario,payload,kwargs", [
        ("suppressed_finals",
         _bet_payload("S1"),
         {"game_id": "S1",
          "finals": [_finals_record("S1", state="post", completed=True)]}),
        ("suppressed_timeout",
         _bet_payload("S2", tipoff=_PAST_LONG),
         {"game_id": "S2", "commence_time": _PAST_LONG}),
        ("not_suppressed_future",
         _bet_payload("S3", tipoff=_FUTURE),
         {"game_id": "S3", "finals": []}),
        ("not_suppressed_no_signal",
         _bet_payload("S4"),
         {"game_id": "S4", "finals": None}),
    ])
    def test_no_dollar_sign(self, scenario, payload, kwargs):
        """(F) No $ character in output for any path."""
        out = apply_game_gate(payload, now=_NOW, **kwargs)
        serialized = json.dumps(out, ensure_ascii=True, default=str)
        assert "$" not in serialized, (
            "$ found in output for scenario %s: %s" % (scenario, serialized)
        )


# ------------------------------------------------------------------ #
# (H) apply_games_gate: only completed games gated in mixed list     #
# ------------------------------------------------------------------ #

class TestApplyGamesGate:
    def test_only_completed_gated(self):
        """(H) Mixed list: completed game gated, future game unchanged."""
        completed = _bet_payload("C1", tipoff="2026-06-18T20:00:00Z")
        future = _bet_payload("F1", tipoff=_FUTURE)
        finals = [_finals_record("C1", state="post", completed=True)]
        results = apply_games_gate(
            [completed, future], finals=finals, now=_NOW,
        )
        assert len(results) == 2
        c_out = next(r for r in results if r["game_id"] == "C1")
        f_out = next(r for r in results if r["game_id"] == "F1")
        assert c_out["decision"] == "no_bet"
        assert "stake_units" not in c_out
        assert f_out["decision"] == "bet"
        assert "stake_units" in f_out

    def test_empty_list_returns_empty(self):
        """Empty input -> empty output."""
        assert apply_games_gate([], finals=None, now=_NOW) == []


# ------------------------------------------------------------------ #
# (I) game_id absent -> passthrough                                   #
# ------------------------------------------------------------------ #

class TestNoGameId:
    def test_missing_game_id_passthrough(self):
        """(I) game_id absent in payload, none passed -> passthrough (conservative)."""
        p = _bet_payload("X")
        del p["game_id"]
        finals = [_finals_record("X", state="post", completed=True)]
        # game_id kwarg also absent
        out = apply_game_gate(p, finals=finals, now=_NOW)
        # Cannot evaluate completion without identity -> should not suppress
        assert out.get("decision") != "no_bet"
        assert out.get("suppressed") is not True
        # Core invariant: no raises, returns a dict
        assert isinstance(out, dict)


# ------------------------------------------------------------------ #
# (J) freshness absent -> stale sentinel added on suppression         #
# ------------------------------------------------------------------ #

class TestFreshnessAbsent:
    def test_no_freshness_key_gets_stale_sentinel(self):
        """(J) freshness key absent in payload -> stale sentinel dict added."""
        p = _bet_payload("410")
        del p["freshness"]
        finals = [_finals_record("410", state="post", completed=True)]
        out = apply_game_gate(p, game_id="410", finals=finals, now=_NOW)
        assert "freshness" in out
        assert isinstance(out["freshness"], dict)
        assert out["freshness"]["status"] == "stale"
        assert out["freshness"]["ok"] is False


# ------------------------------------------------------------------ #
# (K) state_map arm                                                   #
# ------------------------------------------------------------------ #

class TestStateMapArm:
    def test_state_map_completed_suppresses(self):
        """(K) completed=True in state_map -> suppressed."""
        p = _bet_payload("411", freshness_status="fresh", tipoff=_FUTURE)
        sm = {"411": {"completed": True, "state": "post"}}
        out = apply_game_gate(p, game_id="411", state_map=sm, now=_NOW)
        assert out["decision"] == "no_bet"
        assert "stake_units" not in out
        assert out["freshness"]["status"] == "stale"

    def test_state_map_live_not_suppressed(self):
        """state_map entry with completed=False and future commence -> not suppressed."""
        p = _bet_payload("412", freshness_status="fresh", tipoff=_FUTURE)
        sm = {"412": {"completed": False, "state": "in",
                      "commence_time": _FUTURE}}
        out = apply_game_gate(p, game_id="412", state_map=sm, now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out


# ------------------------------------------------------------------ #
# (L) Original payload NOT mutated (deep copy contract)               #
# ------------------------------------------------------------------ #

class TestDeepCopyContract:
    def test_original_unchanged_after_suppression(self):
        """(L) Original payload dict is NOT mutated when gate suppresses."""
        p = _bet_payload("413", decision="bet", stake_units=1.5,
                         freshness_status="fresh")
        original_decision = p["decision"]
        original_freshness_status = p["freshness"]["status"]
        finals = [_finals_record("413", state="post", completed=True)]
        _ = apply_game_gate(p, game_id="413", finals=finals, now=_NOW)
        # Original must be unchanged
        assert p["decision"] == original_decision
        assert p["freshness"]["status"] == original_freshness_status
        assert p["stake_units"] == 1.5  # still present on original

    def test_original_unchanged_on_passthrough(self):
        """(L) Original payload NOT mutated on passthrough path."""
        p = _bet_payload("414", decision="bet", freshness_status="fresh",
                         tipoff=_FUTURE)
        p_copy = dict(p)
        _ = apply_game_gate(p, game_id="414", finals=[], now=_NOW)
        assert p["decision"] == p_copy["decision"]
        assert p["freshness"]["status"] == p_copy["freshness"]["status"]


# ------------------------------------------------------------------ #
# STATUS_FINAL variants and other completed-state tokens              #
# ------------------------------------------------------------------ #

class TestCompletedStateTokens:
    @pytest.mark.parametrize("state", [
        "final", "post", "STATUS_FINAL", "STATUS_FULL_TIME",
        "STATUS_FINAL_PEN", "STATUS_FINAL_OVERTIME",
    ])
    def test_state_token_suppresses(self, state: str):
        """All canonical completed-state tokens trigger suppression."""
        p = _bet_payload("500", freshness_status="fresh", tipoff=_FUTURE)
        finals = [{"game_id": "500", "state": state, "completed": False}]
        out = apply_game_gate(p, game_id="500", finals=finals, now=_NOW)
        assert out["decision"] == "no_bet", (
            "state=%r should suppress but did not" % state
        )
        assert "stake_units" not in out
        assert out["freshness"]["status"] == "stale"
