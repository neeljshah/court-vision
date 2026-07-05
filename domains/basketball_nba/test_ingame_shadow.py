"""Per-file test for the SHADOW-ONLY NBA in-game probability logger.

OFFLINE + deterministic: a fake predictor (predict_live stub) is injected via
the constructor -- no real parquet reads, no network. Covers the binding
safety contract: never raises, honest None on any miss, nba-only, poisoned-
build safety, and that shadow_prob NEVER mutates its inputs (model_prob is
untouched by construction -- this module has no model_prob parameter at all).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_ingame_shadow.py -q
"""
from __future__ import annotations

from domains.basketball_nba import ingame_shadow as S


class _FakePredictor:
    """Deterministic stand-in for NBAPredictor.predict_live."""

    def __init__(self, p_home_win: float = 0.58, raise_on_call: bool = False) -> None:
        self._p = p_home_win
        self._raise = raise_on_call
        self.calls = []

    def predict_live(self, home, away, elapsed_minutes, home_score, away_score):
        if self._raise:
            raise RuntimeError("boom")
        self.calls.append((home, away, elapsed_minutes, home_score, away_score))
        return {"p_home_win": self._p}


_STATE = {"period": 3, "clock": 200.0, "home_score": 62.0, "away_score": 58.0}


def _shadow(**kw) -> S.NbaIngameShadow:
    kw.setdefault("predictor", _FakePredictor())
    return S.NbaIngameShadow(**kw)


def test_known_matchup_returns_prob_from_predictor():
    shadow = _shadow()
    out = shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert out == 0.58


def test_elapsed_minutes_derived_correctly_from_period_and_clock():
    fake = _FakePredictor()
    shadow = _shadow(predictor=fake)
    shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    # period=3 (2 full quarters elapsed = 24min) + (12min - 200s/60 = 8.667min) = 32.667
    assert fake.calls[0][2] == 32.0 + 2.0 / 3.0


def test_non_nba_sport_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("wnba", "BOS", "LAL", _STATE) is None


def test_missing_state_dict_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("nba", "BOS", "LAL", None) is None  # type: ignore[arg-type]


def test_missing_period_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("period")
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None


def test_missing_clock_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("clock")
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None


def test_missing_scores_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("home_score")
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None


def test_missing_team_names_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("nba", "", "LAL", _STATE) is None
    assert shadow.shadow_prob("nba", None, "LAL", _STATE) is None


def test_negative_clock_is_none_never_a_guessed_zero():
    shadow = _shadow()
    state = dict(_STATE)
    state["clock"] = -5.0
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None


def test_bad_period_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state["period"] = "not-an-int"
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None
    state["period"] = 0
    assert shadow.shadow_prob("nba", "BOS", "LAL", state) is None


def test_ot_period_clamps_elapsed_to_48():
    fake = _FakePredictor()
    shadow = _shadow(predictor=fake)
    state = dict(_STATE)
    state["period"] = 5  # OT
    shadow.shadow_prob("nba", "BOS", "LAL", state)
    assert fake.calls[0][2] == 48.0


def test_out_of_range_prob_from_predictor_is_none():
    shadow = _shadow(predictor=_FakePredictor(p_home_win=1.7))
    assert shadow.shadow_prob("nba", "BOS", "LAL", _STATE) is None


def test_predictor_raise_is_none_never_raises():
    shadow = _shadow(predictor=_FakePredictor(raise_on_call=True))
    out = shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert out is None
    # a second call still must not raise.
    out2 = shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert out2 is None


def test_poisoned_build_returns_none_and_never_raises():
    shadow = S.NbaIngameShadow()
    shadow._build = lambda: _mark_broken(shadow)  # type: ignore[method-assign]
    out = shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert out is None
    assert shadow.shadow_prob("nba", "BOS", "LAL", _STATE) is None


def _mark_broken(shadow: S.NbaIngameShadow) -> None:
    shadow._broken = True
    shadow._predictor = None


def test_staleness_triggers_rebuild_with_fake_clock():
    calls = {"n": 0}
    fake = _FakePredictor()

    now = {"t": 1000.0}
    shadow = S.NbaIngameShadow(clock=lambda: now["t"])

    def _counting_build():
        calls["n"] += 1
        shadow._predictor = fake
        shadow._built_at = shadow._now()
        shadow._broken = False
    shadow._build = _counting_build  # type: ignore[method-assign]

    shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert calls["n"] == 1
    now["t"] += 60.0
    shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert calls["n"] == 1
    now["t"] += S.STALE_AFTER_SEC + 1.0
    shadow.shadow_prob("nba", "BOS", "LAL", _STATE)
    assert calls["n"] == 2


def test_get_shadow_singleton_is_stable():
    a = S.get_shadow()
    b = S.get_shadow()
    assert a is b


def test_shadow_prob_does_not_mutate_input_state():
    """shadow_prob is a pure side-computation: the caller's state dict must be
    byte-unchanged after the call (no model_prob field exists to mutate --
    this module never accepts or returns one)."""
    shadow = _shadow()
    state = dict(_STATE)
    before = dict(state)
    shadow.shadow_prob("nba", "BOS", "LAL", state)
    assert state == before
