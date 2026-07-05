"""Per-file test for the SHADOW-ONLY tennis in-game probability logger.

OFFLINE + deterministic: a fake predictor (predict_live stub) is injected via
the constructor -- no real parquet reads, no network. Covers the binding
safety contract: never raises, honest None on any miss, tennis-only,
poisoned-build safety, and that shadow_prob NEVER mutates its inputs
(model_prob is untouched by construction -- this module has no model_prob
parameter at all).

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/tennis/test_ingame_shadow.py -q
"""
from __future__ import annotations

from domains.tennis import ingame_shadow as S


class _FakePredictor:
    """Deterministic stand-in for TennisPredictor.predict_live."""

    def __init__(self, p1_match_win: float = 0.71, raise_on_call: bool = False) -> None:
        self._p = p1_match_win
        self._raise = raise_on_call
        self.calls = []

    def predict_live(self, p1, p2, sets_p1, sets_p2):
        if self._raise:
            raise RuntimeError("boom")
        self.calls.append((p1, p2, sets_p1, sets_p2))
        return {"p1_match_win": self._p}


_STATE = {"home_score": 1.0, "away_score": 0.0, "set": 2}


def _shadow(**kw) -> S.TennisIngameShadow:
    kw.setdefault("predictor", _FakePredictor())
    return S.TennisIngameShadow(**kw)


def test_known_matchup_returns_prob_from_predictor():
    shadow = _shadow()
    out = shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert out == 0.71


def test_sets_passed_through_as_ints():
    fake = _FakePredictor()
    shadow = _shadow(predictor=fake)
    shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert fake.calls[0] == ("Carlos Alcaraz", "Novak Djokovic", 1, 0)


def test_non_tennis_sport_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("nba", "Carlos Alcaraz", "Novak Djokovic", _STATE) is None


def test_missing_state_dict_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", None) is None  # type: ignore[arg-type]


def test_missing_sets_is_none_never_raises():
    shadow = _shadow()
    state = dict(_STATE)
    state.pop("home_score")
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", state) is None
    state2 = dict(_STATE)
    state2.pop("away_score")
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", state2) is None


def test_missing_player_names_is_none():
    shadow = _shadow()
    assert shadow.shadow_prob("tennis", "", "Novak Djokovic", _STATE) is None
    assert shadow.shadow_prob("tennis", None, "Novak Djokovic", _STATE) is None


def test_negative_sets_is_none_never_a_guessed_zero():
    shadow = _shadow()
    state = dict(_STATE)
    state["home_score"] = -1.0
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", state) is None


def test_out_of_range_prob_from_predictor_is_none():
    shadow = _shadow(predictor=_FakePredictor(p1_match_win=1.4))
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE) is None


def test_predictor_raise_is_none_never_raises():
    shadow = _shadow(predictor=_FakePredictor(raise_on_call=True))
    out = shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert out is None
    # a second call still must not raise.
    out2 = shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert out2 is None


def test_poisoned_build_returns_none_and_never_raises():
    shadow = S.TennisIngameShadow()
    shadow._build = lambda: _mark_broken(shadow)  # type: ignore[method-assign]
    out = shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert out is None
    assert shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE) is None


def _mark_broken(shadow: S.TennisIngameShadow) -> None:
    shadow._broken = True
    shadow._predictor = None


def test_staleness_triggers_rebuild_with_fake_clock():
    calls = {"n": 0}
    fake = _FakePredictor()

    now = {"t": 1000.0}
    shadow = S.TennisIngameShadow(clock=lambda: now["t"])

    def _counting_build():
        calls["n"] += 1
        shadow._predictor = fake
        shadow._built_at = shadow._now()
        shadow._broken = False
    shadow._build = _counting_build  # type: ignore[method-assign]

    shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert calls["n"] == 1
    now["t"] += 60.0
    shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
    assert calls["n"] == 1
    now["t"] += S.STALE_AFTER_SEC + 1.0
    shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", _STATE)
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
    shadow.shadow_prob("tennis", "Carlos Alcaraz", "Novak Djokovic", state)
    assert state == before
