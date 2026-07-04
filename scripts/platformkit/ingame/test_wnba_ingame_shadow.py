"""Per-file test for the SHADOW-ONLY WNBA in-game probability logger.

OFFLINE + deterministic: a fake adapter (predict_live stub) is injected via the
constructor -- no real parquet reads, no network. Covers the binding safety
contract: never raises, honest None on any miss, wnba-only, poisoned-build safety.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_wnba_ingame_shadow.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.ingame import wnba_ingame_shadow as S


class _FakeAdapter:
    """Deterministic stand-in for WNBAAdapter.predict_live."""

    def __init__(self, p_home_win: float = 0.62, raise_on_call: bool = False) -> None:
        self._p = p_home_win
        self._raise = raise_on_call
        self.calls = []

    def predict_live(self, home, away, as_of, period, clock_s, home_score,
                     away_score, *, neutral_site: bool = False):
        if self._raise:
            raise RuntimeError("boom")
        self.calls.append((home, away, period, clock_s, home_score, away_score, neutral_site))
        return {"p_home_win": self._p}


_STATE = {"period": 2, "clock": 320.0, "home_score": 41.0, "away_score": 38.0,
          "neutral": False}


def _shadow(**kw) -> S.WnbaIngameShadow:
    kw.setdefault("adapter", _FakeAdapter())
    return S.WnbaIngameShadow(**kw)


def test_known_matchup_returns_prob_from_adapter():
    shadow = _shadow()
    out = shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert out == 0.62


def test_non_wnba_sport_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("mlb", "Las Vegas Aces", "Chicago Sky", _STATE) is None


def test_missing_state_dict_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", None) is None  # type: ignore[arg-type]


def test_missing_period_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("period")
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None


def test_missing_clock_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("clock")
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None


def test_missing_scores_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("home_score")
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None


def test_missing_team_names_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("wnba", "", "Chicago Sky", _STATE) is None
    assert shadow.shadow_prob("wnba", None, "Chicago Sky", _STATE) is None


def test_negative_clock_is_none_never_a_guessed_zero():
    shadow = _shadow()
    state = dict(_STATE)
    state["clock"] = -5.0
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None


def test_bad_period_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state["period"] = "not-an-int"
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None
    state["period"] = 0
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", state) is None


def test_out_of_range_prob_from_adapter_is_none():
    shadow = _shadow(adapter=_FakeAdapter(p_home_win=1.7))
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE) is None


def test_adapter_raise_is_none_never_raises():
    shadow = _shadow(adapter=_FakeAdapter(raise_on_call=True))
    out = shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert out is None
    # a second call still must not raise.
    out2 = shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert out2 is None


def test_poisoned_build_returns_none_and_never_raises():
    def _broken_adapter_factory():
        raise ImportError("no adapter available")

    shadow = S.WnbaIngameShadow()
    shadow._build = lambda: _mark_broken(shadow)  # type: ignore[method-assign]
    out = shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert out is None
    assert shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE) is None


def _mark_broken(shadow: S.WnbaIngameShadow) -> None:
    shadow._broken = True
    shadow._adapter = None


def test_staleness_triggers_rebuild_with_fake_clock():
    calls = {"n": 0}
    fake = _FakeAdapter()

    def _factory():
        calls["n"] += 1
        return fake

    now = {"t": 1000.0}
    shadow = S.WnbaIngameShadow(clock=lambda: now["t"])
    # inject a counting build that mimics the real _build's adapter-construction step.
    def _counting_build():
        calls["n"] += 1
        shadow._adapter = fake
        shadow._built_at = shadow._now()
        shadow._broken = False
    shadow._build = _counting_build  # type: ignore[method-assign]

    shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert calls["n"] == 1
    now["t"] += 60.0
    shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert calls["n"] == 1
    now["t"] += S.STALE_AFTER_SEC + 1.0
    shadow.shadow_prob("wnba", "Las Vegas Aces", "Chicago Sky", _STATE)
    assert calls["n"] == 2


def test_get_shadow_singleton_is_stable():
    a = S.get_shadow()
    b = S.get_shadow()
    assert a is b
