"""predict_service.tests.test_edge_completion_gate_postgame -- BE-R3-2 tests.

Acceptance criteria (QA iter 231/279 -- per-game edges/bestbets postgame gate):

  PG1. game_state='post' in payload -> freshness=stale, decision=no_bet,
       stake_units absent, tier absent, skip_reason='game_final'.
  PG2. game_state='live' (no finals, no timeout) -> payload UNCHANGED (not suppressed).
  PG3. game_state='pre' (no finals, no timeout) -> payload UNCHANGED.
  PG4. game_state absent, finals match -> suppressed (fallback arms intact).
  PG5. game_state absent, timeout arm -> suppressed.
  PG6. gate_decide_payload() alias matches apply_game_gate() on post game.
  PG7. No $ field in suppressed or live output.
  PG8. Original payload NOT mutated (deep copy contract).
  PG9. stake_units absent on suppressed; present on live.
  PG10. tier absent on suppressed; present on live.
  PG11. skip_reason='game_final' on suppressed.
  PG12. suppressed=True on suppressed; not set on live.
  PG13. Mixed list via apply_games_gate: post game suppressed, live game unchanged.

Run (per-file only):
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest predict_service/tests/test_edge_completion_gate_postgame.py -q
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

# Ensure repo root is on sys.path.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.edge_completion_gate import (  # noqa: E402
    DEFAULT_MAX_DURATION_H,
    apply_game_gate,
    apply_games_gate,
    gate_decide_payload,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 20, 22, 0, 0, tzinfo=timezone.utc)
_FUTURE = "2026-06-20T23:30:00Z"       # 1.5 h ahead of _NOW
_PAST_LONG = "2026-06-20T14:00:00Z"    # 8 h before _NOW (> DEFAULT_MAX_DURATION_H)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _game(
    game_id: str = "401",
    game_state: Optional[str] = None,
    decision: str = "bet",
    stake_units: float = 1.0,
    tier: str = "B",
    freshness_status: str = "fresh",
    tipoff: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a minimal per-game payload as produced by decide_game() / edge_api."""
    p: Dict[str, Any] = {
        "game_id": game_id,
        "home": "NYK",
        "away": "SAS",
        "decision": decision,
        "stake_units": stake_units,
        "tier": tier,
        "freshness": {
            "status": freshness_status,
            "ok": freshness_status == "fresh",
            "fresh": freshness_status == "fresh",
            "stale": freshness_status != "fresh",
        },
        "model_prob": 0.62,
        "market_prob": 0.55,
        "ev": 0.06,
        "honest_note": "test",
    }
    if game_state is not None:
        p["game_state"] = game_state
    if tipoff is not None:
        p["tipoff"] = tipoff
    p.update(extra)
    return p


def _finals_rec(game_id: str, state: str = "post",
                completed: bool = True) -> Dict[str, Any]:
    return {"game_id": game_id, "state": state, "completed": completed}


# ---------------------------------------------------------------------------
# PG1: game_state='post' -> fully suppressed
# ---------------------------------------------------------------------------

class TestGameStatePost:
    def test_decision_no_bet(self):
        """PG1: game_state='post' -> decision='no_bet'."""
        p = _game("401", game_state="post")
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert out["decision"] == "no_bet"

    def test_freshness_stale(self):
        """PG1: game_state='post' -> freshness.status='stale'."""
        p = _game("401", game_state="post")
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert out.get("freshness", {}).get("status") == "stale"
        assert out["freshness"]["ok"] is False

    def test_stake_units_absent(self):
        """PG9: stake_units key REMOVED on suppressed game."""
        p = _game("401", game_state="post", stake_units=1.5)
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert "stake_units" not in out

    def test_tier_absent(self):
        """PG10: tier key REMOVED on suppressed game (no tier on a settled game)."""
        p = _game("401", game_state="post", tier="A")
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert "tier" not in out

    def test_skip_reason_game_final(self):
        """PG11: skip_reason='game_final' on suppressed game."""
        p = _game("401", game_state="post")
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert out.get("skip_reason") == "game_final"

    def test_suppressed_flag(self):
        """PG12: suppressed=True and suppress_reason set."""
        p = _game("401", game_state="post")
        out = apply_game_gate(p, game_id="401", now=_NOW)
        assert out.get("suppressed") is True
        assert isinstance(out.get("suppress_reason"), str)
        assert out["suppress_reason"]


# ---------------------------------------------------------------------------
# PG2/PG3: live and pre games are not suppressed
# ---------------------------------------------------------------------------

class TestLiveAndPreGameUntouched:
    def test_live_game_unchanged(self):
        """PG2: game_state='live' + no other signal -> decision unchanged."""
        p = _game("402", game_state="live", tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="402", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out
        assert "tier" in out
        assert out["freshness"]["status"] == "fresh"
        assert out.get("suppressed") is not True

    def test_pre_game_unchanged(self):
        """PG3: game_state='pre' + no other signal -> decision unchanged."""
        p = _game("403", game_state="pre", tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="403", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out
        assert "tier" in out

    def test_no_game_state_future_tipoff_unchanged(self):
        """No game_state field, future tipoff, no finals -> unchanged."""
        p = _game("404", tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="404", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out


# ---------------------------------------------------------------------------
# PG4/PG5: fallback arms still work when game_state absent
# ---------------------------------------------------------------------------

class TestFallbackArms:
    def test_finals_arm_suppresses_without_game_state(self):
        """PG4: game_state absent, finals match -> suppressed via fallback."""
        p = _game("405")          # no game_state key
        p.pop("game_state", None)
        finals = [_finals_rec("405", state="post", completed=True)]
        out = apply_game_gate(p, game_id="405", finals=finals, now=_NOW)
        assert out["decision"] == "no_bet"
        assert "stake_units" not in out
        assert out["freshness"]["status"] == "stale"

    def test_timeout_arm_suppresses_without_game_state(self):
        """PG5: game_state absent, old tipoff -> timeout arm suppresses."""
        p = _game("406", tipoff=_PAST_LONG)
        p.pop("game_state", None)
        out = apply_game_gate(p, game_id="406", finals=[], now=_NOW,
                              commence_time=_PAST_LONG)
        assert out["decision"] == "no_bet"
        assert "stake_units" not in out
        assert out["freshness"]["status"] == "stale"


# ---------------------------------------------------------------------------
# PG6: gate_decide_payload alias
# ---------------------------------------------------------------------------

class TestGateDecidePayloadAlias:
    def test_alias_matches_apply_game_gate_on_post(self):
        """PG6: gate_decide_payload result matches apply_game_gate on post game."""
        p = _game("407", game_state="post")
        via_gate = apply_game_gate(p, game_id="407", now=_NOW)
        via_alias = gate_decide_payload(p, game_id="407", now=_NOW)
        # Both should suppress
        assert via_gate["decision"] == "no_bet"
        assert via_alias["decision"] == "no_bet"
        assert via_gate.get("skip_reason") == via_alias.get("skip_reason")

    def test_alias_live_game_unchanged(self):
        """gate_decide_payload: live game returned unchanged."""
        p = _game("408", game_state="live", tipoff=_FUTURE)
        out = gate_decide_payload(p, game_id="408", finals=[], now=_NOW)
        assert out["decision"] == "bet"
        assert "stake_units" in out


# ---------------------------------------------------------------------------
# PG7: no $ field in any path
# ---------------------------------------------------------------------------

class TestNoDollarField:
    @pytest.mark.parametrize("game_state,suppressed", [
        ("post", True),
        ("live", False),
        ("pre", False),
    ])
    def test_no_dollar_sign(self, game_state, suppressed):
        """PG7: No $ character in output for any game_state."""
        p = _game("500", game_state=game_state, tipoff=_FUTURE)
        out = apply_game_gate(p, game_id="500", finals=[], now=_NOW)
        serialized = json.dumps(out, ensure_ascii=True, default=str)
        assert "$" not in serialized


# ---------------------------------------------------------------------------
# PG8: deep copy contract -- original NOT mutated
# ---------------------------------------------------------------------------

class TestDeepCopyContract:
    def test_post_game_original_not_mutated(self):
        """PG8: Suppressing a post game does NOT mutate the original payload."""
        p = _game("501", game_state="post", stake_units=2.0, tier="A")
        orig_decision = p["decision"]
        orig_freshness = p["freshness"]["status"]
        orig_stake = p["stake_units"]
        orig_tier = p["tier"]
        _ = apply_game_gate(p, game_id="501", now=_NOW)
        assert p["decision"] == orig_decision
        assert p["freshness"]["status"] == orig_freshness
        assert p["stake_units"] == orig_stake
        assert p["tier"] == orig_tier

    def test_live_game_original_not_mutated(self):
        """PG8: Passthrough does NOT mutate the original payload."""
        p = _game("502", game_state="live", tipoff=_FUTURE)
        orig_decision = p["decision"]
        _ = apply_game_gate(p, game_id="502", finals=[], now=_NOW)
        assert p["decision"] == orig_decision


# ---------------------------------------------------------------------------
# PG13: apply_games_gate with mixed post/live list
# ---------------------------------------------------------------------------

class TestMixedGamesList:
    def test_post_suppressed_live_unchanged(self):
        """PG13: apply_games_gate suppresses post, leaves live untouched."""
        post = _game("C1", game_state="post")
        live = _game("L1", game_state="live", tipoff=_FUTURE)
        results = apply_games_gate([post, live], finals=[], now=_NOW)
        assert len(results) == 2
        c_out = next(r for r in results if r["game_id"] == "C1")
        l_out = next(r for r in results if r["game_id"] == "L1")
        assert c_out["decision"] == "no_bet"
        assert "stake_units" not in c_out
        assert "tier" not in c_out
        assert l_out["decision"] == "bet"
        assert "stake_units" in l_out
        assert "tier" in l_out

    def test_empty_list_unchanged(self):
        """apply_games_gate: empty input -> empty output."""
        assert apply_games_gate([], now=_NOW) == []
